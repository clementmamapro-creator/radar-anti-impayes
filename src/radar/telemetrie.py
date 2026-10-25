"""Télémétrie en mémoire : latences, débit, erreurs, ressources du processus.

Volontairement sans dépendance (pas de Prometheus) : le service tient sur une
petite instance. On garde les dernières requêtes dans un tampon circulaire et
on calcule les percentiles à la demande pour la page publique « Sous le capot ».
Aucune donnée personnelle : ni adresse IP, ni SIREN, seulement la route et la durée.
"""

from __future__ import annotations

import os
import resource
import threading
import time
from collections import deque

FENETRE_S = 15 * 60          # fenêtre des indicateurs
MINUTES = 30                 # historique par minute pour les courbes
EXCLUS = {"/metriques", "/health"}  # le suivi ne se mesure pas lui-même


def percentile(valeurs: list[float], p: float) -> float | None:
    if not valeurs:
        return None
    v = sorted(valeurs)
    k = (len(v) - 1) * p
    i, f = int(k), k - int(k)
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * f


def memoire_mo() -> float:
    """Mémoire résidente actuelle du processus (Linux), sinon le pic."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


class Telemetrie:
    def __init__(self, maxlen: int = 20000):
        self.requetes: deque = deque(maxlen=maxlen)  # (horodatage, route, statut, durée ms)
        self.verrou = threading.Lock()
        self.demarre = time.time()
        self._cpu = (time.time(), sum(os.times()[:2]))
        self.compteurs: dict[str, int] = {}

    def enregistrer(self, route: str, statut: int, ms: float, t: float | None = None) -> None:
        if route in EXCLUS:
            return
        with self.verrou:
            self.requetes.append((t or time.time(), route, statut, ms))

    def incrementer(self, nom: str, n: int = 1) -> None:
        with self.verrou:
            self.compteurs[nom] = self.compteurs.get(nom, 0) + n

    def cpu_pct(self) -> float:
        """CPU consommé par le processus depuis le dernier appel, en % d'un cœur."""
        t, c = time.time(), sum(os.times()[:2])
        t0, c0 = self._cpu
        self._cpu = (t, c)
        return round(100 * (c - c0) / (t - t0), 1) if t > t0 else 0.0

    def instantane(self, maintenant: float | None = None) -> dict:
        now = maintenant or time.time()
        with self.verrou:
            recents = [r for r in self.requetes if r[0] >= now - FENETRE_S]
            historique = [r for r in self.requetes if r[0] >= now - MINUTES * 60]
            compteurs = dict(self.compteurs)
        api = [r for r in recents if r[1] != "site"]
        durees = [r[3] for r in api]
        par_route: dict[str, list[float]] = {}
        for r in api:
            par_route.setdefault(r[1], []).append(r[3])
        minutes = []
        debut = int(now // 60) * 60 - (MINUTES - 1) * 60
        for i in range(MINUTES):
            a = debut + i * 60
            d = [r[3] for r in historique if a <= r[0] < a + 60 and r[1] != "site"]
            minutes.append({"t": a, "requetes": len(d), "p95_ms": _arrondi(percentile(d, 0.95))})
        return {
            "fenetre_min": FENETRE_S // 60,
            "requetes": len(recents),
            "requetes_api": len(api),
            "par_minute": round(len(recents) / (FENETRE_S / 60), 2),
            "latence_ms": {k: _arrondi(percentile(durees, p)) for k, p in (("p50", .5), ("p95", .95), ("p99", .99))},
            "erreurs_pct": round(100 * sum(r[2] >= 500 for r in recents) / len(recents), 2) if recents else 0.0,
            "par_route": sorted(
                ({"route": k, "requetes": len(v), "p50_ms": _arrondi(percentile(v, .5)),
                  "p95_ms": _arrondi(percentile(v, .95))} for k, v in par_route.items()),
                key=lambda x: -x["requetes"]),
            "minutes": minutes,
            "compteurs": compteurs,
        }

    def processus(self) -> dict:
        return {
            "demarre_le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.demarre)),
            "en_service_s": int(time.time() - self.demarre),
            "memoire_mo": round(memoire_mo(), 1),
            "cpu_pct": self.cpu_pct(),
            "threads": threading.active_count(),
        }


def _arrondi(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


TELEMETRIE = Telemetrie()
