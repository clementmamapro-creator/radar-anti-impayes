"""Test de charge progressif de l'API en production.

Paliers de concurrence croissante (utilisateurs simultanés) sur la route de score,
la plus utilisée. Pour chaque palier : débit (requêtes par seconde), latences
p50/p95/p99 et taux d'erreur. On s'arrête si le taux d'erreur dépasse 5 %.

Usage : python scripts/test_charge.py https://acquit-solutions.fr resultats.json
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time

import httpx

# Grandes entreprises connues : le test mesure le serveur, pas les entreprises.
SIRENS = ["542051180", "552081317", "552100554", "775670417", "542107651",
          "552032534", "632012100", "572015246", "383474814", "414818930"]
PALIERS = [1, 2, 5, 10, 20, 40]
DUREE_S = 20


def pct(v: list[float], p: float) -> float | None:
    if not v:
        return None
    v = sorted(v)
    return round(v[min(len(v) - 1, int(p * len(v)))], 1)


async def utilisateur(client, base, fin, durees, erreurs, i):
    n = i
    while time.perf_counter() < fin:
        siren = SIRENS[n % len(SIRENS)]
        n += 1
        t = time.perf_counter()
        try:
            r = await client.get(f"{base}/score/{siren}")
            ok = r.status_code < 500
        except httpx.HTTPError:
            ok = False
        (durees if ok else erreurs).append((time.perf_counter() - t) * 1000)


async def palier(base: str, concurrence: int) -> dict:
    durees: list[float] = []
    erreurs: list[float] = []
    limites = httpx.Limits(max_connections=concurrence, max_keepalive_connections=concurrence)
    async with httpx.AsyncClient(timeout=30, limits=limites) as client:
        debut = time.perf_counter()
        fin = debut + DUREE_S
        await asyncio.gather(*(utilisateur(client, base, fin, durees, erreurs, i) for i in range(concurrence)))
        ecoule = time.perf_counter() - debut
    total = len(durees) + len(erreurs)
    return {
        "utilisateurs_simultanes": concurrence,
        "requetes": total,
        "debit_rps": round(total / ecoule, 1),
        "p50_ms": pct(durees, .5), "p95_ms": pct(durees, .95), "p99_ms": pct(durees, .99),
        "moyenne_ms": round(statistics.mean(durees), 1) if durees else None,
        "erreurs_pct": round(100 * len(erreurs) / total, 2) if total else 0.0,
    }


async def main(base: str, sortie: str) -> None:
    # Échauffement : réveille le service et remplit les caches
    async with httpx.AsyncClient(timeout=90) as c:
        for s in SIRENS:
            await c.get(f"{base}/score/{s}")
    resultats = []
    for n in PALIERS:
        r = await palier(base, n)
        print(json.dumps(r, ensure_ascii=False))
        resultats.append(r)
        if r["erreurs_pct"] > 5:
            break
    meilleur = max(resultats, key=lambda r: r["debit_rps"])
    rapport = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cible": base, "route": "/score/{siren}", "duree_palier_s": DUREE_S,
        "paliers": resultats,
        "debit_max_rps": meilleur["debit_rps"],
        "debit_max_par_minute": round(meilleur["debit_rps"] * 60),
        "concurrence_au_debit_max": meilleur["utilisateurs_simultanes"],
    }
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)
    print("Débit maximal :", meilleur["debit_rps"], "req/s")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), sys.argv[2] if len(sys.argv) > 2 else "charge.json"))
