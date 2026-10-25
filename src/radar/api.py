"""API FastAPI et interface web du radar client."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import datetime as dt
import hashlib
import secrets

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import ROOT, load_config
from .scoring import Scorer, search_companies
from .store import DuckDBStore

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
        restantes = _consommer(request, load_config().rag["free_daily_quota"])
    res = a.repondre(q.question, [e.model_dump() for e in q.historique]).to_dict()
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


@app.get("/score/{siren}")
def score(siren: str) -> dict:
    digits = "".join(c for c in siren if c.isdigit())
    if len(digits) != 9:
        raise HTTPException(status_code=422, detail="Un SIREN comporte 9 chiffres.")
    return get_scorer().score(digits).to_dict()


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
