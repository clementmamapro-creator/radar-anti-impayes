/* Calculateur de pénalités de retard entre professionnels (art. L441-10 et D441-5 du Code de commerce).
   Tout est calculé dans le navigateur : aucune donnée n'est envoyée. */
(function () {
  "use strict";

  // Taux par semestre. bce10 = taux de refinancement BCE au 1er janvier / 1er juillet + 10 points ;
  // plancher = 3 × taux d'intérêt légal (créances des professionnels). À mettre à jour chaque semestre.
  var TAUX = [
    { debut: "2024-01-01", lib: "1er semestre 2024", bce10: 14.50, plancher: 15.21 },
    { debut: "2024-07-01", lib: "2nd semestre 2024", bce10: 14.25, plancher: 14.76 },
    { debut: "2025-01-01", lib: "1er semestre 2025", bce10: 13.15, plancher: 11.13 },
    { debut: "2025-07-01", lib: "2nd semestre 2025", bce10: 12.15, plancher: 8.28 },
    { debut: "2026-01-01", lib: "1er semestre 2026", bce10: 12.15, plancher: 7.86 },
    { debut: "2026-07-01", lib: "2nd semestre 2026", bce10: 12.40, plancher: 8.25 }
  ];
  var INDEMNITE = 40;
  var JOUR = 86400000;

  function $(id) { return document.getElementById(id); }
  function eur(x) { return x.toLocaleString("fr-FR", { style: "currency", currency: "EUR" }); }
  function pct(x) { return x.toLocaleString("fr-FR", { maximumFractionDigits: 2 }) + " %"; }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function jour(s) { var p = s.split("-"); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }

  function semestreDe(t) {
    var s = TAUX[0];
    TAUX.forEach(function (x) { if (jour(x.debut) <= t) s = x; });
    return s;
  }

  // Découpe la période de retard par semestre (chaque semestre a son propre taux)
  function calculer(montant, echeance, paiement, tauxContrat) {
    var debut = jour(echeance) + JOUR, fin = jour(paiement);   // exigibles le lendemain de l'échéance
    var jours = Math.max(0, Math.round((fin - debut) / JOUR) + 1);
    var tranches = [], t = debut;
    while (t <= fin) {
      var s = semestreDe(t), d = new Date(t);
      var finSem = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() < 6 ? 6 : 12, 1) - JOUR;
      var bout = Math.min(fin, finSem), n = Math.round((bout - t) / JOUR) + 1;
      var taux = tauxContrat != null ? Math.max(tauxContrat, s.plancher) : s.bce10;
      tranches.push({ lib: s.lib, jours: n, taux: taux, montant: montant * taux / 100 * n / 365, releve: tauxContrat != null && tauxContrat < s.plancher });
      t = bout + JOUR;
    }
    var pen = tranches.reduce(function (a, x) { return a + x.montant; }, 0);
    return { jours: jours, tranches: tranches, penalites: pen, total: jours > 0 ? pen + INDEMNITE : 0, indemnite: jours > 0 ? INDEMNITE : 0 };
  }

  var dernier = null;
  function majAffichage() {
    var montant = parseFloat(($("c-montant").value || "").replace(",", "."));
    var e = $("c-echeance").value, p = $("c-paiement").value;
    var tc = $("c-taux").value === "" ? null : parseFloat($("c-taux").value.replace(",", "."));
    var err = $("c-erreur");
    if (!(montant > 0) || !e || !p) { err.textContent = "Indiquez le montant et les deux dates."; err.hidden = false; return; }
    if (jour(p) < jour(e)) { err.textContent = "La date de paiement est avant l'échéance : il n'y a pas de retard."; err.hidden = false; }
    else err.hidden = true;
    var r = calculer(montant, e, p, tc);
    dernier = { r: r, montant: montant, e: e, p: p };
    animer($("r-total"), r.total);
    $("r-penalites").textContent = eur(r.penalites);
    $("r-indemnite").textContent = eur(r.indemnite);
    $("r-jours").textContent = r.jours.toLocaleString("fr-FR") + " jour" + (r.jours > 1 ? "s" : "");
    // Barre : part des pénalités et de l'indemnité dans le total
    var b = $("r-barre");
    if (r.total > 0) {
      var w = 300 * r.penalites / r.total;
      b.innerHTML = '<rect class="b-pen" x="0" y="0" height="18" width="' + w.toFixed(1) + '" rx="4"/><rect class="b-ind" x="' + w.toFixed(1) + '" y="0" height="18" width="' + (300 - w).toFixed(1) + '" rx="4"/>';
    } else b.innerHTML = "";
    $("r-detail").innerHTML = r.tranches.length ? "<thead><tr><th>Période</th><th>Jours</th><th>Taux</th><th>Pénalités</th></tr></thead><tbody>" +
      r.tranches.map(function (x) {
        return "<tr><td>" + x.lib + "</td><td>" + x.jours + "</td><td>" + pct(x.taux) + (x.releve ? " *" : "") + "</td><td>" + eur(x.montant) + "</td></tr>";
      }).join("") + "</tbody>" : "";
    var releve = r.tranches.some(function (x) { return x.releve; });
    $("r-formule").textContent = r.jours > 0 ? eur(montant) + " × taux annuel × jours de retard ÷ 365, puis + 40 € d'indemnité." +
      (releve ? " * Votre taux est inférieur au minimum légal (3 fois le taux d'intérêt légal) : le minimum s'applique." : "") : "";
  }

  function animer(el, cible) {
    var depart = el._v || 0, t0 = performance.now(), D = 500;
    el._v = cible;
    (function pas(t) {
      var k = Math.min(1, (t - t0) / D), e2 = 1 - Math.pow(1 - k, 3);
      el.textContent = eur(depart + (cible - depart) * e2);
      if (k < 1) requestAnimationFrame(pas);
    })(t0);
  }

  // Valeurs par défaut : échéance il y a 45 jours, paiement aujourd'hui
  var auj = new Date();
  $("c-paiement").value = iso(new Date(Date.UTC(auj.getFullYear(), auj.getMonth(), auj.getDate())));
  $("c-echeance").value = iso(new Date(Date.UTC(auj.getFullYear(), auj.getMonth(), auj.getDate()) - 45 * JOUR));
  ["c-montant", "c-echeance", "c-paiement", "c-taux"].forEach(function (id) { $(id).addEventListener("input", majAffichage); });
  $("r-taux-liste").textContent = TAUX.slice(-3).map(function (x) { return x.lib + " : " + pct(x.bce10); }).join(" ; ");

  $("r-copier").addEventListener("click", function () {
    if (!dernier) return;
    var r = dernier.r, d = function (s) { return new Date(s).toLocaleDateString("fr-FR"); };
    var txt = "Facture de " + eur(dernier.montant) + " échue le " + d(dernier.e) + ", " + r.jours + " jours de retard au " + d(dernier.p) + ".\n" +
      r.tranches.map(function (x) { return "- " + x.lib + " : " + x.jours + " jours à " + pct(x.taux) + " = " + eur(x.montant); }).join("\n") +
      "\nPénalités de retard : " + eur(r.penalites) + " (article L441-10 du Code de commerce)" +
      "\nIndemnité forfaitaire pour frais de recouvrement : " + eur(r.indemnite) + " (article D441-5 du Code de commerce)" +
      "\nTotal dû en plus du principal : " + eur(r.total);
    var btn = this;
    (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(function () {
      btn.textContent = "Copié ✓"; setTimeout(function () { btn.textContent = "Copier le détail pour ma relance"; }, 2000);
    }).catch(function () { window.prompt("Copiez le texte :", txt); });
    try { if (window.umami) window.umami.track("calculateur_copie"); } catch (e) {}
  });

  majAffichage();
  window.AcquitCalcul = calculer;  // exposé pour les tests
})();
