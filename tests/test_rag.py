"""Tests de l'assistant « impayés » (sans réseau ni clé API)."""

from __future__ import annotations

from types import SimpleNamespace

from radar.config import load_config
from radar.rag.assistant import Assistant, verifier_citations
from radar.rag.evaluation import evaluer
from radar.rag.index import BM25Index, tokens
from radar.rag.legi import Article, parse_article, select_articles

COM = "LEGITEXT000005634379"


def xml_article(art_id: str, num: str, etat: str, debut: str, texte: str) -> bytes:
    """Article au format XML de l'export LEGI (structure simplifiée mais fidèle)."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ARTICLE>
  <META>
    <META_COMMUN><ID>{art_id}</ID><NATURE>Article</NATURE></META_COMMUN>
    <META_SPEC><META_ARTICLE><NUM>{num}</NUM><ETAT>{etat}</ETAT><DATE_DEBUT>{debut}</DATE_DEBUT>
      <DATE_FIN>2999-01-01</DATE_FIN></META_ARTICLE></META_SPEC>
  </META>
  <BLOC_TEXTUEL><CONTENU><p>{texte}</p><p>Second alin&#233;a.</p></CONTENU></BLOC_TEXTUEL>
</ARTICLE>""".encode()


def corpus() -> list[Article]:
    def a(num, code, texte):
        return Article(f"ID{num}", code, num, texte, "2024-01-01", f"https://example/{num}")

    return [
        a("L441-10", "Code de commerce", "Le délai convenu entre les parties pour régler les sommes dues ne peut dépasser "
          "soixante jours après la date d'émission de la facture. Les pénalités de retard sont exigibles sans qu'un "
          "rappel soit nécessaire. Tout professionnel en situation de retard de paiement est de plein droit débiteur "
          "d'une indemnité forfaitaire pour frais de recouvrement."),
        a("D441-5", "Code de commerce", "Le montant de l'indemnité forfaitaire pour frais de recouvrement est fixé à 40 euros."),
        a("1344", "Code civil", "Le débiteur est mis en demeure de payer soit par une sommation ou un acte portant "
          "interpellation suffisante, soit, si le contrat le prévoit, par la seule exigibilité de l'obligation."),
        a("1405", "Code de procédure civile", "Le recouvrement d'une créance peut être demandé suivant la procédure "
          "d'injonction de payer lorsque la créance a une cause contractuelle."),
        a("R622-24", "Code de commerce", "Le délai de déclaration des créances est de deux mois à compter de la "
          "publication du jugement d'ouverture au Bulletin officiel des annonces civiles et commerciales."),
    ]


def test_parse_article_et_version_en_vigueur():
    art = parse_article(xml_article("LEGIARTI1", "L441-10", "VIGUEUR", "2023-01-01", "Délai de 60 jours."), "Code de commerce")
    assert art and art.num == "L441-10" and "Délai de 60 jours." in art.texte and "Second alinéa." in art.texte
    assert art.url.endswith("LEGIARTI1")
    assert parse_article(xml_article("X", "L441-10", "ABROGE", "2010-01-01", "ancien"), "Code de commerce") is None


def test_select_articles_garde_la_derniere_version_des_articles_voulus():
    cfg = load_config()
    base = f"legi/global/code_et_TNC_en_vigueur/code_en_vigueur/LEGI/TEXT/00/{COM}/article/LEGI/ARTI/"
    members = [
        (base + "a.xml", xml_article("A1", "L441-10", "VIGUEUR", "2019-01-01", "ancienne")),
        (base + "b.xml", xml_article("A2", "L441-10", "VIGUEUR", "2023-01-01", "récente")),
        (base + "c.xml", xml_article("A3", "L999-1", "VIGUEUR", "2023-01-01", "hors liste")),
        ("legi/autre/LEGITEXT000000000001/article/d.xml", xml_article("A4", "L441-10", "VIGUEUR", "2024-01-01", "autre code")),
    ]
    arts = select_articles(members, cfg)
    assert [(a.num, a.id) for a in arts] == [("L441-10", "A2")]


def test_tokens_francais():
    assert tokens("Les pénalités de retard") == tokens("penalite retard")
    assert "l441-10" in tokens("article L441-10")


