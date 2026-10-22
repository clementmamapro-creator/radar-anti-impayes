"""API FastAPI et interface web du radar client."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from . import __version__
from .config import load_config
from .scoring import Scorer
from .transform import load_tables

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(
    title="Radar anti-impayés",
    version=__version__,
    description="Score de risque de défaillance d'une entreprise à partir des données publiques.",
)


@lru_cache
def get_scorer() -> Scorer:
    cfg = load_config()
    procedures, bilans = load_tables(cfg)
    with_identity = os.getenv("RADAR_IDENTITY", "1") == "1"
    return Scorer(cfg, bilans, procedures, with_identity=with_identity)


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
    s = get_scorer()
    proc = set(s.procedures["siren"])
    last = s.bilans.sort_values("date_cloture").groupby("siren").tail(1)
    healthy = last[~last["siren"].isin(proc)]
    picks = []
    # Un exemple sain, un fragile, un en procédure
    best = healthy.sort_values("taux_endettement").iloc[0]["siren"]
    worst = healthy.sort_values("taux_endettement").iloc[-1]["siren"]
    picks += [{"siren": best, "label": "Exemple 1"}, {"siren": worst, "label": "Exemple 2"}]
    if proc:
        picks.append({"siren": sorted(proc)[0], "label": "Exemple 3"})
    return picks


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
