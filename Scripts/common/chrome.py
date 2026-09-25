"""
Shared HTML "chrome" for every dashboard page: <head>/CSS wiring, and the
body markup (title/tracker panel, language switcher, methods/terms modals,
nav bar, and -- for now -- every view's panel HTML, since the shared JS
engine still references all of it unconditionally regardless of which page
is loaded; see assets/engine.js's module docstring-equivalent comment and
the README's "Multi-page structure" section for why).

Each page module (Scripts/pages/*.py) calls render_page() with its view id;
this module handles everything that's identical across pages.
"""

from __future__ import annotations

import json

from common.paths import PAGE_FILENAMES
from common.theme import json_default

# view id -> nav label (kept in sync with locales/en.yaml + fr.yaml ui.view_*
# keys; the data-i18n attribute still drives the *displayed* text via the JS
# i18n layer, this label is only the no-JS/no-i18n fallback).
NAV_ITEMS = [
    ("map", "ui.view_map", "Current Snapshot"),
    ("trends", "ui.view_trends", "Epidemiological Trends"),
    ("epi-trends", "ui.view_epi_trends", "Spatial Risk"),
    ("context", "ui.view_context", "Public Health Context"),
    ("clinical-symptoms", "ui.view_clinical_symptoms", "Clinical Symptoms"),
    ("surveillance-testing", "ui.view_surveillance_testing", "Surveillance and Testing"),
    ("genomic-epidemiology", "ui.view_genomic_epidemiology", "Genomic Epidemiology"),
]

# Views with no real content yet -- just a "coming soon" stub panel (see
# #stub-<id> in BODY_TEMPLATE). They still get the full shared header/tabs/
# footer chrome and the full map engine + payload underneath (hidden via the
# "stub-view" body class below), matching every other page for now; see the
# README "Multi-page structure" section for why that engine/payload sharing
# exists and the trade-off it implies.
STUB_VIEWS = {"clinical-symptoms", "surveillance-testing"}

HEAD_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>__PAGE_TITLE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<link rel="stylesheet" href="__ASSETS_PREFIX__dashboard.css" />
__EXTRA_HEAD__
<script>
// Applies a saved Trends map/plots split *before* first paint, so a stored
// preference doesn't flash the CSS default (60:40) for a frame before
// engine.js gets around to overriding it later in the load. If nothing is
// stored, the CSS default stands -- this only ever narrows the gap between
// "what the stylesheet says" and "what the user last dragged it to".
(function() {
  try {
    var v = localStorage.getItem("bdbv_trends_panel_width_pct");
    if (v !== null && v !== "") {
      var n = parseFloat(v);
      if (isFinite(n)) {
        n = Math.max(28, Math.min(72, n));
        document.documentElement.style.setProperty("--trends-panel-width", n + "%");
      }
    }
  } catch (e) {}
})();
</script>
</head>
"""

BODY_TEMPLATE = r"""
<body class="view-__INITIAL_VIEW__ __EXTRA_BODY_CLASS__" data-initial-view="__INITIAL_VIEW__">
<header id="site-header">
  <div id="site-header-left">
    <h1 id="page-heading">DRC Ebola Bundibugyo - Epidemic Intelligence Dashboard</h1>
    <div class="sub" id="title-sub"></div>
    <!-- Narrow-screen only (see @media max-width:700px): replaces #title-sub
         with just the "dashboard updated" line + an info icon whose popup
         holds the rest (latest SitRep link, build tag) that title-sub shows
         inline on wider screens. -->
    <div id="header-narrow-row">
      <div class="sub" id="header-updated-line"></div>
      <!-- Narrow-screen copy of the language switch. The wide-screen one is
           rendered into #title-sub by langSwitchHtml() in engine.js, which is
           hidden here; this one is static markup because #header-narrow-row is
           never rebuilt. Both use .lang-btn, and clicks are delegated, so the
           two copies need no separate wiring. -->
      <span class="lang-switch sub" role="group"
            data-i18n-aria="ui.aria.language" aria-label="Language">
        <button type="button" class="lang-btn active" data-lang="en" aria-pressed="true">English</button>
        <span class="lang-sep" aria-hidden="true">|</span>
        <button type="button" class="lang-btn" data-lang="fr" aria-pressed="false">Français</button>
      </span>
      <button type="button" id="header-info-btn" aria-haspopup="true" aria-expanded="false"
              data-i18n-aria="ui.aria.header_info" aria-label="More information">ⓘ</button>
      <div id="header-info-popup" role="tooltip" aria-hidden="true">
        <div id="header-info-popup-body"></div>
        <!-- Static (unlike #header-info-popup-body, which buildTitleSub()
             overwrites on every load/language switch) -- same modals as the
             footer's Contributors/Methods and Terms buttons, which this
             popup replaces on narrow screens (see @media max-width:700px). -->
        <div id="header-info-popup-links">
          <button type="button" id="header-methods-btn" class="link-btn" data-i18n="ui.methods_btn">Contributors, Data, and Methods</button>
          <button type="button" id="header-terms-btn" class="link-btn" data-i18n="ui.terms_btn">Terms of Use</button>
        </div>
      </div>
    </div>
  </div>
  <div id="site-header-right">
    <div id="tracker"></div>
    <div class="sub" id="imperial-model-estimates"></div>
  </div>
