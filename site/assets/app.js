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
    if (!opts.exemple) h += '<p class="fiche-lien"><a href="#assistant">Votre client paie en retard ? Demandez à l\'assistant quels sont vos recours →</a></p>';
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
      .then(function (r) {
        afficher(r);
        // Mesure d'audience anonyme (Umami, sans cookie) : seul le résultat est compté, jamais le SIREN
        try { if (window.umami) window.umami.track("verification", { statut: r.statut, niveau: r.niveau || "aucun" }); } catch (e) {}
      })
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

  // ---- Assistant « impayés » : conversation ----
  var aform = $("#aform"), aq = $("#aq"), abouton = $("#abouton"), afil = $("#afil"), aquota = $("#aquota"),
      anouveau = $("#anouveau"), avide = $("#avide"), apro = $("#apro");
  var MARQUE = '<span class="marque-ia" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>';
  var CLE = "acquit-conversation", MAX_HIST = 3;
  var conversation = [];  // [{question, reponse, sources, avertissement, genere}]
  var enCours = false;

  // Mise en forme légère de la réponse : paragraphes, listes, gras, références de loi
  function formater(t) {
    var html = esc(t)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+?, art(?:icle)?\.? ?[A-Z]?\d[\d-]*)\]/g, '<span class="cite">$1</span>');
    // Regroupe les lignes : suites de puces ou de numéros -> listes, le reste -> paragraphes
    var LISTE = /^\s*([-•*]|\d+[.)])\s+/;
    return html.split(/\n{2,}/).map(function (bloc) {
      var out = "", texte = [], items = [], ordonnee = false;
      function vider() {
        if (texte.length) { out += "<p>" + texte.join("<br>") + "</p>"; texte = []; }
        if (items.length) { out += (ordonnee ? "<ol>" : "<ul>") + items.map(function (i) { return "<li>" + i + "</li>"; }).join("") + (ordonnee ? "</ol>" : "</ul>"); items = []; }
      }
      bloc.split("\n").forEach(function (l) {
        if (LISTE.test(l)) {
          if (texte.length) vider();
          if (!items.length) ordonnee = /^\s*\d/.test(l);
          items.push(l.replace(LISTE, ""));
        } else if (l.trim()) {
          if (items.length) vider();
          texte.push(l);
        }
      });
      vider();
      return out;
    }).join("");
  }

  function sauver() {
    try { localStorage.setItem(CLE, JSON.stringify(conversation.slice(-20))); } catch (e) {}
  }

  function bulleUtilisateur(q) {
    var d = document.createElement("div");
    d.className = "msg msg-moi";
    d.textContent = q;
    afil.appendChild(d);
    return d;
  }

  function bulleAssistant(html, classe) {
    var d = document.createElement("div");
    d.className = "msg msg-ia" + (classe ? " " + classe : "");
    d.innerHTML = MARQUE + '<div class="corps">' + html + "</div>";
    afil.appendChild(d);
    return d;
  }

  function contenuReponse(r) {
    var h = r.reponse ? '<div class="reponse-texte">' + formater(r.reponse) + "</div>"
                      : "<p>Voici les textes de loi qui correspondent à votre question.</p>";
    if (r.sources && r.sources.length) {
      h += '<details class="sources-bloc"><summary>' + r.sources.length + " sources Légifrance</summary>" +
        '<ul class="sources">' + r.sources.map(function (s) {
          return '<li><a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.reference) + "</a>" +
            '<span class="extrait">' + esc(s.extrait) + "</span></li>";
        }).join("") + "</ul></details>";
    }
    if (r.avertissement) h += '<p class="assistant-avert">' + esc(r.avertissement) + "</p>";
    return h;
  }

  function defiler(el) {
    // Montre le début de la nouvelle réponse, pas la fin : on lit de haut en bas
    afil.scrollTo({ top: el.offsetTop - afil.offsetTop - 8, behavior: "smooth" });
  }

  function majEtat() {
    if (anouveau) anouveau.hidden = conversation.length === 0;
    var vide = conversation.length === 0 && !enCours;
    var ex = $("#aexemples");
    if (ex) ex.hidden = !vide;
    if (avide) avide.hidden = !vide;
    afil.hidden = vide;
    aq.placeholder = vide ? "Décrivez votre situation…" : "Posez une question de suivi…";
  }

  function ajuster() { aq.style.height = "auto"; aq.style.height = Math.min(aq.scrollHeight, 180) + "px"; }

  function poser(question) {
    question = question.trim();
    if (enCours) return;
    if (question.length < 5) { aq.focus(); return; }
    enCours = true;
    abouton.disabled = true;
    aq.value = ""; ajuster();
    bulleUtilisateur(question);
    majEtat();
    var attente = bulleAssistant('<div class="ecrit" aria-label="Rédaction en cours"><span></span><span></span><span></span></div>', "msg-attente");
    defiler(attente);
    var t1 = 0, t2 = 0;
    var historique = conversation.filter(function (e) { return e.reponse; }).slice(-MAX_HIST)
      .map(function (e) { return { question: e.question, reponse: e.reponse }; });
    fetch(API + "/assistant", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, historique: historique }) })
      .then(function (res) { return res.json().then(function (d) { if (!res.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Votre question doit faire entre 5 et 1 000 caractères."); return d; }); })
      .then(function (r) {
        attente.remove();
        var e = { question: question, reponse: r.reponse, sources: r.sources, avertissement: r.avertissement };
        conversation.push(e); sauver();
        defiler(bulleAssistant(contenuReponse(e)));
        if (r.questions_restantes_aujourdhui != null) {
          aquota.textContent = r.questions_restantes_aujourdhui + (r.questions_restantes_aujourdhui > 1 ? " questions gratuites restantes" : " question gratuite restante") + " aujourd'hui";
        }
        try { if (window.umami) window.umami.track("assistant", { genere: !!r.genere, suivi: historique.length > 0 }); } catch (err) {}
      })
      .catch(function (err) {
        attente.remove();
        bulleAssistant('<p>' + esc(typeof err.message === "string" ? err.message : "La réponse a échoué. Réessayez dans un instant.") + "</p>", "msg-erreur");
        if (!aq.value) { aq.value = question; ajuster(); }
      })
      .then(function () { clearTimeout(t1); clearTimeout(t2); enCours = false; abouton.disabled = false; majEtat(); });
  }

  if (aform) {
    // Reprise de la conversation enregistrée dans ce navigateur
    try { conversation = JSON.parse(localStorage.getItem(CLE) || "[]") || []; } catch (e) { conversation = []; }
    conversation.forEach(function (e) { bulleUtilisateur(e.question); bulleAssistant(contenuReponse(e)); });
    majEtat();

    aform.addEventListener("submit", function (e) { e.preventDefault(); poser(aq.value); });
    // Le bouton « retour en haut » s'efface quand la zone de saisie est à l'écran (mobile)
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        document.body.classList.toggle("chat-visible", es[0].isIntersecting);
      }).observe(aform);
    }
    aq.addEventListener("input", ajuster);
    aq.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); poser(aq.value); }
    });
    document.querySelectorAll("#aexemples button").forEach(function (b) {
      b.addEventListener("click", function () { poser(b.dataset.q || b.textContent); });
    });
    // PDF et dictée : réservés aux offres payantes (bientôt)
    var proTimer;
    document.querySelectorAll(".outil[data-pro]").forEach(function (b) {
      b.addEventListener("click", function () {
        apro.textContent = b.dataset.pro + " : inclus dans les offres Éco et Pro, bientôt disponibles.";
        apro.hidden = false;
        clearTimeout(proTimer);
        proTimer = setTimeout(function () { apro.hidden = true; }, 3500);
      });
    });
    if (anouveau) anouveau.addEventListener("click", function () {
      conversation = []; sauver();
      afil.innerHTML = "";
      majEtat(); aq.focus();
    });
  }

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
