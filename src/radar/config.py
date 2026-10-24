"""Chargement de la configuration du projet."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


def _find_root() -> Path:
    """Dossier contenant config.yaml : RADAR_HOME, sinon le dépôt, sinon le dossier courant."""
    if os.getenv("RADAR_HOME"):
        return Path(os.environ["RADAR_HOME"]).resolve()
    repo = Path(__file__).resolve().parents[2]
    return repo if (repo / "config.yaml").exists() else Path.cwd()


ROOT = _find_root()


@dataclass(frozen=True)
class Config:
    raw: dict

    @property
    def raw_dir(self) -> Path:
        return ROOT / self.raw["paths"]["raw_dir"]

    @property
    def db_path(self) -> Path:
        return ROOT / self.raw["paths"]["db"]

    @property
    def model_dir(self) -> Path:
        return ROOT / self.raw["paths"]["model_dir"]

    @property
    def corpus_path(self) -> Path:
        return ROOT / self.raw["rag"]["corpus"]

    @property
    def rag(self) -> dict:
        return self.raw["rag"]

    @property
    def bodacc(self) -> dict:
        return self.raw["sources"]["bodacc"]

    @property
    def ratios(self) -> dict:
        return self.raw["sources"]["ratios"]

    @property
    def entreprises(self) -> dict:
        return self.raw["sources"]["entreprises"]

    @property
    def target(self) -> dict:
        return self.raw["target"]

    @property
    def model(self) -> dict:
        return self.raw["model"]

    @property
    def feature_names(self) -> list[str]:
        """Noms internes des ratios utilisés par le modèle."""
        return list(self.ratios["features"].keys())


def load_config(path: Path | None = None) -> Config:
    path = path or ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        return Config(yaml.safe_load(f))