</header>
<nav id="page-tabs">
  <div id="view-tabs" class="view-tabs">
__NAV_LINKS__
  </div>
</nav>
<!-- .sheet-head / .sheet-body is what keeps the dialog still while its content
     scrolls: the sheet is capped at the overlay's height and the body is the
     scroll container, so the title and close button stay put. Without the
     split the sheet has no height bound, which makes the overlay itself the
     scroller and drags the whole dialog off screen. Any modal added here needs
     both wrappers -- tests/test_modal_scroll_containment.py enforces it. -->
<div id="methods-modal" class="modal" role="dialog" aria-label="Contributors, Data, and Methods" aria-modal="true">
  <div class="sheet">
    <div class="sheet-head">
      <button class="close" id="methods-close" aria-label="Close">✕</button>
      <h2 id="methods-modal-title" data-i18n="ui.methods_modal_title">Contributors, Data, and Methods</h2>
    </div>
    <div class="sheet-body">
      <div id="methods-content"></div>
    </div>
  </div>
</div>
<div id="terms-modal" class="modal" role="dialog" aria-label="Terms of Use" aria-modal="true">
  <div class="sheet">
    <div class="sheet-head">
      <button class="close" id="terms-close" aria-label="Close">✕</button>
      <h2 id="terms-modal-title" data-i18n="ui.terms_modal_title">Terms of Use</h2>
    </div>
    <div class="sheet-body">
      <div id="terms-updated" style="font-size:11px;color:#888;margin-bottom:10px"></div>
      <div id="terms-content"></div>
    </div>
  </div>
</div>
<div id="viewport-area">
<div id="map"></div>
<!-- Standalone health-zone search: ONE node serving every view, a sibling of
     #map so it is never trapped inside a panel or rail. dashboard.css
     positions it per body.view-* across three width bands; engine.js's
     ZONE_SEARCH_VIEWS table supplies each view's index filter, i18n keys and
     select() action. Replaces the three separate boxes that used to live in
     #controls, #trends-controls and .epi-controls.

     #zone-search-results holds ONLY options (it is a listbox); the
     no-matches message is #zone-search-empty, a sibling shown in its place;
     #zone-search-live is announcement-only. -->
<div id="zone-search">
  <input type="search" id="zone-search-input" autocomplete="off" spellcheck="false"
         role="combobox" aria-autocomplete="list" aria-controls="zone-search-results"
         aria-expanded="false" aria-activedescendant=""
         data-i18n-placeholder="ui.zone_search_placeholder"
         placeholder="Type a health zone name…"
         data-i18n-aria="ui.zone_search" aria-label="Search health zone" />
  <div id="zone-search-results" role="listbox" hidden></div>
  <div id="zone-search-empty" hidden></div>
  <div id="zone-search-live" role="status" aria-live="polite" class="visually-hidden"></div>
