const PAYLOAD = JSON.parse(document.getElementById("payload").textContent);
const ZONE_DATA = PAYLOAD.zone_data;
const I18N = PAYLOAD.i18n || {};
let LAYERS = PAYLOAD.layers;
const TRAVEL_FROM = PAYLOAD.travel_from || "Mongbwalu";
// Fixed epicentre reference for the info box's "Distance from ..." rows. This is
// deliberately independent of the interactive selection / travel-layer origin:
// the info box always reports the selected zone's distance from the epicentre,
// not from itself.
const DISTANCE_ORIGIN_NOM = PAYLOAD.matrix_default_origin || TRAVEL_FROM;
const MATRICES = PAYLOAD.matrices || {};
const MATRIX_INDEX = {};
(function buildMatrixIndex() {
  (MATRICES.zones || []).forEach(function(nom, i) { MATRIX_INDEX[nom] = i; });
})();
let matrixOriginNom = null;         // set only via the focused zone (setMapSelection)
const FLOW_CATALOGS = PAYLOAD.flow_catalogs || {};
const IMPORT_FORCE_PAIRWISE = PAYLOAD.import_force_pairwise || null;
const FLOW_ARC_LAYER = PAYLOAD.flow_arc_layer || null;
let flowHubNom = null;              // set only via the focused zone (setMapSelection)
let flowHubUserSelected = false;
let mapSelectedNom = null;          // the single "focused zone" for the snapshot view
let flowArcStats = null;
let activeView = "map";
// Declared up here, far from the context-view code that owns it, because
// applyStaticI18n() reads it and the zone-search controller calls that during
// module init -- leaving the declaration next to its users put it in the
// temporal dead zone at that point and threw on every page load.
let contextSelectedNom = null;
// Assigned by wirePanelToggles() far below; lets the zone search open a
// collapsed detail panel on narrow screens without duplicating
// setCollapsed()'s glyph handling. Declared up here rather than beside that
// IIFE so the binding exists before any earlier code can reach it -- the same
// precaution contextSelectedNom above needed.
let expandPanel = function() {};
// Genomic tab (see genomic.js): the shared engine exposes only GENERIC, tip-
// agnostic map hooks. `genomicMapHooks` is assigned once the map/layers exist
// (below) and drives zone-level selection subscribe/emit + zone highlighting;
// `genomicHighlightNoms` is the zone set the coordinator has asked us to outline
// (re-applied by styleFn/restyleZonesForActiveView so it survives zoom).
let genomicMapHooks = null;
let genomicHighlightNoms = [];
// True while the map is panning/zooming. Hover decoration (zone tooltip, epi
// float, trends province hover) is suppressed while this is set: during a move
// the browser keeps firing mouseover as zones slide under the cursor, and any
// decoration opened then would be stranded after the move (see the movestart/
// moveend handlers by geoLayer).
let mapMoving = false;
const MATRIX_ORIGIN_FILL = "#5b9bd5";
const FLOW_OUT_COLOR = "#b23b2e";
const FLOW_IN_COLOR = "#5b86b3";
const FLOW_MUTED_FILL = "#e8e4dc";
const EPICENTER_NOMS = new Set(PAYLOAD.epicenter_noms || []);
const EPICENTER_FILL = PAYLOAD.epicenter_fill || "#9b7d4e";
let currentLang = (function resolveLang() {
  const stored = localStorage.getItem("bdbv-dashboard-lang");
  if (stored && I18N.strings && I18N.strings[stored]) return stored;
  const nav = (navigator.language || "").slice(0, 2).toLowerCase();
  if (nav === "fr" && I18N.strings && I18N.strings.fr) return "fr";
  return I18N.default || "en";
})();

function t(path) {
  const parts = String(path).split(".");
  let node = (I18N.strings && I18N.strings[currentLang]) || (I18N.strings && I18N.strings.en) || {};
  for (let i = 0; i < parts.length; i++) {
    if (node == null || typeof node !== "object") return path;
    node = node[parts[i]];
  }
  return node != null ? node : path;
}

function tf(path, vars) {
  let s = String(t(path));
  if (vars) {
    Object.keys(vars).forEach(function(k) {
      s = s.split("{" + k + "}").join(String(vars[k]));
    });
  }
  return s;
}

function localeTag() {
  return currentLang === "fr" ? "fr-FR" : "en-US";
}

function fmtLocale(v) {
  return (v == null ? 0 : v).toLocaleString(localeTag());
}

function trackerCaveats() {
  const byLang = (I18N.tracker_caveats || {})[currentLang];
  if (byLang && byLang.length) return byLang;
  return PAYLOAD.tracker_caveats || [];
}

function layerEpicenterHighlight(layer) {
  return !!(layer && layer.epicenter_highlight);
}
function layerUsesMatrix(layer) {
  return !!(layer && layer.matrix_id);
}
function layerUsesFlowArcs(layer) {
  return !!(layer && layer.viz === "flow_arcs");
}
function flowArcsOverlayActive() {
  if (!FLOW_ARC_LAYER) return false;
  if (activeView === "map") {
    const box = document.getElementById("show-flow-arcs");
    return !!(box && box.checked);
  }
  // Epidemiological trends: same curved Flowminder arcs as snapshot, only while a zone is selected.
  if (activeView === "epi-trends") {
    return !!epiSelectedNom;
  }
  return false;
}
function flowArcLayerDef() {
  return FLOW_ARC_LAYER;
}
function layerOriginHighlight(layer) {
  return !!(layer && layer.origin_highlight);
}
function flowCatalogForLayer(layer) {
  if (!layer || !layer.flow_catalog) return null;
  return FLOW_CATALOGS[layer.flow_catalog] || null;
}
function layerEpicenterNoms(layer) {
  if (layer && layer.epicenter_noms && layer.epicenter_noms.length) {
    return new Set(layer.epicenter_noms);
  }
  return EPICENTER_NOMS;
}
function isEpicenterZone(ref, layer) {
  return layerEpicenterHighlight(layer) && layerEpicenterNoms(layer).has(ref);
}
function isHubZone(ref, layer) {
  if (layerUsesMatrix(layer) && layerOriginHighlight(layer)) {
    return !!(matrixOriginNom && ref === matrixOriginNom);
  }
  return false;
}
function isMatrixOriginZone(ref, layer) {
  return isHubZone(ref, layer);
}
function hubDisplayName(nom) {
  return zoneDisplayName(nom) || TRAVEL_FROM;
}
function matrixOriginDisplayName() {
  return matrixOriginNom ? hubDisplayName(matrixOriginNom) : "—";
}
function flowHubDisplayName() {
  return hubDisplayName(flowHubNom);
}
function matrixValue(matrixId, originNom, destNom, scaleOverride) {
  const ds = MATRICES.datasets && MATRICES.datasets[matrixId];
  if (!ds || !ds.values) return null;
  const oi = MATRIX_INDEX[originNom];
  const di = MATRIX_INDEX[destNom];
  if (oi == null || di == null) return null;
  const raw = ds.values[oi][di];
  if (raw == null || Number.isNaN(raw)) return null;
  const scale = scaleOverride != null ? scaleOverride : (ds.scale || 1);
  return raw / scale;
}
function applyMatrixOriginToLayers() {
  const origin = matrixOriginDisplayName();
  LAYERS.forEach(function(L) {
    if (!L.label_template) return;
    L.label = L.label_template.split("{origin}").join(origin);
  });
}
function flowHubHasData(nom, layer) {
  const cat = flowCatalogForLayer(layer);
  if (!cat || !nom) return false;
  const outs = (cat.out_by_origin && cat.out_by_origin[nom]) || [];
  const ins = (cat.in_by_dest && cat.in_by_dest[nom]) || [];
  return outs.length > 0 || ins.length > 0;
}
function syncFlowHintPanels() {
  const flowLayer = flowArcLayerDef();
  const flowActive = flowArcsOverlayActive();
  const selected = flowActive && flowHubUserSelected;
  const noData = selected && !flowHubHasData(flowHubNom, flowLayer);
  document.body.classList.toggle("flow-hub-selected", selected);
  document.body.classList.toggle("flow-hub-no-data", noData);
  const emptyHint = document.getElementById("flow-empty-hint");
  if (emptyHint) {
    emptyHint.textContent = noData
      ? tf("ui.hints.flow_no_data", {zone: flowHubDisplayName()})
      : t("ui.hints.flow_no_data");
  }
}
function syncMatrixUi() {
  const layer = getLayer(layerSelect.value);
  const travelActive = !!(layer && layerUsesMatrix(layer) && activeView === "map");
  const flowActive = flowArcsOverlayActive();
  document.body.classList.toggle("matrix-layer-active", travelActive);
  document.body.classList.toggle("flow-layer-active", flowActive);
  if (!flowActive) {
    document.body.classList.remove("flow-hub-selected", "flow-hub-no-data");
  }
  syncFlowHintPanels();
  if (layer && (layerUsesMatrix(layer) || flowActive)) {
    updateLayerMeta(layer);
    updateLegend(layer);
  }
}
function featureByNom(nom) {
  if (!nom) return null;
  const feats = (PAYLOAD.geometry && PAYLOAD.geometry.features) || [];
  for (let i = 0; i < feats.length; i++) {
    if (feats[i].properties && feats[i].properties.nom === nom) return feats[i];
  }
  return null;
}

// One derived read of "what is selected right now". The five per-view
// selection variables stay where they are -- merging them would touch every
// view's logic -- but this is the only function that answers the question, so
// the five tabs paint selection through one path instead of five.
//
// That is a convention, not an encapsulation: nothing stops a new view from
// painting its own highlight inline, and a sixth activeView added without a
// branch here falls through to [] silently rather than failing. Keep new views
// in step by adding them here.
function currentSelectedNoms() {
  if (activeView === "map") return mapSelectedNom ? [mapSelectedNom] : [];
  if (activeView === "epi-trends") return epiSelectedNom ? [epiSelectedNom] : [];
  if (activeView === "context") return contextSelectedNom ? [contextSelectedNom] : [];
  if (activeView === "genomic-epidemiology") return genomicHighlightNoms.slice();
  if (activeView === "trends") {
    // Province scope selects a province, not a zone; that ring is drawn by
    // applyProvinceOutlineStyles() into the province-selection pane.
    if (trendsScope === "health_zone" && trendsSelectedKey) return [trendsSelectedKey];
    return [];
  }
  return [];
}

function refreshZoneSelection() {
  zoneRings.set(currentSelectedNoms().map(featureByNom).filter(Boolean));
}

// The snapshot view's single focused zone. Drives the info box, the persistent
// highlight, and — where the active layer cares — the flow-arc origin and the
// matrix travel origin. Passing the already-focused nom (or null) clears focus.
function setMapSelection(nom) {
  const next = (nom && nom === mapSelectedNom) ? null : (nom || null);
  mapSelectedNom = next;
  flowHubNom = next;
  flowHubUserSelected = !!next;
  matrixOriginNom = next;
  applyMatrixOriginToLayers();
  rebuildLayerSelect();
  recompute();
  syncMatrixUi();
  renderMapInfoBox();
  refreshZoneSelection();
}

function renderMapInfoBox() {
  const el = document.getElementById("info-body");
  if (!el) return;
  const feat = featureByNom(mapSelectedNom);
  if (!feat) {
    el.className = "info-empty";
    el.textContent = t("ui.hover_zone");   // "Select a health zone."
    return;
  }
  el.className = "";
  el.innerHTML = infoHTML(feat);
}

