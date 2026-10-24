"""Interface en ligne de commande.

    python -m radar inspect     # vérifie les colonnes réelles des sources
    python -m radar ingest      # télécharge BODACC + ratios (données réelles)
    python -m radar demo        # génère des données synthétiques (hors ligne)
    python -m radar build       # normalise les données dans DuckDB
    python -m radar train       # entraîne et évalue le modèle
    python -m radar score 123456789
    python -m radar serve       # lance l'API et l'interface web
    python -m radar export      # paquet de service allégé (base + modèle)
    python -m radar fetch URL   # installe un paquet de service (build de l'image)
    python -m radar corpus      # textes de loi officiels pour l'assistant (export LEGI)
    python -m radar eval-rag    # évalue la recherche de l'assistant
    python -m radar ask "question"
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
    ex = sub.add_parser("export")
    ex.add_argument("--out", default="dist")
    fe = sub.add_parser("fetch")
    fe.add_argument("url")
    sub.add_parser("corpus")
    ev = sub.add_parser("eval-rag")
    ev.add_argument("--generation", type=int, default=0, help="nombre de réponses générées à contrôler (coûte des appels API)")
    ak = sub.add_parser("ask")
    ak.add_argument("question")
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
    elif args.cmd == "export":
        from pathlib import Path

        from .export import export_serving

        export_serving(cfg, Path(args.out))
    elif args.cmd == "fetch":
        from .export import fetch_serving

        fetch_serving(args.url)
    elif args.cmd == "corpus":
        from .rag.legi import build_corpus

        build_corpus(cfg)
    elif args.cmd == "eval-rag":
        from .config import ROOT
        from .rag.evaluation import evaluer, load_questions
        from .rag.legi import load_corpus

        questions = load_questions(ROOT / "eval" / "questions_rag.yaml")
        res = evaluer(load_corpus(cfg.corpus_path), questions, k=cfg.rag["retrieval_k"])
        if args.generation:
            from .rag.assistant import Assistant
            from .rag.evaluation import evaluer_generation

            res["generation"] = evaluer_generation(Assistant(cfg), questions, n=args.generation)
        cfg.model_dir.mkdir(parents=True, exist_ok=True)
        (cfg.model_dir / "rag_eval.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.cmd == "ask":
        from .rag.assistant import Assistant

        print(json.dumps(Assistant(cfg).repondre(args.question).to_dict(), indent=2, ensure_ascii=False))
    elif args.cmd == "serve":
        import uvicorn

        uvicorn.run("radar.api:app", host="0.0.0.0", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