</div>
<div id="context-hint" data-i18n="ui.hints.context">Click a health zone to see response context</div>
<div id="travel-hint" data-i18n="ui.hints.travel">Click a health zone to set travel origin (double-click to zoom)</div>
<div id="flow-hint" data-i18n="ui.hints.flow">Click a health zone to show movement flows (double-click to zoom)</div>
<div id="flow-empty-hint" data-i18n="ui.hints.flow_no_data">No movement data available for this health zone.</div>
<div id="controls" class="panel">
  <div class="panel-header">
    <strong data-i18n="ui.layer">Layer</strong>
    <button class="panel-toggle" data-target="controls" type="button" data-i18n-aria="ui.aria.toggle_layer" data-i18n-title="ui.aria.collapse_layer" aria-label="Toggle layer controls" title="Collapse / expand layer controls">−</button>
  </div>
  <div class="panel-body">
    <label for="layer-select" data-i18n="ui.source">Source</label>
    <select id="layer-select"></select>
    <div class="checkbox-row">
      <input type="checkbox" id="show-cases" />
      <label for="show-cases" style="margin:0;color:#eee" data-i18n="ui.show_cases">Show active-case markers</label>
    </div>
    <div class="checkbox-row" id="show-flow-arcs-row">
      <input type="checkbox" id="show-flow-arcs" />
      <label for="show-flow-arcs" style="margin:0;color:#eee" data-i18n="ui.show_flow_arcs">Show Flowminder in- and out-flow</label>
    </div>
    <div class="footer" id="layer-meta"></div>
  </div>
</div>
<div id="legend" class="panel">
  <div class="panel-header">
    <div id="legend-title"><strong data-i18n="ui.legend">Legend</strong></div>
    <button class="panel-toggle" data-target="legend" type="button" data-i18n-aria="ui.aria.toggle_legend" data-i18n-title="ui.aria.collapse_legend" aria-label="Toggle legend" title="Collapse / expand legend">−</button>
  </div>
  <div class="panel-body">
    <div class="legend-bar" id="legend-bar"></div>
    <div class="legend-ticks" id="legend-ticks"></div>
    <div class="legend-scale" id="legend-scale"></div>
    <div id="legend-gray" style="font-size:11px;color:#bbb;margin-top:4px"></div>
  </div>
</div>
<div id="trends-legend" class="panel">
  <div id="trends-legend-title"><strong data-i18n="ui.trends_confirmed_title">Confirmed cases (cumulative)</strong></div>
  <div id="trends-mode-toggle" role="group" data-i18n-aria="ui.trends_mode_aria" aria-label="Map colouring mode">
    <button type="button" class="trends-mode-btn active" data-mode="cumulative" data-i18n="ui.trends_mode_cumulative">Cumulative cases</button>
    <button type="button" class="trends-mode-btn" data-mode="recency" data-i18n="ui.trends_mode_recency">Recency</button>
  </div>
  <div id="trends-cumulative-legend">
    <p id="trends-legend-desc" data-i18n="ui.trends_legend_desc">Transcribed from INSP sitreps. Cases are sometimes revised downwards in consecutive sitreps.</p>
    <div class="legend-bar" id="trends-legend-bar"></div>
    <div class="legend-ticks" id="trends-legend-ticks"></div>
    <div class="legend-scale" id="trends-legend-scale" data-i18n="ui.trends_scale_log">(log scale)</div>
  </div>
  <div id="trends-recency-legend" style="display:none">
    <p id="trends-recency-desc" data-i18n="ui.trends_recency_desc">Health zones coloured by time since their most recent confirmed case.</p>
    <div class="recency-swatches">
      <div class="recency-swatch"><span class="recency-chip" style="background:#b2182b"></span><span data-i18n="ui.trends_recency_cat1">Case in last 14 days</span></div>
      <div class="recency-swatch"><span class="recency-chip" style="background:#ef8a62"></span><span data-i18n="ui.trends_recency_cat2">Case 15–42 days ago</span></div>
      <div class="recency-swatch"><span class="recency-chip" style="background:#fddbc7"></span><span data-i18n="ui.trends_recency_cat3">No case for &gt;42 days</span></div>
      <div class="recency-swatch"><span class="recency-chip" style="background:#e0e0e0"></span><span data-i18n="ui.trends_recency_cat4">No confirmed case</span></div>
    </div>
  </div>
  <div id="trends-play-row">
    <button type="button" id="trends-play-btn" data-i18n-aria="ui.trends_play" aria-label="Play">▶</button>
    <input type="range" id="trends-date-slider" min="0" max="0" value="0"
           data-i18n-aria="ui.trends_slider_aria" aria-label="SitRep date for confirmed cases map" />
  </div>
  <span id="trends-date-label" data-i18n="ui.trends_as_of">As of —</span>
</div>
<div id="info" class="panel">
  <div id="info-header">
    <strong data-i18n="ui.zone">Zone</strong>
    <button id="info-toggle" type="button" data-i18n-aria="ui.aria.toggle_zone" data-i18n-title="ui.aria.collapse_zone" aria-label="Toggle zone details" title="Collapse / expand zone details">−</button>
  </div>
  <div id="info-body" class="info-empty" data-i18n="ui.hover_zone">Select a health zone.</div>
