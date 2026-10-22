"""API FastAPI et interface web du radar client."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import ROOT, load_config
from .scoring import Scorer, search_companies
from .store import DuckDBStore

SITE_DIR = Path(os.getenv("RADAR_SITE_DIR", ROOT / "site"))

app = FastAPI(
    title="Acquit API",
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


@app.get("/health")
def health() -> dict:
    cfg = load_config()
    metrics_path = cfg.model_dir / "metrics.json"
    trained = None
    if metrics_path.exists():
        trained = json.loads(metrics_path.read_text(encoding="utf-8")).get("entraine_le")
    return {"status": "ok", "version": __version__, "modele_entraine_le": trained, "demo": is_demo()}


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
