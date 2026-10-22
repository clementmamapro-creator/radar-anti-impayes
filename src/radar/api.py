"""API FastAPI et interface web du radar client."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import __version__
from .config import load_config
from .scoring import Scorer
from .store import DuckDBStore

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(
    title="Radar anti-impayés",
    version=__version__,
    description="Score de risque de défaillance d'une entreprise à partir des données publiques.",
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