</div>
<div id="view-switcher">
  <div id="footer-links">
    <button id="methods-btn" class="link-btn" type="button" data-i18n="ui.methods_btn">Contributors, Data, and Methods</button>
    <button id="terms-btn"   class="link-btn" type="button" data-i18n="ui.terms_btn">Terms of Use</button>
  </div>
  <div id="partners"></div>
</div>
<div id="epi-split-handle" role="separator" aria-orientation="vertical"
     data-i18n-aria="ui.aria.epi_split" aria-label="Resize map and table panels"
     tabindex="0"></div>
<div id="epi-trends-panel">
  <h2 id="epi-trends-title" data-i18n="ui.epi_trends_title">Health zones ranked by national relative risk of invasion</h2>
  <p id="epi-trends-subtitle"></p>
  <!-- The table always shows the national ranking; there is no geographic
       scope toggle. Zone search lives in the standalone #zone-search
       component over the map (see ZONE_SEARCH_VIEWS in engine.js); picking a
       zone there selects/highlights its row rather than filtering the list. -->
  <!-- Sortable column headers replace the old "Rank by relative risk /
       Rank by vulnerability-based priority" buttons -- click (or Enter/Space)
       any header to sort by it, click again to reverse. See
       wireEpiTrendsUi()'s header click handler + updateEpiSortIndicators()
       for the .sort-arrow glyph. -->
  <div id="epi-trends-table-wrap">
    <table id="epi-trends-table">
      <thead>
        <tr>
          <th class="sortable" data-sort="province" tabindex="0" role="button"
              data-i18n-aria="ui.epi_col_province" aria-label="Province"><span class="th-label" data-i18n="ui.epi_col_province">Province</span><span class="sort-arrow" aria-hidden="true"></span></th>
          <th class="sortable" data-sort="zone" tabindex="0" role="button"
              data-i18n-aria="ui.epi_col_zone" aria-label="Health zone"><span class="th-label" data-i18n="ui.epi_col_zone">Health zone</span><span class="sort-arrow" aria-hidden="true"></span></th>
          <th class="num sortable" data-sort="p_invasion" tabindex="0" role="button"
              data-i18n-aria="ui.epi_col_p_invasion" aria-label="Invasion probability"><span class="th-label" data-i18n="ui.epi_col_p_invasion">Invasion probability</span><span class="sort-arrow" aria-hidden="true"></span></th>
          <th class="num sortable" data-sort="p_ci" tabindex="0" role="button"
              data-i18n-aria="ui.epi_col_p_ci" aria-label="95% CrI"><span class="th-label" data-i18n="ui.epi_col_p_ci">95% CrI</span><span class="sort-arrow" aria-hidden="true"></span></th>
          <th class="num sortable" data-sort="norm_rr" tabindex="0" role="button"
              data-i18n-aria="ui.epi_col_norm_rr" aria-label="Relative risk (norm.)"><span class="th-label" data-i18n="ui.epi_col_norm_rr">Relative risk (norm.)</span><span class="sort-arrow" aria-hidden="true"></span></th>
          <th class="num sortable" data-sort="rr_rank" tabindex="0" role="button"
              data-i18n-aria="ui.epi_col_rr_rank" aria-label="Rank"><span class="th-label" data-i18n="ui.epi_col_rr_rank">Rank</span><span class="sort-arrow" aria-hidden="true"></span></th>
          <th class="num sortable" data-sort="priority" tabindex="0" role="button"
              data-i18n-aria="ui.epi_col_priority" aria-label="Vulnerability-based priority"><span class="th-label" data-i18n="ui.epi_col_priority">Vulnerability-based priority</span><span class="sort-arrow" aria-hidden="true"></span></th>
          <th class="num sortable" data-sort="priority_rank" tabindex="0" role="button"
              data-i18n-aria="ui.epi_col_priority_rank" aria-label="Rank of vulnerability-based priority"><span class="th-label" data-i18n="ui.epi_col_priority_rank">Rank of vulnerability-based priority</span><span class="sort-arrow" aria-hidden="true"></span></th>
        </tr>
      </thead>
      <tbody id="epi-trends-tbody"></tbody>
    </table>
  </div>
  <p id="epi-trends-method"></p>
  <div id="epi-trends-downloads">
    <button type="button" id="epi-download-map" data-i18n="ui.epi_download_map">Download map (JPG)</button>
    <button type="button" id="epi-download-csv" data-i18n="ui.epi_download_csv">Download data (CSV)</button>
  </div>
