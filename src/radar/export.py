"""Paquet de service : base allégée + modèle, pour l'hébergement gratuit (512 Mo).

La base complète contient tout l'historique des bilans (nécessaire à
l'entraînement). Pour scorer, seul le dernier bilan de chaque entreprise
compte : on précalcule ses variables d'historique (évolution du chiffre
d'affaires, nombre de bilans) et on ne garde qu'une ligne par SIREN.
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import duckdb
import httpx

from .config import ROOT, Config

ARCHIVE = "acquit-serve.tar.gz"

LATEST_SQL = """
WITH h AS (
    SELECT *,
        lag(chiffre_affaires) OVER w AS _prev_ca,
        row_number() OVER w AS nb_bilans
    FROM src.bilans
    WINDOW w AS (PARTITION BY siren ORDER BY date_cloture)
), e AS (
    SELECT * EXCLUDE (_prev_ca),
        CASE
            WHEN _prev_ca IS NULL OR _prev_ca = 0 OR chiffre_affaires IS NULL
                 OR isnan(_prev_ca) OR isnan(chiffre_affaires) THEN NULL
            ELSE greatest(-1.0, least(5.0, (chiffre_affaires - _prev_ca) / abs(_prev_ca)))
        END AS evolution_ca
    FROM h
)
SELECT * FROM e
QUALIFY row_number() OVER (PARTITION BY siren ORDER BY date_cloture DESC) = 1
ORDER BY siren
"""


def export_serving(cfg: Config, out_dir: Path) -> Path:
    """Écrit out_dir/acquit-serve.tar.gz (data/radar.duckdb + models/) et renvoie son chemin."""
    stage = out_dir / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    (stage / "data").mkdir(parents=True)
    (stage / "models").mkdir(parents=True)
    db = stage / "data" / "radar.duckdb"

    with duckdb.connect(str(db)) as con:
        con.execute(f"ATTACH '{cfg.db_path}' AS src (READ_ONLY)")
        con.execute(f"CREATE TABLE bilans AS {LATEST_SQL}")
        con.execute("CREATE TABLE procedures AS SELECT * FROM src.procedures ORDER BY siren")
        con.execute("CREATE INDEX idx_bilans_siren ON bilans (siren)")
        con.execute("CREATE INDEX idx_procedures_siren ON procedures (siren)")
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("bilans", "procedures")}
        con.execute("DETACH src")
        con.execute("CHECKPOINT")
    for name in ("model.joblib", "metrics.json"):
        shutil.copy2(cfg.model_dir / name, stage / "models" / name)
    # Corpus juridique de l'assistant et son évaluation, s'ils ont été construits
    if cfg.corpus_path.exists():
        shutil.copy2(cfg.corpus_path, stage / "data" / cfg.corpus_path.name)
    if (cfg.model_dir / "rag_eval.json").exists():
        shutil.copy2(cfg.model_dir / "rag_eval.json", stage / "models" / "rag_eval.json")

    archive = out_dir / ARCHIVE
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(stage / "data", arcname="data")
        tar.add(stage / "models", arcname="models")
    size = archive.stat().st_size / 1e6
    print(f"Paquet de service : {archive} ({size:.0f} Mo) ; entreprises : {counts['bilans']}, "
          f"procédures : {counts['procedures']}")
    return archive


def fetch_serving(url: str, dest: Path = ROOT) -> None:
    """Télécharge et extrait le paquet de service (utilisé au build de l'image)."""
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / ARCHIVE
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    with tarfile.open(tmp) as tar:
        tar.extractall(dest, filter="data")
    tmp.unlink()
    print("Paquet de service installé dans", dest)
