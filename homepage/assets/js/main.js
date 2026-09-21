/*
 * Majors Golfbox – Seiten-Logik.
 * Kein Build-Tooling, kein Framework. Laedt Inhalte aus content/*.json,
 * damit Bewertungen, Fotos, Trackman-Grafiken, Turniere und Texte ohne
 * Code-Aenderung pflegbar sind.
 */
(function () {
  "use strict";

  var LANG_KEY = "mgb_lang";
  var CONSENT_KEY = "mgb_cookie_consent"; // "all" | "necessary"

  function detectInitialLang() {
    var stored = localStorage.getItem(LANG_KEY);
    if (stored === "de" || stored === "en") return stored;
    return (navigator.language || "de").slice(0, 2) === "en" ? "en" : "de";
  }

  var state = {
    lang: detectInitialLang(),
    i18n: null,
    config: null,
    reviews: null,
    gallery: null,
    trackman: null,
    tournaments: null
  };

  function fetchJSON(path) {
    return fetch(path, { cache: "no-store" }).then(function (res) {
      if (!res.ok) throw new Error("Konnte " + path + " nicht laden (" + res.status + ")");
      return res.json();
    });
  }

  function t(dict, path) {
    var parts = path.split(".");
    var node = dict;
    for (var i = 0; i < parts.length; i++) {
      if (node == null) return "";
      node = node[parts[i]];
    }
    return node == null ? "" : node;
  }

  /* ---------------------------------------------------------------------
     i18n: statische Texte
     --------------------------------------------------------------------- */
  function applyStaticTranslations() {
    var dict = state.i18n[state.lang];
    document.documentElement.lang = state.lang;

    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var val = t(dict, el.getAttribute("data-i18n"));
      if (val) el.textContent = val;
    });

    document.querySelectorAll("[data-i18n-attr]").forEach(function (el) {
      el.getAttribute("data-i18n-attr").split(";").forEach(function (pair) {
        var kv = pair.split(":");
        if (kv.length !== 2) return;
        var val = t(dict, kv[1].trim());
        if (val) el.setAttribute(kv[0].trim(), val);
      });
    });

    document.querySelectorAll(".lang-switch button").forEach(function (btn) {
      btn.setAttribute("aria-pressed", btn.getAttribute("data-lang") === state.lang ? "true" : "false");
    });
  }

  /* ---------------------------------------------------------------------
     Dynamische Inhalte (Preise, Highlights, FAQ, Turniere, Bewertungen)
     --------------------------------------------------------------------- */
  function renderHighlights() {
    var items = t(state.i18n[state.lang], "highlights.items") || [];
    var grid = document.getElementById("highlightGrid");
    grid.innerHTML = "";
    items.forEach(function (item) {
      var card = document.createElement("div");
      card.className = "highlight-card";
      var h3 = document.createElement("h3");
      h3.textContent = item.title;
      var p = document.createElement("p");
      p.textContent = item.text;
      card.appendChild(h3);
      card.appendChild(p);
      grid.appendChild(card);
    });
  }

  function renderPriceTable() {
    var preise = t(state.i18n[state.lang], "preise");
    var rows = document.getElementById("priceRows");
    rows.innerHTML = "";
    (preise.rows || []).forEach(function (row) {
      var tr = document.createElement("tr");
      var tdZeit = document.createElement("td");
      tdZeit.textContent = row.zeitraum;
      var tdPreis = document.createElement("td");
      tdPreis.className = "price-value";
      tdPreis.textContent = row.preis;
      tr.appendChild(tdZeit);
      tr.appendChild(tdPreis);
      rows.appendChild(tr);
    });

    var creditGrid = document.getElementById("creditGrid");
    creditGrid.innerHTML = "";
    (preise.guthaben_rows || []).forEach(function (row) {
      var card = document.createElement("div");
      card.className = "credit-card";
      var inp = document.createElement("div");
      inp.className = "in";
      inp.textContent = row.einzahlung;
      var out = document.createElement("div");
      out.className = "out";
      out.textContent = "→ " + row.gutschrift;
      card.appendChild(inp);
      card.appendChild(out);
      creditGrid.appendChild(card);
    });
  }

  function renderFAQ() {
    var items = t(state.i18n[state.lang], "faq.items") || [];
    var list = document.getElementById("faqList");
    list.innerHTML = "";
    items.forEach(function (item, idx) {
      var details = document.createElement("details");
      details.className = "faq-item";
      if (idx === 0) details.open = true;
      var summary = document.createElement("summary");
      summary.textContent = item.q;
      var answer = document.createElement("div");
      answer.className = "faq-answer";
      answer.textContent = item.a;
      details.appendChild(summary);
      details.appendChild(answer);
      list.appendChild(details);
    });
  }

  function renderTournaments() {
    var section = document.getElementById("turniere");
    var grid = document.getElementById("tournamentGrid");
    grid.innerHTML = "";
    var active = (state.tournaments && state.tournaments.active) || [];

    if (active.length === 0) {
      section.classList.add("is-empty");
      return;
    }
    section.classList.remove("is-empty");

    active.forEach(function (item) {
      var card = document.createElement("div");
      card.className = "tournament-card";
      var cadence = document.createElement("span");
      cadence.className = "cadence";
      cadence.textContent = state.lang === "en" ? item.cadence_en : item.cadence_de;
      var h3 = document.createElement("h3");
      h3.textContent = state.lang === "en" ? item.title_en : item.title_de;
      var p = document.createElement("p");
      p.className = "text-muted";
      p.textContent = state.lang === "en" ? item.prize_en : item.prize_de;
      card.appendChild(cadence);
      card.appendChild(h3);
      card.appendChild(p);
      grid.appendChild(card);
    });
  }

  function renderReviews() {
    if (!state.reviews) return;
    var r = state.reviews;
    var full = Math.round(r.rating);
    document.getElementById("reviewsStars").textContent =
      "★★★★★".slice(0, full) + "☆☆☆☆☆".slice(0, 5 - full);
    document.getElementById("reviewsRating").textContent = r.rating.toFixed(1);
    document.getElementById("reviewsCount").textContent = r.count;
    var badge = document.getElementById("reviewsBadge");
    badge.href = r.profile_url || "#";
  }

  /* ---------------------------------------------------------------------
     Slider: Bay-Fotos & Trackman-Grafiken
     --------------------------------------------------------------------- */
  function buildSlider(containerId, images, opts) {
    var container = document.getElementById(containerId);
    if (!images || images.length === 0) return null;
    container.innerHTML = "";
    var imgEls = images.map(function (item, idx) {
      var img = document.createElement("img");
      img.src = opts.basePath + item.file;
      img.alt = opts.altFor ? opts.altFor(item) : "";
      img.loading = "lazy";
      if (idx === 0) img.classList.add("is-active");
      img.addEventListener("error", function () { img.style.display = "none"; });
      container.appendChild(img);
      return img;
    });

    var caption = null;
    if (opts.captionEl) {
      caption = opts.captionEl;
    }

    var current = 0;
    function show(idx) {
      imgEls[current].classList.remove("is-active");
      current = (idx + imgEls.length) % imgEls.length;
      imgEls[current].classList.add("is-active");
      if (caption) caption.textContent = opts.captionFor ? opts.captionFor(images[current]) : "";
    }
    if (caption) caption.textContent = opts.captionFor ? opts.captionFor(images[0]) : "";

    var timer = null;
    function startAuto() {
      if (imgEls.length < 2) return;
      timer = setInterval(function () { show(current + 1); }, opts.interval || 5000);
    }
    function stopAuto() { if (timer) clearInterval(timer); }
    startAuto();
    container.addEventListener("mouseenter", stopAuto);
    container.addEventListener("mouseleave", startAuto);

    return {
      show: show,
      next: function () { show(current + 1); },
      prev: function () { show(current - 1); },
      count: imgEls.length,
      destroy: stopAuto
    };
  }

  var gallerySliderCtl = null;
  function renderGallery() {
    if (!state.gallery) return;
    if (gallerySliderCtl) gallerySliderCtl.destroy();
    gallerySliderCtl = buildSlider("gallerySlider", state.gallery.images, {
      basePath: "assets/img/bay/",
      altFor: function (item) { return state.lang === "en" ? item.alt_en : item.alt_de; },
      interval: 6000
    });
    if (gallerySliderCtl && gallerySliderCtl.count > 1) {
      var dots = document.createElement("div");
      dots.className = "slider-dots";
      for (var i = 0; i < gallerySliderCtl.count; i++) {
        (function (i) {
          var b = document.createElement("button");
          b.type = "button";
          b.setAttribute("aria-label", "Foto " + (i + 1));
          b.addEventListener("click", function () { gallerySliderCtl.show(i); });
          dots.appendChild(b);
        })(i);
      }
      document.getElementById("gallerySlider").appendChild(dots);
    }
  }

  var trackmanSliderCtl = null;
  function renderTrackman() {
    if (!state.trackman) return;
    if (trackmanSliderCtl) trackmanSliderCtl.destroy();
    var captionText = document.getElementById("trackmanCaptionText");
    trackmanSliderCtl = buildSlider("trackmanSlider", state.trackman.images, {
      basePath: "assets/img/trackman/",
      altFor: function (item) { return "Trackman – " + item.metric; },
      captionEl: captionText,
      captionFor: function (item) { return item.metric; },
      interval: 4000
    });
    var prev = document.getElementById("trackmanPrev");
    var next = document.getElementById("trackmanNext");
    if (trackmanSliderCtl) {
      prev.onclick = function () { trackmanSliderCtl.prev(); };
      next.onclick = function () { trackmanSliderCtl.next(); };
    }
  }

  /* ---------------------------------------------------------------------
     Kontakt / CTAs aus config.json
     --------------------------------------------------------------------- */
  function applyConfig() {
    var c = state.config;
    if (!c) return;

    document.querySelectorAll('[data-track="booking_click"]').forEach(function (el) {
      el.href = c.booking_url;
    });
    document.querySelectorAll('[data-track="call_click"]').forEach(function (el) {
      el.href = "tel:" + c.phone_href;
    });

    var phone = document.getElementById("contactPhone");
    phone.href = "tel:" + c.phone_href;
    phone.textContent = c.phone_display;

    var altPhone = document.getElementById("priceAltPhone");
    if (altPhone && c.phone_alt_display) {
      altPhone.href = "tel:" + c.phone_alt_href;
      altPhone.textContent = c.phone_alt_display;
    }

    var wa = document.getElementById("contactWhatsapp");
    wa.href = "https://wa.me/" + c.whatsapp_number;

    var email = document.getElementById("contactEmail");
    email.href = "mailto:" + c.email;
    email.textContent = c.email;

    var addr = document.getElementById("contactAddress");
    addr.href = c.google_maps_url;
    addr.textContent = c.address.street + ", " + c.address.zip_city;

    document.getElementById("year").textContent = new Date().getFullYear();
  }

  /* ---------------------------------------------------------------------
     Cookie-Consent + Google Ads/Analytics (erst nach Zustimmung)
     --------------------------------------------------------------------- */
  function loadTrackingScripts() {
    if (window.__mgbTrackingLoaded || !state.config) return;
    var c = state.config;
    if (!c.google_analytics_id || c.google_analytics_id.indexOf("XXXX") !== -1) return; // Platzhalter-ID: noch nicht scharf schalten

    window.__mgbTrackingLoaded = true;
    var script = document.createElement("script");
    script.async = true;
    script.src = "https://www.googletagmanager.com/gtag/js?id=" + c.google_analytics_id;
    document.head.appendChild(script);

    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", c.google_analytics_id);
    if (c.google_ads_conversion_id && c.google_ads_conversion_id.indexOf("XXXX") === -1) {
      window.gtag("config", c.google_ads_conversion_id);
    }
  }

  function fireConversion(kind) {
    if (localStorage.getItem(CONSENT_KEY) !== "all") return;
    if (typeof window.gtag !== "function" || !state.config) return;
    var c = state.config;
    var label = kind === "booking" ? c.google_ads_label_booking : c.google_ads_label_call;
    if (!label || label.indexOf("XXXX") !== -1 || !c.google_ads_conversion_id || c.google_ads_conversion_id.indexOf("XXXX") !== -1) return;
    window.gtag("event", "conversion", { send_to: c.google_ads_conversion_id + "/" + label });
  }

  function initConsent() {
    var banner = document.getElementById("cookieBanner");
    var stored = localStorage.getItem(CONSENT_KEY);

    if (stored === "all") {
      loadTrackingScripts();
    } else if (stored !== "necessary") {
      banner.hidden = false;
    }

    document.getElementById("cookieAcceptAll").addEventListener("click", function () {
      localStorage.setItem(CONSENT_KEY, "all");
      banner.hidden = true;
      loadTrackingScripts();
    });
    document.getElementById("cookieNecessary").addEventListener("click", function () {
      localStorage.setItem(CONSENT_KEY, "necessary");
      banner.hidden = true;
    });

    document.querySelectorAll('[data-track="booking_click"]').forEach(function (el) {
      el.addEventListener("click", function () { fireConversion("booking"); });
    });
    document.querySelectorAll('[data-track="call_click"]').forEach(function (el) {
      el.addEventListener("click", function () { fireConversion("call"); });
    });
  }

  /* ---------------------------------------------------------------------
     Navigation
     --------------------------------------------------------------------- */
  function initNav() {
    var toggle = document.getElementById("navToggle");
    var nav = document.getElementById("mainNav");
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        nav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      });
    });

    document.querySelectorAll(".lang-switch button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.lang = btn.getAttribute("data-lang");
        localStorage.setItem(LANG_KEY, state.lang);
        renderAll();
      });
    });
  }

  /* ---------------------------------------------------------------------
     Alles neu rendern (bei Sprachwechsel)
     --------------------------------------------------------------------- */
  function renderAll() {
    applyStaticTranslations();
    renderHighlights();
    renderPriceTable();
    renderFAQ();
    renderTournaments();
    renderReviews();
    renderGallery();
    renderTrackman();
  }

  /* ---------------------------------------------------------------------
     Start
     --------------------------------------------------------------------- */
  Promise.all([
    fetchJSON("content/i18n.json"),
    fetchJSON("content/config.json"),
    fetchJSON("content/reviews.json"),
    fetchJSON("content/gallery.json"),
    fetchJSON("content/trackman.json"),
    fetchJSON("content/tournaments.json")
  ]).then(function (results) {
    state.i18n = results[0];
    state.config = results[1];
    state.reviews = results[2];
    state.gallery = results[3];
    state.trackman = results[4];
    state.tournaments = results[5];

    initNav();
    applyConfig();
    renderAll();
    initConsent();
  }).catch(function (err) {
    console.error("Majors Golfbox: Inhalte konnten nicht geladen werden.", err);
  });
})();
