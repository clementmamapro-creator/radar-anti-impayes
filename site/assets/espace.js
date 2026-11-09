/* Espace client Acquit (V0, semaine 1) : connexion par lien e-mail, profil de l'entreprise,
   « Mon secteur » (carte BODACC). La connexion et le profil passent par Supabase avec la clé
   publique ; la sécurité repose sur la Row Level Security (chaque compte ne voit que sa ligne). */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var ECRANS = ["chargement", "connexion", "indispo", "app"];
  var PAL = ["#F4E6D6", "#E8C9A8", "#D49C70", "#B9693F", "#8E3A14"];
  var BIENTOT = {
    semaine: ["Ma semaine", "Chaque lundi, trois actions prêtes à valider : répondre, publier, relancer."],
    demandes: ["Demandes", "Collez un message reçu : la réponse est rédigée pour vous, dans votre ton."],
    publications: ["Publications", "Une photo de chantier devient une publication et un visuel aux couleurs de votre entreprise."],
    factures: ["Devis et factures", "Le suivi de vos factures et des relances prêtes à envoyer."]
  };
  var sb = null, user = null, entreprise = null, geo = null, carte = null, secteurPret = false;
  var moisIdx = 11, depChoisi = null, minuterie = null;

  function ecran(nom) { ECRANS.forEach(function (e) { $(e).hidden = e !== nom; }); }
  function montrer(el, txt) { el.textContent = txt; el.hidden = false; }
  function fmtMois(ym) {
    if (!ym) return "";
    var p = ym.split("-");
    return new Intl.DateTimeFormat("fr-FR", { month: "short", year: "numeric" }).format(new Date(+p[0], +p[1] - 1, 1));
  }
  function fmtPct(v) { return v == null ? "—" : (v > 0 ? "+" : "") + String(v).replace(".", ",") + " %"; }
  function fmtN(v) { return v == null ? "—" : Number(v).toLocaleString("fr-FR"); }
  function nomDep(code) { return geo && geo.dep[code] ? geo.dep[code].n + " (" + code + ")" : code; }

  // --- Démarrage --------------------------------------------------------------
  async function init() {
    var conf;
    try {
      var r = await fetch("/espace/config");
      if (!r.ok) throw new Error("config");
      conf = await r.json();
    } catch (e) { ecran("indispo"); return; }
    if (!window.supabase) { ecran("indispo"); return; }
    sb = window.supabase.createClient(conf.supabase_url, conf.supabase_publishable_key, {
      auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
    });
    sb.auth.onAuthStateChange(function (evt) {
      if (evt === "SIGNED_OUT") { user = null; entreprise = null; ecran("connexion"); }
    });
    geo = await fetch("assets/carte-france.json").then(function (r) { return r.json(); }).catch(function () { return null; });
    remplirDepartements();
    var res = await sb.auth.getSession();
    if (/[?&](code|error)=/.test(location.search)) history.replaceState(null, "", location.pathname + location.hash);
    var session = res.data && res.data.session;
    if (!session) { ecran("connexion"); return; }
    await ouvrir(session.user);
  }

  // --- Connexion --------------------------------------------------------------
  $("form-connexion").addEventListener("submit", async function (e) {
    e.preventDefault();
    var email = $("email").value.trim(), err = $("erreur-connexion");
    err.hidden = true;
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { montrer(err, "Vérifiez l'adresse e-mail."); return; }
    $("btn-lien").disabled = true;
    var res = await sb.auth.signInWithOtp({
      email: email,
      options: { emailRedirectTo: location.origin + "/espace", shouldCreateUser: false }
    });
    $("btn-lien").disabled = false;
    if (res.error) {
      var m = (res.error.message || "").toLowerCase();
      montrer(err, m.indexOf("signup") >= 0 || m.indexOf("not allowed") >= 0
        ? "Cette adresse n'est pas encore invitée au pilote. Écrivez-nous pour y participer."
        : m.indexOf("rate") >= 0 ? "Trop de demandes. Réessayez dans quelques minutes."
        : "Le lien n'a pas pu être envoyé. Réessayez dans un instant.");
      return;
    }
    $("form-connexion").hidden = true;
    $("lien-envoye").hidden = false;
  });

  $("deconnexion").addEventListener("click", function () { sb.auth.signOut(); });
  $("deconnexion-2").addEventListener("click", function () { sb.auth.signOut(); });

  async function ouvrir(u) {
    user = u;
    $("email-connecte").textContent = u.email || "";
    $("email-profil").textContent = u.email || "";
    var res = await sb.from("entreprises").select("*").maybeSingle();
    entreprise = res.error ? null : res.data;
    majCote();
    ecran("app");
    if (!entreprise) { location.hash = "#profil"; afficher(); }
    else afficher();
  }

  function majCote() {
    $("nom-entreprise").textContent = entreprise ? entreprise.nom : "Votre entreprise";
  }

  // --- Navigation ---------------------------------------------------------------
  window.addEventListener("hashchange", function () { if (user) afficher(); });
  function afficher() {
    var vue = (location.hash || "#secteur").slice(1);
    if (!entreprise) vue = "profil";
    document.querySelectorAll(".nav").forEach(function (a) {
      var on = a.dataset.vue === vue;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    ["secteur", "profil", "bientot"].forEach(function (v) { $("vue-" + v).hidden = true; });
    if (vue === "profil") { ouvrirProfil(); $("vue-profil").hidden = false; }
    else if (BIENTOT[vue]) { $("bientot-titre").textContent = BIENTOT[vue][0]; $("bientot-texte").textContent = BIENTOT[vue][1]; $("vue-bientot").hidden = false; }
    else { $("vue-secteur").hidden = false; ouvrirSecteur(); }
    window.scrollTo(0, 0);
  }

  // --- Profil -------------------------------------------------------------------
  function remplirDepartements() {
    if (!geo) return;
    var codes = Object.keys(geo.dep).sort();
    [$("p-dep"), $("dep")].forEach(function (sel) {
      sel.innerHTML = "";
      codes.forEach(function (c) {
        var o = document.createElement("option");
        o.value = c; o.textContent = c + " · " + geo.dep[c].n;
        sel.appendChild(o);
      });
    });
  }
  function ouvrirProfil() {
    var neuf = !entreprise;
    $("profil-titre").textContent = neuf ? "Bienvenue" : "Votre entreprise";
    $("profil-intro").textContent = neuf
      ? "Quelques informations pour commencer. Elles servent à personnaliser votre espace."
      : "Ces informations servent à personnaliser votre espace. Vous pouvez les changer à tout moment.";
    var e = entreprise || {};
    $("p-nom").value = e.nom || ""; $("p-metier").value = e.metier || ""; $("p-ville").value = e.ville || "";
    if (e.departement) $("p-dep").value = e.departement;
    $("p-rayon").value = String(e.rayon_km || 15); $("p-ton").value = e.ton || "cordial";
    $("profil-ok").hidden = true; $("erreur-profil").hidden = true;
  }
  $("form-profil").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    var err = $("erreur-profil"); err.hidden = true; $("profil-ok").hidden = true;
    var ligne = {
      user_id: user.id, nom: $("p-nom").value.trim(), metier: $("p-metier").value.trim(),
      ville: $("p-ville").value.trim() || null, departement: $("p-dep").value,
      rayon_km: +$("p-rayon").value, ton: $("p-ton").value
    };
    if (!ligne.nom || !ligne.metier) { montrer(err, "Indiquez au moins le nom de l'entreprise et votre métier."); return; }
    $("btn-profil").disabled = true;
    var res = await sb.from("entreprises").upsert(ligne, { onConflict: "user_id" }).select().single();
    $("btn-profil").disabled = false;
    if (res.error) { montrer(err, "L'enregistrement n'a pas abouti. Réessayez dans un instant."); return; }
    var premier = !entreprise;
    entreprise = res.data; majCote();
    depChoisi = entreprise.departement; secteurPret = false;
    if (premier) location.hash = "#secteur";
    else $("profil-ok").hidden = false;
  });

  // --- Mon secteur ----------------------------------------------------------------
  async function ouvrirSecteur() {
    $("t-zone").textContent = nomDep(entreprise.departement);
    $("t-rayon").textContent = "rayon d'intervention : " + entreprise.rayon_km + " km";
    $("t-metier").textContent = entreprise.metier;
    $("t-ville").textContent = entreprise.ville || "";
    if (!depChoisi) depChoisi = entreprise.departement;
    if (secteurPret) { fiche(); return; }
    if (!carte) {
      carte = await fetch("/carte").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    }
    if (carte) {
      $("t-france").textContent = fmtN(carte.total) + " défaillances";
      $("t-france-evo").textContent = fmtPct(carte.evolution_pct) + " sur un an";
      $("secteur-maj").textContent = "Données du BODACC, du " + new Date(carte.periode.debut).toLocaleDateString("fr-FR") + " au " + new Date(carte.periode.fin).toLocaleDateString("fr-FR");
    }
    dessinerCarte();
    secteurPret = true;
    fiche();
  }

  function moisVisibles() { return carte && carte.mois ? carte.mois.slice(-12) : []; }
  function valeur(code) {
    var mois = carte && carte.mois ? carte.mois : [], serie = carte && carte.series ? carte.series[code] : null;
    if (serie && mois.length) return serie[mois.length - 12 + moisIdx] || 0;
    return carte && carte.departements[code] ? carte.departements[code].n : 0;
  }

  function dessinerCarte() {
    var svg = $("carte");
    if (!geo) { svg.setAttribute("aria-label", "Carte indisponible"); return; }
    if (!svg.childNodes.length) {
      Object.keys(geo.dep).forEach(function (c) {
        var p = document.createElementNS("http://www.w3.org/2000/svg", "path");
        p.setAttribute("d", geo.dep[c].d); p.dataset.dep = c;
        var t = document.createElementNS("http://www.w3.org/2000/svg", "title"); t.textContent = geo.dep[c].n; p.appendChild(t);
        p.addEventListener("click", function () { depChoisi = c; $("dep").value = c; fiche(); colorer(); });
        svg.appendChild(p);
      });
    }
    var aSerie = !!(carte && carte.series && Object.keys(carte.series).length && moisVisibles().length === 12);
    $("jouer").hidden = !aSerie; $("mois").hidden = !aSerie;
    colorer();
  }

  function colorer() {
    var paths = $("carte").querySelectorAll("path");
    var vals = [].map.call(paths, function (p) { return valeur(p.dataset.dep); });
    var tri = vals.slice().sort(function (a, b) { return a - b; });
    paths.forEach(function (p, i) {
      var k = 0; for (var q = 1; q < 5; q++) if (vals[i] > tri[Math.floor(tri.length * q / 5)]) k = q;
      p.style.fill = PAL[k];
      p.classList.toggle("choisi", p.dataset.dep === depChoisi);
    });
    var m = moisVisibles();
    $("mois").value = moisIdx;
    $("mois-lib").textContent = m.length ? fmtMois(m[moisIdx]) : "12 derniers mois";
    $("carte").setAttribute("aria-label", "Carte des défaillances par département" + (m.length ? ", " + fmtMois(m[moisIdx]) : ""));
    barres();
  }

  var ficheCache = {};
  async function fiche() {
    var c = depChoisi;
    $("dep").value = c; $("f-nom").textContent = nomDep(c);
    var d = ficheCache[c];
    if (!d) {
      d = await fetch("/secteur/" + encodeURIComponent(c)).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
      if (d) ficheCache[c] = d;
    }
    if (c !== depChoisi) return;
    var v = $("f-verdict");
    if (!d) { v.textContent = "Données indisponibles"; v.className = "pastille"; $("f-n").textContent = "—"; $("f-evo").textContent = "—"; $("f-conseil").textContent = ""; $("f-barres").innerHTML = ""; return; }
    v.textContent = d.verdict.libelle; v.className = "pastille " + d.verdict.code;
    $("f-n").textContent = fmtN(d.n_12_mois); $("f-evo").textContent = fmtPct(d.evolution_pct);
    $("f-conseil").textContent = d.verdict.conseil;
    barres();
  }

  function barres() {
    var d = ficheCache[depChoisi], box = $("f-barres");
    if (!d || !d.serie || !d.serie.length) { box.innerHTML = ""; return; }
    var max = Math.max.apply(null, d.serie.concat([1]));
    if (box.children.length !== d.serie.length) {
      box.innerHTML = "";
      d.serie.forEach(function () { box.appendChild(document.createElement("span")); });
    }
    [].forEach.call(box.children, function (s, i) {
      s.style.height = Math.max(4, Math.round(d.serie[i] / max * 100)) + "%";
      s.classList.toggle("courant", i === moisIdx);
      s.title = fmtMois(d.mois[i]) + " : " + d.serie[i];
    });
  }

  $("dep").addEventListener("change", function () { depChoisi = this.value; fiche(); colorer(); });
  $("mois").addEventListener("input", function () { arreter(); moisIdx = +this.value; colorer(); });
  $("jouer").addEventListener("click", function () {
    if (minuterie) { arreter(); return; }
    if (moisIdx >= 11) moisIdx = 0;
    $("icone-jouer").setAttribute("d", "M6 5h4v14H6zM14 5h4v14h-4z");
    $("jouer").setAttribute("aria-label", "Mettre en pause");
    colorer();
    minuterie = setInterval(function () {
      if (moisIdx >= 11) { arreter(); return; }
      moisIdx++; colorer();
    }, 700);
  });
  function arreter() {
    if (minuterie) clearInterval(minuterie);
    minuterie = null;
    $("icone-jouer").setAttribute("d", "M7 5v14l12-7z");
    $("jouer").setAttribute("aria-label", "Lire l'évolution sur 12 mois");
  }

  init();
})();