def test_recherche_et_evaluation():
    idx = BM25Index(corpus())
    assert idx.search("combien vaut l'indemnité forfaitaire de recouvrement", k=2)[0][0].num == "D441-5"
    assert idx.search("comment mettre en demeure mon client", k=2)[0][0].num == "1344"
    assert idx.search("article L441-10", k=1)[0][0].num == "L441-10"
    res = evaluer(corpus(), [
        {"question": "Quel est le délai de paiement maximum ?", "articles": ["L441-10"]},
        {"question": "Combien de temps pour déclarer ma créance après le BODACC ?", "articles": ["R622-24"]},
        {"question": "Comment faire une injonction de payer ?", "articles": ["1405"]},
    ], k=3)
    assert res["questions_evaluees"] == 3 and res["reussite@3"] == 1.0


class FakeClient:
    """Imite le client Anthropic : renvoie une réponse qui cite un article fourni et un article inventé."""

    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        text = "Le délai est de 60 jours [Code de commerce, art. L441-10]. Voir aussi [Code civil, art. 9999]."
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_assistant_genere_et_verifie_les_citations():
    fake = FakeClient()
    a = Assistant(load_config(), articles=corpus(), client=fake)
    r = a.repondre("Quel est le délai de paiement maximum entre entreprises ?")
    assert r.genere and "60 jours" in r.reponse
    assert r.citations_non_fournies == ["9999"]
    assert any(s.num == "L441-10" for s in r.sources)
    assert len(fake.calls) == 2  # reformulation de la question, puis réponse
    assert "<article" not in fake.calls[0]["messages"][0]["content"]
    prompt = fake.calls[1]["messages"][0]["content"]
    assert "<article" in prompt and "L441-10" in prompt  # le modèle ne voit que les articles retrouvés
    assert fake.calls[1]["thinking"] == {"type": "disabled"}


def test_assistant_sans_cle_renvoie_les_sources(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = Assistant(load_config(), articles=corpus()).repondre("indemnité forfaitaire de 40 euros")
    assert r.reponse is None and not r.genere and r.sources[0].num == "D441-5"


def test_verifier_citations():
    assert verifier_citations("[Code civil, art. 1344] et [Code civil, article 1231-6]", corpus()) == ["1231-6"]


def test_quota_free(monkeypatch):
    from fastapi.testclient import TestClient

    from radar import api

    api.get_assistant.cache_clear()
    monkeypatch.setattr(api, "get_assistant", lambda: Assistant(load_config(), articles=corpus(), client=FakeClient()))
    api._quota.clear()
    c = TestClient(api.app)
    limite = load_config().rag["free_daily_quota"]
    for i in range(limite):
        r = c.post("/assistant", json={"question": "Quel est le délai de paiement ?"})
        assert r.status_code == 200 and r.json()["questions_restantes_aujourdhui"] == limite - i - 1
    assert c.post("/assistant", json={"question": "Quel est le délai de paiement ?"}).status_code == 429


def test_archives_et_fusion():
    from radar.rag.legi import archives_a_lire, fusionner

    page = ('<a href="Freemium_legi_global_20250101-140000.tar.gz">x</a><a href="Freemium_legi_global_20250713-140000.tar.gz">x</a>'
            '<a href="LEGI_20250601-210000.tar.gz">x</a><a href="LEGI_20250714-210000.tar.gz">x</a><a href="LEGI_20261020-210000.tar.gz">x</a>')
    urls = archives_a_lire(page, "B/")
    assert urls == ["B/Freemium_legi_global_20250713-140000.tar.gz", "B/LEGI_20250714-210000.tar.gz", "B/LEGI_20261020-210000.tar.gz"]
    ancien = Article("1", "Code de commerce", "L441-10", "ancien", "2019-04-26", "u")
    nouveau = Article("2", "Code de commerce", "L441-10", "nouveau", "2026-01-01", "u")
    assert [a.texte for a in fusionner([ancien], [nouveau])] == ["nouveau"]
    assert [a.texte for a in fusionner([nouveau], [ancien])] == ["nouveau"]
