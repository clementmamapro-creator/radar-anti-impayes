"""Évaluation de la recherche : pour chaque question du jeu d'évaluation, les
articles attendus sont-ils parmi ceux retrouvés ?

Métriques :
- rappel@k : part des articles attendus retrouvés dans les k premiers ;
- réussite@k : part des questions dont au moins un article attendu est retrouvé ;
- MRR : rang moyen inversé du premier article attendu.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .index import BM25Index
from .legi import Article


def load_questions(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["questions"]


def evaluer(articles: list[Article], questions: list[dict], k: int = 5) -> dict:
    index = BM25Index(articles)
    presents = {a.num for a in articles}
    rappels, reussites, rr, echecs = [], [], [], []
    for q in questions:
        attendus = [str(n) for n in q["articles"] if str(n) in presents]
        if not attendus:
            continue
        trouves = [a.num for a, _ in index.search(q["question"], k=k)]
        hits = [n for n in attendus if n in trouves]
        rappels.append(len(hits) / len(attendus))
        reussites.append(1.0 if hits else 0.0)
        rang = next((i + 1 for i, n in enumerate(trouves) if n in attendus), None)
        rr.append(1 / rang if rang else 0.0)
        if not hits:
            echecs.append({"question": q["question"], "attendus": attendus, "trouves": trouves})
    n = len(rappels)
    return {
        "questions_evaluees": n,
        f"rappel@{k}": round(sum(rappels) / n, 3) if n else None,
        f"reussite@{k}": round(sum(reussites) / n, 3) if n else None,
        "mrr": round(sum(rr) / n, 3) if n else None,
        "echecs": echecs,
    }


def evaluer_generation(assistant, questions: list[dict], n: int = 10) -> dict:
    """Contrôle automatique des réponses générées sur les n premières questions.

    - citee : la réponse cite au moins un article ;
    - fidele : aucun article cité n'est absent des articles fournis au modèle ;
    - attendu_cite : au moins un des articles attendus est cité.
    """
    from .assistant import CITATION_RE

    lignes = []
    for q in questions[:n]:
        r = assistant.repondre(q["question"])
        if not r.genere:
            continue
        cites = {num for _, num in CITATION_RE.findall(r.reponse or "")}
        lignes.append({
            "question": q["question"],
            "citee": bool(cites),
            "fidele": not r.citations_non_fournies,
            "attendu_cite": bool(cites & {str(x) for x in q["articles"]}),
            "reponse": r.reponse,
        })
    m = len(lignes)
    part = lambda k: round(sum(x[k] for x in lignes) / m, 3) if m else None  # noqa: E731
    return {"reponses_generees": m, "taux_citation": part("citee"), "taux_fidelite": part("fidele"),
            "taux_article_attendu_cite": part("attendu_cite"), "exemples": lignes}
