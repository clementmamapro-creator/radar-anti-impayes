"""Interface en ligne de commande.

    python -m radar inspect     # vérifie les colonnes réelles des sources
    python -m radar ingest      # télécharge BODACC + ratios (données réelles)
    python -m radar demo        # génère des données synthétiques (hors ligne)
    python -m radar build       # normalise les données dans DuckDB
    python -m radar train       # entraîne et évalue le modèle
    python -m radar score 123456789
    python -m radar serve       # lance l'API et l'interface web
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import load_config


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="radar")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inspect")
    sub.add_parser("ingest")
    demo = sub.add_parser("demo")
    demo.add_argument("--entreprises", type=int, default=6000)
    sub.add_parser("build")
    sub.add_parser("train")
    sc = sub.add_parser("score")
    sc.add_argument("siren")
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    cfg = load_config()
    bodacc_path = cfg.raw_dir / "bodacc_collectives.parquet"
    ratios_path = cfg.raw_dir / "ratios.parquet"

    if args.cmd == "inspect":
        from .ingest import inspect_sources

        missing = inspect_sources(cfg)
        return 1 if any(missing.values()) else 0

    if args.cmd == "ingest":
        from .ingest import ingest_all

        ingest_all(cfg)
    elif args.cmd == "demo":
        from .synthetic import write_raw

        write_raw(cfg, cfg.raw_dir, n_companies=args.entreprises)
        print("Données synthétiques écrites dans", cfg.raw_dir, "(fictives, pour démonstration)")
    elif args.cmd == "build":
        from .transform import build_tables

        print(build_tables(cfg, bodacc_path, ratios_path))
    elif args.cmd == "train":
        from .features import build_training_set
        from .train import train
        from .transform import load_tables

        procedures, bilans = load_tables(cfg)
        df = build_training_set(bilans, procedures, cfg)
        report = train(df, cfg)
        print(json.dumps(report["metrics"], indent=2, ensure_ascii=False))
    elif args.cmd == "score":
        from .scoring import Scorer
        from .store import DuckDBStore

        scorer = Scorer(cfg, DuckDBStore(cfg.db_path))
        print(json.dumps(scorer.score(args.siren).to_dict(), indent=2, ensure_ascii=False))
    elif args.cmd == "serve":
        import uvicorn

        uvicorn.run("radar.api:app", host="0.0.0.0", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