function applyStaticI18n() {
  document.documentElement.lang = currentLang;
  document.title = t("meta.title");
  const heading = document.getElementById("page-heading");
  if (heading) heading.textContent = t("meta.heading");
  document.querySelectorAll("[data-i18n]").forEach(function(el) {
    const key = el.getAttribute("data-i18n");
    const val = t(key);
    if (el.id === "info-body" && !el.classList.contains("info-empty")) return;
    if (el.id === "context-body" && contextSelectedNom) return;
    el.textContent = val;
  });
  document.querySelectorAll("[data-i18n-aria]").forEach(function(el) {
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria")));
  });
  document.querySelectorAll("[data-i18n-title]").forEach(function(el) {
    el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(function(el) {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-placeholder")));
  });
  document.querySelectorAll(".lang-btn").forEach(function(btn) {
    const on = btn.dataset.lang === currentLang;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  const methodsModal = document.getElementById("methods-modal");
  const termsModal = document.getElementById("terms-modal");
  if (methodsModal) methodsModal.setAttribute("aria-label", t("ui.methods_modal_title"));
  if (termsModal) termsModal.setAttribute("aria-label", t("ui.terms_modal_title"));
}

function updateLegalContent() {
  const methods = (I18N.methods_html || {})[currentLang] || PAYLOAD.methods_html || "";
  const terms = (I18N.terms_html || {})[currentLang] || PAYLOAD.terms_html || "";
  const updated = ((I18N.terms_updated || {})[currentLang]) || PAYLOAD.terms_updated || "";
  document.getElementById("methods-content").innerHTML =
    methods || "<p style='color:#888'>" + t("ui.methods_missing") + "</p>";
  document.getElementById("terms-content").innerHTML =
    terms || "<p style='color:#888'>" + t("ui.terms_missing") + "</p>";
  const termsUpdatedEl = document.getElementById("terms-updated");
  if (termsUpdatedEl) {
    termsUpdatedEl.textContent = updated ? (t("ui.terms_updated") + " " + updated) : "";
  }
}

function formatBuildTimestamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const locale = currentLang === "fr" ? "fr-FR" : "en-GB";
  const datePart = d.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const timePart = d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });
  return datePart + ", " + timePart + " UTC";
}

// Language switch: two plain links, each written in its own language, so
// neither label needs translating. Rendered here (rather than sitting in the
// static markup like the narrow-screen copy in #header-narrow-row) because
// #title-sub's innerHTML is rebuilt on every switch -- which is also why the
// click handler is delegated rather than bound per node.
const LANG_LABELS = { en: "English", fr: "Français" };
function langSwitchHtml() {
  const langs = Object.keys(LANG_LABELS).filter(function(l) {
    return I18N.strings && I18N.strings[l];
  });
  if (langs.length < 2) return "";
  return "<span class='lang-switch' role='group' data-i18n-aria='ui.aria.language' aria-label='" +
    t("ui.aria.language") + "'>" +
    langs.map(function(lang) {
      const on = lang === currentLang;
      return "<button type='button' class='lang-btn" + (on ? " active" : "") + "' data-lang='" + lang +
        "' aria-pressed='" + (on ? "true" : "false") + "'>" + LANG_LABELS[lang] + "</button>";
    }).join("<span class='lang-sep' aria-hidden='true'>|</span>") +
    "</span>";
}

function buildTitleSub() {
  const linkStyle = "color:#9fcdfb;text-decoration:underline";
  // Latest SitRep link + "built on" tag -- shown inline in #title-sub on
  // wide screens; on narrow screens (see @media max-width:700px) this moves
  // into the info icon's popup instead, since #title-sub itself is hidden
  // there in favor of #header-narrow-row.
  let sitrepHtml =
    t("ui.title_sub.latest") + " " +
    "<a href='" + (PAYLOAD.insp_sitrep_url || "https://insp.cd/") + "' target='_blank' rel='noopener' " +
    "style='" + linkStyle + "'>" + t("ui.title_sub.insp_sitrep") + "</a>" +
    " - " + PAYLOAD.asof;
  const db = PAYLOAD.data_build;
  if (db && db.url && db.tag) {
    sitrepHtml +=
      " · " + t("ui.title_sub.built_on") + " <a href='" + db.url + "' target='_blank' rel='noopener' style='" + linkStyle + "'>" +
       db.tag + "</a>";
  }
  // "Dashboard updated" line -- shown on every screen size: inline (as the
  // second line of #title-sub) when wide, or standalone next to the info
  // icon in #header-narrow-row when narrow.
  let updatedHtml = "";
  const builtAtFormatted = formatBuildTimestamp(PAYLOAD.dashboard_built_at);
  if (builtAtFormatted) {
    updatedHtml = t("ui.title_sub.dashboard_updated") + " " + builtAtFormatted;
  }

  document.getElementById("title-sub").innerHTML =
    sitrepHtml + "<br/>" + (updatedHtml ? updatedHtml + " · " : "") + langSwitchHtml();

  const updatedLineEl = document.getElementById("header-updated-line");
  if (updatedLineEl) updatedLineEl.innerHTML = updatedHtml;
  const popupBodyEl = document.getElementById("header-info-popup-body");
  if (popupBodyEl) popupBodyEl.innerHTML = sitrepHtml;
}

function buildTracker() {
  const totals = PAYLOAD.totals || {};
  const tracker = document.getElementById("tracker");
  const caveats = trackerCaveats();
  const caveatByMetric = {};
  caveats.forEach(function(c) { caveatByMetric[c.metric] = c.mark; });
  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function countWithMark(v, metric) {
    const base = fmtLocale(v);
    const mark = caveatByMetric[metric];
    return mark
      ? base + "<span class='caveat-mark' aria-hidden='true'>" + esc(mark) + "</span>"
      : base;
  }
  // Suspected counts hang under the confirmed figure they qualify, so they can
  // only be read against the right number. A zero renders nothing at all --
  // "0 suspected" reads as a finding rather than the absence of one.
  function qualifier(v, metric) {
    const n = v || 0;
    if (!n) return "";
    const key = n === 1 ? "ui.tracker.suspected_one" : "ui.tracker.suspected_other";
    const num = "<span class='qnum'>" + countWithMark(n, metric) + "</span>";
    return "<div class='qual'>" + tf(key, { n: num }) + "</div>";
  }
  const tr = t("ui.tracker");
  const footnotesHTML = caveats.length
    ? "<div class='tracker-footnotes'>" +
        caveats.map(function(c) {
          return "<p><span class='mark'>" + esc(c.mark) + "</span>" + esc(c.warning) + "</p>";
        }).join("") +
      "</div>"
    : "";
  // PAYLOAD.asof can legitimately be empty: ASOF_FALLBACK is "" and
  // detect_asof() returns it when neither the sitrep CSVs nor the build
  // GeoJSON yield a date. Fall back to the undated wording rather than
  // rendering "cumulative to " with nothing after it.
  const asof = PAYLOAD.asof || "";
  const eyebrow = asof
    ? tf("ui.tracker.eyebrow", { date: esc(asof) })
    : t("ui.tracker.eyebrow_nodate");
  tracker.innerHTML =
    "<div class='stats-block'>" +
      "<div class='global-title'>" + eyebrow + "</div>" +
      "<div class='global-row'>" +
        "<div class='global-cell cases'>" +
          "<div class='num'>" + countWithMark(totals.global_confirmed_cases, "confirmed_cases") + "</div>" +
          "<div class='sub'>" + tr.cases + "</div>" +
          qualifier(totals.global_suspected_cases, "suspected_cases") +
        "</div>" +
        "<div class='global-cell deaths'>" +
          "<div class='num'>" + countWithMark(totals.global_confirmed_deaths, "confirmed_deaths") + "</div>" +
          "<div class='sub'>" + tr.deaths + "</div>" +
          qualifier(totals.global_suspected_deaths, "suspected_deaths") +
        "</div>" +
        "<div class='global-cell recovered'>" +
          "<div class='num'>" + fmtLocale(totals.global_recovered_cases) + "</div>" +
          "<div class='sub'>" + tr.recovered + "</div>" +
        "</div>" +
      "</div>" +
    "</div>" +
    footnotesHTML;
}

function buildModeledEstimateNote() {
  const root = document.getElementById("imperial-model-estimates");
  if (!root) return;
  root.innerHTML = "";
  root.style.display = "none";
}

// --- narrow-header info popup (see #header-narrow-row in chrome.py) ---
// Hover opens it on desktop via CSS alone (:hover/:focus-within); this just
// adds a click/tap toggle for touch devices, where hover doesn't apply, plus
// close-on-outside-click and Escape.
(function wireHeaderInfoPopup() {
  const row = document.getElementById("header-narrow-row");
  const btn = document.getElementById("header-info-btn");
  const popup = document.getElementById("header-info-popup");
  if (!row || !btn || !popup) return;
  function setOpen(open) {
    row.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    popup.setAttribute("aria-hidden", open ? "false" : "true");
  }
  btn.addEventListener("click", function(e) {
    e.stopPropagation();
    setOpen(!row.classList.contains("open"));
  });
  document.addEventListener("click", function(e) {
    if (!e.target.closest("#header-narrow-row")) setOpen(false);
  });
  row.addEventListener("keydown", function(e) {
    if (e.key === "Escape") {
      setOpen(false);
      btn.blur();
    }
  });
  // Methods/Terms open a full-screen modal over everything, but tidy up by
  // closing the popup itself rather than leaving it open underneath.
  const popupLinks = document.getElementById("header-info-popup-links");
  if (popupLinks) {
    popupLinks.addEventListener("click", function() { setOpen(false); });
  }
})();

// --- partners strip ---
// The strip carries no bounding box under the theme, so the gaps are what
// group the logos: .partner-group holds one affiliation (tight gap), #partners
// spaces the groups apart (wide gap). Each logo also carries its own scale
// factor on --partner-h -- see PARTNER_GROUPS/PARTNER_SCALE in
// common/data_sources.py for both, and the design spec for why.
(function buildPartners() {
  const partners = PAYLOAD.partners || [];
  const root = document.getElementById("partners");
  if (!partners.length || !root) { if (root) root.style.display="none"; return; }
  let html = "";
  let openGroup = null;
  partners.forEach(function(p) {
    const group = p.group || 0;
    if (group !== openGroup) {
      if (openGroup !== null) html += "</span>";
      html += "<span class='partner-group'>";
      openGroup = group;
    }
    const scale = p.scale || 1;
    const img = "<img src='" + p.data_uri + "' alt='" + p.alt + "' title='" + p.alt + "' " +
      "style='height:calc(var(--partner-h) * " + scale + ")' />";
    html += p.href
      ? "<a href='" + p.href + "' target='_blank' rel='noopener'>" + img + "</a>"
      : img;
  });
  if (openGroup !== null) html += "</span>";
  root.innerHTML = html;
})();

const layerSelect = document.getElementById("layer-select");
const layerMeta = document.getElementById("layer-meta");

function rebuildLayerSelect() {
  const selected = layerSelect.value;
  layerSelect.innerHTML = "";
  const groups = {};
  for (const L of LAYERS) {
    if (!groups[L.group]) {
      const og = document.createElement("optgroup");
      og.label = L.group;
      layerSelect.appendChild(og);
      groups[L.group] = og;
    }
    const o = document.createElement("option");
    o.value = L.id; o.textContent = L.label;
    groups[L.group].appendChild(o);
  }
  if (selected && getLayer(selected)) layerSelect.value = selected;
  else if (LAYERS.length) layerSelect.value = LAYERS[0].id;
}

function setLang(lang) {
  if (!I18N.strings || !I18N.strings[lang]) return;
  currentLang = lang;
  localStorage.setItem("bdbv-dashboard-lang", lang);
  LAYERS = (I18N.layers && I18N.layers[lang]) || PAYLOAD.layers;
  applyStaticI18n();
  rebuildLayerSelect();
  buildTitleSub();
  buildTracker();
  buildModeledEstimateNote();
  updateLegalContent();
  applyMatrixOriginToLayers();
  rebuildLayerSelect();
  recompute();
  syncMatrixUi();
  refreshMarkerTooltips();
  if (activeView === "trends") {
    updateTrendsDateLabel();
    syncTrendsPlayButton();
    renderTrendsPlots();
  } else if (activeView === "context") {
    renderContextPanel(contextSelectedNom);
  } else if (activeView === "epi-trends") {
    updateEpiTitle();
    updateEpiMetaNotes();
    renderEpiLegendBars();
    renderEpiTrendsTable();
  } else {
    // Map view: re-render the focused zone's info box (or the placeholder) in
    // the new language. applyStaticI18n early-returns for a non-empty info box,
    // so this is the path that keeps a selected zone localized.
    renderMapInfoBox();
  }
}

// Delegated, not bound per node: the wide-screen copy of the switch lives
// inside #title-sub, which buildTitleSub() replaces wholesale on every switch,
// so per-node listeners would survive exactly one click.
document.addEventListener("click", function(e) {
  const btn = e.target.closest && e.target.closest(".lang-btn");
  if (btn) setLang(btn.dataset.lang || "en");
});

function getLayer(id) { return LAYERS.find(L => L.id === id); }

// color palettes
const PLASMA = [
  [13,8,135],[75,3,161],[125,3,168],[168,34,150],[203,70,121],
  [229,107,93],[248,148,65],[253,195,40],[240,249,33]];
const REDS = [
  [255,245,235],[254,217,181],[253,173,118],[252,127,73],[239,77,55],
  [205,32,32],[140,17,17]];
// Spatial-risk confirmed-cases ramp: same orange->red identity as REDS, but
// with the near-white low stop lifted so a low-count zone reads as clearly
// orange (not near-white, which was indistinguishable from a near-zero
// invasion-probability zone). Kept separate from the shared REDS palette so
// this only affects the spatial-risk (invasion) map.
const RISK_ORANGES = [
  [253,216,172],[253,173,118],[252,127,73],[239,77,55],
  [205,32,32],[140,17,17]];
// Brand sequential ramp: #f6e3df → #e8b3a6 → #d08163 → #aa4a32 → #7c1d1d
const OUTBREAK = [
  [246,227,223],[232,179,166],[208,129,99],[170,74,50],[124,29,29]];
const VIRIDIS = [
  [68,1,84],[72,40,120],[62,73,137],[49,104,142],[38,130,142],[31,158,137],
  [53,183,121],[109,206,89],[180,222,44],[253,231,37]];
// Darker, subdued purple ramp for invasion probability. The near-white low
// stop was lifted so a near-zero-probability zone reads as clearly lavender
// rather than near-white (which was indistinguishable from a low-count
// confirmed-cases zone on the spatial-risk map).
const PURPLES = [
  [211,196,224],[184,164,201],[150,124,171],[117,90,140],
  [91,68,112],[72,52,90],[55,40,72],[42,30,56]];
const PALETTES = {
  plasma:PLASMA, plasma_r:[...PLASMA].reverse(),
  reds:REDS, outbreak:OUTBREAK, viridis:VIRIDIS, purples:PURPLES,
};

function lerpColor(stops, t) {
  if (t <= 0) return stops[0];
  if (t >= 1) return stops[stops.length - 1];
  const s = t * (stops.length - 1);
  const i = Math.floor(s), f = s - i;
  const a = stops[i], b = stops[i + 1];
  return [a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f, a[2]+(b[2]-a[2])*f];
}
function rgb(c) { return "rgb(" + Math.round(c[0]) + "," + Math.round(c[1]) + "," + Math.round(c[2]) + ")"; }

const PROJ_MASK = PAYLOAD.projection_mask || null;
const PROJ_MASK_LAYERS = new Set((PROJ_MASK && PROJ_MASK.layers) || []);

function valueForZone(ref, zone, layer) {
  if (PROJ_MASK && PROJ_MASK_LAYERS.has(layer.id)) {
    const m = zone[PROJ_MASK.field];
    if (m == null || Number.isNaN(m) || Number(m) < PROJ_MASK.min) return null;
  }
  if (layerUsesMatrix(layer)) {
    return matrixValue(layer.matrix_id, matrixOriginNom, ref, layer.matrix_scale);
  }
  const v = zone[layer.field];
  return (v == null || Number.isNaN(v)) ? null : Number(v);
}

// --- map setup ---
const INITIAL_VIEW = PAYLOAD.initial_view || {lat: -2.5, lon: 22.5, zoom: 5};
// No on-map zoom control: the top-left corner it occupied collided with the
// LAYER panel, and every view either relocates a search box into that corner
// or expects touch users to pinch-zoom. Zoom via wheel/pinch/double-click.
const map = L.map("map", {zoomControl: false}).setView([INITIAL_VIEW.lat, INITIAL_VIEW.lon], INITIAL_VIEW.zoom);
// CARTO's raster basemaps require an API key as of 2026. Without one the tiles
// still render, but under a repeated "API key required" watermark -- a notice,
// not an outage, so a keyless build degrades rather than breaking.
//
// The key is a public client-side credential, not a secret: it is served in
// this file to every visitor by design (the quota is per-key fair use, 5M
// tiles/month, and CARTO's terms only require that the attribution below stays
// visible). It is nonetheless substituted at build time from CARTO_BASEMAP_KEY
// rather than committed here, so it lives in exactly one place and can be
// rotated without a source change. See README "CARTO basemap key".
//
// The placeholder deliberately contains braces so it fails the character test
// below: an unsubstituted build therefore sends no `key` parameter at all
// instead of a literal "". The same test rejects a
// malformed injected value, which is what keeps a stray quote in the
// environment from breaking out of this string literal.
//
// NOTE: CARTO is retiring these raster tiles in favour of vector basemaps
// (light_all -> positron-gl-style). That migration means Leaflet -> MapLibre
// and is tracked separately; the key applies either way.
const CARTO_KEY = "";
const CARTO_TILES = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
  + (/^[A-Za-z0-9_-]+$/.test(CARTO_KEY) ? "?key=" + encodeURIComponent(CARTO_KEY) : "");
L.tileLayer(CARTO_TILES, {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>, &copy; <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: "abcd", maxZoom: 19
}).addTo(map);

// Zone borders read as hairlines at the national default zoom (many small
// zones packed together) and gain presence as you zoom into the outbreak.
// One ramp drives the resting stroke; every other state is a multiple of it,
// so the hierarchy (resting < focus < hover < selected) holds at every zoom.
//
// ramp-min is both the z5 intercept and the clamp floor on purpose: the map
// sets no minZoom, so below z5 the border stops thinning rather than vanishing.
function zoneWeight(zoom) {
  const base = zoneNum("--zone-stroke-weight-base", "1.7");
  const lo = zoneNum("--zone-stroke-ramp-min", "0.6");
  const hi = zoneNum("--zone-stroke-ramp-max", "1.15");
  const slope = zoneNum("--zone-stroke-ramp-slope", "0.1");
  return base * Math.max(lo, Math.min(hi, lo + (zoom - 5) * slope));
}

// themeVar() returns strings; this is the numeric read. The fallback is parsed
// too, so a malformed theme value degrades to the documented default rather
// than to NaN (a NaN weight silently drops the stroke entirely in Leaflet).
//
// Reads a token directly rather than taking a resolved value, so each token
// appears exactly once in the source, with exactly one fallback literal.
// tests/test_zone_state_styling.py treats zoneNum() as a token reader
// alongside themeVar() for that reason.
function zoneNum(name, fallback) {
  const v = parseFloat(themeVar(name, fallback));
  return isFinite(v) ? v : parseFloat(fallback);
}

// Stroke half of a zone's style, by state. Weight is already resolved for the
// current zoom. Callers Object.assign() this onto the fill half, so nothing
// hardcodes a colour or a weight.
//
// "hidden"  -- zone not visible for the active spatial-risk layer
// "failloud" -- active zone with no count; should never happen, must stay loud
// "focus"   -- spatial-risk flow-connected neighbour of the selected zone
// "dim"     -- spatial-risk non-focus zone while something is selected
function zoneStroke(state) {
  const w = zoneWeight(map.getZoom());
  const rest = themeVar("--zone-stroke", "#fdfaf4");
  const restOp = zoneNum("--zone-stroke-opacity", "0.7");
  switch (state) {
    case "hover":
      return {
        color: themeVar("--zone-hover-stroke", "#ffffff"),
        opacity: zoneNum("--zone-hover-stroke-opacity", "0.98"),
        weight: w * zoneNum("--zone-hover-weight-mult", "1.7")
      };
    case "nodata":
      return {
        color: themeVar("--zone-nodata-stroke", "#6b635a"),
        opacity: zoneNum("--zone-nodata-stroke-opacity", "0.45"),
        weight: w * zoneNum("--zone-nodata-weight-mult", "1")
      };
    case "hidden":
      return {
        color: themeVar("--zone-nodata-stroke", "#6b635a"),
        opacity: zoneNum("--zone-nodata-stroke-opacity", "0.45"),
        weight: w * zoneNum("--zone-hidden-weight-mult", "0.7")
      };
    case "failloud":
      return {
        color: themeVar("--zone-failloud-stroke", "#111"),
        opacity: zoneNum("--zone-failloud-stroke-opacity", "1"),
        weight: w * zoneNum("--zone-failloud-weight-mult", "1")
      };
    case "focus":
      return {color: rest, opacity: restOp, weight: w * zoneNum("--zone-focus-weight-mult", "1.35")};
    case "dim":
      return {color: rest, opacity: zoneNum("--zone-dim-stroke-opacity", "0.25"), weight: w};
    // Role markers are the one place opacity is not tokenised. They are the
    // only strokes left at full black, and there is no intent to fade them --
    // a --zone-role-stroke-opacity token would be a knob nobody turns.
    case "epicenter":
      return {
        color: themeVar("--zone-role-stroke", "#111"),
        opacity: 1,
        weight: w * zoneNum("--zone-role-weight-mult-epicenter", "1.35")
      };
    case "origin":
      return {
        color: themeVar("--zone-role-stroke", "#111"),
        opacity: 1,
        weight: w * zoneNum("--zone-role-weight-mult-origin", "1.6")
      };
    default:   // "rest"
      return {color: rest, opacity: restOp, weight: w};
  }
}

map.createPane("flow-arcs");
map.getPane("flow-arcs").style.zIndex = "450";
map.createPane("epi-links");
map.getPane("epi-links").style.zIndex = "455";
const flowArcLayer = L.layerGroup();
const epiLinkLayer = L.layerGroup();

// A selected zone's highlight is drawn OUTSIDE the polygon layer, in its own
// pane. Inside the polygon layer, every hover handler calls bringToFront() on
// the zone under the cursor, so a hovered neighbour's border paints over the
// selected zone's shared edge -- and no amount of re-fronting survives the next
// restyle. A higher pane makes the guarantee structural instead.
//
// The ring is two stacked paths because a single Leaflet path carries one
// stroke: a dark casing underneath, then the amber ring. The casing's visible
// part is the half that sticks out, (casingMult - innerMult) / 2 of the resting
// weight on each side.
function SelectionRing(paneName, zIndex, weights) {
  map.createPane(paneName);
  const pane = map.getPane(paneName);
  pane.style.zIndex = String(zIndex);
  // Clicks must reach the polygon underneath, or click-to-deselect dies the
  // moment a zone is selected.
  pane.style.pointerEvents = "none";
  const group = L.layerGroup().addTo(map);
  let current = [];

  function ring(features, color, opacity, weight) {
    return L.geoJSON({type: "FeatureCollection", features: features}, {
      pane: paneName,
      interactive: false,
      style: function () {
        return {color: color, opacity: opacity, weight: weight, fill: false};
      }
    });
  }

  function draw() {
    group.clearLayers();
    if (!current.length) return;
    // The caller resolves its own weights, so every token is read with literal
    // arguments at the call site. Passing token NAMES in here instead would
    // hide them from tests/test_zone_state_styling.py, whose regex only sees
    // literal zoneNum()/themeVar() calls -- the guard would silently stop
    // covering exactly the tokens that draw the selection.
    const w = weights();
    group.addLayer(ring(
      current,
      themeVar("--zone-selected-casing", "#5c3a12"),
      zoneNum("--zone-selected-casing-opacity", "0.9"),
      w.casing
    ));
    group.addLayer(ring(
      current,
      themeVar("--zone-selected-stroke", "#ffae42"),
      zoneNum("--zone-selected-stroke-opacity", "1"),
      w.inner
    ));
  }

  return {
    // Takes GeoJSON features, not keys: one factory serves both the zone (nom)
    // and province (province name) key spaces, and each caller already knows
    // how to resolve its own keys.
    set: function (features) { current = (features || []).filter(Boolean); draw(); },
    clear: function () { current = []; draw(); },
    redraw: draw
  };
}

// 445: above the zone polygons (overlayPane, 400), below the flow arcs (450)
// and epi-links (455). Selecting a zone on the spatial-risk tab is what draws
// its arcs, so a ring above them would occlude every arc terminus at the
// selected zone. Markers (600) and tooltips (650) still draw over the ring --
// requirement 4 is a guarantee against zones, not against everything.
const zoneRings = SelectionRing("zone-selection", 445, function () {
  const base = zoneWeight(map.getZoom());
  return {
    inner: base * zoneNum("--zone-selected-weight-mult", "2.2"),
    casing: base * zoneNum("--zone-selected-casing-mult", "3.6")
  };
});

function zoneCentroid(nom) {
  const z = ZONE_DATA[nom];
  if (!z || z.centroid_lat == null || z.centroid_lon == null) return null;
  if (!isFinite(z.centroid_lat) || !isFinite(z.centroid_lon)) return null;
  return [z.centroid_lat, z.centroid_lon];
}

function clearFlowArcs() {
  flowArcLayer.clearLayers();
  if (map.hasLayer(flowArcLayer)) map.removeLayer(flowArcLayer);
  flowArcStats = null;
}

function quadraticBezierPoints(lat1, lon1, lat2, lon2, bend) {
  const steps = 24;
  const midLat = (lat1 + lat2) / 2;
  const midLon = (lon1 + lon2) / 2;
  const dlat = lat2 - lat1;
  const dlon = lon2 - lon1;
  const len = Math.sqrt(dlat * dlat + dlon * dlon) || 1;
  const sign = bend >= 0 ? 1 : -1;
  const offset = 0.18 * len * sign;
  // Counterclockwise bow from (lat1,lon1) toward (lat2,lon2) in the map plane.
  const cpLat = midLat + (dlon / len) * offset;
  const cpLon = midLon + (-dlat / len) * offset;
  const pts = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const u = 1 - t;
    const lat = u * u * lat1 + 2 * u * t * cpLat + t * t * lat2;
    const lon = u * u * lon1 + 2 * u * t * cpLon + t * t * lon2;
    pts.push([lat, lon]);
  }
  return pts;
}

function flowArcWeight(count, maxCount) {
  if (!maxCount || maxCount <= 0) return 1.5;
  return 1 + 4 * Math.sqrt(count / maxCount);
}

function flowArcWeightNormalized(frac) {
  if (frac == null || !isFinite(frac) || frac <= 0) return 1.2;
  return 1 + 4 * Math.max(0, Math.min(1, frac));
}

function zoneConfirmedCases(nom) {
  const z = ZONE_DATA[nom];
  if (!z) return 0;
  const c = Number(z.effective_confirmed_cases);
  return (isFinite(c) && c > 0) ? c : 0;
}

function importationPressure(sourceNom, movers) {
  // Spatial risk: Flowminder inflow edges weighted by confirmed cases in the
  // external (origin) health zone. No movement → no pressure.
  const n = Number(movers);
  if (!isFinite(n) || n <= 0) return 0;
  return zoneConfirmedCases(sourceNom);
}

// Legend icon for a flow arrow: a horizontal line with a chevron in the
// middle, matching the on-map arrows drawn by addFlowWingMarker() (same
// two-stroke chevron, so the legend reads as the same symbol). Used by the
// snapshot legend (updateLegend) and mirrored in the static Spatial Risk
// legend markup in common/chrome.py.
function flowArrowSwatch(color) {
  return "<span class='arrow-swatch'>" +
    "<svg xmlns='http://www.w3.org/2000/svg' width='26' height='12' viewBox='0 0 26 12'>" +
    "<line x1='1' y1='6' x2='25' y2='6' stroke='" + color + "' stroke-width='1.6' stroke-linecap='round'/>" +
    "<line x1='10' y1='2' x2='16' y2='6' stroke='" + color + "' stroke-width='1.6' stroke-linecap='round'/>" +
    "<line x1='10' y1='10' x2='16' y2='6' stroke='" + color + "' stroke-width='1.6' stroke-linecap='round'/>" +
    "</svg></span>";
}

function addFlowWingMarker(pts, color, opts) {
  opts = opts || {};
  if (!pts || pts.length < 2) return;
  // Place near the destination for inward (import) arrows so they read as
  // pointing into the selected health zone; otherwise mid-arc.
  const frac = opts.nearEnd ? 0.78 : 0.5;
  const midIdx = Math.max(1, Math.min(pts.length - 2, Math.floor((pts.length - 1) * frac)));
  const mid = pts[midIdx];
  const prev = pts[Math.max(0, midIdx - 1)];
  const next = pts[Math.min(pts.length - 1, midIdx + 1)];
  // Screen-space bearing so the chevron follows the drawn path (toward hub
  // for inflow polylines that run origin → selected zone).
  const p0 = map.latLngToLayerPoint(L.latLng(prev[0], prev[1]));
  const p1 = map.latLngToLayerPoint(L.latLng(next[0], next[1]));
  const angle = Math.atan2(p1.y - p0.y, p1.x - p0.x) * 180 / Math.PI;
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" ' +
    'style="transform:rotate(' + angle + 'deg)">' +
    '<line x1="2" y1="3.5" x2="11" y2="8" stroke="' + color + '" stroke-width="1.7" stroke-linecap="round"/>' +
    '<line x1="2" y1="12.5" x2="11" y2="8" stroke="' + color + '" stroke-width="1.7" stroke-linecap="round"/>' +
    '</svg>';
  L.marker([mid[0], mid[1]], {
    icon: L.divIcon({
      className: "flow-wing-icon",
      html: svg,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    }),
    interactive: false,
    pane: "flow-arcs",
  }).addTo(flowArcLayer);
}

function renderFlowArcs(hubNom, layer) {
  clearFlowArcs();
  const cat = flowCatalogForLayer(layer);
  if (!cat || !hubNom) return;
  const hub = zoneCentroid(hubNom);
  if (!hub) return;

  const outs = (cat.out_by_origin && cat.out_by_origin[hubNom]) || [];
  const ins = (cat.in_by_dest && cat.in_by_dest[hubNom]) || [];
  const outSorted = outs.slice().sort(function(a, b) { return b[1] - a[1]; });
  const inSorted = ins.slice().sort(function(a, b) { return b[1] - a[1]; });
  // Spatial risk: only inflows into the selected zone (drawn in red),
  // weighted by confirmed cases in each external origin zone.
  const useImportPressure = activeView === "epi-trends";

  let maxMetric = 0;
  if (useImportPressure) {
    inSorted.forEach(function(p) {
      const m = importationPressure(p[0], p[1]);
      if (m > maxMetric) maxMetric = m;
    });
  } else {
    outSorted.concat(inSorted).forEach(function(p) {
      const m = Number(p[1]) || 0;
      if (m > maxMetric) maxMetric = m;
    });
    if (maxMetric < 1) maxMetric = 1;
  }

  if (!useImportPressure) {
    outSorted.forEach(function(pair) {
      const dest = pair[0];
      const count = pair[1];
      const end = zoneCentroid(dest);
      if (!end) return;
      const pts = quadraticBezierPoints(hub[0], hub[1], end[0], end[1], 1);
      const line = L.polyline(pts, {
        color: FLOW_OUT_COLOR,
        weight: flowArcWeight(count, maxMetric),
        opacity: 0.82,
        pane: "flow-arcs",
        // Arrows are annotations of the selected zone, not controls. Keep the
        // hover tooltip but stop clicks bubbling to the map's click handler,
        // which would otherwise clear the selection (and the arrows with it).
        bubblingMouseEvents: false,
      });
      line.bindTooltip(tf("ui.flow_arc_tooltip", {
        from: flowHubDisplayName(),
        to: hubDisplayName(dest),
        count: fmt(count),
      }), {direction: "top", sticky: true});
      line.on("click", forwardArcClickToZone);
      line.addTo(flowArcLayer);
      addFlowWingMarker(pts, FLOW_OUT_COLOR);
    });
  }

  const pairwiseEdges = (useImportPressure && IMPORT_FORCE_PAIRWISE
    && IMPORT_FORCE_PAIRWISE.in_by_dest
    && IMPORT_FORCE_PAIRWISE.in_by_dest[hubNom]) || null;
  if (pairwiseEdges) {
    // Only origins with a centroid are drawable; compute the per-zone max foi
    // over THOSE, so the widest *visible* arrow reaches full width even if a
    // centroid-less origin had a higher foi.
    const drawable = pairwiseEdges
      .map(function(e) {
        return {origin: e[0], foi: e[1], share: e[2], start: zoneCentroid(e[0])};
      })
      .filter(function(e) { return !!e.start; });
    let maxFoi = 0;
    drawable.forEach(function(e) { if (e.foi > maxFoi) maxFoi = e.foi; });
    drawable.forEach(function(e) {
      const pts = quadraticBezierPoints(e.start[0], e.start[1], hub[0], hub[1], 1);
      const line = L.polyline(pts, {
        color: FLOW_OUT_COLOR,
        weight: flowArcWeight(e.foi, maxFoi),      // 1 + 4*sqrt(foi/maxFoi)
        opacity: 0.82,
        pane: "flow-arcs",
        bubblingMouseEvents: false, // see note on the outflow arc above
      });
      line.bindTooltip(tf("ui.import_force_tooltip", {
        from: hubDisplayName(e.origin),
        to: flowHubDisplayName(),
        foi: e.foi.toPrecision(2),
        share: (e.share != null ? (e.share * 100).toFixed(1) + "%" : "—"),
      }), {direction: "top", sticky: true});
      line.on("click", forwardArcClickToZone);
      line.addTo(flowArcLayer);
      addFlowWingMarker(pts, FLOW_OUT_COLOR, {nearEnd: true});
    });
    flowArcStats = {
      outTotal: outs.length, outShown: 0,
      inTotal: drawable.length, inShown: drawable.length,
      metric: "import_force", maxMetric: maxFoi,
    };
    flowArcLayer.addTo(map);
    return;
  }

  inSorted.forEach(function(pair) {
    const origin = pair[0];
    const count = pair[1];
    const start = zoneCentroid(origin);
    if (!start) return;
    const cases = zoneConfirmedCases(origin);
    const pressure = useImportPressure ? importationPressure(origin, count) : count;
    const weight = useImportPressure
      ? flowArcWeightNormalized(maxMetric > 0 ? pressure / maxMetric : 0)
      : flowArcWeight(count, maxMetric);
    const color = useImportPressure ? FLOW_OUT_COLOR : FLOW_IN_COLOR;
    // Always draw origin → selected hub so chevrons point inward.
    const pts = quadraticBezierPoints(start[0], start[1], hub[0], hub[1], 1);
    const line = L.polyline(pts, {
      color: color,
      weight: weight,
      opacity: 0.82,
      pane: "flow-arcs",
      bubblingMouseEvents: false, // see note on the outflow arc above
    });
    if (useImportPressure) {
      line.bindTooltip(tf("ui.importation_pressure_tooltip", {
        from: hubDisplayName(origin),
        to: flowHubDisplayName(),
        pressure: (maxMetric > 0 ? pressure / maxMetric : 0).toFixed(3),
        cases: fmt(cases),
        count: fmt(count),
      }), {direction: "top", sticky: true});
    } else {
      line.bindTooltip(tf("ui.flow_arc_tooltip", {
        from: hubDisplayName(origin),
        to: flowHubDisplayName(),
        count: fmt(count),
      }), {direction: "top", sticky: true});
    }
    line.on("click", forwardArcClickToZone);
    line.addTo(flowArcLayer);
    addFlowWingMarker(pts, color, useImportPressure ? {nearEnd: true} : null);
  });

  flowArcStats = {
    outTotal: outs.length,
    outShown: useImportPressure ? 0 : outSorted.length,
    inTotal: ins.length,
    inShown: inSorted.length,
    metric: useImportPressure ? "importation_pressure" : "persons",
    maxMetric: maxMetric,
  };
  flowArcLayer.addTo(map);
}

