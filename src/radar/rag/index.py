"""Recherche des articles pertinents : BM25 adapté au français.

Le corpus est petit (quelques dizaines d'articles) : BM25 avec une
normalisation soignée (accents, mots vides, racinisation légère, synonymes
du vocabulaire des TPE) suffit, tient en mémoire et s'explique facilement.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from .legi import Article

STOP = set("""
a au aux avec ce ces cette d dans de des du elle en est et etc il ils je l la le les leur leurs lui
ma mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te
tes toi ton tu un une vos votre vous y ete etre avoir ai as avons avez ont fait faire peut peuvent
doit doivent sont si plus tout tous toute toutes comment quoi quel quelle quels quelles dois puis
""".split())

# Vocabulaire du quotidien -> vocabulaire juridique
SYNONYMES = {
    "impaye": "paiement retard creance",
    "paie": "paiement",
    "payer": "paiement",
    "retard": "retard delai",
    "relance": "mise demeure",
    "relancer": "mise demeure",
    "facture": "facture",
    "client": "debiteur",
    "faillite": "procedure collective redressement liquidation",
    "liquidation": "liquidation judiciaire procedure",
    "redressement": "redressement judiciaire procedure",
    "tribunal": "juridiction injonction",
    "acompte": "paiement",
    "interets": "interet",
    "penalite": "penalite interet retard",
    "penalites": "penalite interet retard",
    "indemnite": "indemnite forfaitaire recouvrement",
    "huissier": "commissaire justice",
    "prescription": "prescription",
    "recuperer": "recouvrement",
    "prescrit": "prescription",
    "prescrite": "prescription",
    "echeancier": "delai grace report echelonnement",
    "arreter": "suspendre exception inexecution",
    "chantier": "travaux execution",
    "devis": "contrat",
    "engage": "force obligatoire contrat",
    "declarer": "declaration",
    "executoire": "formule executoire",
}


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _racine(t: str) -> str:
    for suf in ("ements", "ement", "ations", "ation", "ments", "ment", "ees", "es", "s", "x", "e"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def tokens(text: str, expand: bool = False) -> list[str]:
    raw = re.findall(r"[a-z0-9]+(?:-[0-9]+)*", _sans_accents(text.lower()))
    out = []
    for t in raw:
        if t in STOP:
            continue
        out.append(t if any(c.isdigit() for c in t) else _racine(t))
        if expand and t in SYNONYMES:
            out.extend(_racine(s) for s in SYNONYMES[t].split())
    return out


class BM25Index:
    def __init__(self, articles: list[Article], k1: float = 1.4, b: float = 0.75, themes: dict | None = None):
        self.articles = articles
        self.k1, self.b = k1, b
        themes = {str(k): v for k, v in (themes or {}).items()}
        # Indexé : titre (code + numéro), thèmes éditoriaux (comptés deux fois : ils résument l'article) et texte officiel
        self.docs = [
            tokens(f"{a.titre} {a.num.lower()} {themes.get(a.num, '')} {themes.get(a.num, '')} {a.texte}")
            for a in articles
        ]
        self.tf = [Counter(d) for d in self.docs]
        self.avgdl = sum(len(d) for d in self.docs) / max(1, len(self.docs))
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query: str, k: int = 5) -> list[tuple[Article, float]]:
        q = tokens(query, expand=True)
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            # Un numéro d'article cité tel quel dans la question est un signal très fort
            if self.articles[i].num.lower() in query.lower():
                s += 10
            scores.append(s)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [(self.articles[i], round(scores[i], 3)) for i in order[:k] if scores[i] > 0]
