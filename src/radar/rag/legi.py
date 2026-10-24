"""Construction du corpus juridique depuis l'export open data LEGI (DILA).

L'export « Freemium » contient toute la base Légifrance au format XML, un
fichier par version d'article. On le lit en flux (sans l'écrire sur disque)
et on ne garde que les articles listés dans `config.yaml`, dans leur version
en vigueur.
"""

from __future__ import annotations

import html
import json
import re
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

from ..config import Config

FREEMIUM_RE = re.compile(r'href="(Freemium_legi_global_[\d-]+\.tar\.gz)"')
TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Article:
    id: str          # identifiant Légifrance (LEGIARTI…)
    code: str        # nom du code
    num: str         # numéro d'article (ex. L441-10)
    texte: str
    date_debut: str  # début de la version en vigueur
    url: str

    @property
    def titre(self) -> str:
        return f"{self.code}, article {self.num}"


def contenu_texte(xml_contenu: str) -> str:
    """HTML du bloc textuel -> texte brut lisible (paragraphes conservés)."""
    t = re.sub(r"<br\s*/?>|</p>|</li>", "\n", xml_contenu, flags=re.I)
    t = html.unescape(TAG_RE.sub("", t))
    lines = [re.sub(r"\s+", " ", line).strip() for line in t.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_article(raw: bytes, code_nom: str) -> Article | None:
    root = ET.fromstring(raw)
    meta = root.find("META/META_SPEC/META_ARTICLE")
    if meta is None:
        return None
    contenu = root.find("BLOC_TEXTUEL/CONTENU")
    texte = contenu_texte(ET.tostring(contenu, encoding="unicode")) if contenu is not None else ""
    art_id = root.findtext("META/META_COMMUN/ID", default="")
    return Article(
        id=art_id,
        code=code_nom,
        num=(meta.findtext("NUM") or "").strip(),
        texte=texte,
        date_debut=meta.findtext("DATE_DEBUT") or "",
        url=f"https://www.legifrance.gouv.fr/codes/article_lc/{art_id}",
    ) if (meta.findtext("ETAT") or "") == "VIGUEUR" else None


def latest_freemium_url(cfg: Config, client: httpx.Client) -> str:
    base = cfg.raw["rag"]["legi_index"]
    page = client.get(base, timeout=60).text
    files = sorted(FREEMIUM_RE.findall(page))
    if not files:
        raise RuntimeError("Aucun export Freemium LEGI trouvé sur " + base)
    return base + files[-1]


def select_articles(members, cfg: Config) -> list[Article]:
    """Parcourt les fichiers d'une archive LEGI et garde les articles voulus.

    `members` produit des couples (chemin, contenu) pour les fichiers XML d'article.
    """
    wanted = cfg.raw["rag"]["articles"]
    best: dict[tuple[str, str], Article] = {}
    for path, raw in members:
        for text_id, spec in wanted.items():
            if f"/{text_id}/article/" not in path:
                continue
            art = parse_article(raw, spec["nom"])
            if art and art.num in {str(n) for n in spec["nums"]}:
                key = (text_id, art.num)
                if key not in best or art.date_debut > best[key].date_debut:
                    best[key] = art
    return sorted(best.values(), key=lambda a: (a.code, a.num))


def stream_archive(url: str, text_ids: list[str]):
    """Lit une archive .tar.gz distante en flux et produit les XML d'articles des codes voulus."""
    marks = [f"/{t}/article/" for t in text_ids]
    with httpx.stream("GET", url, timeout=None, follow_redirects=True) as r:
        r.raise_for_status()

        class _Raw:
            def __init__(self, it):
                self.it, self.buf = it, b""

            def read(self, n=-1):
                while n < 0 or len(self.buf) < n:
                    try:
                        self.buf += next(self.it)
                    except StopIteration:
                        break
                out, self.buf = (self.buf, b"") if n < 0 else (self.buf[:n], self.buf[n:])
                return out

        with tarfile.open(fileobj=_Raw(r.iter_bytes(1 << 20)), mode="r|gz") as tar:
            for m in tar:
                if m.isfile() and m.name.endswith(".xml") and any(k in m.name for k in marks):
                    f = tar.extractfile(m)
                    if f is not None:
                        yield m.name, f.read()


def build_corpus(cfg: Config) -> Path:
    with httpx.Client(follow_redirects=True) as client:
        url = latest_freemium_url(cfg, client)
    print("Export LEGI :", url)
    articles = select_articles(stream_archive(url, list(cfg.raw["rag"]["articles"])), cfg)
    expected = sum(len(s["nums"]) for s in cfg.raw["rag"]["articles"].values())
    out = cfg.corpus_path
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for a in articles:
            f.write(json.dumps(asdict(a), ensure_ascii=False) + "\n")
    found = {a.num for a in articles}
    missing = [str(n) for s in cfg.raw["rag"]["articles"].values() for n in s["nums"] if str(n) not in found]
    print(f"Corpus : {len(articles)}/{expected} articles -> {out}")
    if missing:
        print("Articles introuvables :", ", ".join(missing))
    return out


def load_corpus(path: Path) -> list[Article]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [Article(**json.loads(line)) for line in f if line.strip()]
