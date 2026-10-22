"""Ingestion des données ouvertes (BODACC et ratios financiers INPI/BCE).

Les deux jeux sont publiés sur des plateformes Opendatasoft. On utilise
l'endpoint d'export (fichier complet, sans pagination) au format Parquet,
puis on charge le résultat dans DuckDB.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from .config import Config

log = logging.getLogger(__name__)


def _export_url(base_url: str, dataset: str, fmt: str = "parquet") -> str:
    return f"{base_url}/catalog/datasets/{dataset}/exports/{fmt}"


def download_export(
    base_url: str,
    dataset: str,
    dest: Path,
    where: str | None = None,
    timeout: float = 600.0,
) -> Path:
    """Télécharge l'export complet d'un jeu Opendatasoft en streaming."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    params = {"where": where} if where else {}
    url = _export_url(base_url, dataset)
    log.info("Téléchargement %s (%s)", dataset, where or "tout")
    with httpx.stream("GET", url, params=params, timeout=timeout, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1 << 20):
                f.write(chunk)
    log.info("Écrit %s (%.1f Mo)", dest, dest.stat().st_size / 1e6)
    return dest


def fetch_schema(base_url: str, dataset: str) -> list[str]:
    """Retourne la liste des colonnes réelles d'un jeu Opendatasoft."""
    r = httpx.get(f"{base_url}/catalog/datasets/{dataset}", timeout=30, follow_redirects=True)
    r.raise_for_status()
    return [f["name"] for f in r.json()["fields"]]


def inspect_sources(cfg: Config) -> dict[str, list[str]]:
    """Compare le mapping de config.yaml aux colonnes réellement publiées.

    Retourne, pour chaque source, la liste des colonnes du mapping introuvables.
    """
    missing: dict[str, list[str]] = {}
    for name, src in (("bodacc", cfg.bodacc), ("ratios", cfg.ratios)):
        real = set(fetch_schema(src["base_url"], src["dataset"]))
        expected = set(src["columns"].values()) | set(src.get("features", {}).values())
        missing[name] = sorted(expected - real)
        print(f"\n== {name} : {len(real)} colonnes publiées")
        print("  " + ", ".join(sorted(real)))
        if missing[name]:
            print(f"  ⚠ Introuvables (à corriger dans config.yaml) : {missing[name]}")
        else:
            print("  ✓ Mapping complet")
    return missing


def ingest_all(cfg: Config) -> dict[str, Path]:
    """Télécharge les deux sources dans data/raw."""
    out = {}
    out["bodacc"] = download_export(
        cfg.bodacc["base_url"],
        cfg.bodacc["dataset"],
        cfg.raw_dir / "bodacc_collectives.parquet",
        where=cfg.bodacc.get("where"),
    )
    out["ratios"] = download_export(
        cfg.ratios["base_url"],
        cfg.ratios["dataset"],
        cfg.raw_dir / "ratios.parquet",
    )
    return out