// --- Epidemiological trends (invasion risk) ---
const INVASION_RISK = PAYLOAD.invasion_risk || null;
const INVASION_ZONES = (INVASION_RISK && INVASION_RISK.zones) || {};
const INVASION_SCOPES = (INVASION_RISK && INVASION_RISK.scopes) || [];
// The Spatial Risk table always shows the national ranking -- there is no
// geographic scope toggle any more (the old National/Provincial buttons were
// removed). epiCurrentScope() therefore always resolves to the "national"
// INVASION_SCOPES entry (rr_nat / rr_nat_rank); the province-specific columns
// still ship in the payload and CSV download, they're just no longer surfaced
// in the UI.
// Sortable column headers replace the old "rank by relative risk / rank by
// vulnerability-based priority" buttons -- any column can be sorted by
// clicking (or Enter/Space on) its header, see wireEpiTrendsUi().
let epiSortKey = "rr_rank";
let epiSortDir = "asc";
let epiSelectedNom = null;
let epiFocusNoms = null; // Set of noms to keep vivid when a zone is selected
let epiInvasionDomain = {min: 0, max: 1, palette: PURPLES};
let epiCasesDomain = {min: 0, max: 1, isLog: true, palette: RISK_ORANGES};

function clearEpiLinks() {
  epiLinkLayer.clearLayers();
  if (map.hasLayer(epiLinkLayer)) map.removeLayer(epiLinkLayer);
}

function renderEpiStraightLinks(hubNom) {
  clearEpiLinks();
  if (!hubNom) return;
  const hub = zoneCentroid(hubNom);
  if (!hub) return;
  const cat = flowCatalogForLayer(FLOW_ARC_LAYER);
  if (!cat) return;

  const edges = [];
  const outs = (cat.out_by_origin && cat.out_by_origin[hubNom]) || [];
  const ins = (cat.in_by_dest && cat.in_by_dest[hubNom]) || [];
  outs.forEach(function(pair) {
    if (pair && pair[0] && Number(pair[1]) > 0) edges.push({nom: pair[0], count: Number(pair[1]), dir: "out"});
  });
  ins.forEach(function(pair) {
    if (pair && pair[0] && Number(pair[1]) > 0) edges.push({nom: pair[0], count: Number(pair[1]), dir: "in"});
  });
  if (!edges.length) return;

  let maxCount = 1;
  edges.forEach(function(e) { if (e.count > maxCount) maxCount = e.count; });

  edges.forEach(function(e) {
    const end = zoneCentroid(e.nom);
    if (!end) return;
    const color = e.dir === "out" ? FLOW_OUT_COLOR : FLOW_IN_COLOR;
    const line = L.polyline([hub, end], {
      color: color,
      weight: 1.2 + 3.5 * Math.sqrt(e.count / maxCount),
      opacity: 0.85,
      pane: "epi-links",
      interactive: false,
    });
    line.bindTooltip(tf("ui.flow_arc_tooltip", {
      from: e.dir === "out" ? hubDisplayName(hubNom) : hubDisplayName(e.nom),
      to: e.dir === "out" ? hubDisplayName(e.nom) : hubDisplayName(hubNom),
      count: fmt(e.count),
    }), {direction: "top", sticky: true});
    line.addTo(epiLinkLayer);
  });
  epiLinkLayer.addTo(map);
}

function epiCurrentScope() {
  // Always the national scope (rr_nat / rr_nat_rank) -- the provincial toggle
  // was removed, so there is no other scope to resolve to.
  return INVASION_SCOPES.find(function(s) { return s.id === "national"; }) || INVASION_SCOPES[0] || null;
}

function epiZoneVisible(row) {
  // National scope shows every zone; nothing to filter now that the
  // provincial toggle is gone.
  return !!epiCurrentScope();
}

function epiFlowConnectedNoms(hubNom) {
  const out = new Set([hubNom]);
  const layer = FLOW_ARC_LAYER;
  const cat = flowCatalogForLayer(layer);
  if (!cat || !hubNom) return out;
  // Spatial risk focuses on inflows into the selected zone.
  const ins = (cat.in_by_dest && cat.in_by_dest[hubNom]) || [];
  ins.forEach(function(p) { if (p && p[0]) out.add(p[0]); });
  return out;
}

function epiFmtProb(v) {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(v).toLocaleString(undefined, {minimumFractionDigits: 3, maximumFractionDigits: 3});
}

