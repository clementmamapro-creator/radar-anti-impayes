"""API FastAPI et interface web du radar client."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import datetime as dt
import hashlib
import secrets
import time

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import ROOT, load_config
from .scoring import CACHE_STATS, Scorer, search_companies
from .store import DuckDBStore
from .telemetrie import TELEMETRIE

SITE_DIR = Path(os.getenv("RADAR_SITE_DIR", ROOT / "site"))

app = FastAPI(
    title="Acquit Solutions API",
    version=__version__,
    description="Risque de défaillance d'une entreprise et conditions de paiement recommandées, "
    "à partir des données publiques.",
)

# Le site vitrine peut être hébergé ailleurs que l'API (ex. Cloudflare Pages) :
# lister ses domaines dans RADAR_CORS_ORIGINS, séparés par des virgules.
_origins = [o.strip() for o in os.getenv("RADAR_CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET"], allow_headers=["*"])


@app.middleware("http")
async def mesurer(request: Request, call_next):
    """Durée et statut de chaque requête, par route (jamais l'adresse IP ni le SIREN)."""
    debut = time.perf_counter()
    statut = 500
    try:
        reponse = await call_next(request)
        statut = reponse.status_code
        return reponse
    finally:
        route = request.scope.get("route")
        chemin = getattr(route, "path", None)
        nom = chemin if chemin and chemin != "/" else "site"
        TELEMETRIE.enregistrer(nom, statut, (time.perf_counter() - debut) * 1000)


@lru_cache
def get_scorer() -> Scorer:
    cfg = load_config()
    with_identity = os.getenv("RADAR_IDENTITY", "1") == "1"
    return Scorer(cfg, DuckDBStore(cfg.db_path), with_identity=with_identity)


def is_demo() -> bool:
    """Vrai quand l'API tourne sur les données synthétiques (fictives)."""
    return os.getenv("RADAR_DEMO", "0") == "1"


@lru_cache
def get_assistant():
    from .rag.assistant import Assistant

    return Assistant(load_config())


# Quota du pack Free : N questions par jour et par visiteur. Le visiteur est
# reconnu par une empreinte salée de son adresse IP, gardée en mémoire le jour
# même seulement (rien n'est écrit sur disque, le sel change à chaque démarrage).
_SEL = secrets.token_hex(16)
_quota: dict[str, int] = {}
_quota_jour = [dt.date.today()]


def _visiteur(request: Request) -> str:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    return hashlib.sha256((_SEL + ip).encode()).hexdigest()[:16]


def _consommer(request: Request, limite: int) -> int:
    if _quota_jour[0] != dt.date.today():
        _quota.clear()
        _quota_jour[0] = dt.date.today()
    v = _visiteur(request)
    if _quota.get(v, 0) >= limite:
        raise HTTPException(
            status_code=429,
            detail=f"Vous avez utilisé vos {limite} questions gratuites du jour. Revenez demain, "
                   "ou passez au pack Éco pour des questions illimitées.",
        )
    _quota[v] = _quota.get(v, 0) + 1
    return limite - _quota[v]


class Echange(BaseModel):
    question: str = Field(max_length=1000)
    reponse: str = Field(max_length=4000)


class Question(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    historique: list[Echange] = Field(default_factory=list, max_length=10)


@app.post("/assistant")
def assistant(q: Question, request: Request) -> dict:
    """Assistant « impayés » : réponse sourcée à partir des textes de loi officiels."""
    a = get_assistant()
    if not a.disponible:
        raise HTTPException(status_code=503, detail="L'assistant n'est pas encore disponible.")
    restantes = None
    if a.client is not None:
        try:
            restantes = _consommer(request, load_config().rag["free_daily_quota"])
        except HTTPException:
            TELEMETRIE.incrementer("assistant_quota_atteint")
            raise
    res = a.repondre(q.question, [e.model_dump() for e in q.historique]).to_dict()
    TELEMETRIE.incrementer("assistant_questions")
    TELEMETRIE.incrementer("assistant_suivis", 1 if q.historique else 0)
    TELEMETRIE.incrementer("assistant_reponses_redigees", 1 if res.get("genere") else 0)
    TELEMETRIE.incrementer("assistant_citations_non_fournies", len(res.get("citations_non_fournies") or []))
    res["questions_restantes_aujourdhui"] = restantes
    return res


@app.get("/health")
def health() -> dict:
    cfg = load_config()
    metrics_path = cfg.model_dir / "metrics.json"
    trained = None
    if metrics_path.exists():
        trained = json.loads(metrics_path.read_text(encoding="utf-8")).get("entraine_le")
    a = get_assistant()
    return {
        "status": "ok", "version": __version__, "modele_entraine_le": trained, "demo": is_demo(),
        "assistant": {"articles": len(a.articles), "generation": a.client is not None},
    }


_VOLUMES: dict = {}


def _volumes() -> dict:
    """Taille de la base de service, lue une fois ; vide si la base n'est pas encore là."""
    if not _VOLUMES:
        try:
            store = get_scorer().store
            _VOLUMES.update(store.volumes() if hasattr(store, "volumes") else {})
        except Exception:  # base absente (CI, premier démarrage) : la page s'affiche quand même
            return {}
    return _VOLUMES


def _lire_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@app.get("/metriques")
def metriques() -> dict:
    """Indicateurs publics du service, affichés en direct sur la page « Sous le capot »."""
    cfg = load_config()
    m = _lire_json(cfg.model_dir / "metrics.json")
    ev = _lire_json(cfg.model_dir / "rag_eval.json")
    a = get_assistant()
    trafic = TELEMETRIE.instantane()
    retenu = (m.get("metrics") or {}).get("lightgbm_calibre", {})
    test = ev.get("test", {}).get("hybride", {})
    gen = ev.get("generation", {})
    hits = sum(v for k, v in CACHE_STATS.items() if k.endswith("_hits"))
    total = hits + sum(v for k, v in CACHE_STATS.items() if k.endswith("_misses"))
    return {
        "service": {
            "version": __version__,
            "commit": (os.getenv("RENDER_GIT_COMMIT") or "")[:7] or None,
            "instance": os.getenv("RADAR_INSTANCE", "Render Starter · 0,5 CPU · 512 Mo"),
            "demo": is_demo(),
            **TELEMETRIE.processus(),
        },
        "trafic": trafic,
        "cache": {"taux_pct": round(100 * hits / total, 1) if total else None, **CACHE_STATS},
        "donnees": {**_volumes(), "corpus_articles": len(a.articles)},
        "modele": {
            "entraine_le": m.get("entraine_le"),
            "lignes_entrainement": (m.get("train") or {}).get("lignes"),
            "lignes_test": (m.get("test") or {}).get("lignes"),
            "annees_test": (m.get("test") or {}).get("annees"),
            "roc_auc": retenu.get("roc_auc"),
            "rappel_top10": retenu.get("recall_top10"),
            "brier": retenu.get("brier"),
            "reference_auc": ((m.get("metrics") or {}).get("baseline_logreg") or {}).get("roc_auc"),
            "niveaux": (m.get("niveaux_actuels") or {}).get("detail"),
        },
        "assistant": {
            "generation": a.client is not None,
            "modele": cfg.rag.get("model"),
            "test_reussite_at5": test.get("reussite@5"),
            "test_rappel_at5": test.get("rappel@5"),
            "test_mrr": test.get("mrr"),
            "test_questions": test.get("questions_evaluees"),
            "taux_citation": gen.get("taux_citation"),
            "taux_fidelite": gen.get("taux_fidelite"),
        },
    }


@app.get("/carte")
def carte_defaillances() -> dict:
    """Ouvertures de procédures collectives par département, 12 derniers mois (BODACC)."""
    from .carte import carte

    data = carte(load_config())
    if data is None:
        raise HTTPException(status_code=503, detail="Carte momentanément indisponible.")
    return data


@app.get("/exemples")
def exemples() -> list[dict]:
    """SIREN d'exemple pour la démonstration (uniquement en mode démo)."""
    if not is_demo():
        return []
    # Un exemple sain, un fragile, un en procédure
    samples = get_scorer().store.sample_sirens()
    sirens = samples["sain"] + samples["fragile"] + samples["procedure"]
    return [{"siren": s, "label": f"Exemple {i}"} for i, s in enumerate(sirens, start=1)]


@app.get("/recherche")
def recherche(q: str = Query(min_length=2, max_length=100)) -> list[dict]:
    """Suggestions d'entreprises par nom, pour retrouver un SIREN."""
    if is_demo():
        return []  # les entreprises de démonstration sont fictives : pas de recherche réelle
    return search_companies(load_config(), q)


# Cache des scores complets : les données et le modèle ne changent qu'une fois par
# semaine (et chaque mise à jour redémarre le service, donc vide ce cache).
# Le test de charge a montré que le calcul (modèle + SHAP) sature le CPU vers 27 req/s.
_SCORES: dict[str, dict] = {}
_SCORES_MAX = 5000


@app.get("/score/{siren}")
def score(siren: str) -> dict:
    digits = "".join(c for c in siren if c.isdigit())
    if len(digits) != 9:
        raise HTTPException(status_code=422, detail="Un SIREN comporte 9 chiffres.")
    if digits in _SCORES:
        CACHE_STATS["score_hits"] = CACHE_STATS.get("score_hits", 0) + 1
        return _SCORES[digits]
    CACHE_STATS["score_misses"] = CACHE_STATS.get("score_misses", 0) + 1
    scorer = get_scorer()
    res = scorer.score(digits).to_dict()
    # On ne fige pas un résultat dont l'identité a échoué (panne passagère de l'API publique)
    if res.get("identite") is not None or not scorer.with_identity:
        if len(_SCORES) >= _SCORES_MAX:
            _SCORES.pop(next(iter(_SCORES)))
        _SCORES[digits] = res
    return res


@app.get("/model")
def model_info() -> dict:
    cfg = load_config()
    path = cfg.model_dir / "metrics.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Aucun modèle entraîné.")
    return json.loads(path.read_text(encoding="utf-8"))


# Le site vitrine, servi par la même application tant qu'il n'est pas hébergé à part.
# Monté en dernier pour ne pas masquer les routes de l'API.
if SITE_DIR.is_dir():
    app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