</div>
<!-- panel-header/panel-toggle here reuse the same collapse mechanism as the
     Trends plot cards (#trends etc. in #trends-panel below) -- clicking
     collapses #epi-trends-legend to just this title bar via the existing
     generic wirePanelToggles()/.panel.collapsed .panel-body CSS, no new JS
     needed. wirePanelToggles() also auto-collapses every .panel-toggle panel
     on load when the viewport is narrow, so on small screens this legend
     starts collapsed to a compact title bar instead of covering map space. -->
<div id="epi-trends-legend" class="panel">
  <div class="panel-header">
    <strong data-i18n="ui.epi_map_legend">Map colouring</strong>
    <button class="panel-toggle" data-target="epi-trends-legend" type="button"
            data-i18n-aria="ui.aria.toggle_epi_legend" data-i18n-title="ui.aria.collapse_epi_legend"
            aria-label="Toggle map legend" title="Collapse / expand map legend">−</button>
  </div>
  <div class="panel-body">
    <div class="legend-row" id="epi-legend-invasion-label"></div>
    <div class="legend-bar" id="epi-legend-invasion-bar"></div>
    <div class="legend-ticks" id="epi-legend-invasion-ticks"></div>
    <div class="legend-row" style="margin-top:10px" data-i18n="ui.epi_legend_active">Confirmed cases</div>
    <div class="legend-bar" id="epi-legend-cases-bar"></div>
    <div class="legend-ticks" id="epi-legend-cases-ticks"></div>
    <div class="checkbox-row" style="margin-top:10px">
      <input type="checkbox" id="epi-show-cases" />
      <label for="epi-show-cases" style="margin:0" data-i18n="ui.show_cases">Show active-case markers</label>
    </div>
    <div id="epi-flow-legend" style="margin-top:10px;font-size:11px;color:#5c574f;line-height:1.35">
      <div style="margin-bottom:4px">
        <span class="arrow-swatch"><svg xmlns="http://www.w3.org/2000/svg" width="26" height="12" viewBox="0 0 26 12"><line x1="1" y1="6" x2="25" y2="6" stroke="#b23b2e" stroke-width="1.6" stroke-linecap="round"/><line x1="10" y1="2" x2="16" y2="6" stroke="#b23b2e" stroke-width="1.6" stroke-linecap="round"/><line x1="10" y1="10" x2="16" y2="6" stroke="#b23b2e" stroke-width="1.6" stroke-linecap="round"/></svg></span>
        <span data-i18n="ui.legend.flow_in">inflow to selected location</span>
      </div>
      <div data-i18n="ui.legend.importation_pressure_width">Red inflows only; line width ∝ each origin's modelled import-force contribution to the selected zone (next-week forecast), scaled 0–1 vs that zone's top source</div>
    </div>
  </div>
</div>
<!-- Trends tab right-hand rail: a persistent (not floating) panel, sized by
     dragging #trends-split-handle, mirroring the #epi-trends-panel /
     #epi-split-handle pattern used on the Spatial Risk tab. Holds the scope
     controls up top and a scrollable column of plot cards
     below -- #trends is the first card; more can be appended into
     #trends-plots-column later without touching the layout mechanics. -->
<div id="trends-panel">
  <div id="trends-controls">
    <div class="trends-scope-row" role="group"
         data-i18n-aria="ui.trends_scope" aria-label="Geographic scope">
      <button type="button" class="trends-scope-btn active" data-scope="national"
              data-i18n="ui.trends_scope_national">National</button>
      <button type="button" class="trends-scope-btn" data-scope="province"
              data-i18n="ui.trends_scope_province">Provincial</button>
      <button type="button" class="trends-scope-btn" data-scope="health_zone"
              data-i18n="ui.trends_scope_health_zone">Health Zone</button>
    </div>
  </div>
  <div id="trends-plots-column">
    <div id="trends" class="panel trends-plot-card">
      <div class="panel-header">
        <strong id="trends-title" data-i18n="ui.trends_panel">Daily Cases by Symptom Onset</strong>
        <button class="panel-toggle" data-target="trends" type="button"
                data-i18n-aria="ui.aria.toggle_trends" data-i18n-title="ui.aria.collapse_trends"
                aria-label="Toggle trends panel" title="Collapse / expand trends">−</button>
      </div>
      <div id="trends-body" class="panel-body trends-empty"></div>
    </div>
    <div id="trends-deaths" class="panel trends-plot-card">
      <div class="panel-header">
        <strong id="trends-deaths-title" data-i18n="ui.trends_deaths_panel">Cumulative Deaths</strong>
        <button class="panel-toggle" data-target="trends-deaths" type="button"
                data-i18n-aria="ui.aria.toggle_trends" data-i18n-title="ui.aria.collapse_trends"
                aria-label="Toggle cumulative deaths panel" title="Collapse / expand cumulative deaths">−</button>
      </div>
      <div id="trends-deaths-body" class="panel-body trends-empty"></div>
    </div>
    <div id="trends-positivity" class="panel trends-plot-card">
      <div class="panel-header">
        <strong id="trends-positivity-title" data-i18n="ui.trends_positivity_panel">Test Positivity</strong>
        <button class="panel-toggle" data-target="trends-positivity" type="button"
                data-i18n-aria="ui.aria.toggle_trends" data-i18n-title="ui.aria.collapse_trends"
                aria-label="Toggle test positivity panel" title="Collapse / expand test positivity">−</button>
      </div>
      <div id="trends-positivity-body" class="panel-body trends-empty"></div>
    </div>
    <div id="trends-labs" class="panel trends-plot-card" style="display:none">
      <div class="panel-header">
        <strong id="trends-labs-title" data-i18n="ui.trends_labs_panel">Laboratory testing</strong>
        <button class="panel-toggle" data-target="trends-labs" type="button"
                data-i18n-aria="ui.aria.toggle_trends" data-i18n-title="ui.aria.collapse_trends"
                aria-label="Toggle laboratory testing panel" title="Collapse / expand laboratory testing">−</button>
      </div>
      <div id="trends-labs-body" class="panel-body trends-empty"></div>
    </div>
    <!-- More .trends-plot-card panels can be added here as additional plot
         types come online (e.g. testing-over-time). -->
  </div>
</div>
<div id="trends-split-handle" role="separator" aria-orientation="vertical"
     aria-label="Resize map and trends panels" tabindex="0"></div>
<div id="epi-float" class="panel"></div>
<div id="context-national" class="panel">
  <div class="panel-header">
    <strong data-i18n="ui.context_national">National and Provincial Response</strong>
    <button class="panel-toggle" data-target="context-national" type="button" data-i18n-aria="ui.aria.toggle_context_national" data-i18n-title="ui.aria.collapse_context_national" aria-label="Toggle national and provincial context panel" title="Collapse / expand national and provincial context">−</button>
  </div>
  <div id="context-national-body" class="panel-body context-empty"></div>
</div>
<div id="context" class="panel">
  <div class="panel-header">
    <strong id="context-title" data-i18n="ui.context_zone">Health zone context</strong>
    <button class="panel-toggle" data-target="context" type="button" data-i18n-aria="ui.aria.toggle_context_zone" data-i18n-title="ui.aria.collapse_context_zone" aria-label="Toggle health zone context panel" title="Collapse / expand zone context">−</button>
  </div>
  <div id="context-body" class="panel-body context-empty" data-i18n="ui.context_click_zone">Click a health zone on the map.</div>
</div>
<div id="stub-clinical-symptoms" class="panel stub-panel">
  <h2 data-i18n="ui.view_clinical_symptoms">Clinical Symptoms</h2>
  <p data-i18n="ui.stub_coming_soon">Coming soon.</p>
</div>
<div id="stub-surveillance-testing" class="panel stub-panel">
  <h2 data-i18n="ui.view_surveillance_testing">Surveillance and Testing</h2>
  <p data-i18n="ui.stub_coming_soon">Coming soon.</p>
</div>
__PAGE_BODY__
</div>
"""

SCRIPTS_TEMPLATE = r"""<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script src="__ASSETS_PREFIX__engine.js"></script>
__EXTRA_SCRIPTS__
</body>
</html>
"""

PAGE_TITLES = {
    "map": "DRC Ebola Bundibugyo - Epidemic Intelligence Dashboard",
    "trends": "DRC Ebola Bundibugyo - Epidemic Intelligence Dashboard — epidemiological trends",
    "epi-trends": "DRC Ebola Bundibugyo - Epidemic Intelligence Dashboard — spatial risk",
    "context": "DRC Ebola Bundibugyo - Epidemic Intelligence Dashboard — public health context",
    "clinical-symptoms": "DRC Ebola Bundibugyo - Epidemic Intelligence Dashboard — clinical symptoms",
    "surveillance-testing": "DRC Ebola Bundibugyo - Epidemic Intelligence Dashboard — surveillance and testing",
    "genomic-epidemiology": "DRC Ebola Bundibugyo - Epidemic Intelligence Dashboard — genomic epidemiology",
}


def _render_nav(active_view: str, assets_prefix: str) -> str:
    """Real cross-page <a> links, replacing the old JS-only tab buttons.

    Kept as ``class="view-tab"`` / ``data-view="..."`` so the existing CSS
    (`.view-tab`, `.view-tab.active`) and the small bits of engine.js that
    still query `.view-tab[data-view=...]` keep working unmodified.
    """
    links = []
    for view_id, i18n_key, label in NAV_ITEMS:
        # Pages live alongside each other (all in output/ or all at repo
        # root), so a bare relative filename is correct in both contexts.
        # assets_prefix is unused here; it only applies to the assets/ subfolder.
        href = PAGE_FILENAMES[view_id]
        active = " active" if view_id == active_view else ""
        links.append(
            f'      <a href="{href}" class="view-tab{active}" data-view="{view_id}" '
            f'data-i18n="{i18n_key}">{label}</a>'
        )
    return "\n".join(links)


# Payload keys only one view reads; stripped from every OTHER page's inline
# payload so a big per-view blob doesn't bloat pages that never use it. Map:
# payload key -> set of view_ids allowed to carry it.
_PAGE_SCOPED_PAYLOAD_KEYS = {
    "import_force_pairwise": {"epi-trends"},
    "genomic": {"genomic-epidemiology"},
    # ~373 KB of series data only the Trends tab reads. Its SVG predecessor
    # (onset_trends) was unscoped and cost every page 5.35 MB.
    "trends": {"trends"},
}


def render_page(view_id: str, payload: dict, assets_prefix: str = "assets/",
                *, page_body: str = "", extra_scripts: str = "",
                extra_head: str = "") -> str:
    """Assemble one full page. ``view_id`` is one of the ids in NAV_ITEMS
    (map | trends | epi-trends | context | clinical-symptoms |
    surveillance-testing | genomic-epidemiology); the last three are
    STUB_VIEWS -- "coming soon" placeholders, see that set's docstring.

    ``payload`` is the shared dict from common.payload.build_shared_payload();
    it is embedded inline (as before the split) rather than loaded from an
    external assets/payload.json, so each page keeps the original
    synchronous ``JSON.parse(...)`` bootstrap in engine.js unchanged. See the
    README for the size/caching trade-off this implies.
    """
    if view_id not in PAGE_FILENAMES:
        raise ValueError(f"unknown view_id {view_id!r}; expected one of {list(PAGE_FILENAMES)}")

    scoped_payload = {
        k: v for k, v in payload.items()
        if k not in _PAGE_SCOPED_PAYLOAD_KEYS or view_id in _PAGE_SCOPED_PAYLOAD_KEYS[k]
    }
    payload_json = json.dumps(scoped_payload, separators=(",", ":"), default=json_default,
                               allow_nan=False)

    head = HEAD_TEMPLATE.replace("__PAGE_TITLE__", PAGE_TITLES[view_id])
    head = head.replace("__EXTRA_HEAD__", extra_head)
    head = head.replace("__ASSETS_PREFIX__", assets_prefix)

    body = BODY_TEMPLATE.replace("__INITIAL_VIEW__", view_id)
    body = body.replace("__EXTRA_BODY_CLASS__", "stub-view" if view_id in STUB_VIEWS else "")
    body = body.replace("__NAV_LINKS__", _render_nav(view_id, assets_prefix))
    body = body.replace("__PAGE_BODY__", page_body)

    scripts = SCRIPTS_TEMPLATE.replace("__PAYLOAD__", payload_json)
    # Expand __EXTRA_SCRIPTS__ before __ASSETS_PREFIX__ so any prefix tokens the
    # page's own <script> tags carry are resolved too.
    scripts = scripts.replace("__EXTRA_SCRIPTS__", extra_scripts)
    scripts = scripts.replace("__ASSETS_PREFIX__", assets_prefix)

    return head + body + scripts