function epiFmtNum(v, digits) {
  if (v == null || Number.isNaN(v)) return "—";
  if (digits == null) return Number(v).toLocaleString(undefined, {maximumFractionDigits: 2});
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

function updateEpiTitle() {
  const el = document.getElementById("epi-trends-title");
  if (!el) return;
  // Always the national ranking now that the provincial scope is gone.
  el.textContent = t("ui.epi_trends_title");
}

function epiCapitalizeFirst(text) {
  const s = String(text || "");
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function epiParseIsoDate(iso) {
  if (!iso) return null;
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function epiOrdinalDay(n) {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return n + "th";
  const rem10 = n % 10;
  if (rem10 === 1) return n + "st";
  if (rem10 === 2) return n + "nd";
  if (rem10 === 3) return n + "rd";
  return n + "th";
}

function epiFormatLongDate(iso) {
  const d = epiParseIsoDate(iso);
  if (!d || Number.isNaN(d.getTime())) return "";
  const monthsEn = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const monthsFr = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"];
  if (currentLang === "fr") {
    return d.getDate() + " " + monthsFr[d.getMonth()] + " " + d.getFullYear();
  }
  return monthsEn[d.getMonth()] + " " + epiOrdinalDay(d.getDate());
}

function epiForecastEndIso() {
  if (INVASION_RISK && INVASION_RISK.forecast_end_date) {
    return INVASION_RISK.forecast_end_date;
  }
  const cutoff = INVASION_RISK && INVASION_RISK.cutoff_date;
  const weeks = INVASION_RISK && INVASION_RISK.horizon_window;
  const d = epiParseIsoDate(cutoff);
  if (!d || weeks == null || Number.isNaN(Number(weeks))) return null;
  d.setDate(d.getDate() + Math.round(Number(weeks)) * 7);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return yyyy + "-" + mm + "-" + dd;
}

function updateEpiMetaNotes() {
  const sub = document.getElementById("epi-trends-subtitle");
  if (sub) {
    // Prefer the pipeline's own forecast_start_date (ground truth from
    // run_info.json's forecast_target_windows) over cutoff_date, which is
    // "data up to" (last training day), not "forecast starts on".
    const startIso = INVASION_RISK && (
      INVASION_RISK.forecast_start_date || INVASION_RISK.cutoff_date
    );
    const weeksRaw = INVASION_RISK && (
      INVASION_RISK.forecasting_window != null
        ? INVASION_RISK.forecasting_window
        : INVASION_RISK.horizon_window
    );
    const weeks = (weeksRaw == null || Number.isNaN(Number(weeksRaw)))
      ? null
      : Math.round(Number(weeksRaw));
    const endIso = epiForecastEndIso();
    const startLabel = epiFormatLongDate(startIso);
    const endLabel = epiFormatLongDate(endIso);
    if (startLabel && endLabel && weeks != null) {
      sub.textContent = tf("ui.epi_forecast_subtitle", {
        start: startLabel,
        weeks: String(weeks),
        week_unit: weeks === 1 ? t("ui.epi_week_one") : t("ui.epi_week_other"),
        end: endLabel,
      });
    } else {
      sub.textContent = "";
    }
  }
  const methodEl = document.getElementById("epi-trends-method");
  if (!methodEl) return;
  if (!INVASION_RISK) {
    methodEl.textContent = t("ui.epi_no_data");
    return;
  }
  const label = (INVASION_RISK.method_label) || t("ui.epi_method_label");
  const url = INVASION_RISK.method_url || t("ui.epi_method_url");
  const cutoffLabel = epiFormatLongDate(INVASION_RISK.cutoff_date);
  let html = escHtml(t("ui.epi_method_prefix")) + " " +
    "<a href='" + escHtml(url) + "' target='_blank' rel='noopener'>" +
    escHtml(label) + "</a>";
  if (cutoffLabel) {
    html += " · " + escHtml(tf("ui.epi_data_up_to", {date: cutoffLabel}));
  }
  methodEl.innerHTML = html;
}

function renderEpiLegendBars() {
  function fillBar(barId, ticksId, domain, round) {
    const bar = document.getElementById(barId);
    const ticks = document.getElementById(ticksId);
    if (!bar || !ticks) return;
    const stops = [];
    for (let i = 0; i <= 10; i++) {
      const tt = i / 10;
      stops.push(rgb(lerpColor(domain.palette, tt)) + " " + Math.round(tt * 100) + "%");
    }
    bar.style.background = "linear-gradient(to right, " + stops.join(", ") + ")";
    const lo = domain.min, hi = domain.max;
    const mid = domain.isLog ? Math.sqrt(Math.max(lo, 1e-9) * Math.max(hi, 1e-9)) : (lo + hi) / 2;
    ticks.innerHTML =
      "<span>" + fmtLegend(lo, round) + "</span>" +
      "<span>" + fmtLegend(mid, round) + "</span>" +
      "<span>" + fmtLegend(hi, round) + "</span>";
  }
  const invLabel = document.getElementById("epi-legend-invasion-label");
  if (invLabel) {
    const raw = (INVASION_RISK && INVASION_RISK.p_case_invasion_label) ||
      t("ui.epi_p_invasion");
    invLabel.textContent = epiCapitalizeFirst(raw);
  }
  const activeLabel = document.querySelector('#epi-trends-legend [data-i18n="ui.epi_legend_active"]');
  if (activeLabel) {
    activeLabel.textContent = epiCapitalizeFirst(t("ui.epi_legend_active"));
  }
  fillBar("epi-legend-invasion-bar", "epi-legend-invasion-ticks", epiInvasionDomain, 2);
  fillBar("epi-legend-cases-bar", "epi-legend-cases-ticks", epiCasesDomain, "int");
}

function updateEpiFloat(nom, latlng) {
  const box = document.getElementById("epi-float");
  if (!box) return;
  const row = INVASION_ZONES[nom];
  if (!row || !epiZoneVisible(row)) {
    box.classList.remove("visible");
    return;
  }
  const name = zoneDisplayName(nom) || nom;
  box.innerHTML =
    "<strong>" + escHtml(name) + "</strong>" +
    "<table>" +
    "<tr><td>" + escHtml(t("ui.epi_surveillance_gap")) + "</td><td>" + epiFmtNum(row.surveillance_gap, 3) + "</td></tr>" +
    "<tr><td>" + escHtml(t("ui.epi_access_gap")) + "</td><td>" + epiFmtNum(row.access_gap, 3) + "</td></tr>" +
    "<tr><td>" + escHtml(t("ui.epi_social_vuln")) + "</td><td>" + epiFmtNum(row.social_vulnerability, 3) + "</td></tr>" +
    "</table>";
  const c = latlng
    ? [latlng.lat, latlng.lng]
    : zoneCentroid(nom);
  if (c) {
    const pt = map.latLngToContainerPoint(L.latLng(c[0], c[1]));
    const mapEl = map.getContainer();
    const x = Math.min(Math.max(12, pt.x + 14), mapEl.clientWidth - 220);
    const y = Math.min(Math.max(12, pt.y - 20), mapEl.clientHeight - 120);
    box.style.left = x + "px";
    box.style.top = y + "px";
  }
  box.classList.add("visible");
}

function hideEpiFloat() {
  const box = document.getElementById("epi-float");
  if (box) box.classList.remove("visible");
}

function setEpiSelected(nom) {
  if (!nom || !INVASION_ZONES[nom] || !epiZoneVisible(INVASION_ZONES[nom])) {
    epiSelectedNom = null;
    epiFocusNoms = null;
    clearEpiLinks();
    clearFlowArcs();
  } else {
    epiSelectedNom = nom;
    epiFocusNoms = epiFlowConnectedNoms(nom);
    flowHubNom = nom;
    clearEpiLinks();
    renderFlowArcs(nom, flowArcLayerDef());
  }
  renderEpiTrendsTable();
  recomputeEpiTrends();
  refreshZoneSelection();
}

// Extracts the value used to sort a given column -- shared by the click
// handler (which just needs to know which column) and epiSortedRows(). "zone"
// and "province" are strings; everything else is numeric-or-null. "norm_rr"
// (the on-screen "Relative risk (norm.)" column) is item.rr divided by a
// constant (the max across visible rows), so it sorts identically to the raw
// relative risk -- no need to recompute the normalised value just to sort by it.
function epiSortValue(item, key) {
  switch (key) {
    case "province": return item.row.province || "";
    case "zone": return zoneDisplayName(item.nom) || item.nom || "";
    case "p_invasion": return item.row.p_case_invasion;
    // No single natural sort key for a range -- use the lower bound.
    case "p_ci": return item.row.p_case_lo;
    case "norm_rr": return item.rr;
    case "rr_rank": return item.rrRank;
    case "priority": return item.priority;
    case "priority_rank": return item.priorityRank;
    default: return null;
  }
}

// Generic comparator for sortable-column values: nulls always sort last
// regardless of direction (there's nothing meaningful to rank an unknown
// value against), strings compare case/locale-insensitively, numbers compare
// numerically. dir "desc" just flips a non-null comparison.
function epiCompareValues(a, b, dir) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  const cmp = (typeof a === "string" || typeof b === "string")
    ? String(a).localeCompare(String(b), undefined, {sensitivity: "base", numeric: true})
    : (a - b);
  return dir === "desc" ? -cmp : cmp;
}

function epiSortedRows() {
  const scope = epiCurrentScope();
  if (!scope) return [];
  const rows = [];
  Object.keys(INVASION_ZONES).forEach(function(nom) {
    const row = INVASION_ZONES[nom];
    if (!epiZoneVisible(row)) return;
    rows.push({
      nom: nom,
      row: row,
      rr: row[scope.rr],
      rrRank: row[scope.rank],
      priority: row.priority,
      priorityRank: row.priority_rank,
    });
  });
  rows.sort(function(a, b) {
    const cmp = epiCompareValues(epiSortValue(a, epiSortKey), epiSortValue(b, epiSortKey), epiSortDir);
    if (cmp !== 0) return cmp;
    // Stable tiebreaker so equal/both-null values still render in a
    // predictable order instead of shuffling between re-renders.
    return String(zoneDisplayName(a.nom) || a.nom).localeCompare(String(zoneDisplayName(b.nom) || b.nom));
  });
  return rows;
}

function epiFmtCi(lo, hi, digits) {
  const a = epiFmtNum(lo, digits);
  const b = epiFmtNum(hi, digits);
  if (a === "—" && b === "—") return "—";
  return a + " - " + b;
}

function renderEpiTrendsTable() {
  const tbody = document.getElementById("epi-trends-tbody");
  if (!tbody) return;
  const rows = epiSortedRows();
  if (!rows.length) {
    // Covers both "Provincial scope, no province picked yet" (epiCurrentScope()
    // returned null) and "a scope is active but happens to match zero zones" --
    // same prompt either way, since the fix in both cases is "search for a
    // province above".
    tbody.innerHTML = "<tr class='epi-empty-row'><td colspan='8' class='trends-empty'>" +
      escHtml(t("ui.epi_scope_empty")) + "</td></tr>";
    return;
  }
  let maxRr = 0;
  rows.forEach(function(item) {
    if (item.rr != null && !Number.isNaN(item.rr) && item.rr > maxRr) maxRr = item.rr;
  });
  tbody.innerHTML = rows.map(function(item) {
    const sel = item.nom === epiSelectedNom ? " selected" : "";
    const norm = (item.rr == null || Number.isNaN(item.rr) || maxRr <= 0)
      ? null
      : (item.rr / maxRr);
    const pInv = item.row.p_case_invasion;
    const pLo = item.row.p_case_lo;
    const pHi = item.row.p_case_hi != null ? item.row.p_case_hi : item.row.p_case_high;
    return "<tr class='" + sel + "' data-nom='" + escHtml(item.nom) + "'>" +
      "<td>" + escHtml(item.row.province || "—") + "</td>" +
      "<td>" + escHtml(zoneDisplayName(item.nom) || item.nom) + "</td>" +
      "<td class='num'>" + epiFmtNum(pInv, 3) + "</td>" +
      "<td class='num'>" + epiFmtCi(pLo, pHi, 3) + "</td>" +
      "<td class='num'>" + epiFmtNum(norm, 3) + "</td>" +
      "<td class='num'>" + (item.rrRank == null ? "—" : item.rrRank) + "</td>" +
      "<td class='num'>" + epiFmtNum(item.priority, 3) + "</td>" +
      "<td class='num'>" + (item.priorityRank == null ? "—" : item.priorityRank) + "</td>" +
      "</tr>";
  }).join("");
}

// Fills in the ▲/▼ glyph on whichever column header matches epiSortKey and
// clears it from every other header -- called once at setup and again
// whenever a header click changes epiSortKey/epiSortDir.
function updateEpiSortIndicators() {
  document.querySelectorAll("#epi-trends-table th[data-sort]").forEach(function(th) {
    const key = th.getAttribute("data-sort");
    const active = key === epiSortKey;
    const arrow = th.querySelector(".sort-arrow");
    th.classList.toggle("sort-active", active);
    th.setAttribute("aria-sort", active ? (epiSortDir === "desc" ? "descending" : "ascending") : "none");
    if (arrow) arrow.textContent = active ? (epiSortDir === "desc" ? "▼" : "▲") : "";
  });
}

function recomputeEpiTrends() {
  if (!INVASION_RISK) return;
  const invasionVals = [];
  const caseVals = [];
  Object.keys(INVASION_ZONES).forEach(function(nom) {
    const row = INVASION_ZONES[nom];
    if (!epiZoneVisible(row)) return;
    if (row.was_active_before) {
      const z = ZONE_DATA[nom] || {};
      const c = z.effective_confirmed_cases;
      if (c != null && !Number.isNaN(Number(c)) && Number(c) > 0) caseVals.push(Number(c));
    } else if (row.p_case_invasion != null && !Number.isNaN(row.p_case_invasion)) {
      invasionVals.push(row.p_case_invasion);
    }
  });
  if (invasionVals.length) {
    epiInvasionDomain = {
      min: Math.min.apply(null, invasionVals),
      max: Math.max.apply(null, invasionVals),
      palette: PURPLES,
    };
    if (epiInvasionDomain.max === epiInvasionDomain.min) {
      epiInvasionDomain.max = epiInvasionDomain.min + 0.01;
    }
  } else {
    epiInvasionDomain = {min: 0, max: 1, palette: PURPLES};
  }
  if (caseVals.length) {
    const lo = Math.min.apply(null, caseVals);
    const hi = Math.max.apply(null, caseVals);
    epiCasesDomain = {
      min: lo,
      max: hi === lo ? lo * 10 : hi,
      isLog: true,
      palette: RISK_ORANGES,
    };
  } else {
    epiCasesDomain = {min: 1, max: 10, isLog: true, palette: RISK_ORANGES};
  }
  updateEpiTitle();
  updateEpiMetaNotes();
  renderEpiLegendBars();
  renderEpiTrendsTable();
  geoLayer.setStyle(styleFn);
  clearEpiLinks();
  if (flowArcsOverlayActive()) {
    renderFlowArcs(flowHubNom || epiSelectedNom, flowArcLayerDef());
  } else {
    clearFlowArcs();
  }
}

function epiTrendsStyleFn(feature) {
  const ref = feature.properties.nom;
  const row = INVASION_ZONES[ref];
  if (!row || !epiZoneVisible(row)) {
    return Object.assign({}, zoneStroke("hidden"), {fillColor: "#222", fillOpacity: 0.04});
  }
  let fill = ZERO_FILL;
  let has = false;
  if (row.was_active_before) {
    const z = ZONE_DATA[ref] || {};
    const v = z.effective_confirmed_cases;
    if (v != null && !Number.isNaN(Number(v))) {
      has = true;
      const num = Number(v);
      if (num <= 0) fill = NODATA_FILL;
      else {
        let t = (Math.log(num) - Math.log(epiCasesDomain.min)) /
          (Math.log(epiCasesDomain.max) - Math.log(epiCasesDomain.min) || 1);
        if (!isFinite(t)) t = 0;
        t = Math.max(0, Math.min(1, t));
        fill = rgb(lerpColor(epiCasesDomain.palette, t));
      }
    }
  } else if (row.p_case_invasion != null && !Number.isNaN(row.p_case_invasion)) {
    has = true;
    let t = (row.p_case_invasion - epiInvasionDomain.min) /
      (epiInvasionDomain.max - epiInvasionDomain.min || 1);
    if (!isFinite(t)) t = 0;
    t = Math.max(0, Math.min(1, t));
    fill = rgb(lerpColor(epiInvasionDomain.palette, t));
  }
  if (!has) {
    // Fail-loud: an active zone with no count. Sits on a solid mid-grey fill,
    // so it keeps a black stroke where every other state went off-white.
    return Object.assign({}, zoneStroke("failloud"), {fillColor: NODATA_FILL, fillOpacity: 0.55});
  }
  let fillOpacity = 0.82;
  let stroke = zoneStroke("rest");
  if (epiSelectedNom) {
    const focus = epiFocusNoms && epiFocusNoms.has(ref);
    if (ref === epiSelectedNom) {
      fillOpacity = 0.95;          // ring comes from the zone-selection pane
    } else if (focus) {
      fillOpacity = 0.78;
      stroke = zoneStroke("focus");
    } else {
      // Dimming is the focus signal: drop the stroke too, or a bright mesh of
      // full-strength borders reads straight through the dimmed fills.
      fillOpacity = 0.12;
      stroke = zoneStroke("dim");
    }
  }
  return Object.assign({}, stroke, {fillColor: fill, fillOpacity: fillOpacity});
}

function enterEpiTrendsView() {
  if (!INVASION_RISK || !Object.keys(INVASION_ZONES).length) {
    const methodEl = document.getElementById("epi-trends-method");
    if (methodEl) methodEl.textContent = t("ui.epi_no_data");
  }
  hideProvinceOutlines();
  clearContextSelection();
  clearEpiLinks();
  const epiCases = document.getElementById("epi-show-cases");
  if (epiCases && showCasesBox) epiCases.checked = !!showCasesBox.checked;
  if (!epiSelectedNom) {
    flowHubNom = PAYLOAD.flow_default_hub || flowHubNom;
    clearFlowArcs();
  } else {
    flowHubNom = epiSelectedNom;
    renderFlowArcs(epiSelectedNom, flowArcLayerDef());
  }
  updateEpiMetaNotes();
}

function leaveEpiTrendsView() {
  epiSelectedNom = null;
  epiFocusNoms = null;
  hideEpiFloat();
  clearEpiLinks();
  clearFlowArcs();
  document.body.classList.remove("view-epi-trends", "epi-splitting");
  refreshZoneSelection();
}

const ZERO_FILL    = "#c4bfb6";
const NODATA_FILL = "#7d7d7d";   // fail-loud: an active zone with no count (should never happen)
let currentValues = new Map();
let currentDomain = {min:0, max:1, isLog:true, palette:OUTBREAK};

function recompute() {
  const layer = getLayer(layerSelect.value);
  const highlightEpicenter = layerEpicenterHighlight(layer);
  currentValues.clear();
  const positives = [];
  let lo = Infinity, hi = -Infinity;
  for (const feat of PAYLOAD.geometry.features) {
    const ref = feat.properties.nom;
    const zone = ZONE_DATA[ref];
    if (!zone) continue;
    const v = valueForZone(ref, zone, layer);
    if (v == null || Number.isNaN(v)) {
      if (!highlightEpicenter || !isEpicenterZone(ref, layer)) continue;
      currentValues.set(ref, v);
      continue;
    }
    currentValues.set(ref, v);
    if (highlightEpicenter && isEpicenterZone(ref, layer)) continue;
    if (layerOriginHighlight(layer) && isMatrixOriginZone(ref, layer)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
    if (v > 0) positives.push(v);
  }
  if (!isFinite(lo)) { lo = 0; hi = 1; }
  // Log vs. linear is decided per layer on the backend (layer_config.yaml /
  // EXTRA_LAYER_DEFS' "scale" field), not by a user-facing toggle.
  const useLog = layer.scale === "log" && positives.length > 0;
  let dlo, dhi;
  if (useLog) {
    dlo = Math.min.apply(null, positives);
    dhi = Math.max.apply(null, positives);
    if (dhi === dlo) dhi = dlo * 10;
  } else {
    dlo = Math.min(0, lo);
    dhi = (hi === dlo) ? dlo + 1 : hi;
  }
  currentDomain = {min:dlo, max:dhi, isLog:useLog, palette:PALETTES[layer.palette] || PLASMA};
  geoLayer.setStyle(styleFn);
  if (flowArcsOverlayActive()) {
    renderFlowArcs(flowHubNom, flowArcLayerDef());
  } else {
    clearFlowArcs();
  }
  restoreRoleZoneOrder();
  updateLegend(layer);
  updateLayerMeta(layer);
}

function valueToColor(v, ref, layer) {
  if (isHubZone(ref, layer)) return MATRIX_ORIGIN_FILL;
  if (isEpicenterZone(ref, layer)) return EPICENTER_FILL;
  const d = currentDomain;
  if (d.isLog && v <= 0) return ZERO_FILL;
  let t;
  if (d.isLog) t = (Math.log(v) - Math.log(d.min)) / (Math.log(d.max) - Math.log(d.min));
  else t = (v - d.min) / (d.max - d.min || 1);
  if (!isFinite(t)) t = 0;
  t = Math.max(0, Math.min(1, t));
  return rgb(lerpColor(d.palette, t));
}

// Fill half of a zone's style. The stroke half comes from zoneStroke().
// `bump` is the selected/highlighted variant: it keeps the layer's fill (so the
// value stays readable under the ring) and lifts the opacity slightly. Both the
// snapshot and genomic branches used to carry their own copy of this.
function zoneFillStyle(v, has, ref, layer, bump) {
  if (!has) return {fillOpacity: 0};
  const isZero = currentDomain.isLog ? v <= 0 : v === 0;
  if (bump) {
    return {fillColor: valueToColor(v, ref, layer), fillOpacity: isZero ? 0.55 : 0.85};
  }
  const isOutbreak = layer && layer.palette === "outbreak";
  return {
    fillColor: valueToColor(v, ref, layer),
    fillOpacity: isZero ? (isOutbreak ? 0.48 : 0.55) : (isOutbreak ? 0.72 : 0.85)
  };
}

function trendsRecencyStyle(ref) {
  const cat = getTrendsRecencyAt(ref, trendsDateIdx);
  const fillColor = RECENCY_FILL[cat] || RECENCY_NODATA_FILL;
  // Category 4 ("never") is a muted neutral; give it a slightly lower opacity
  // so the active categories read as the foreground.
  const fillOpacity = cat === 4 || !cat ? 0.55 : 0.85;
  const style = Object.assign({}, zoneStroke("rest"), {fillColor, fillOpacity});
  // Mirror the cumulative view: suppress zone strokes in Provincial scope so the
  // province outlines are the only line work.
  if (trendsScope === "province") style.weight = 0;
  return style;
}

function styleFn(feature) {
  if (activeView === "epi-trends") return epiTrendsStyleFn(feature);
  if (activeView === "trends" && trendsColorMode === "recency") {
    return trendsRecencyStyle(feature.properties.nom);
  }
  const ref = feature.properties.nom;
  const v = currentValues.get(ref);
  const has = v != null && !Number.isNaN(v);
  const layer = getLayer(layerSelect.value);
  // Checked BEFORE the role markers, as it was before this refactor: on the
  // genomic tab the coordinator's highlight must keep the choropleth fill even
  // when the active layer would paint this zone as an epicentre or a travel
  // origin. The epicentre zones are the highest-sequence-count zones, so they
  // are the ones most likely to be highlighted -- this collision is the normal
  // case, not an edge case.
  if (activeView === "genomic-epidemiology" && genomicHighlightNoms.indexOf(ref) !== -1) {
    return Object.assign({}, zoneStroke("rest"), zoneFillStyle(v, has, ref, layer, true));
  }
  // In Provincial scope, suppress ALL zone-level strokes so the province
  // outlines are the only line work. Fills are untouched.
  const prov = function (s) {
    if (activeView === "trends" && trendsScope === "province") s.weight = 0;
    return s;
  };
  if (isHubZone(ref, layer)) {
    return prov(Object.assign({}, zoneStroke("origin"), {
      fillColor: MATRIX_ORIGIN_FILL, fillOpacity: 0.92
    }));
  }
  if (isEpicenterZone(ref, layer)) {
    return prov(Object.assign({}, zoneStroke("epicenter"), {
      fillColor: EPICENTER_FILL, fillOpacity: 0.88
    }));
  }
  // Map focus stays BELOW the role markers, where it has always been.
  if (activeView === "map" && ref === mapSelectedNom) {
    return prov(Object.assign({}, zoneStroke("rest"), zoneFillStyle(v, has, ref, layer, true)));
  }
  if (!has) {
    return prov(Object.assign({}, zoneStroke("nodata"), {fillOpacity: 0}));
  }
  return prov(Object.assign({}, zoneStroke("rest"), zoneFillStyle(v, has, ref, layer, false)));
}

function fmtLegend(v, round) {
  if (v == null || Number.isNaN(v)) return "—";
  if (typeof v !== "number") return String(v);
  if (round === "int" || round == null) return Math.round(v).toLocaleString();
  var d = Number(round);
  if (!isFinite(d)) return Math.round(v).toLocaleString();
  return v.toLocaleString(undefined, {minimumFractionDigits: d, maximumFractionDigits: d});
}

function fmt(v, kind) {
  if (v == null || Number.isNaN(v)) return "—";
  if (typeof v !== "number") return String(v);
  if (kind === "rel") return v.toFixed(2);
  if (kind === "cal") {
    if (Math.abs(v) < 1) return v.toFixed(1);
    return Math.round(v).toLocaleString();
  }
  return Math.round(v).toLocaleString();
}

function updateLayerMeta(layer) {
  let html = layer.source || "";
  if (layerUsesMatrix(layer)) {
    const originLine = matrixOriginNom
      ? tf("ui.matrix_origin", {origin: matrixOriginDisplayName()})
      : t("ui.matrix_select_hint");
    html = (html ? html + "<br>" : "") + originLine;
  }
  if (flowArcsOverlayActive() && !flowHubNom) {
    // Nothing focused: prompt to pick a zone instead of showing a stale
    // "Selected location: <default>" line (flowHubDisplayName falls back to
    // TRAVEL_FROM when the hub is null).
    html = (html ? html + "<br>" : "") + t("ui.hints.flow");
  } else if (flowArcsOverlayActive()) {
    const flowLayer = flowArcLayerDef();
    const hubLine = tf("ui.flow_hub", {hub: flowHubDisplayName()});
    html = (html ? html + "<br>" : "") + hubLine;
    if (flowArcStats) {
      html += "<br>" + tf("ui.flow_arc_summary", {
        outShown: flowArcStats.outShown,
        outTotal: flowArcStats.outTotal,
        inShown: flowArcStats.inShown,
        inTotal: flowArcStats.inTotal,
      });
    } else {
      const cat = flowCatalogForLayer(flowLayer);
      const hasHub = cat && (
        (cat.out_by_origin && cat.out_by_origin[flowHubNom]) ||
        (cat.in_by_dest && cat.in_by_dest[flowHubNom])
      );
      if (!hasHub) {
        html += "<br>" + t("ui.flow_no_data");
      }
    }
  }
  layerMeta.innerHTML = html;
}

function updateLegend(layer) {
  document.getElementById("legend-title").innerHTML = "<strong>" + layer.label + "</strong>";
  const stops = [];
  const N = 32;
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    stops.push(rgb(lerpColor(currentDomain.palette, t)) + " " + Math.round(t * 100) + "%");
  }
  document.getElementById("legend-bar").style.background = "linear-gradient(to right, " + stops.join(", ") + ")";
  const ticks = document.getElementById("legend-ticks");
  const lo = currentDomain.min, hi = currentDomain.max;
  const mid = currentDomain.isLog ? Math.sqrt(lo * hi) : (lo + hi) / 2;
  var lr = layer.legend_round != null ? layer.legend_round : "int";
  ticks.innerHTML =
    "<span>" + fmtLegend(lo,  lr) + "</span>" +
    "<span>" + fmtLegend(mid, lr) + "</span>" +
    "<span>" + fmtLegend(hi,  lr) + "</span>";
  document.getElementById("legend-scale").textContent =
    layer.legend_caption
      ? layer.legend_caption
      : (currentDomain.isLog ? t("ui.legend.log_scale") : t("ui.legend.linear_scale"));
  var grayParts = [
    "<span class='swatch' style='background:" + ZERO_FILL + "'></span>" + t("ui.legend.zero"),
    "<span class='swatch swatch-no-data'></span>" + t("ui.legend.no_data")
  ];
  if (layerEpicenterHighlight(layer)) {
    grayParts.push(
      "<span class='swatch' style='background:" + EPICENTER_FILL + "'></span>" + t("ui.legend.epicenter")
    );
  }
  if (layerUsesMatrix(layer) && layerOriginHighlight(layer)) {
    grayParts.push(
      "<span class='swatch' style='background:" + MATRIX_ORIGIN_FILL + "'></span>" + t("ui.legend.matrix_origin")
    );
  }
  // Flow arrows go on their own line(s) below the inline zero/no-data row so
  // the arrow icons read clearly and don't crowd the gray legend.
  var flowHTML = "";
  if (flowArcsOverlayActive()) {
    flowHTML =
      "<div class='legend-flow-row'>" + flowArrowSwatch(FLOW_OUT_COLOR) + t("ui.legend.flow_out") + "</div>" +
      "<div class='legend-flow-row'>" + flowArrowSwatch(FLOW_IN_COLOR) + t("ui.legend.flow_in") + "</div>";
    const scaleEl = document.getElementById("legend-scale");
    scaleEl.textContent = (scaleEl.textContent || "") + " · " + t("ui.legend.flow_width");
  }
  document.getElementById("legend-gray").innerHTML = grayParts.join(" · ") + flowHTML;
}

function infoHTML(feature) {
  const ref = feature.properties.nom;
  const z = ZONE_DATA[ref] || {};
  const name = feature.properties.name || t("ui.case_tooltip.unnamed");
  const info = t("ui.info");
  let h = "<div><strong>" + name + "</strong></div>";
  // The nom is the underlying geometry key; surface it as a secondary line only
  // when it actually differs from the display name. For almost every zone the
  // geometry uses the place name as its nom, so name === ref and this line would
  // just repeat the name. When omitted, the first <h4>'s top margin keeps the gap.
  if (ref && ref !== name) {
    h += "<div style='color:#aaa;font-size:11px;margin-bottom:6px'>" + ref + "</div>";
  }

  // Trimmed to the fields Ciara asked to keep visible in the hover/click
  // panel: confirmed cases, confirmed deaths, population, health facilities,
  // incoming mobility, distance from the travel-matrix origin, and genomic
  // surveillance (when available). Total/suspected case counts, contact
  // tracing, testing capacity, and modeled relative-risk projection used to
  // show here too but were dropped to keep the panel shorter -- that data
  // still lives in ZONE_DATA/PAYLOAD if it needs to resurface elsewhere.
  h += "<h4>" + info.observed_cases + " (" + PAYLOAD.asof + ")</h4>";
  h += "<table>";
  h += "<tr><td>" + info.confirmed + "</td><td>" + fmt(z.confirmed_cases) + "</td></tr>";
  h += "<tr><td>" + info.confirmed_deaths + "</td><td>" + fmt(z.confirmed_deaths) + "</td></tr>";
  h += "</table>";

  h += "<h4>" + info.population + "</h4>";
  h += "<table>";
  h += "<tr><td>" + info.pop_count + "</td><td>" + fmt(z.worldpop__pop_count__pop_count) + "</td></tr>";
  h += "</table>";

  h += "<h4>" + info.health_facilities_grid3 + "</h4>";
  h += "<table>";
  h += "<tr><td>" + info.healthsite_count + "</td><td>" + fmt(z.grid3_healthsites__healthsite_count__healthsite_count) + "</td></tr>";
  h += "</table>";

  h += "<h4>" + info.incoming_mobility + "</h4>";
  h += "<table>";
  h += "<tr><td>" + info.displaced_12mo + "</td><td>" + fmt(z.displaced_in_individuals_12mo) + "</td></tr>";
  h += "<tr><td>" + info.flowminder_mar + "</td><td>" + fmt(z.flowminder_in_mar2026) + "</td></tr>";
  h += "<tr><td>" + info.flowminder_apr + "</td><td>" + fmt(z.flowminder_in_202604) + "</td></tr>";
  h += "<tr><td>" + info.flowminder_may + "</td><td>" + fmt(z.flowminder_short_trips__outflow_20260524__outflow_20260524, "cal") + "</td></tr>";
  h += "</table>";

  h += "<h4>" + tf("ui.info.distance_from", {origin: hubDisplayName(DISTANCE_ORIGIN_NOM)}) + "</h4>";
  h += "<table>";
  h += "<tr><td>" + info.travel_time_h + "</td><td>" + fmt(matrixValue("osrm__travel_time", DISTANCE_ORIGIN_NOM, ref, 60)) + "</td></tr>";
  h += "<tr><td>" + info.road_distance_km + "</td><td>" + fmt(matrixValue("osrm__road_distance", DISTANCE_ORIGIN_NOM, ref, 1)) + "</td></tr>";
  h += "</table>";

  if (z.genomic_sequence_count) {
    h += "<h4>" + info.genomic_surveillance + "</h4>";
    h += "<table>";
    h += "<tr><td>" + info.genome_sequences + "</td><td>" + fmt(z.genomic_sequence_count) + "</td></tr>";
    h += "</table>";
  }
  return h;
}

// Lightweight per-zone readout for the snapshot hover tooltip: the active
// layer's label and this zone's value (matrix layers → travel time/distance
// from the focused origin). "No data" when the layer has no value here.
function layerHoverTooltipHTML(feature) {
  const ref = feature.properties.nom;
  const name = feature.properties.name || t("ui.case_tooltip.unnamed");
  if (activeView === "trends" && trendsColorMode === "recency") {
    const cat = getTrendsRecencyAt(ref, trendsDateIdx);
    const catLabel = t("ui.trends_recency_cat" + (cat || 4));
    let line2;
    if (!cat || cat === 4) {
      line2 = t("ui.trends_recency_tooltip_never");
    } else {
      const days = getTrendsRecencyDaysAt(ref, trendsDateIdx);
      line2 = days >= 0
        ? tf("ui.trends_recency_tooltip_days", {days: days})
        : t("ui.trends_recency_tooltip_never");
    }
    return "<strong>" + name + "</strong><br/>" + catLabel + "<br/>" + line2;
  }
  const layer = getLayer(layerSelect.value);
  const v = currentValues.get(ref);
  const has = v != null && !Number.isNaN(v);
  const body = has
    ? (layer ? layer.label + ": " : "") + fmtLegend(v, layer && layer.legend_round != null ? layer.legend_round : "int")
    : t("ui.layer_no_data");
  return "<strong>" + name + "</strong><br/>" + body;
}

// Hover calls bringToFront() on the zone under the cursor, and resetStyle() on
// mouseout restores that zone's STYLE but not its DOM order -- so it stays in
// front and clips the heavier border of any role-marker zone (epicentre /
// travel origin) it shares an edge with. Selection is immune because its ring
// is drawn in a pane above the polygons; role markers still live in the polygon
// layer, where order is all they have. Re-assert it whenever a hover ends or
// the layer is re-styled.
function restoreRoleZoneOrder() {
  const layer = getLayer(layerSelect.value);
  const wantsEpicenter = layerEpicenterHighlight(layer);
  const wantsOrigin = layerUsesMatrix(layer) && layerOriginHighlight(layer);
  if (!wantsEpicenter && !wantsOrigin) return;
  geoLayer.eachLayer(function (l) {
    if (!l.feature) return;
    const ref = l.feature.properties.nom;
    if (isHubZone(ref, layer) || isEpicenterZone(ref, layer)) l.bringToFront();
  });
}

// What a click on a zone means, per view. Factored out of the polygon click
// handler so a click landing on a flow arc can be forwarded to the polygon
// underneath (see forwardArcClickToZone) and behave identically -- the two
// paths cannot drift into different selection behaviour.
function handleZoneClick(feature) {
  if (activeView === "trends") {
    // Re-clicking the current selection clears it, same as Context / Spatial
    // Risk / Snapshot. In province scope the unit is the PARENT province, so
    // clicking any zone inside the selected province deselects it -- there is
    // no such thing as "the province polygon you originally clicked".
    if (trendsScope === "province") {
      const province = feature.properties.province || null;
      setTrendsSelection(province === trendsSelectedKey ? null : province);
    } else if (trendsScope === "health_zone") {
      const nom = feature.properties.nom || null;
      setTrendsSelection(nom === trendsSelectedKey ? null : nom);
    }
    return;   // national scope has no zone selection
  }
  if (activeView === "context") {
    // Re-clicking the selected zone toggles it off (empty-map click also
    // clears -- see the map "click" handler below).
    if (feature.properties.nom === contextSelectedNom) clearContextSelection();
    else selectContextZone(feature.properties.nom);
    return;
  }
  if (activeView === "epi-trends") {
    // Re-clicking the already-selected zone toggles it off. Any other zone
    // switches the selection to it.
    const nom = feature.properties.nom;
    setEpiSelected(nom === epiSelectedNom ? null : nom);
    return;
  }
  if (activeView === "genomic-epidemiology") {
    // Ownership rule (R7): on the genomic view the genomic coordinator drives
    // selection, not setMapSelection. Route the zone click to the generic hook
    // (genomic.js maps the zone to its tip-set and highlights the tree).
    if (genomicMapHooks) genomicMapHooks._emitZoneClick(feature.properties.nom);
    return;
  }
  if (activeView === "map") {
    // One "focused zone" for the snapshot view: click to focus, click the
    // focused zone again to clear. Focus drives the info box, the flow-arc
    // origin, and the matrix travel origin. No click-to-zoom.
    setMapSelection(feature.properties.nom);
  }
}

// Arrows annotate the selected zone rather than acting as controls, and they
// sit in a pane above the zones -- so a click landing on one used to be
// swallowed outright, making every arrow a dead stripe across an otherwise
// clickable polygon. Forward it to the polygon underneath instead.
//
// bubblingMouseEvents stays false on the arcs: with no zone under the cursor
// the click must still NOT reach the map handler, which would clear the
// selection and take the arrows with it.
function forwardArcClickToZone(ev) {
  L.DomEvent.stop(ev);
  const src = ev.originalEvent;
  const pt = (src && src.clientX != null)
    ? {x: src.clientX, y: src.clientY}
    : lastPointerClient;
  const layer = zoneLayerAtClientPoint(pt);
  if (layer && layer.feature) handleZoneClick(layer.feature);
}

const geoLayer = L.geoJSON(PAYLOAD.geometry, {
  style: styleFn,
  onEachFeature: function (feature, layer) {
    layer.on({
      mouseover: function(e) {
        // While the map is moving, zones slide under the cursor and fire
        // mouseover; opening hover decoration then strands it after the move
        // ends (movestart only clears what already existed when the move began,
        // not what a mid-move mouseover creates). Suppress it entirely while
        // moving -- a real hover after the map settles re-fires mouseover.
        if (mapMoving) return;
        // Requirement: a selected zone does not react to hover. That is about
        // STYLING only -- it keeps its tooltip, its floating readout and its
        // province-hover behaviour. Guard the setStyle/bringToFront pairs
        // below, never the whole handler.
        const isSelected = currentSelectedNoms().indexOf(feature.properties.nom) !== -1;
        if (activeView === "genomic-epidemiology") {
          // Zones are clickable here -- the click routes to the genomic
          // coordinator -- so they get the same hover lift as everywhere else.
          // What they must NOT get is the snapshot's layer-value tooltip (the
          // default fall-through below): those are bound per-hover, and the
          // "tooltipopen" sweep only covers marker/arc layers, so a dropped
          // mouseout on fast motion strands one open. Lift the border, bind
          // nothing.
          if (!isSelected) {
            e.target.setStyle(zoneStroke("hover"));
            e.target.bringToFront();
          }
          return;
        }
        if (activeView === "trends") {
          if (trendsScope === "national") return;
          if (trendsScope === "province") {
            // Highlight the parent province's outline (matches click-to-select),
            // rather than the individual zone. Gated inside setTrendsProvinceHover
            // to no-op once a province is selected.
            setTrendsProvinceHover(feature.properties.province);
            return;
          }
          if (!isSelected) {
            e.target.setStyle(zoneStroke("hover"));
            e.target.bringToFront();
          }
          return;
        }
        if (activeView === "context") {
          if (!isSelected) {
            e.target.setStyle(zoneStroke("hover"));
            e.target.bringToFront();
          }
          return;
        }
        if (activeView === "epi-trends") {
          if (!isSelected) {
            e.target.setStyle(zoneStroke("hover"));
            e.target.bringToFront();
          }
          updateEpiFloat(feature.properties.nom, e.latlng);   // fires for selected zones too
          return;
        }
        if (!isSelected) {
          e.target.setStyle(zoneStroke("hover"));
          e.target.bringToFront();
        }
        // Hover no longer fills the info box (that follows the focused zone).
        // Show a lightweight, layer-aware tooltip instead.
        e.target.bindTooltip(layerHoverTooltipHTML(feature), {sticky: true, direction: "top"}).openTooltip(e.latlng);
      },
      mouseout: function(e) {
        if (activeView === "genomic-epidemiology") {
          // Mirror of the mouseover lift. No tooltip was bound, so nothing to
          // unbind; resetStyle cannot disturb a selected zone's ring, which
          // lives in the zone-selection pane.
          geoLayer.resetStyle(e.target);
          return;
        }
        if (activeView === "trends") {
          if (trendsScope === "province") {
            // Zone was never restyled on hover in province scope; just clear the
            // province-outline highlight.
            setTrendsProvinceHover(null);
            return;
          }
          geoLayer.resetStyle(e.target);
          return;
        }
        if (activeView === "context") {
          geoLayer.resetStyle(e.target);
          return;
        }
        if (activeView === "epi-trends") {
          hideEpiFloat();
          geoLayer.resetStyle(e.target);
          return;
        }
        if (e.target.getTooltip()) e.target.unbindTooltip();
        geoLayer.resetStyle(e.target);
        // Selection is drawn in the zone-selection pane, so resetStyle here
        // cannot disturb it -- there is no focus border left in styleFn to lose.
      },
      click: function(e) {
        L.DomEvent.stop(e);
        handleZoneClick(feature);
      },
      dblclick: function(e) {
        if (activeView === "context") return;
        if (activeView === "map") return;   // no zoom-to-zone on the snapshot view
        if (activeView === "trends" && trendsScope === "national") {
          return;
        }
        L.DomEvent.stop(e);
        map.fitBounds(e.target.getBounds(), {padding:[40,40]});
      }
    });
    // Registered separately from the handler map above so it runs whichever
    // branch that mouseout took (several return early).
    layer.on("mouseout", restoreRoleZoneOrder);
  }
}).addTo(map);

// Re-apply zone borders (e.g. after a zoom, so the weight ramp picks up the new
// zoom). styleFn encodes every resting/tier style; selection lives in its own
// pane and is rebuilt here rather than re-fronted, which is what the old
// per-view bringToFront() blocks were doing.
function restyleZonesForActiveView() {
  geoLayer.setStyle(styleFn);
  restoreRoleZoneOrder();
  refreshZoneSelection();
}

map.on("zoomend", restyleZonesForActiveView);

// A pan (or any map move) slides the zones out from under a stationary cursor,
// and the browser does not reliably fire the zone's mouseout in that case --
// especially on a fast drag -- so the hover tooltip / floating readout / hover
// highlight would otherwise stay stranded until the zone is hovered and left
// again. Tear that transient hover decoration down as soon as the map starts
// moving, then re-apply the resting styles.
function tearDownHoverDecoration() {
  // Zone hover tooltips are bound per-hover (see the geoLayer mouseover
  // handler), so unbind them.
  geoLayer.eachLayer(function (layer) {
    if (layer.getTooltip && layer.getTooltip()) layer.unbindTooltip();
  });
  // Active-case / genome markers and flow / epi-link arcs bind their tooltip
  // once at creation and let Leaflet open it on hover; a fast drag misses the
  // mouseout and strands it open, exactly like the zone tooltips did. Close
  // (do NOT unbind -- the binding must survive for later hovers) any that are
  // open on those layers.
  [caseLayer, genomeLayer, flowArcLayer, epiLinkLayer].forEach(function (grp) {
    grp.eachLayer(function (l) {
      // Guard on a tooltip actually being bound: some members (e.g. the flow-arc
      // wing markers) have none, and Leaflet's isTooltipOpen() dereferences
      // this._tooltip unconditionally -- calling it on a tooltip-less layer
      // throws, which (via the movestart handler) would abort the whole pan/zoom.
      if (l.getTooltip && l.getTooltip() && l.isTooltipOpen()) l.closeTooltip();
    });
  });
  hideEpiFloat();
  setTrendsProvinceHover(null);
}

map.on("movestart", function () {
  mapMoving = true;
  tearDownHoverDecoration();
  restyleZonesForActiveView();
});

// Clear the moving flag once the map settles so hover decoration works again.
// The mapMoving guard on mouseover means nothing should have accumulated during
// the move, but tear down once more as a safety net (e.g. a mouseover that
// raced the movestart, or a marker/arc tooltip Leaflet opened mid-drag).
// A pan that starts ON a zone leaves the cursor inside that same zone when it
// ends. The hover lift was torn down at movestart, and Leaflet fires no fresh
// mouseover because the pointer never left -- so the border stays un-lifted
// until you move out and back in. Track the pointer and restore the lift for
// whatever zone sits under it once the map settles.
//
// Border only, deliberately: re-opening a tooltip here is the stranding hazard
// tearDownHoverDecoration() exists to prevent, and the spatial-risk float
// readout needs a latlng this path does not have. Both come back on the next
// real mouseover.
let lastPointerClient = null;
document.addEventListener("mousemove", function (e) {
  lastPointerClient = {x: e.clientX, y: e.clientY};
}, {passive: true});

function zoneLayerAtClientPoint(pt) {
  if (!pt) return null;
  // Scan the whole stack rather than just the topmost element: flow arcs and
  // epi-links sit in panes above the zones, and what we want is the polygon
  // underneath them. Elements with pointer-events:none (the selection rings)
  // are already excluded by the browser.
  const els = document.elementsFromPoint
    ? document.elementsFromPoint(pt.x, pt.y)
    : [document.elementFromPoint(pt.x, pt.y)];
  let found = null;
  for (let i = 0; i < els.length && !found; i++) {
    const el = els[i];
    if (!el) continue;
    geoLayer.eachLayer(function (layer) {
      if (!found && layer._path === el) found = layer;
    });
  }
  return found;
}

function restoreHoverUnderCursor() {
  // Mirrors which views lift a zone border on hover (see the mouseover
  // handler): national scope has no zone hover, and province scope hovers the
  // parent province outline rather than the zone.
  if (activeView === "trends" && trendsScope !== "health_zone") return;
  const layer = zoneLayerAtClientPoint(lastPointerClient);
  if (!layer || !layer.feature) return;
  if (currentSelectedNoms().indexOf(layer.feature.properties.nom) !== -1) return;
  layer.setStyle(zoneStroke("hover"));
  layer.bringToFront();
}

map.on("moveend", function () {
  mapMoving = false;
  tearDownHoverDecoration();
  restoreHoverUnderCursor();
});

map.on("click", function() {
  if (activeView === "context") clearContextSelection();
  if (activeView === "epi-trends") setEpiSelected(null);
  // Snapshot: clicking empty map clears the focused zone (info box → placeholder,
  // highlight cleared, arcs cleared, matrix choropleth goes empty).
  if (activeView === "map") setMapSelection(null);
  // Genomic: clicking empty map clears the coordinator's current selection.
  if (activeView === "genomic-epidemiology" && genomicMapHooks) genomicMapHooks._emitBackgroundClick();
});

// --- unified health-zone search -----------------------------------------
// One #zone-search node (common/chrome.py), a sibling of #map, serving every
// view. dashboard.css positions it per body.view-*; the ZONE_SEARCH_VIEWS
// table below supplies each view's index filter, i18n keys and select()
// action; wireZoneSearch() at the end of this section is the single
// controller. Replaces the three separate implementations that used to live
// in #controls, #trends-controls and .epi-controls.
const ZONE_SEARCH_INDEX = (PAYLOAD.geometry.features || []).map(function(feat) {
  const props = feat.properties || {};
  const name = props.name || props.nom || "";
  const nom = props.nom || "";
  return {
    nom: nom,
    name: name,
    label: name,
    haystack: (name + " " + nom).toLowerCase(),
  };
}).filter(function(z) { return !!z.nom; })
  .sort(function(a, b) {
    return String(a.name).localeCompare(String(b.name), undefined, {sensitivity: "base"});
  });

// --- the one search index: every province + health zone, regardless of
// whether a plot happens to exist for it. Each view filters it down by `kind`
// via ZONE_SEARCH_VIEWS below -- only Trends lists provinces, because only
// Trends has a province scope. ZONE_SEARCH_INDEX above is now a private
// intermediate of this list; nothing else reads it.
const LOCATION_INDEX = (function() {
  const provinceNames = {};
  (PAYLOAD.province_boundaries && PAYLOAD.province_boundaries.features || []).forEach(function(feat) {
    const name = feat.properties && feat.properties.province;
    if (name) provinceNames[name] = true;
  });
  const provinces = Object.keys(provinceNames).map(function(name) {
    return {id: name, label: name, kind: "province", haystack: name.toLowerCase()};
  });
  const zones = ZONE_SEARCH_INDEX.map(function(z) {
    return {id: z.nom, label: z.name, kind: "health_zone", haystack: z.haystack};
  });
  return provinces.concat(zones).sort(function(a, b) {
    return String(a.label).localeCompare(String(b.label), undefined, {sensitivity: "base"});
  });
})();

// The view comes from <body data-initial-view>, NOT from activeView:
// bootstrapInitialView() runs at the very bottom of this file, so activeView
// is still its "map" default here. Every page is a single view (the nav is
// real cross-page links, and setActiveView() is called once, from that
// bootstrap), so one read at init is enough.
const ZONE_SEARCH_VIEW_ID = document.body.dataset.initialView || "map";

const ZONE_SEARCH_VIEWS = {
  "map": {
    kinds: ["health_zone"],
    placeholder: "ui.zone_search_placeholder",
    aria: "ui.zone_search",
    // Collapsible detail panel to open after a narrow-screen selection; absent
    // on views that have none. See pick() in wireZoneSearch().
    panel: "info",
    select: function(entry) { setMapSelection(entry.id); },
  },
  "context": {
    kinds: ["health_zone"],
    placeholder: "ui.zone_search_placeholder",
    aria: "ui.zone_search",
    panel: "context",
    select: function(entry) { selectContextZone(entry.id); },
  },
  "trends": {
    kinds: ["province", "health_zone"],
    // The only tab that lists provinces, so the only one whose placeholder
    // and accessible name say "location" rather than "health zone".
    placeholder: "ui.trends_search_placeholder",
    aria: "ui.trends_search",
    select: function(entry) {
      // Scope FIRST: setTrendsScope() nulls the selection, so setting the
      // selection before it would be undone immediately.
      if (entry.kind !== trendsScope) activateTrendsScope(entry.kind);
      setTrendsSelection(entry.id);
    },
  },
  "epi-trends": {
    kinds: ["health_zone"],
    placeholder: "ui.zone_search_placeholder",
    aria: "ui.zone_search",
    select: function(entry) {
      // A ranked list of one zone isn't useful, so this selects/highlights the
      // row rather than filtering the table -- same as clicking the row.
      // setEpiSelected() re-renders the table, so find the row afterwards.
      setEpiSelected(entry.id);
      const tbody = document.getElementById("epi-trends-tbody");
      if (!tbody) return;
      const rows = tbody.querySelectorAll("tr[data-nom]");
      for (let i = 0; i < rows.length; i++) {
        if (rows[i].getAttribute("data-nom") === entry.id) {
          if (rows[i].scrollIntoView) rows[i].scrollIntoView({block: "center"});
          break;
        }
      }
    },
  },
  "genomic-epidemiology": {
    kinds: ["health_zone"],
    placeholder: "ui.zone_search_placeholder",
    aria: "ui.zone_search",
    // {toggle:false} matters: _emitZoneClick is a toggle by design (clicking
    // the same polygon twice clears). The search clears its input after every
    // pick, so a repeat search would silently DEselect while the shared zoom
    // still framed the zone -- map says "here", tree says "nothing".
    select: function(entry) {
      if (genomicMapHooks) genomicMapHooks._emitZoneClick(entry.id, {toggle: false});
    },
  },
};

// Zoom padding as Leaflet [x, y]. Narrow Trends/Spatial Risk maps are
// height:40vh -- ~192px on a 480px viewport -- so [40,40] would eat 80px of it.
function zoneSearchPad() {
  return window.matchMedia("(max-width: 700px)").matches ? [16, 16] : [40, 40];
}

// Width of map hidden behind an OVERLAYING panel. Zero everywhere except
// Genomic: the Trends and Spatial Risk rails narrow #map itself, so Leaflet
// already fits inside the visible area there, but #genomic-panel sits on top
// of a full-width #map. Its width is an inline px style written by
// applyWidth() in genomic.js, so it is read from the element.
function zoneSearchInsetX() {
  if (ZONE_SEARCH_VIEW_ID !== "genomic-epidemiology") return 0;
  const panel = document.getElementById("genomic-panel");
  return panel ? panel.offsetWidth : 0;
}

// The two knobs that decide how close a searched unit is framed. Tune these,
// not the fitBounds() call.
//
// BACKOFF is the one that matters. A bare fitBounds() frames the polygon
// edge-to-edge, so a health zone fills the map and every neighbour falls off
// screen -- the map stops answering "where is this?" at the moment it is most
// being asked. One level out halves the scale, leaving the unit dominant but
// ringed by its neighbours. It is applied to the NATURAL fit rather than by
// lowering MAX_ZOOM, because the cap only bites on the very smallest polygons:
// a mid-sized zone fits at z9 and never reaches the cap at all, so a lower cap
// would do nothing for the common case.
//
// MAX_ZOOM still caps the smallest units, which back off from a fit so tight
// (z13+) that one level out is still too close.
const ZONE_SEARCH_ZOOM_BACKOFF = 1;
const ZONE_SEARCH_MAX_ZOOM = 9;

// Frames one unit. Named for its first caller, but it is the shared zoom now:
// the Spatial Risk table calls it too, with a literal {kind, id} rather than a
// search-index entry. Anything that selects a unit the user did not point at
// on the map should route through here, so one set of knobs frames them all.
//
// NEVER pass `padding` alongside paddingTopLeft/paddingBottomRight: Leaflet
// resolves each side as `paddingBottomRight || padding || [0,0]`, so a
// directional key REPLACES padding on that side rather than adding to it, and
// [0,0] is truthy. tests/test_zone_search.py guards this.
function zoneSearchZoomTo(entry) {
  let bounds = null;
  if (entry.kind === "province") {
    provinceOutlineLayer.eachLayer(function(layer) {
      const props = layer.feature && layer.feature.properties;
      if (!bounds && props && props.province === entry.id) bounds = layer.getBounds();
    });
  } else {
    const layer = findGeoLayerByNom(entry.id);
    if (layer) bounds = layer.getBounds();
  }
  // No geometry (a zone in the index but absent from the drawn layer): the
  // selection still applies, the zoom is simply skipped.
  if (!bounds || !bounds.isValid()) return;
  const pad = zoneSearchPad();
  const topLeft = pad;
  const bottomRight = [pad[0] + zoneSearchInsetX(), pad[1]];
  // getBoundsZoom() takes TOTAL padding as a single point, where fitBounds
  // takes it per side -- sum the two sides so this sees exactly the fit
  // fitBounds is about to compute, then hand back one level less as the cap.
  const fitZoom = map.getBoundsZoom(bounds, false, L.point(
    topLeft[0] + bottomRight[0],
    topLeft[1] + bottomRight[1]
  ));
  map.fitBounds(bounds, {
    paddingTopLeft: topLeft,
    paddingBottomRight: bottomRight,
    // fitBounds() only ever zooms further OUT than its natural fit for a
    // maxZoom below it, so capping at fit-minus-backoff is what applies the
    // back-off; the framing (centre, directional padding) stays Leaflet's.
    maxZoom: Math.min(ZONE_SEARCH_MAX_ZOOM, fitZoom - ZONE_SEARCH_ZOOM_BACKOFF),
  });
}

function findGeoLayerByNom(nom) {
  let found = null;
  geoLayer.eachLayer(function(layer) {
    if (!found && layer.feature && layer.feature.properties && layer.feature.properties.nom === nom) {
      found = layer;
    }
  });
  return found;
}

(function wireZoneSearch() {
  const view = ZONE_SEARCH_VIEWS[ZONE_SEARCH_VIEW_ID];
  const root = document.getElementById("zone-search");
  const input = document.getElementById("zone-search-input");
  const results = document.getElementById("zone-search-results");
  const empty = document.getElementById("zone-search-empty");
  const live = document.getElementById("zone-search-live");
  // Stub pages have no table entry: no-op rather than dereference view.kinds.
  if (!view || !root || !input || !results || !empty || !live) return;

  // Set, not a hand-rolled object: matches EPICENTER_NOMS / PROJ_MASK_LAYERS
  // above, which are the file's existing idiom for small membership tests.
  const kinds = new Set(view.kinds);

  let matches = [];
  let activeIdx = -1;

  // Per-view i18n goes on the data-i18n-* ATTRIBUTES, never the properties:
  // applyStaticI18n() re-reads those attributes on every language toggle, so
  // setting input.placeholder here would survive only until the first EN/FR
  // switch -- a bug that only ever shows up in the French build.
  input.setAttribute("data-i18n-placeholder", view.placeholder);
  input.setAttribute("data-i18n-aria", view.aria);
  applyStaticI18n();

  function isNarrow() {
    return window.matchMedia("(max-width: 700px)").matches;
  }

  function close() {
    results.hidden = true;
    results.innerHTML = "";
    empty.hidden = true;
    matches = [];
    activeIdx = -1;
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-activedescendant", "");
    live.textContent = "";
  }

  function setActive(idx) {
    if (!matches.length) return;
    activeIdx = Math.max(0, Math.min(idx, matches.length - 1));
    const opts = results.querySelectorAll(".zone-search-option");
    opts.forEach(function(el, i) {
      const on = i === activeIdx;
      el.classList.toggle("active", on);
      el.setAttribute("aria-selected", on ? "true" : "false");
    });
    const active = opts[activeIdx];
    if (active) {
      input.setAttribute("aria-activedescendant", active.id);
      if (active.scrollIntoView) active.scrollIntoView({block: "nearest"});
    }
  }

  function render(query) {
    const q = String(query || "").trim().toLowerCase();
    if (!q) {
      close();
      return;
    }
    matches = LOCATION_INDEX.filter(function(it) {
      return kinds.has(it.kind) && it.haystack.indexOf(q) !== -1;
    }).slice(0, 40);
    if (!matches.length) {
      const msg = t("ui.zone_search_no_matches");
      results.hidden = true;
      results.innerHTML = "";
      empty.textContent = msg;
      empty.hidden = false;
      activeIdx = -1;
      // aria-expanded tracks the LISTBOX, and there is nothing selectable.
      input.setAttribute("aria-expanded", "false");
      input.setAttribute("aria-activedescendant", "");
      live.textContent = msg;
      return;
    }
    empty.hidden = true;
    results.innerHTML = matches.map(function(it, i) {
      return "<button type='button' role='option' class='zone-search-option' tabindex='-1'" +
        " id='zone-search-opt-" + i + "' aria-selected='false' data-idx='" + i + "'>" +
        escHtml(it.label) + "</button>";
    }).join("");
    results.hidden = false;
    input.setAttribute("aria-expanded", "true");
    setActive(0);
    live.textContent = tf("ui.zone_search_matches", {n: matches.length});
  }

  function pick(idx) {
    const entry = matches[idx];
    if (!entry) return;
    view.select(entry);
    zoneSearchZoomTo(entry);
    // The box is a query field, not a state indicator: the selection is
    // visible in the map highlight / info panel / table row / plot titles.
    input.value = "";
    close();
    // Desktop: stay focused so the next search starts immediately. Narrow:
    // the on-screen keyboard would cover half the map we just zoomed.
    if (isNarrow()) {
      input.blur();
      // wirePanelToggles() auto-collapses every panel on load at this width,
      // so without this the only feedback from a search is a zoom and a
      // highlight on a map the user may not recognise. #context-national is
      // deliberately left collapsed: the search selects a ZONE, and #context
      // is where zone context appears.
      if (view.panel) expandPanel(view.panel);
    }
  }

  input.addEventListener("input", function() { render(input.value); });
  input.addEventListener("focus", function() {
    if (input.value.trim()) render(input.value);
  });

  input.addEventListener("keydown", function(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (results.hidden) render(input.value);
      else setActive(activeIdx + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(activeIdx - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      // No-op on a closed list.
      if (!results.hidden) pick(activeIdx);
    } else if (e.key === "Escape") {
      // preventDefault matters: Chrome and WebKit clear an
      // input[type=search] natively on Esc, which would pre-empt the
      // two-stage close-then-clear.
      e.preventDefault();
      if (!results.hidden || !empty.hidden) close();
      else input.value = "";
    } else if (e.key === "Tab") {
      close();
    }
  });

  // mousedown, not click: the input must not lose focus before we read the
  // index. pointermove moves the ACTIVE row rather than painting a separate
  // hover state, so keyboard and mouse can never highlight two rows at once.
  results.addEventListener("mousedown", function(e) {
    const btn = e.target.closest(".zone-search-option");
    if (!btn) return;
    e.preventDefault();
    pick(parseInt(btn.getAttribute("data-idx"), 10));
  });
  results.addEventListener("pointermove", function(e) {
    const btn = e.target.closest(".zone-search-option");
    if (!btn) return;
    const idx = parseInt(btn.getAttribute("data-idx"), 10);
    // Only on an actual row change: setActive() also calls scrollIntoView(),
    // and re-running it on every pixel of movement within one row is wasted
    // work that can nudge the list under a stationary cursor.
    if (idx === activeIdx) return;
    setActive(idx);
  });

  document.addEventListener("click", function(e) {
    if (!root.contains(e.target)) close();
  });
})();

// --- province outlines (Trends view) ---
let trendsScope = "national";
let trendsColorMode = "cumulative"; // "cumulative" | "recency"

// Confirmed-case recency category fills (see docs spec 2026-09-02). Index by
// category int 1..4; 0 / missing -> no-data neutral.
// Keep these in sync with the recency swatch colours in Scripts/common/chrome.py.
const RECENCY_FILL = {1: "#b2182b", 2: "#ef8a62", 3: "#fddbc7", 4: "#e0e0e0"};
const RECENCY_NODATA_FILL = "#e0e0e0";

function getTrendsRecencyAt(nom, dateIdx) {
  const rc = PAYLOAD.confirmed_recency;
  if (!rc || !rc.by_nom) return 0;
  const series = rc.by_nom[nom];
  if (!series || dateIdx < 0 || dateIdx >= series.length) return 0;
  return series[dateIdx];
}

function getTrendsRecencyDaysAt(nom, dateIdx) {
  const rc = PAYLOAD.confirmed_recency;
  if (!rc || !rc.days_by_nom) return -1;
  const series = rc.days_by_nom[nom];
  if (!series || dateIdx < 0 || dateIdx >= series.length) return -1;
  return series[dateIdx];
}

function trendsRecencyAvailable() {
  const rc = PAYLOAD.confirmed_recency;
  return !!(rc && rc.by_nom && rc.dates && rc.dates.length);
}
let trendsSelectedKey = null;
let trendsHoverTimer = null;
let trendsHoveredProvince = null;
function themeVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
function provinceBaseWeight() {
  const provinceMode = activeView === "trends" && trendsScope === "province";
  return provinceMode
    ? zoneNum("--province-outline-weight-wide", "1.4")
    : zoneNum("--province-outline-weight", "1");
}

// Province outlines wear one of two resting colours, decided by whether they
// are an OVERLAY or the polygon layer itself:
//
//   overlay (every other tab/scope) -- gold. Zone borders are drawn underneath
//     them, and the colour difference is what makes the province mesh read as
//     a separate layer rather than a heavier zone border.
//   province scope on Trends -- off-white, the same --zone-stroke every other
//     tab's polygons rest at. Here styleFn() zeroes the zone borders, so these
//     outlines ARE the clickable polygon layer: there is no second layer left
//     for gold to distinguish them from, and a gold mesh just looks like the
//     one tab that opted out of the shared resting colour.
//
// Both share the rest of the state grammar: hover is a white lift, selection is
// the cased amber ring drawn in the province-selection pane. A SELECTED
// province draws its RESTING outline; without that it would show a red base
// line under an amber ring.
function provinceOutlineStyle(state) {
  const provinceMode = activeView === "trends" && trendsScope === "province";
  if (state === "hover") {
    return {
      color: themeVar("--province-hover-stroke", "#ffffff"),
      opacity: zoneNum("--province-hover-stroke-opacity", "0.98"),
      weight: provinceBaseWeight() * zoneNum("--province-hover-weight-mult", "1.7"),
      fillOpacity: 0,
    };
  }
  return {
    color: provinceMode
      ? themeVar("--zone-stroke", "#fdfaf4")
      : themeVar("--province-outline", "#9b7d4e"),
    weight: provinceBaseWeight(),
    // Held above the zone resting opacity (0.7) on purpose: in province scope
    // this mesh carries the whole map, with no zone borders under it.
    opacity: provinceMode ? 0.95 : 0.88,
    fillOpacity: 0,
  };
}

map.createPane("province-outline");
map.getPane("province-outline").style.zIndex = 550;
const provinceOutlineLayer = L.geoJSON(PAYLOAD.province_boundaries || {type:"FeatureCollection", features:[]}, {
  pane: "province-outline",
  interactive: false,
  style: function() {
    return provinceOutlineStyle("rest");
  },
});

// 560: above the province outlines (550). Province rings are NOT zoom-scaled --
// they multiply the province resting weight, which is fixed.
const provinceRings = SelectionRing("province-selection", 560, function () {
  const base = provinceBaseWeight();
  return {
    inner: base * zoneNum("--province-selected-weight-mult", "2.2"),
    casing: base * zoneNum("--province-selected-casing-mult", "3.6")
  };
});

function provinceFeaturesFor(name) {
  if (!name) return [];
  const fc = PAYLOAD.province_boundaries || {features: []};
  return (fc.features || []).filter(function (f) {
    return f.properties && f.properties.province === name;
  });
}

// Hover and selection were a single variable: whichever province was passed in
// got the red style, and hover was suppressed entirely once anything was
// selected. They are now distinct states -- hovering a non-selected province
// still lifts it while another is selected, and the selected one ignores hover.
function applyProvinceOutlineStyles(hoveredProvince) {
  trendsHoveredProvince = hoveredProvince || null;
  const selected = (activeView === "trends" && trendsScope === "province")
    ? trendsSelectedKey : null;
  provinceOutlineLayer.eachLayer(function (layer) {
    const name = layer.feature.properties.province;
    const isHover = !!trendsHoveredProvince && name === trendsHoveredProvince && name !== selected;
    layer.setStyle(provinceOutlineStyle(isHover ? "hover" : "rest"));
    if (isHover) layer.bringToFront();
  });
  provinceRings.set(provinceFeaturesFor(selected));
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderTrendsPanel(_unused) {
  renderTrendsPlots();
}

function setTrendsProvinceHover(province) {
  // No longer gated on "nothing selected": a selected province ignores hover,
  // but its neighbours still respond.
  if (activeView === "trends" && trendsScope === "province") {
    applyProvinceOutlineStyles(province || null);
  }
}

function trendsPlotData() {
  return PAYLOAD.onset_trends || null;
}

function trendsIndexes() {
  const data = trendsPlotData();
  return (data && data.indexes) || {};
}

function trendsIndexEntry(bucket, key) {
  if (!key) return null;
  const entries = trendsIndexes()[bucket] || {};
  if (entries[key]) return entries[key];
  const target = String(key).toLowerCase();
  const keys = Object.keys(entries);
  for (let i = 0; i < keys.length; i++) {
    if (String(keys[i]).toLowerCase() === target) return entries[keys[i]];
  }
  return null;
}

// Always returns a real array, however the manifest happens to have shaped
// lab_codes (missing, a single string, etc.) -- a non-array value here used
// to reach a bare .forEach() downstream and throw, which silently froze the
// whole labs card (the exception aborted renderTrendsLabs() before it could
// update the DOM, so it just kept showing whatever the previous selection
// had rendered).
function asCodeArray(v) {
  if (Array.isArray(v)) return v;
  if (v == null || v === "") return [];
  return [v];
}

function trendsLabCodesForSelection() {
  if (trendsScope === "health_zone" && trendsSelectedKey) {
    const entry = trendsIndexEntry("by_health_zone", trendsSelectedKey);
    return asCodeArray(entry && entry.lab_codes);
  }
  if (trendsScope === "province" && trendsSelectedKey) {
    const entry = trendsIndexEntry("by_province", trendsSelectedKey);
    return asCodeArray(entry && entry.lab_codes);
  }
  return [];
}

// Normalizes a place name for cross-dataset matching: strips accents,
// drops parenthetical suffixes ("Idiofa (Secteur)"), and collapses
// punctuation/whitespace. Health zone naming has historically drifted a bit
// between data feeds (see _NAME_TO_NOM on the Python side), so lab metadata
// doesn't always spell a zone name exactly the same way the case/geometry
// data does.
function normalizeLabLocationKey(s) {
  return String(s || "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/\([^)]*\)/g, "")
    .replace(/[^a-z0-9]+/gi, " ")
    .trim()
    .toLowerCase();
}

function trendsLabsForSelection() {
  const data = trendsPlotData() || {};
  const labs = data.labs || [];
  // National shows every lab -- no province/health-zone subsetting needed.
  if (trendsScope === "national") return labs;
  if (!trendsSelectedKey) return [];

  // Match each lab's own health_zone/province field against the current
  // selection directly, rather than relying solely on the manifest's
  // indexes.by_health_zone/by_province reverse lookup -- in practice that
  // index hasn't always been populated for every health zone.
  const candidateKeys = (trendsScope === "health_zone"
    ? [trendsSelectedKey, zoneDisplayName(trendsSelectedKey)]
    : [trendsSelectedKey]
  ).map(normalizeLabLocationKey).filter(Boolean);
  const labField = trendsScope === "health_zone" ? "health_zone" : "province";
  const direct = labs.filter(function(lab) {
    const val = lab[labField];
    return val && candidateKeys.indexOf(normalizeLabLocationKey(val)) !== -1;
  });

  // Union in anything the manifest's index knows about that the direct
  // field match missed.
  const codes = trendsLabCodesForSelection();
  if (codes.length) {
    const byCode = data.labs_by_code || {};
    const seen = new Set(direct.map(function(l) { return l.lab_code || l.id; }));
    codes.forEach(function(code) {
      const lab = byCode[code];
      const key = lab && (lab.lab_code || lab.id);
      if (lab && key && !seen.has(key)) {
        direct.push(lab);
        seen.add(key);
      }
    });
  }
  return direct;
}

function findTrendsLab(id) {
  const labs = (trendsPlotData() && trendsPlotData().labs) || [];
  for (let i = 0; i < labs.length; i++) {
    if (labs[i].id === id) return labs[i];
  }
  return null;
}

function trendsEntityList() {
  const data = trendsPlotData();
  if (!data) return [];
  if (trendsScope === "province") {
    return Object.keys(data.provinces || data.plots || {}).sort(function(a, b) {
      return String(a).localeCompare(String(b), undefined, {sensitivity: "base"});
    }).map(function(id) {
      return {id: id, label: id, kind: "province"};
    });
  }
  if (trendsScope === "health_zone") {
    return Object.keys(data.health_zones || {}).sort(function(a, b) {
      return String(a).localeCompare(String(b), undefined, {sensitivity: "base"});
    }).map(function(id) {
      return {id: id, label: zoneDisplayName(id) || id, kind: "health_zone"};
    });
  }
  return [{id: "national", label: t("ui.trends_scope_national"), kind: "national"}];
}

function resolveTrendsPlot() {
  const data = trendsPlotData();
  if (!data) return null;
  if (trendsScope === "national") return data.national || null;
  if (trendsScope === "province") {
    if (!trendsSelectedKey) return null;
    return (data.provinces && data.provinces[trendsSelectedKey]) ||
      (data.plots && data.plots[trendsSelectedKey]) || null;
  }
  if (trendsScope === "health_zone") {
    if (!trendsSelectedKey) return null;
    return (data.health_zones && data.health_zones[trendsSelectedKey]) || null;
  }
  return null;
}

// Every plot SVG from the data pipeline bakes its own chart title into the
// top of the image (in the same spot the card header's title already
// shows), plus a bit of margin above the actual chart panel. Rather than
// leaving that redundant text (and blank space) visible, shift the SVG's
// viewBox down to crop it off entirely instead of just visually clipping a
// gap. Every plot type currently shares the same 648x324 canvas with a
// 25.28pt top margin before the chart panel starts, so one fixed crop
// works everywhere; if a plot ever uses a different margin, the regex
// simply won't match cleanly enough to matter -- worst case the title
// stays visible rather than the chart getting mangled.
const PLOT_SVG_TITLE_CROP = 40.56; // 26 + 20% + 30%
function cropPlotSvgTop(svg, cropPx) {
  if (!svg) return svg;
  const m = svg.match(/viewBox=(['"])\s*([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s*\1/);
  if (!m) return svg;
  const quote = m[1];
  const minX = parseFloat(m[2]);
  const minY = parseFloat(m[3]);
  const w = parseFloat(m[4]);
  const h = parseFloat(m[5]);
  if (!isFinite(minX) || !isFinite(minY) || !isFinite(w) || !isFinite(h)) return svg;
  if (!(cropPx > 0) || cropPx >= h) return svg;
  const newViewBox = minX + " " + (minY + cropPx) + " " + w + " " + (h - cropPx);
  return svg.replace(m[0], "viewBox=" + quote + newViewBox + quote);
}

// Shared renderer for every card in #trends-plots-column: fills in the SVG
// (or an appropriate empty-state message) for whichever plot was resolved.
// #trends (confirmed cases), #trends-deaths (cumulative deaths), and
// #trends-positivity (rolling test positivity) all use this -- future plot
// cards should too, rather than re-implementing the empty-state copy.
function renderPlotCard(titleId, bodyId, plot, fallbackTitleKey) {
  const titleEl = document.getElementById(titleId);
  const body = document.getElementById(bodyId);
  if (!body) return;
  if (plot && plot.svg) {
    // Built from the localized plot-type label + place name rather than
    // plot.title (the SVG's own baked title) -- that text is generated once
    // in English by the data pipeline and never changes with the language
    // toggle. Place names (provinces/health zones) are proper nouns with no
    // separate French form in this dataset, so only the type label and
    // "National" need localizing.
    if (titleEl) {
      const place = plot.id === "national" ? t("ui.trends_scope_national") : (plot.label || plot.id || "");
      titleEl.textContent = place ? (t(fallbackTitleKey) + " - " + place) : t(fallbackTitleKey);
    }
    body.className = "panel-body";
    body.innerHTML = "<div class='onset-chart-wrap'>" + cropPlotSvgTop(plot.svg, PLOT_SVG_TITLE_CROP) + "</div>";
    return;
  }
  if (titleEl) titleEl.textContent = t(fallbackTitleKey);
  body.className = "panel-body trends-empty";
  if (trendsScope === "national") {
    body.innerHTML = "<p>" + escHtml(t("ui.trends_no_plot").replace("{name}", t("ui.trends_scope_national"))) + "</p>";
  } else if (trendsScope === "province") {
    body.innerHTML = "<p>" + escHtml(
      trendsSelectedKey
        ? tf("ui.trends_no_plot", {name: trendsSelectedKey})
        : t("ui.trends_select_province")
    ) + "</p>";
  } else if (trendsScope === "health_zone") {
    body.innerHTML = "<p>" + escHtml(
      trendsSelectedKey
        ? tf("ui.trends_no_plot", {name: zoneDisplayName(trendsSelectedKey) || trendsSelectedKey})
        : t("ui.trends_select_health_zone")
    ) + "</p>";
  }
}

function renderTrendsPlot() {
  renderPlotCard("trends-title", "trends-body", resolveTrendsPlot(), "ui.trends_panel");
}

function resolveCumulativeDeathsPlot() {
  const data = trendsPlotData();
  const deaths = data && data.cumulative_deaths;
  if (!deaths) return null;
  if (trendsScope === "national") return deaths.national || null;
  if (trendsScope === "province") {
    if (!trendsSelectedKey) return null;
    return (deaths.provinces && deaths.provinces[trendsSelectedKey]) || null;
  }
  if (trendsScope === "health_zone") {
    if (!trendsSelectedKey) return null;
    return (deaths.health_zones && deaths.health_zones[trendsSelectedKey]) || null;
  }
  return null;
}

function resolveRollingPositivityPlot() {
  const data = trendsPlotData();
  const positivity = data && data.rolling_positivity;
  if (!positivity) return null;
  if (trendsScope === "national") return positivity.national || null;
  if (trendsScope === "province") {
    if (!trendsSelectedKey) return null;
    return (positivity.provinces && positivity.provinces[trendsSelectedKey]) || null;
  }
  if (trendsScope === "health_zone") {
    if (!trendsSelectedKey) return null;
    return (positivity.health_zones && positivity.health_zones[trendsSelectedKey]) || null;
  }
  return null;
}

function renderCumulativeDeathsPlot() {
  renderPlotCard("trends-deaths-title", "trends-deaths-body", resolveCumulativeDeathsPlot(), "ui.trends_deaths_panel");
}

function renderRollingPositivityPlot() {
  renderPlotCard("trends-positivity-title", "trends-positivity-body", resolveRollingPositivityPlot(), "ui.trends_positivity_panel");
}

function trendsSelectionLabel() {
  if (trendsScope === "national") return t("ui.trends_scope_national");
  if (!trendsSelectedKey) return "";
  if (trendsScope === "health_zone") {
    return zoneDisplayName(trendsSelectedKey) || trendsSelectedKey;
  }
  return trendsSelectedKey;
}

function renderTrendsLabs() {
  const card = document.getElementById("trends-labs");
  const titleEl = document.getElementById("trends-labs-title");
  const body = document.getElementById("trends-labs-body");
  if (!card || !body) return;

  // National always shows (every lab); province/health zone need a selection first.
  const show = trendsScope === "national" ||
    ((trendsScope === "province" || trendsScope === "health_zone") && trendsSelectedKey);
  card.style.display = show ? "" : "none";
  if (!show) {
    body.innerHTML = "";
    body.className = "panel-body trends-empty";
    return;
  }

  // Set the title before computing labs: an unexpected manifest/lab data
  // shape used to throw inside trendsLabsForSelection() and silently freeze
  // this whole card -- everything after the throw (including the title)
  // never ran, so it just kept showing the previous selection.
  const locationLabel = trendsSelectionLabel();
  if (titleEl) {
    titleEl.textContent = tf("ui.trends_labs_panel", {location: locationLabel});
  }

  let labs = [];
  try {
    labs = trendsLabsForSelection();
  } catch (err) {
    console.error("trendsLabsForSelection failed for", trendsScope, trendsSelectedKey, err);
    labs = [];
  }

  if (!labs.length) {
    body.className = "panel-body trends-empty";
    body.innerHTML = "<p>" + escHtml(tf("ui.trends_no_labs", {name: locationLabel})) + "</p>";
    return;
  }

  try {
    body.className = "panel-body trends-labs-body";
    body.innerHTML = labs.map(function(lab) {
      return "<div class='trends-lab-subplot'>" +
        "<h4 class='trends-lab-subplot-title'>" + escHtml(lab.label || lab.lab_code || lab.id) + "</h4>" +
        "<div class='onset-chart-wrap'>" + cropPlotSvgTop(lab.svg, PLOT_SVG_TITLE_CROP) + "</div>" +
        "</div>";
    }).join("");
  } catch (err) {
    console.error("renderTrendsLabs markup failed for", trendsScope, trendsSelectedKey, err);
    body.className = "panel-body trends-empty";
    body.innerHTML = "<p>" + escHtml(tf("ui.trends_no_labs", {name: locationLabel})) + "</p>";
  }
}

// Renders every card in the plots column. Call sites that used to call
// renderTrendsPlot() directly now call this instead, so the deaths card
// (and any future card) stays in sync with the scope/selection too.
function renderTrendsPlots() {
  renderTrendsPlot();
  renderCumulativeDeathsPlot();
  renderRollingPositivityPlot();
  renderTrendsLabs();
}

// fitMapToTrendsSelection() used to live here and auto pan/zoom the map to
// whichever province/health zone was selected, with padding carved out for
// the old floating trends panel that used to sit on top of the map. Now
// that the map and plots panel are two separate fixed columns (nothing
// overlaps), that auto-pan just made the map jump around distractingly on
// every click, so it's been removed -- CLICKING a zone/province still does
// not move the map.
//
// SEARCHING one does, via zoneSearchZoomTo(). The asymmetry is deliberate:
// a searched location can be offscreen, a clicked one cannot. Do not
// "restore consistency" by deleting one side -- they answer different needs.

function setTrendsSelection(key) {
  trendsSelectedKey = key || null;
  // Repaint outlines and the province ring for the new selection. All three
  // scopes want the same call now that the ring reads trendsSelectedKey itself;
  // the branches only survived from when this passed the selection in.
  //
  // Carries the CURRENT hover through rather than clearing it. Deselecting by
  // re-clicking leaves the cursor sitting on the province it just cleared, and
  // passing null there dropped it to flat resting with no way back until the
  // pointer crossed into another zone -- mouseover does not re-fire inside the
  // zone you are already in. Search-driven calls are unaffected: the pointer is
  // in the search box, so trendsHoveredProvince is already null.
  applyProvinceOutlineStyles(trendsHoveredProvince);
  renderTrendsPlots();
  if (activeView === "trends") geoLayer.setStyle(styleFn);
  refreshZoneSelection();
}

function setTrendsScope(scope) {
  trendsScope = scope || "national";
  trendsSelectedKey = null;
  applyProvinceOutlineStyles(null);
  renderTrendsPlots();
  if (activeView === "trends") {
    geoLayer.setStyle(styleFn);
    showProvinceOutlines();
  }
  refreshZoneSelection();
}

function syncTrendsPlayButton() {
  const btn = document.getElementById("trends-play-btn");
  if (!btn) return;
  btn.classList.toggle("playing", !!trendsSliderAnimating);
  // Actual play/pause glyphs -- no need to localize the symbol itself, but
  // the accessible name still is (aria-label), same strings as before.
  btn.textContent = trendsSliderAnimating ? "⏸" : "▶";
  btn.setAttribute("aria-label", trendsSliderAnimating ? t("ui.trends_pause") : t("ui.trends_play"));
}

function formatContextDate(raw) {
  if (!raw) return "";
  const s = String(raw).trim();
  if (!s) return "";
  if (s.length >= 10 && s[2] === "-" && s[5] === "-") {
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const d = parseInt(s.slice(0, 2), 10);
    const m = parseInt(s.slice(3, 5), 10);
    const y = s.slice(6, 10);
    if (m >= 1 && m <= 12 && d >= 1) {
      return String(d) + " " + months[m - 1] + " " + y;
    }
  }
  if (s.length >= 10 && s[4] === "-" && s[7] === "-") {
    const parts = s.slice(0, 10).split("-");
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const m = parseInt(parts[1], 10);
    const d = parseInt(parts[2], 10);
    if (m >= 1 && m <= 12 && d >= 1) {
      return String(d) + " " + months[m - 1] + " " + parts[0];
    }
  }
  if (s.indexOf("/") >= 0) {
    const bits = s.split("/");
    if (bits.length === 3) {
      const a = parseInt(bits[0], 10), b = parseInt(bits[1], 10);
      let y = parseInt(bits[2], 10);
      if (y < 100) y += 2000;
      const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      const day = a > 12 ? a : b;
      const month = a > 12 ? b : a;
      if (month >= 1 && month <= 12) {
        return String(day) + " " + months[month - 1] + " " + y;
      }
    }
  }
  return s;
}

function contextDateSortKey(pillar) {
  if (pillar && pillar.date_iso) {
    const t = Date.parse(pillar.date_iso);
    if (!isNaN(t)) return t;
  }
  const raw = pillar ? pillar.date : null;
  if (raw == null) return Number.NEGATIVE_INFINITY;
  const s = String(raw).trim();
  if (!s) return Number.NEGATIVE_INFINITY;
  if (s.length >= 10 && s[2] === "-" && s[5] === "-") {
    const d = parseInt(s.slice(0, 2), 10);
    const m = parseInt(s.slice(3, 5), 10) - 1;
    const y = parseInt(s.slice(6, 10), 10);
    const t = Date.UTC(y, m, d);
    if (!isNaN(t)) return t;
  }
  if (s.length >= 10 && s[4] === "-" && s[7] === "-") {
    const t = Date.parse(s.slice(0, 10));
    if (!isNaN(t)) return t;
  }
  if (s.indexOf("/") >= 0) {
    const bits = s.split("/");
    if (bits.length === 3) {
      const a = parseInt(bits[0], 10), b = parseInt(bits[1], 10);
      let y = parseInt(bits[2], 10);
      if (y < 100) y += 2000;
      const day = a > 12 ? a : b;
      const month = (a > 12 ? b : a) - 1;
      const t = Date.UTC(y, month, day);
      if (!isNaN(t)) return t;
    }
  }
  return Number.NEGATIVE_INFINITY;
}

function sortContextPillarsByDate(pillars) {
  return pillars.slice().sort(function(a, b) {
    const diff = contextDateSortKey(b) - contextDateSortKey(a);
    if (diff !== 0) return diff;
    return phrLabel(a).localeCompare(phrLabel(b));
  });
}

function phrPillarCategoryClass(pillar) {
  const cat = pillar.category || (pillar.metric || "").replace(/^national_/, "").replace(/^provincial_/, "");
  if (!cat) return "";
  return "pillar-" + cat.replace(/_/g, "-");
}

function phrLabel(pillar) {
  const key = (pillar.metric || "").replace(/^national_/, "").replace(/^provincial_/, "");
  const labels = t("phr");
  if (labels && typeof labels === "object" && labels[key]) return labels[key];
  return pillar.label || key;
}

function phrScopeStamp(pillar) {
  if (pillar && pillar.scope_tag && pillar.scope !== "national" && pillar.scope !== "zone") {
    return pillar.scope_tag;
  }
  if (!pillar) return "";
  if (pillar.scope === "national") return t("scope_tags.national");
  if (pillar.scope === "provincial" && pillar.province) {
    return String(pillar.province).toUpperCase();
  }
  if (pillar.scope === "zone") return t("scope_tags.health_zone");
  return pillar.scope_tag || "";
}

function renderContextPillarHtml(pillar, opts) {
  opts = opts || {};
  const catClass = phrPillarCategoryClass(pillar);
  let meta = "";
  if (!opts.hideScopeTag) {
    const stamp = phrScopeStamp(pillar);
    if (stamp) meta = "<span class='scope-tag'>" + escHtml(stamp) + "</span>";
  }
  const dateStr = formatContextDate(pillar.date);
  if (dateStr) meta += "<span>" + t("ui.context_as_of") + " " + escHtml(dateStr) + "</span>";
  const metaBlock = meta ? "<div class='context-meta'>" + meta + "</div>" : "";
  return (
    "<div class='context-pillar " + catClass + "'>" +
      "<h4>" + escHtml(phrLabel(pillar)) + "</h4>" +
      metaBlock +
      "<p>" + escHtml(pillar.text) + "</p>" +
    "</div>"
  );
}

function zoneFeatureProps(nom) {
  for (const feat of PAYLOAD.geometry.features) {
    if (feat.properties.nom === nom) {
      return feat.properties;
    }
  }
  return null;
}

function zoneDisplayName(nom) {
  const props = zoneFeatureProps(nom);
  return props ? (props.name || nom) : nom;
}

function zoneProvince(nom) {
  const props = zoneFeatureProps(nom);
  return props ? (props.province || null) : null;
}

function phrContext() {
  const byLang = (I18N.phr_context || PAYLOAD.phr_context_by_lang || null);
  if (byLang && (byLang.en || byLang.fr)) {
    return byLang[currentLang] || byLang.en || {national: [], by_nom: {}};
  }
  const legacy = PAYLOAD.phr_context || {};
  if (legacy.national || legacy.by_nom) return legacy;
  return {national: [], by_nom: {}};
}

function filterRollupsForContext(nom) {
  const allRollups = phrContext().national || [];
  if (!nom) {
    return allRollups.filter(function(p) { return p.scope === "national"; });
  }
  const province = zoneProvince(nom);
  return allRollups.filter(function(p) {
    if (p.scope === "national") return true;
    if (p.scope === "provincial" && province && p.province === province) return true;
    return false;
  });
}

function renderNationalContextPanel(nom) {
  const body = document.getElementById("context-national-body");
  if (!body) return;
  body.scrollTop = 0;
  const rollups = filterRollupsForContext(nom);
  if (!rollups.length) {
    body.className = "panel-body context-empty";
    body.innerHTML = nom
      ? "<p>" + t("ui.context_no_national_area") + "</p>"
      : "<p>" + t("ui.context_no_national") + "</p>";
    return;
  }
  body.className = "panel-body";
  body.innerHTML = sortContextPillarsByDate(rollups).map(function(p) {
    return renderContextPillarHtml(p);
  }).join("");
}

function clearContextSelection() {
  contextSelectedNom = null;
  renderContextPanel(null);
  refreshZoneSelection();
}

function selectContextZone(nom) {
  if (!nom) return;
  contextSelectedNom = nom;
  renderContextPanel(nom);
  refreshZoneSelection();
}

function renderContextPanel(nom) {
  const body = document.getElementById("context-body");
  const title = document.getElementById("context-title");
  if (!body) return;
  document.body.classList.toggle("context-zone-hovered", !!nom);
  renderNationalContextPanel(nom);
  body.scrollTop = 0;
  if (!nom) {
    if (title) title.textContent = t("ui.context_zone");
    body.className = "panel-body context-empty";
    body.innerHTML = "<p>" + t("ui.context_click_zone") + "</p>";
    return;
  }
  const zonePillars = (phrContext().by_nom || {})[nom] || [];
  const displayName = zoneDisplayName(nom);
  if (title) title.textContent = displayName;
  if (!zonePillars.length) {
    body.className = "panel-body context-empty";
    body.innerHTML = "<p>" + tf("ui.context_no_zone", {zone: escHtml(displayName)}) + "</p>";
    return;
  }
  body.className = "panel-body";
  body.innerHTML = sortContextPillarsByDate(zonePillars).map(function(p) {
    return renderContextPillarHtml(p, {hideScopeTag: true});
  }).join("");
}

function showProvinceOutlines() {
  if (!map.hasLayer(provinceOutlineLayer)) {
    provinceOutlineLayer.addTo(map);
  }
  provinceOutlineLayer.bringToFront();
  applyProvinceOutlineStyles(null);
}

function hideProvinceOutlines() {
  if (map.hasLayer(provinceOutlineLayer)) {
    map.removeLayer(provinceOutlineLayer);
  }
  // Clear the ring explicitly rather than letting applyProvinceOutlineStyles()
  // infer it from state. Callers reach here BEFORE clearing trendsSelectedKey
  // and before activeView moves off "trends" (see leaveTrendsView), so the
  // inference would re-draw the ring instead of removing it -- and the ring
  // lives in its own pane, so dropping provinceOutlineLayer does not take it
  // with us. Unreachable today (tab switches are full page loads), but live
  // the moment soft navigation lands.
  provinceRings.clear();
  applyProvinceOutlineStyles(null);
}

// --- Map / Trends / Context tab switching ---
let savedMapLayerId = null;
let trendsDateIdx = 0;
let trendsSliderTimer = null;
let trendsSliderAnimating = false;
let trendsSliderPointerDown = false;
const TRENDS_SLIDER_STEP_MS = 150;

function setTrendsSliderBusy(busy) {
  document.body.classList.toggle("trends-slider-busy", !!busy);
}

function syncTrendsSliderBusy() {
  setTrendsSliderBusy(trendsSliderAnimating || trendsSliderPointerDown);
}

function stopTrendsSliderAnimation() {
  if (trendsSliderTimer != null) {
    clearInterval(trendsSliderTimer);
    trendsSliderTimer = null;
  }
  trendsSliderAnimating = false;
  syncTrendsSliderBusy();
  syncTrendsPlayButton();
}

function applyTrendsDateIdx(idx) {
  const ts = PAYLOAD.confirmed_timeseries;
  const slider = document.getElementById("trends-date-slider");
  if (!ts || !ts.dates || !ts.dates.length) return;
  trendsDateIdx = Math.max(0, Math.min(idx, ts.dates.length - 1));
  if (slider) slider.value = String(trendsDateIdx);
  updateTrendsDateLabel();
  recomputeTrendsMap();
}

function playTrendsSliderAnimation() {
  stopTrendsSliderAnimation();
  const ts = PAYLOAD.confirmed_timeseries;
  if (!ts || !ts.dates || ts.dates.length < 2) return;
  trendsSliderAnimating = true;
  syncTrendsSliderBusy();
  syncTrendsPlayButton();
  let idx = 0;
  applyTrendsDateIdx(0);
  trendsSliderTimer = setInterval(function() {
    if (activeView !== "trends") {
      stopTrendsSliderAnimation();
      return;
    }
    idx += 1;
    if (idx >= ts.dates.length) {
      applyTrendsDateIdx(ts.dates.length - 1);
      stopTrendsSliderAnimation();
      return;
    }
    applyTrendsDateIdx(idx);
  }, TRENDS_SLIDER_STEP_MS);
}

function getTrendsConfirmedAt(nom, dateIdx) {
  const ts = PAYLOAD.confirmed_timeseries;
  if (!ts || !ts.by_nom) return 0;
  const series = ts.by_nom[nom];
  if (!series || dateIdx < 0 || dateIdx >= series.length) return 0;
  return series[dateIdx];
}

function initTrendsLegendBar() {
  const ts = PAYLOAD.confirmed_timeseries;
  if (!ts) return;
  const layer = getLayer("obs::confirmed");
  const palette = PALETTES[(layer && layer.palette) || "reds"] || REDS;
  const bar = document.getElementById("trends-legend-bar");
  if (!bar) return;
  const stops = [];
  const N = 32;
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    stops.push(rgb(lerpColor(palette, t)) + " " + Math.round(t * 100) + "%");
  }
  bar.style.background = "linear-gradient(to right, " + stops.join(", ") + ")";
  const lo = ts.min_positive || 1;
  const hi = ts.max_confirmed || 1;
  const mid = Math.sqrt(lo * hi);
  const ticks = document.getElementById("trends-legend-ticks");
  if (ticks) {
    ticks.innerHTML =
      "<span>" + fmtLegend(lo, "int") + "</span>" +
      "<span>" + fmtLegend(mid, "int") + "</span>" +
      "<span>" + fmtLegend(hi, "int") + "</span>";
  }
  const scaleEl = document.getElementById("trends-legend-scale");
  if (scaleEl) scaleEl.textContent = t("ui.trends_scale_log");
}

function syncTrendsModeToggle() {
  const btns = document.querySelectorAll(".trends-mode-btn");
  btns.forEach(function (b) {
    const on = b.getAttribute("data-mode") === trendsColorMode;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
  const title = document.getElementById("trends-legend-title");
  const cumu = document.getElementById("trends-cumulative-legend");
  const rec = document.getElementById("trends-recency-legend");
  const recency = trendsColorMode === "recency";
  if (cumu) cumu.style.display = recency ? "none" : "";
  if (rec) rec.style.display = recency ? "" : "none";
  if (title) {
    const strong = title.querySelector("strong");
    if (strong) {
      strong.setAttribute("data-i18n", recency ? "ui.trends_recency_title" : "ui.trends_confirmed_title");
      strong.textContent = t(recency ? "ui.trends_recency_title" : "ui.trends_confirmed_title");
    }
  }
}

function setTrendsColorMode(mode) {
  const next = mode === "recency" && trendsRecencyAvailable() ? "recency" : "cumulative";
  if (next === trendsColorMode) { syncTrendsModeToggle(); return; }
  trendsColorMode = next;
  syncTrendsModeToggle();
  // Re-paint the current frame without restarting the animation.
  if (activeView === "trends") geoLayer.setStyle(styleFn);
}

function updateTrendsDateLabel() {
  const ts = PAYLOAD.confirmed_timeseries;
  const label = document.getElementById("trends-date-label");
  if (!label || !ts || !ts.dates || !ts.dates.length) return;
  const iso = ts.dates[trendsDateIdx];
  const raw = (ts.date_labels && ts.date_labels[iso]) || iso;
  label.textContent = t("ui.trends_as_of").replace("—", formatContextDate(raw));
}

function recomputeTrendsMap() {
  const ts = PAYLOAD.confirmed_timeseries;
  if (!ts || !ts.dates || !ts.dates.length) return;
  const layer = getLayer("obs::confirmed") || { palette: "reds" };
  currentValues.clear();
  for (const feat of PAYLOAD.geometry.features) {
    const ref = feat.properties.nom;
    currentValues.set(ref, getTrendsConfirmedAt(ref, trendsDateIdx));
  }
  const lo = ts.min_positive || 1;
  let hi = ts.max_confirmed || 1;
  if (hi <= lo) hi = lo + 1;
  currentDomain = {
    min: lo,
    max: hi,
    isLog: true,
    palette: PALETTES[layer.palette] || REDS,
  };
  // No selection re-paint needed: the ring lives in its own pane and survives
  // this restyle untouched. This fires on every time-slider tick.
  geoLayer.setStyle(styleFn);
}

function restoreCaseMarkersForView(view) {
  if (view === "trends") {
    map.removeLayer(caseLayer);
    return;
  }
  if (view === "genomic-epidemiology") {
    // The genomic tab shows the per-zone genome-count circles; the active-case
    // markers sit at the same zone centroids and would overlap them, so keep
    // them off here regardless of the (hidden) show-cases toggle.
    map.removeLayer(caseLayer);
    return;
  }
  if (view === "epi-trends") {
    const epiCases = document.getElementById("epi-show-cases");
    const on = epiCases ? epiCases.checked : (showCasesBox && showCasesBox.checked);
    if (on) caseLayer.addTo(map);
    else map.removeLayer(caseLayer);
    return;
  }
  if (showCasesBox.checked) caseLayer.addTo(map);
  else map.removeLayer(caseLayer);
}

function restoreFlowArcsForView(view) {
  if (view !== "map" && view !== "epi-trends") {
    clearFlowArcs();
    return;
  }
  if (flowArcsOverlayActive()) {
    renderFlowArcs(flowHubNom, flowArcLayerDef());
  } else {
    clearFlowArcs();
  }
}

function enterTrendsView() {
  savedMapLayerId = layerSelect.value;
  clearFlowArcs();
  layerSelect.value = "obs::confirmed";
  map.removeLayer(caseLayer);
  showProvinceOutlines();
  clearContextSelection();
  const ts = PAYLOAD.confirmed_timeseries;
  const legendPanel = document.getElementById("trends-legend");
  if (!ts || !ts.dates || !ts.dates.length) {
    if (legendPanel) legendPanel.style.display = "none";
    recompute();
  } else {
    if (legendPanel) legendPanel.style.display = "";
    // Always enter in the cumulative view; the toggle opts into recency.
    trendsColorMode = "cumulative";
    const toggle = document.getElementById("trends-mode-toggle");
    if (toggle) toggle.style.display = trendsRecencyAvailable() ? "" : "none";
    syncTrendsModeToggle();
    initTrendsLegendBar();
    const slider = document.getElementById("trends-date-slider");
    if (slider) slider.max = String(ts.dates.length - 1);
    // Auto-play from the start every time the tab is opened, rather than
    // jumping straight to the latest sitrep and waiting for a manual Play click.
    playTrendsSliderAnimation();
  }
  const activeScopeBtn = document.querySelector(".trends-scope-btn.active");
  setTrendsScope((activeScopeBtn && activeScopeBtn.getAttribute("data-scope")) || "national");
  map.invalidateSize({animate: false});
}

function leaveTrendsView() {
  stopTrendsSliderAnimation();
  trendsSliderPointerDown = false;
  setTrendsSliderBusy(false);
  hideProvinceOutlines();
  trendsSelectedKey = null;
  renderTrendsPlots();
  if (savedMapLayerId) {
    layerSelect.value = savedMapLayerId;
    recompute();
  }
  refreshZoneSelection();
}

function setActiveView(view) {
  if (view === activeView) return;
  if (view === "trends") {
    enterTrendsView();
  } else if (view === "epi-trends") {
    if (activeView === "trends") leaveTrendsView();
    else {
      hideProvinceOutlines();
      clearContextSelection();
    }
    enterEpiTrendsView();
  } else if (view === "context") {
    clearFlowArcs();
    if (activeView === "trends") leaveTrendsView();
    else if (activeView === "epi-trends") leaveEpiTrendsView();
    else {
      hideProvinceOutlines();
      renderTrendsPanel(null);
    }
    clearContextSelection();
  } else {
    if (activeView === "trends") leaveTrendsView();
    else if (activeView === "epi-trends") leaveEpiTrendsView();
    else {
      hideProvinceOutlines();
      clearContextSelection();
    }
  }
  activeView = view;
  refreshZoneSelection();
  restoreCaseMarkersForView(view);
  restoreFlowArcsForView(view);
  document.body.classList.toggle("view-map", view === "map");
  document.body.classList.toggle("view-trends", view === "trends");
  document.body.classList.toggle("view-epi-trends", view === "epi-trends");
  document.body.classList.toggle("view-context", view === "context");
  syncMatrixUi();
  document.querySelectorAll(".view-tab").forEach(function(btn) {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  if (view === "epi-trends") {
    map.invalidateSize();
    recomputeEpiTrends();
  } else if (view === "trends") {
    map.invalidateSize();
  } else if (view === "map") {
    map.invalidateSize();
    recompute();
  } else if (view === "genomic-epidemiology") {
    map.invalidateSize();
    // Show the per-zone genome markers: the genomic tab links them to the tree
    // tips (click a marker → select that zone's tips). This is the only view
    // that shows them -- the snapshot map's layer box has no genome toggle.
    // Guarded on the layer/markers existing (built above; absent if no genome data).
    if (typeof genomeLayer !== "undefined" && GENOME_SEQUENCES.length) {
      genomeLayer.addTo(map);
    }
  }
}

// NOTE: view switching used to happen here via a click handler on
// ".view-tab" buttons that called setActiveView() without a page reload.
// Now that each view is a separate page, ".view-tab" elements are real
// <a href="..."> links (see common/chrome.py) and navigation is handled by
// the browser. setActiveView() is instead invoked once on load, below, to
// initialise whichever view this page represents (see "page bootstrap").
//
// Clicking the tab for the view you're already on would otherwise reload the
// same page needlessly; cancel that navigation so the current tab stays put.
document.querySelectorAll(".view-tab").forEach(function(tab) {
  tab.addEventListener("click", function(ev) {
    if (tab.classList.contains("active")) ev.preventDefault();
  });
});

(function wireTrendsDateSlider() {
  const slider = document.getElementById("trends-date-slider");
  if (!slider) return;
  function onUserSliderChange() {
    if (activeView !== "trends") return;
    stopTrendsSliderAnimation();
    applyTrendsDateIdx(parseInt(slider.value, 10) || 0);
  }
  function onSliderPointerDown() {
    trendsSliderPointerDown = true;
    syncTrendsSliderBusy();
    stopTrendsSliderAnimation();
  }
  function onSliderPointerUp() {
    trendsSliderPointerDown = false;
    syncTrendsSliderBusy();
  }
  slider.addEventListener("input", onUserSliderChange);
  slider.addEventListener("pointerdown", onSliderPointerDown);
  slider.addEventListener("pointerup", onSliderPointerUp);
  slider.addEventListener("pointercancel", onSliderPointerUp);
  const playBtn = document.getElementById("trends-play-btn");
  if (playBtn) {
    playBtn.addEventListener("click", function() {
      if (activeView !== "trends") return;
      if (trendsSliderAnimating) stopTrendsSliderAnimation();
      else playTrendsSliderAnimation();
    });
  }
  syncTrendsPlayButton();
})();

// Single source of truth for "make this scope the active one": syncs the
// segmented-control buttons and updates the scope state together. Both the
// button click handler below and ZONE_SEARCH_VIEWS.trends.select() call it, so
// the button UI and trendsScope can never disagree.
function activateTrendsScope(scope) {
  document.querySelectorAll(".trends-scope-btn").forEach(function(b) {
    b.classList.toggle("active", b.getAttribute("data-scope") === scope);
  });
  setTrendsScope(scope);
}

(function wireTrendsPanelUi() {
  document.querySelectorAll(".trends-scope-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      activateTrendsScope(btn.getAttribute("data-scope") || "national");
    });
  });
  document.querySelectorAll(".trends-mode-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setTrendsColorMode(btn.getAttribute("data-mode"));
    });
  });
  activateTrendsScope("national");
})();

// --- Trends tab map/plots split handle (mirrors wireEpiTrendsUi's
// #epi-split-handle drag logic, with its own CSS var + storage key so the
// Trends and Spatial Risk tabs remember independent split positions). ---
(function wireTrendsSplitUi() {
  const splitHandle = document.getElementById("trends-split-handle");
  const TRENDS_SPLIT_MIN = 28;
  const TRENDS_SPLIT_MAX = 72;
  const TRENDS_SPLIT_KEY = "bdbv_trends_panel_width_pct";

  function clampTrendsSplitPct(pct) {
    return Math.max(TRENDS_SPLIT_MIN, Math.min(TRENDS_SPLIT_MAX, pct));
  }

  function applyTrendsSplitPct(pct, invalidate) {
    const value = clampTrendsSplitPct(pct);
    document.documentElement.style.setProperty("--trends-panel-width", value + "%");
    if (splitHandle) splitHandle.setAttribute("aria-valuenow", String(Math.round(value)));
    try { localStorage.setItem(TRENDS_SPLIT_KEY, String(value)); } catch (e) {}
    if (invalidate && activeView === "trends") {
      map.invalidateSize({animate: false});
    }
    return value;
  }

  function readStoredTrendsSplit() {
    try {
      const raw = localStorage.getItem(TRENDS_SPLIT_KEY);
      if (raw == null || raw === "") return 40;
      const n = Number(raw);
      return Number.isFinite(n) ? n : 40;
    } catch (e) {
      return 40;
    }
  }

  applyTrendsSplitPct(readStoredTrendsSplit(), false);
  if (!splitHandle) return;
  splitHandle.setAttribute("aria-valuemin", String(TRENDS_SPLIT_MIN));
  splitHandle.setAttribute("aria-valuemax", String(TRENDS_SPLIT_MAX));
  let dragging = false;
  function splitFromClientX(clientX) {
    const w = window.innerWidth || document.documentElement.clientWidth || 1;
    // Panel is on the right: width% = distance from right edge.
    return clampTrendsSplitPct(((w - clientX) / w) * 100);
  }
  function onPointerMove(e) {
    if (!dragging) return;
    if (e.cancelable) e.preventDefault();
    const x = e.touches && e.touches[0] ? e.touches[0].clientX : e.clientX;
    applyTrendsSplitPct(splitFromClientX(x), false);
  }
  function onPointerUp() {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("trends-splitting");
    window.removeEventListener("mousemove", onPointerMove);
    window.removeEventListener("mouseup", onPointerUp);
    window.removeEventListener("touchmove", onPointerMove);
    window.removeEventListener("touchend", onPointerUp);
    window.removeEventListener("touchcancel", onPointerUp);
    if (activeView === "trends") map.invalidateSize({animate: false});
  }
  function onPointerDown(e) {
    if (activeView !== "trends") return;
    dragging = true;
    document.body.classList.add("trends-splitting");
    const x = e.touches && e.touches[0] ? e.touches[0].clientX : e.clientX;
    applyTrendsSplitPct(splitFromClientX(x), false);
    window.addEventListener("mousemove", onPointerMove);
    window.addEventListener("mouseup", onPointerUp);
    window.addEventListener("touchmove", onPointerMove, {passive: false});
    window.addEventListener("touchend", onPointerUp);
    window.addEventListener("touchcancel", onPointerUp);
    if (e.cancelable) e.preventDefault();
  }
  splitHandle.addEventListener("mousedown", onPointerDown);
  splitHandle.addEventListener("touchstart", onPointerDown, {passive: false});
  splitHandle.addEventListener("keydown", function(e) {
    if (activeView !== "trends") return;
    let delta = 0;
    if (e.key === "ArrowLeft") delta = 2;
    else if (e.key === "ArrowRight") delta = -2;
    else if (e.key === "Home") {
      applyTrendsSplitPct(40, true);
      e.preventDefault();
      return;
    } else return;
    const cur = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--trends-panel-width")
    ) || 40;
    applyTrendsSplitPct(cur + delta, true);
    e.preventDefault();
  });
})();

// --- active-case markers ---
const ACTIVE_CASES = PAYLOAD.active_case_markers || [];
const GENOME_SEQUENCES = PAYLOAD.genome_sequence_markers || [];
const GENOME_MAX_COUNT = GENOME_SEQUENCES.reduce(function(max, g) {
  return Math.max(max, g.count || 0);
}, 1);
const caseIcon = L.divIcon({className:"", html:"<div class='case-icon'></div>", iconSize:[14,14]});
const caseLayer = L.layerGroup();
const genomeLayer = L.layerGroup();

// Markers (active-case, genome) and arcs (flow, epi-link) bind their tooltip
// once and let Leaflet open it on hover / close it on mouseout. Whipping the
// cursor over a dense cluster fires a burst of mouseovers but the browser drops
// most of the matching mouseouts, so their tooltips pile up open -- a "bunch"
// of stranded tooltips -- independent of any map movement. Enforce the natural
// invariant that only one hover tooltip shows at a time: whenever any overlay
// tooltip opens, close every other open one. Leaflet fires "tooltipopen" on the
// map with e.tooltip._source pointing at the layer that just opened.
map.on("tooltipopen", function (e) {
  const src = e.tooltip && e.tooltip._source;
  [caseLayer, genomeLayer, flowArcLayer, epiLinkLayer].forEach(function (grp) {
    grp.eachLayer(function (l) {
      // Guard on a tooltip actually being bound before isTooltipOpen():
      // flow-arc wing markers have none, and Leaflet's isTooltipOpen()
      // dereferences this._tooltip unconditionally, so calling it on a
      // tooltip-less layer throws. An uncaught throw here aborts Leaflet's
      // click-event dispatch, which swallows the case-marker click that would
      // otherwise select the zone (see handleCaseMarkerClick). Mirror the same
      // guard used in tearDownHoverDecoration().
      if (l !== src && l.getTooltip && l.getTooltip() && l.isTooltipOpen()) l.closeTooltip();
    });
  });
});

const showCasesBox = document.getElementById("show-cases");

function genomeIcon(count) {
  const minD = 10;
  const maxD = 38;
  const t = GENOME_MAX_COUNT > 1 ? (count - 1) / (GENOME_MAX_COUNT - 1) : 1;
  const d = Math.round(minD + t * (maxD - minD));
  return L.divIcon({
    className: "",
    html: "<div class='genome-icon' style='width:" + d + "px;height:" + d + "px;'></div>",
    iconSize: [d, d],
    iconAnchor: [d / 2, d / 2],
  });
}

// The genome markers are genomic-tab-only, so the layer box carries a single
// marker toggle (active cases) and there is no cross-layer exclusion to keep.
function syncCaseMarkerToggle() {
  if (showCasesBox.checked) caseLayer.addTo(map);
  else map.removeLayer(caseLayer);
}

function caseMarkerTooltip(c) {
  const row = function(label, val) {
    return "<div class='case-tt-row'><span>" + label + "</span><span>" + fmt(Number(val) || 0) + "</span></div>";
  };
  return (
    "<strong>" + (c.name || t("ui.case_tooltip.unnamed")) + "</strong>" +
    row(t("ui.case_tooltip.suspected_cases"), c.suspected) +
    row(t("ui.case_tooltip.confirmed_cases"), c.confirmed) +
    row(t("ui.case_tooltip.confirmed_deaths"), c.confirmed_deaths) +
    // Confirmed count is harmonised (line list ∪ sitrep); suspected/deaths are
    // sitrep only — label the mixed provenance so the numbers aren't misread.
    "<div class='case-tt-source' style='margin-top:5px;padding-top:4px;" +
    "border-top:1px solid rgba(128,128,128,0.35);color:#9aa0a6;font-size:10px'>" +
    t("ui.case_tooltip.source_note") + "</div>"
  );
}

function genomeMarkerTooltip(g) {
  return (
    "<strong>" + (g.name || t("ui.case_tooltip.unnamed")) + "</strong><br/>" +
    t("ui.genome_tooltip").replace("{n}", g.count)
  );
}

function refreshMarkerTooltips() {
  caseLayer.eachLayer(function(m) {
    if (m._bdbvCase) m.setTooltipContent(caseMarkerTooltip(m._bdbvCase));
  });
  genomeLayer.eachLayer(function(m) {
    if (m._bdbvGenome) m.setTooltipContent(genomeMarkerTooltip(m._bdbvGenome));
  });
}

// A case marker sits in the marker pane above its zone polygon and (unlike a
// path) does not bubble clicks, so without this it would swallow the click and
// leave the zone unselectable via its own case dot. One marker == one zone
// (c.nom), so route the click to the same select/toggle logic as clicking the
// polygon in whichever view is active. Returns true if it handled the click.
function handleCaseMarkerClick(nom) {
  if (!nom) return false;
  if (activeView === "epi-trends") {
    setEpiSelected(nom === epiSelectedNom ? null : nom);
    return true;
  }
  if (activeView === "context") {
    if (nom === contextSelectedNom) clearContextSelection();
    else {
      const lyr = findGeoLayerByNom(nom);
      if (lyr) selectContextZone(nom);
    }
    return true;
  }
  if (activeView === "map") {
    setMapSelection(nom);
    return true;
  }
  return false;
}

for (const c of ACTIVE_CASES) {
  if (!isFinite(c.lat) || !isFinite(c.lon)) continue;
  const m = L.marker([c.lat, c.lon], {icon: caseIcon});
  m._bdbvCase = c;
  m.bindTooltip(caseMarkerTooltip(c), {direction:"top", offset:[0,-8]});
  m.on("click", function(e) {
    if (handleCaseMarkerClick(c.nom)) L.DomEvent.stop(e);
  });
  caseLayer.addLayer(m);
}

for (const g of GENOME_SEQUENCES) {
  if (!isFinite(g.lat) || !isFinite(g.lon)) continue;
  const m = L.marker([g.lat, g.lon], {icon: genomeIcon(g.count)});
  m._bdbvGenome = g;
  m.bindTooltip(genomeMarkerTooltip(g), {direction:"top", offset:[0,-8]});
  // On the genomic view a marker click selects that zone's tip-set (routed to the
  // genomic coordinator via the generic hook; genomic.js owns the tip logic).
  m.on("click", function(e) {
    if (activeView === "genomic-epidemiology" && genomicMapHooks) {
      genomicMapHooks._emitMarkerClick(g.nom);
      L.DomEvent.stop(e);
    }
  });
  genomeLayer.addLayer(m);
}

// --- Generic map hooks for per-tab modules (currently the genomic tab) ---
// Deliberately tip-agnostic (design R6): the shared engine exposes zone-level
// selection subscribe/emit + zone highlighting + the raw per-zone genome markers.
// ALL tip logic (which zone maps to which tips, tip highlighting) lives in
// genomic.js. genomic.js reads window.__bdbvMapHooks after engine.js has run.
genomicMapHooks = (function () {
  let onZoneClickCb = null, onMarkerClickCb = null, onBackgroundClickCb = null;
  return {
    map: map,
    // Per-zone genome markers ({nom,name,lat,lon,count}); genomic.js joins these
    // zones to the tree tips. A defensive copy so callers can't mutate ours.
    genomeMarkers: GENOME_SEQUENCES.map(function (g) { return { nom: g.nom, name: g.name, count: g.count }; }),
    // Registration doubles as the genomic readiness signal: it happens in
    // startCoordinator(), i.e. only once the tree/tip data has resolved. Until
    // then _emitZoneClick no-ops, so the search would zoom the map and select
    // nothing -- and would do so forever if the payload is absent or the tree
    // never mounts. So #zone-search starts hidden on this view and appears
    // here. Hiding rather than disabling means a never-mounting tree leaves no
    // broken-looking box. _emitMarkerClick shares this coordinator, so this
    // one gate covers every genomic entry point.
    //
    // This is the ONE place the search reaches into these otherwise
    // tip-agnostic hooks; it is deliberate, not drift.
    onZoneClick: function (cb) {
      onZoneClickCb = cb;
      const box = document.getElementById("zone-search");
      if (box) box.classList.add("zone-search-ready");
    },
    onMarkerClick: function (cb) { onMarkerClickCb = cb; },
    onBackgroundClick: function (cb) { onBackgroundClickCb = cb; },
    // opts is forwarded untouched; the search passes {toggle:false} so a
    // repeat search selects rather than deselecting. See genomic.js selectZone.
    _emitZoneClick: function (nom, opts) { if (onZoneClickCb) onZoneClickCb(nom, opts); },
    _emitMarkerClick: function (nom) { if (onMarkerClickCb) onMarkerClickCb(nom); },
    _emitBackgroundClick: function () { if (onBackgroundClickCb) onBackgroundClickCb(); },
    // Outline a set of zones (by canonical nom) on the backdrop map, and emphasise
    // their genome markers. Pass [] to clear. Survives zoom via styleFn.
    highlightZones: function (noms) {
      genomicHighlightNoms = (noms || []).slice();
      geoLayer.setStyle(styleFn);
      const sel = {};
      genomicHighlightNoms.forEach(function (n) { sel[n] = true; });
      genomeLayer.eachLayer(function (m) {
        const el = m.getElement && m.getElement();
        if (el && m._bdbvGenome) el.classList.toggle("genome-marker-sel", !!sel[m._bdbvGenome.nom]);
      });
      refreshZoneSelection();
    },
  };
})();
window.__bdbvMapHooks = genomicMapHooks;

showCasesBox.addEventListener("change", function() {
  const epiCases = document.getElementById("epi-show-cases");
  if (epiCases) epiCases.checked = showCasesBox.checked;
  syncCaseMarkerToggle();
  if (activeView === "epi-trends") restoreCaseMarkersForView("epi-trends");
});

// --- Flowminder in/out flow arcs (toggle overlay) ---
const showFlowArcsBox = document.getElementById("show-flow-arcs");
const showFlowArcsRow = document.getElementById("show-flow-arcs-row");
let flowArcsUserPref = true;
if (!PAYLOAD.flow_arcs_available || !FLOW_ARC_LAYER) {
  if (showFlowArcsRow) showFlowArcsRow.style.display = "none";
  flowArcsUserPref = false;
} else if (showFlowArcsBox) {
  if (showFlowArcsRow) showFlowArcsRow.style.display = "";
  showFlowArcsBox.checked = true;
  flowArcsUserPref = true;
  showFlowArcsBox.addEventListener("change", function() {
    flowArcsUserPref = !!showFlowArcsBox.checked;
    recompute();
    syncMatrixUi();
  });
}

// --- Epidemiological trends controls ---
(function wireEpiTrendsUi() {
  const tbody = document.getElementById("epi-trends-tbody");
  const tab = document.querySelector('.view-tab[data-view="epi-trends"]');
  const splitHandle = document.getElementById("epi-split-handle");
  const EPI_SPLIT_MIN = 28;
  const EPI_SPLIT_MAX = 72;
  const EPI_SPLIT_KEY = "bdbv_epi_panel_width_pct";

  function clampEpiSplitPct(pct) {
    return Math.max(EPI_SPLIT_MIN, Math.min(EPI_SPLIT_MAX, pct));
  }

  function applyEpiSplitPct(pct, invalidate) {
    const value = clampEpiSplitPct(pct);
    document.documentElement.style.setProperty("--epi-panel-width", value + "%");
    if (splitHandle) splitHandle.setAttribute("aria-valuenow", String(Math.round(value)));
    try { localStorage.setItem(EPI_SPLIT_KEY, String(value)); } catch (e) {}
    if (invalidate && activeView === "epi-trends") {
      map.invalidateSize({animate: false});
    }
    return value;
  }

  function readStoredEpiSplit() {
    try {
      const raw = localStorage.getItem(EPI_SPLIT_KEY);
      if (raw == null || raw === "") return 50;
      const n = Number(raw);
      return Number.isFinite(n) ? n : 50;
    } catch (e) {
      return 50;
    }
  }

  applyEpiSplitPct(readStoredEpiSplit(), false);
  if (splitHandle) {
    splitHandle.setAttribute("aria-valuemin", String(EPI_SPLIT_MIN));
    splitHandle.setAttribute("aria-valuemax", String(EPI_SPLIT_MAX));
    let dragging = false;
    function splitFromClientX(clientX) {
      const w = window.innerWidth || document.documentElement.clientWidth || 1;
      // Panel is on the right: width% = distance from right edge.
      return clampEpiSplitPct(((w - clientX) / w) * 100);
    }
    function onPointerMove(e) {
      if (!dragging) return;
      if (e.cancelable) e.preventDefault();
      const x = e.touches && e.touches[0] ? e.touches[0].clientX : e.clientX;
      applyEpiSplitPct(splitFromClientX(x), false);
    }
    function onPointerUp() {
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove("epi-splitting");
      window.removeEventListener("mousemove", onPointerMove);
      window.removeEventListener("mouseup", onPointerUp);
      window.removeEventListener("touchmove", onPointerMove);
      window.removeEventListener("touchend", onPointerUp);
      window.removeEventListener("touchcancel", onPointerUp);
      if (activeView === "epi-trends") map.invalidateSize({animate: false});
    }
    function onPointerDown(e) {
      if (activeView !== "epi-trends") return;
      dragging = true;
      document.body.classList.add("epi-splitting");
      const x = e.touches && e.touches[0] ? e.touches[0].clientX : e.clientX;
      applyEpiSplitPct(splitFromClientX(x), false);
      window.addEventListener("mousemove", onPointerMove);
      window.addEventListener("mouseup", onPointerUp);
      window.addEventListener("touchmove", onPointerMove, {passive: false});
      window.addEventListener("touchend", onPointerUp);
      window.addEventListener("touchcancel", onPointerUp);
      if (e.cancelable) e.preventDefault();
    }
    splitHandle.addEventListener("mousedown", onPointerDown);
    splitHandle.addEventListener("touchstart", onPointerDown, {passive: false});
    splitHandle.addEventListener("keydown", function(e) {
      if (activeView !== "epi-trends") return;
      let delta = 0;
      if (e.key === "ArrowLeft") delta = 2;
      else if (e.key === "ArrowRight") delta = -2;
      else if (e.key === "Home") {
        applyEpiSplitPct(50, true);
        e.preventDefault();
        return;
      } else return;
      const cur = parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--epi-panel-width")
      ) || 50;
      applyEpiSplitPct(cur + delta, true);
      e.preventDefault();
    });
  }

  if (!INVASION_RISK || !Object.keys(INVASION_ZONES).length) {
    if (tab) tab.style.display = "none";
    if (splitHandle) splitHandle.style.display = "none";
    return;
  }
  // Sortable column headers replace the old rank-by-RR/rank-by-priority
  // buttons -- click (or Enter/Space) any header to sort by it, click again
  // to reverse. See epiSortValue()/epiCompareValues()/epiSortedRows() and
  // updateEpiSortIndicators() for the ▲/▼ glyph.
  document.querySelectorAll("#epi-trends-table th[data-sort]").forEach(function(th) {
    function activateSort() {
      const key = th.getAttribute("data-sort");
      if (epiSortKey === key) {
        epiSortDir = epiSortDir === "asc" ? "desc" : "asc";
      } else {
        epiSortKey = key;
        epiSortDir = "asc";
      }
      updateEpiSortIndicators();
      renderEpiTrendsTable();
    }
    th.addEventListener("click", activateSort);
    th.addEventListener("keydown", function(e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      activateSort();
    });
  });
  updateEpiSortIndicators();
  if (tbody) {
    tbody.addEventListener("click", function(e) {
      const tr = e.target.closest("tr[data-nom]");
      if (!tr) return;
      const nom = tr.getAttribute("data-nom");
      setEpiSelected(nom);
      // Rows zoom, polygons do not (see the note above setTrendsSelection).
      // A row sits in a scrolling ranked table that is sorted by risk, not by
      // geography, so the zone it names is routinely nowhere near the current
      // viewport -- the same "can be offscreen" case the search box answers,
      // and the reason a polygon click is exempt does not apply.
      //
      // Only follow a selection that actually took: setEpiSelected() silently
      // clears when the zone is missing from INVASION_ZONES or hidden for the
      // active layer, and framing a zone that nothing ended up selecting is
      // worse than not moving at all.
      if (epiSelectedNom === nom) zoneSearchZoomTo({kind: "health_zone", id: nom});
    });
  }
  const epiCases = document.getElementById("epi-show-cases");
  if (epiCases) {
    epiCases.checked = !!(showCasesBox && showCasesBox.checked);
    epiCases.addEventListener("change", function() {
      if (showCasesBox) showCasesBox.checked = epiCases.checked;
      if (activeView === "epi-trends") restoreCaseMarkersForView("epi-trends");
      else syncCaseMarkerToggle();
    });
  }

  function triggerDownload(filename, href) {
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  const csvBtn = document.getElementById("epi-download-csv");
  if (csvBtn) {
    csvBtn.addEventListener("click", function() {
      const csv = (INVASION_RISK && INVASION_RISK.download_csv) || "";
      if (!csv) return;
      const blob = new Blob([csv], {type: "text/csv;charset=utf-8"});
      const url = URL.createObjectURL(blob);
      const stamp = (INVASION_RISK.cutoff_date || "data").replace(/-/g, "");
      triggerDownload("invasion_risk_model_estimates_" + stamp + ".csv", url);
      setTimeout(function() { URL.revokeObjectURL(url); }, 1500);
    });
  }

  const mapBtn = document.getElementById("epi-download-map");
  if (mapBtn) {
    mapBtn.addEventListener("click", function() {
      if (typeof html2canvas !== "function") {
        window.alert(t("ui.epi_download_map_unavailable"));
        return;
      }
      const hadCases = map.hasLayer(caseLayer);
      const hadSelection = epiSelectedNom;
      const prevCenter = map.getCenter();
      const prevZoom = map.getZoom();
      clearEpiLinks();
      clearFlowArcs();
      if (hadSelection) setEpiSelected(null);
      if (hadCases) map.removeLayer(caseLayer);
      hideEpiFloat();
      document.body.classList.add("epi-map-exporting");
      map.invalidateSize({animate: false});
      try {
        map.fitBounds(geoLayer.getBounds(), {
          padding: [28, 28],
          animate: false,
          maxZoom: 7,
        });
      } catch (err) {
        map.setView([-2.5, 23.5], 5, {animate: false});
      }
      setTimeout(function() {
        html2canvas(map.getContainer(), {
          useCORS: true,
          allowTaint: true,
          backgroundColor: "#ffffff",
          scale: 2,
        }).then(function(canvas) {
          const jpg = canvas.toDataURL("image/jpeg", 0.92);
          const stamp = (INVASION_RISK && INVASION_RISK.cutoff_date || "map").replace(/-/g, "");
          triggerDownload("invasion_risk_map_" + stamp + ".jpg", jpg);
        }).catch(function(err) {
          console.error(err);
          window.alert(t("ui.epi_download_map_unavailable"));
        }).finally(function() {
          document.body.classList.remove("epi-map-exporting");
          map.invalidateSize({animate: false});
          map.setView(prevCenter, prevZoom, {animate: false});
          if (hadCases && (
            (document.getElementById("epi-show-cases") || {}).checked ||
            (showCasesBox && showCasesBox.checked)
          )) {
            caseLayer.addTo(map);
          }
          if (hadSelection) setEpiSelected(hadSelection);
        });
      }, 180);
    });
  }
})();

// Default: total cases layer, active-case markers ON, flow arcs ON from Mongbwalu.
showCasesBox.checked = true;
caseLayer.addTo(map);

layerSelect.addEventListener("change", function() {
  // OSRM layers (travel time / road distance) render from the origin zone's
  // matrix row, which visually competes with the Flowminder in/out-flow arcs
  // radiating from the same origin — turn the arcs off automatically, then
  // restore the user's Flowminder preference when leaving those layers.
  if (showFlowArcsBox && PAYLOAD.flow_arcs_available && FLOW_ARC_LAYER) {
    if (layerUsesMatrix(getLayer(layerSelect.value))) {
      showFlowArcsBox.checked = false;
    } else if (flowArcsUserPref) {
      showFlowArcsBox.checked = true;
    }
  }
  recompute();
  syncMatrixUi();
});

// --- modal wiring (Methods + Terms) ---
// btnIds may be a single id or an array -- the header-info-popup's
// methods/terms buttons (narrow screens) open the same modals as the
// footer's Contributors/Methods and Terms buttons (wide screens).
function wireModal(modalId, btnIds, closeId) {
  const modal = document.getElementById(modalId);
  const closeBtn = document.getElementById(closeId);
  if (!modal) return;
  function open() {
    document.querySelectorAll(".modal.open").forEach(m => m.classList.remove("open"));
    modal.classList.add("open");
  }
  function close() { modal.classList.remove("open"); }
  (Array.isArray(btnIds) ? btnIds : [btnIds]).forEach(function(id) {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", open);
  });
  if (closeBtn) closeBtn.addEventListener("click", close);
  modal.addEventListener("click", function(e) {
    if (e.target === modal) close();
  });
}
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") {
    document.querySelectorAll(".modal.open").forEach(m => m.classList.remove("open"));
  }
});
wireModal("methods-modal", ["methods-btn", "header-methods-btn"], "methods-close");
wireModal("terms-modal", ["terms-btn", "header-terms-btn"], "terms-close");

// --- collapsible panels (zone info + layer controls + legend) ---
(function wirePanelToggles() {
  function setCollapsed(panel, btn, collapsed) {
    if (collapsed) {
      panel.classList.add("collapsed");
      btn.textContent = "+";
    } else {
      panel.classList.remove("collapsed");
      btn.textContent = "−";
    }
  }
  expandPanel = function(panelId) {
    const panel = document.getElementById(panelId);
    if (!panel || !panel.classList.contains("collapsed")) return;
    // #info is the one collapsible panel whose toggle is a bare id rather than
    // a .panel-toggle[data-target] -- see chrome.py. tests/test_zone_search.py
    // checks both forms so a new panel: entry cannot silently miss its toggle.
    const btn = panelId === "info"
      ? document.getElementById("info-toggle")
      : document.querySelector('.panel-toggle[data-target="' + panelId + '"]');
    if (btn) setCollapsed(panel, btn, false);
  };
  const infoPanel = document.getElementById("info");
  const infoBtn = document.getElementById("info-toggle");
  if (infoPanel && infoBtn) {
    infoBtn.addEventListener("click", function() {
      setCollapsed(infoPanel, infoBtn, !infoPanel.classList.contains("collapsed"));
    });
  }
  document.querySelectorAll(".panel-toggle").forEach(function(btn) {
    const panel = document.getElementById(btn.dataset.target);
    if (!panel) return;
    btn.addEventListener("click", function() {
      setCollapsed(panel, btn, !panel.classList.contains("collapsed"));
    });
  });
  if (window.matchMedia && window.matchMedia("(max-width: 700px)").matches) {
    if (infoPanel && infoBtn) setCollapsed(infoPanel, infoBtn, true);
    document.querySelectorAll(".panel-toggle").forEach(function(btn) {
      const panel = document.getElementById(btn.dataset.target);
      if (panel) setCollapsed(panel, btn, true);
    });
  }
})();

// The snapshot info box starts empty (placeholder) until a zone is focused.
// (The #info-body element keeps its `info-empty` class from chrome.py, and
// applyStaticI18n in initDashboardI18n fills it with the placeholder string.)

(function initDashboardI18n() {
  LAYERS = (I18N.layers && I18N.layers[currentLang]) || PAYLOAD.layers;
  applyStaticI18n();
  rebuildLayerSelect();
  buildTitleSub();
  buildTracker();
  buildModeledEstimateNote();
  updateLegalContent();
  layerSelect.value = "obs::total";
  applyMatrixOriginToLayers();
  rebuildLayerSelect();
  recompute();
  syncMatrixUi();
})();

// --- deep-linking via URL params, e.g. ?cases=1 ---
// Runs last so it overrides the defaults set above (cases ON, flow arcs ON).
// There is no ?genomes= param any more: the genome-count markers are shown by
// the Genomic Epidemiology tab only, so the snapshot map has nothing to toggle.
(function applyMarkerUrlParams() {
  const params = new URLSearchParams(window.location.search);
  function isTruthy(v) {
    return v !== null && !["0", "false", "no"].includes(v.toLowerCase());
  }
  const casesParam = params.get("cases");
  if (isTruthy(casesParam) && showCasesBox) {
    showCasesBox.checked = true;
    syncCaseMarkerToggle();
  }
})();

// --- page bootstrap (multi-page split) ---
// Each page's <body data-initial-view="..."> tells the shared engine which
// of the four views this page represents. The engine's default in-memory
// state (activeView = "map", body class "view-map") matches the snapshot
// page, so no extra work is needed there; every other page runs the same
// enter/leave transition logic that used to fire on tab click.
(function bootstrapInitialView() {
  const initialView = document.body.dataset.initialView || "map";
  if (initialView !== "map") {
    setActiveView(initialView);
  }
})();
