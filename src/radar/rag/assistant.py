"""Assistant « impayés » : réponse rédigée par un LLM à partir des seuls articles retrouvés.

Garde-fous :
- le modèle ne voit que les articles retrouvés et doit citer ceux qu'il utilise ;
- il répond « je ne sais pas » si les textes fournis ne suffisent pas ;
- les citations sont vérifiées : un article cité qui n'a pas été fourni est signalé ;
- sans clé API, l'assistant renvoie quand même les articles pertinents.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

from ..config import Config
from .index import BM25Index
from .legi import Article, load_corpus

AVERTISSEMENT = (
    "Information juridique générale, fondée sur les textes officiels cités. "
    "Ce n'est pas un conseil juridique personnalisé : pour un litige, consultez un avocat ou un commissaire de justice."
)

SYSTEM = """Tu es l'assistant « impayés » d'Acquit Solutions. Tu aides des artisans et des dirigeants de TPE françaises \
à comprendre leurs droits face à un client qui paie en retard ou ne paie pas.

Règles impératives :
1. Réponds UNIQUEMENT à partir des articles de loi fournis entre balises <article>. N'invente aucune règle, aucun délai, aucun montant.
2. Cite chaque règle avec la référence entre crochets, exactement sous la forme [Code de commerce, art. L441-10].
3. Si les articles fournis ne permettent pas de répondre entièrement, ne l'invente pas : dis avec bienveillance ce que les textes \
disponibles permettent d'affirmer, ce qui reste à vérifier, et vers qui se tourner (avocat, commissaire de justice, expert-comptable). \
Ne réponds jamais par un simple « je ne sais pas ».
4. Si la question ne concerne pas les paiements, impayés ou recouvrement entre professionnels, indique poliment que tu ne traites que ce sujet.
5. Écris en français simple, en vouvoyant, en 150 à 250 mots : d'abord la réponse directe, puis les étapes concrètes.
6. N'affirme jamais qu'une entreprise précise est de mauvaise foi ou insolvable."""

CITATION_RE = re.compile(r"\[([^\]]+?),\s*art(?:icle)?\.?\s*([A-Z]?\d[\d-]*)\]")


@dataclass
class Source:
    reference: str
    num: str
    url: str
    extrait: str


@dataclass
class Reponse:
    question: str
    reponse: str | None
    sources: list[Source] = field(default_factory=list)
    citations_non_fournies: list[str] = field(default_factory=list)
    genere: bool = False
    avertissement: str = AVERTISSEMENT

    def to_dict(self) -> dict:
        return asdict(self)


def _contexte(articles: list[Article]) -> str:
    return "\n\n".join(
        f'<article reference="{a.code}, art. {a.num}" en_vigueur_depuis="{a.date_debut}">\n{a.texte}\n</article>'
        for a in articles
    )


def verifier_citations(texte: str, fournis: list[Article]) -> list[str]:
    """Numéros d'articles cités dans la réponse mais absents des articles fournis."""
    nums = {a.num for a in fournis}
    return sorted({num for _, num in CITATION_RE.findall(texte) if num not in nums})


class Assistant:
    def __init__(self, cfg: Config, articles: list[Article] | None = None, client=None):
        self.cfg = cfg
        self.articles = articles if articles is not None else load_corpus(cfg.corpus_path)
        self.index = BM25Index(self.articles) if self.articles else None
        self._client = client

    @property
    def disponible(self) -> bool:
        return self.index is not None

    @property
    def client(self):
        if self._client is None and os.getenv("ANTHROPIC_API_KEY"):
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def repondre(self, question: str) -> Reponse:
        question = question.strip()[:1000]
        if not self.index:
            return Reponse(question, None)
        trouves = [a for a, _ in self.index.search(question, k=self.cfg.rag["retrieval_k"])]
        sources = [Source(a.titre, a.num, a.url, a.texte if len(a.texte) <= 280 else a.texte[:280].rsplit(" ", 1)[0] + "…")
                   for a in trouves]
        if not trouves:
            return Reponse(question, "Je n'ai trouvé aucun texte de loi correspondant à votre question. "
                                     "Reformulez-la, ou consultez un professionnel du droit.", sources)
        if self.client is None:
            return Reponse(question, None, sources)
        msg = self.client.messages.create(
            model=self.cfg.rag["model"],
            max_tokens=self.cfg.rag["max_tokens"],
            system=SYSTEM,
            messages=[{"role": "user", "content": f"{_contexte(trouves)}\n\nQuestion : {question}"}],
        )
        texte = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        return Reponse(question, texte, sources, verifier_citations(texte, trouves), genere=True)
