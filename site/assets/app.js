/* Acquit — vérification d'un client depuis la page d'accueil. */
(function () {
  "use strict";

  // L'API peut être hébergée ailleurs que le site : définir window.ACQUIT_API avant ce script.
  var API = (window.ACQUIT_API || "").replace(/\/$/, "");
  var $ = function (s) { return document.querySelector(s); };
  var form = $("#form"), input = $("#q"), bouton = $("#bouton"), fiche = $("#fiche");
  var liste = $("#suggestions"), exemples = $("#exemples");
  var demo = false;

  var TAMPON = '<svg class="tampon-fiche" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="29" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="32" cy="32" r="23" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M21.5 33.5 L28.5 40.5 L43 25" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="square"/></svg>';
  var NIVEAU = {
    "faible": ["niveau-faible", "Risque faible"],
    "modéré": ["niveau-modere", "Risque modéré"],
    "élevé": ["niveau-eleve", "Risque élevé"],
    "procedure_en_cours": ["niveau-eleve", "Procédure en cours"],
    "donnees_insuffisantes": ["niveau-neutre", "Données insuffisantes"]
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function siren(s) { return String(s).replace(/\D/g, "").slice(0, 9).replace(/(\d{3})(?=\d)/g, "$1 "); }
  function dateFr(d) { return new Date(d).toLocaleDateString("fr-FR"); }
  function pct(p) { return (p * 100).toLocaleString("fr-FR", { maximumFractionDigits: 1 }) + " %"; }
  function majuscule(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  // Position du curseur : zones de largeur 2/4/14, alignées sur les seuils de 2 % et 6 %
  function position(p) {
    if (p < 0.02) return (p / 0.02) * 10;
    if (p < 0.06) return 10 + ((p - 0.02) / 0.04) * 20;
    return 30 + Math.min(1, (p - 0.06) / 0.34) * 70;
  }

  function fichHtml(r, opts) {
    opts = opts || {};
    var key = r.statut === "score" ? r.niveau : r.statut;
    var niv = NIVEAU[key] || ["niveau-neutre", ""];
    var nom = (r.identite && r.identite.nom) || opts.nom || (demo ? "Entreprise fictive" : "Entreprise");
    // Entreprises dont l'identité est protégée à l'INSEE (souvent des entrepreneurs individuels)
    if (/NON[- ]DIFFUSIBLE/i.test(nom)) nom = "Entreprise non diffusible (identité protégée)";
    var meta = ["SIREN " + siren(r.siren)];
    if (r.identite && r.identite.date_creation) meta.push("créée en " + String(r.identite.date_creation).slice(0, 4));
    var h = "";
    h += '<div class="fiche-tete"><span>' + (opts.exemple ? "Exemple de fiche client" : "Fiche client") + "</span><span>" +
      (opts.exemple ? "Entreprise fictive" : "Vérifiée le " + dateFr(Date.now())) + "</span></div>";
    h += TAMPON;
    h += '<p class="fiche-nom">' + esc(nom) + "</p>";
    h += '<p class="fiche-id">' + esc(meta.join(" · ")) + "</p>";
    h += '<div class="fiche-reco"><span class="niveau ' + niv[0] + '">' + niv[1] + "</span>";
    if (r.recommandation) {
      h += "<h3>" + esc(r.recommandation.titre) + "</h3><p>" + esc(r.recommandation.texte) + "</p>";
    }
    h += "</div>";
    if (r.statut === "score") {
      h += '<div class="regle" role="img" aria-label="Risque de défaillance estimé à 12 mois : ' + pct(r.probabilite) + '">' +
        '<div class="regle-piste"><span></span><span></span><span></span><i class="regle-curseur" style="left:0%"></i></div>' +
        '<div class="regle-legende"><span>Risque estimé à 12 mois</span><span>' + pct(r.probabilite) + "</span></div></div>";
      if (r.facteurs && r.facteurs.length) {
        h += '<p class="fiche-titre-bloc">Ce qui pèse le plus</p><ul class="facteurs">' + r.facteurs.map(function (f) {
          var up = f.effet === "augmente";
          return '<li><span class="signe ' + (up ? "up" : "down") + '" aria-hidden="true">' + (up ? "+" : "−") + "</span><span>" + esc(f.phrase) + "</span></li>";
        }).join("") + "</ul>";
      }
    }
    if (r.procedures && r.procedures.length) {
      h += '<p class="fiche-titre-bloc">Annonces au BODACC</p><ul class="procedures">' + r.procedures.map(function (p) {
        return "<li>" + dateFr(p.date) + " : " + esc(p.nature) + "</li>";
      }).join("") + "</ul>";
    }
    var pied = [];
    if (r.date_dernier_bilan) pied.push("Comptes clos le " + dateFr(r.date_dernier_bilan) + ".");
    if (r.rappel_legal) pied.push(r.rappel_legal);
    if (r.avertissement) pied.push(r.avertissement);
    h += '<p class="fiche-pied">' + esc(pied.join(" ")) + "</p>";
    return h;
  }

  function afficher(r, opts) {
    fiche.innerHTML = fichHtml(r, opts);
    var c = fiche.querySelector(".regle-curseur");
    if (c) requestAnimationFrame(function () { requestAnimationFrame(function () { c.style.left = position(r.probabilite) + "%"; }); });
  }

  var EXEMPLE = {
    siren: "000000000", statut: "score", probabilite: 0.041, niveau: "modéré",
    date_dernier_bilan: "2025-12-31",
    identite: { nom: "Menuiserie des Coteaux" },
    recommandation: { titre: "Demandez un acompte", texte: "Demandez un acompte d'environ 30 % à la signature et un paiement du solde à 15 jours." },
    facteurs: [
      { effet: "augmente", phrase: "Le taux d'endettement : au-dessus de la médiane des entreprises, ce qui augmente le risque." },
      { effet: "augmente", phrase: "Le délai de paiement de ses fournisseurs : au-dessus de la médiane des entreprises, ce qui augmente le risque." },
      { effet: "réduit", phrase: "La marge d'exploitation (EBE) : au-dessus de la médiane des entreprises, ce qui réduit le risque." }
    ],
    procedures: [],
    avertissement: "Risque estimé à partir des données publiques. Ce score est une aide à la décision, pas un jugement sur l'entreprise."
  };

  function attente() {
    fiche.innerHTML = '<div class="fiche-tete"><span>Fiche client</span><span></span></div><p class="fiche-nom fiche-attente">Vérification en cours…</p>';
  }

  function verifier(s) {
    var digits = String(s).replace(/\D/g, "");
    if (digits.length !== 9) {
      fiche.innerHTML = '<p class="erreur">Un SIREN comporte 9 chiffres. Vous pouvez aussi saisir le nom de l\'entreprise et la choisir dans la liste.</p>';
      return;
    }
    attente();
    bouton.disabled = true;
    var lent = setTimeout(function () {
      var p = fiche.querySelector(".fiche-attente");
      if (p) p.textContent = "Le service se réveille, cela peut prendre jusqu'à une minute.";
    }, 3500);
    fetch(API + "/score/" + digits)
      .then(function (res) { return res.json().then(function (d) { if (!res.ok) throw new Error(d.detail || "La vérification a échoué."); return d; }); })
      .then(function (r) { afficher(r); })
      .catch(function (e) { fiche.innerHTML = '<p class="erreur">' + esc(e.message || "La vérification a échoué. Réessayez dans un instant.") + "</p>"; })
      .then(function () { clearTimeout(lent); bouton.disabled = false; });
    if (window.matchMedia("(max-width: 959px)").matches) fiche.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // Suggestions par nom
  var courant = -1, resultats = [], minuterie = null;
  function fermer() { liste.hidden = true; courant = -1; input.setAttribute("aria-expanded", "false"); }
  function montrer(items) {
    resultats = items;
    if (!items.length) { fermer(); return; }
    liste.innerHTML = items.map(function (it, i) {
      var meta = [siren(it.siren), [it.code_postal, it.ville].filter(Boolean).join(" ")].filter(Boolean).join(" · ");
      return '<li role="option" id="opt-' + i + '" data-i="' + i + '"><div class="nom">' + esc(it.nom) + '</div><div class="meta">' + esc(meta) + "</div></li>";
    }).join("");
    liste.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }
  function choisir(i) {
    var it = resultats[i];
    if (!it) return;
    input.value = it.nom;
    fermer();
    verifier(it.siren);
  }
  input.addEventListener("input", function () {
    var v = input.value.trim();
    if (/^[\d\s]+$/.test(v)) { input.value = siren(v); fermer(); return; }
    clearTimeout(minuterie);
    if (v.length < 2) { fermer(); return; }
    minuterie = setTimeout(function () {
      fetch(API + "/recherche?q=" + encodeURIComponent(v))
        .then(function (r) { return r.ok ? r.json() : []; })
        .then(montrer)
        .catch(fermer);
    }, 250);
  });
  input.addEventListener("keydown", function (e) {
    if (liste.hidden) return;
    var opts = liste.querySelectorAll("li");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      courant = (courant + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
      opts.forEach(function (o, i) { o.setAttribute("aria-selected", i === courant ? "true" : "false"); });
      input.setAttribute("aria-activedescendant", "opt-" + courant);
    } else if (e.key === "Enter" && courant >= 0) {
      e.preventDefault(); choisir(courant);
    } else if (e.key === "Escape") { fermer(); }
  });
  liste.addEventListener("mousedown", function (e) {
    var li = e.target.closest("li");
    if (li) { e.preventDefault(); choisir(+li.dataset.i); }
  });
  input.addEventListener("blur", function () { setTimeout(fermer, 150); });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var v = input.value.trim();
    if (/^[\d\s]+$/.test(v)) { verifier(v); return; }
    if (resultats.length) { choisir(0); return; }
    fiche.innerHTML = '<p class="erreur">Saisissez le SIREN, ou le nom de l\'entreprise puis choisissez-la dans la liste.</p>';
  });

  afficher(EXEMPLE, { exemple: true });

  // Mode démonstration : bandeau et exemples cliquables
  fetch(API + "/health").then(function (r) { return r.json(); }).then(function (h) {
    if (!h.demo) return;
    demo = true;
    $("#demo").hidden = false;
    return fetch(API + "/exemples").then(function (r) { return r.json(); }).then(function (ex) {
      exemples.innerHTML = ex.map(function (x) {
        return '<button type="button" data-s="' + esc(x.siren) + '">' + esc(x.label) + "</button>";
      }).join("");
      exemples.querySelectorAll("button").forEach(function (b) {
        b.addEventListener("click", function () { input.value = siren(b.dataset.s); verifier(b.dataset.s); });
      });
    });
  }).catch(function () { /* le site reste utilisable sans ces informations */ });
})();
