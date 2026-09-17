"""
"Genomic Epidemiology" page -> output/genomic-epidemiology.html.

Contributes the right-rail panel shell (via render_page's page_body seam) and a
page-scoped genomic.js that reads the `genomic` payload slice. Static chrome
strings use data-i18n / data-i18n-html / data-i18n-title (EN+FR locales); SVG
labels and empty-states are translated at render time in genomic.js.
"""

from __future__ import annotations

from common.chrome import render_page

VIEW_ID = "genomic-epidemiology"

# Page-scoped CSP: PearTree's bundle injects an `@import` to fonts.googleapis.com
# (+ a gstatic font fetch). `font-src 'self' data:` blocks the font download so no
# external request leaves the page; the tree falls back to the system font stack
# (which is what every other panel uses anyway). Only font loading is restricted --
# scripts/styles/images stay unconstrained (no default-src), so the rest of the
# page (Leaflet, html2canvas) is unaffected. Proven in the Phase 0 spike.
_HEAD = r"""<meta http-equiv="Content-Security-Policy" content="font-src 'self' data:;" />"""

# Right-rail order: phylogeny → cases/genomes → correlation → Ne.
# genomic.js fills the .gen-body divs from PAYLOAD.genomic.
_BODY = r"""<div id="genomic-panel">
  <div id="genomic-resize" role="separator" aria-orientation="vertical" data-i18n-title="ui.aria.genomic_resize" data-i18n-aria="ui.aria.genomic_resize" title="Drag to resize" tabindex="0"></div>
  <p class="gen-intro" data-i18n-html="ui.genomic.intro">A more detailed report of the data, methodology, and result interpretation can be found at <a href="https://virological.org/t/genomic-epidemiology-of-the-ongoing-2026-bundibugyo-virus-disease-outbreak-in-the-democratic-republic-of-the-congo/1045" target="_blank" rel="noopener">virological.org/t/genomic-epidemiology-of-the-ongoing-2026-bundibugyo-virus-disease-outbreak-in-the-democratic-republic-of-the-congo/1045</a>.</p>
  <section class="gen-card gen-tree-card" id="gen-tree-card">
    <div class="gen-card-head">
      <span class="gen-title" tabindex="0">
        <h2 data-i18n="ui.genomic.phylogeny_title">Phylogeny</h2>
        <span class="gen-info" aria-hidden="true">i</span>
        <span class="gen-tip" role="tooltip" data-i18n="ui.genomic.phylogeny_tip">Time-scale phylogeny of sequenced Bundibugyo viral genomes, with tips coloured by health zone where sample collection took place. Node bars indicate the 95% HPD of the inferred dates.</span>
      </span>
      <span class="gen-toggles">
        <button type="button" id="gen-tree-legend" class="gen-toggle" aria-pressed="false" data-i18n="ui.genomic.legend" data-i18n-title="ui.genomic.legend_title" title="Show/hide the health-zone colour legend">Legend</button>
        <button type="button" id="gen-tree-nodebars" class="gen-toggle" aria-pressed="true" data-i18n="ui.genomic.node_bars" data-i18n-title="ui.genomic.node_bars_title" title="Show/hide node confidence (95% HPD) bars">Node Bars</button>
        <button type="button" id="gen-tree-tiplabels" class="gen-toggle" aria-pressed="true" data-i18n="ui.genomic.tip_labels" data-i18n-title="ui.genomic.tip_labels_title" title="Show/hide health-zone tip labels">Tip Labels</button>
      </span>
    </div>
    <div class="gen-tree-wrap">
      <div class="gen-body gen-tree-body" id="gen-tree-body" data-i18n="ui.genomic.loading">Loading…</div>
      <div class="gen-tree-legend-box" id="gen-tree-legend-box" hidden></div>
    </div>
  </section>
  <section class="gen-card" id="gen-dist-card">
    <div class="gen-card-head">
      <span class="gen-title" tabindex="0">
        <h2 data-i18n="ui.genomic.dist_title">Confirmed cases &amp; genomes</h2>
        <span class="gen-info" aria-hidden="true">i</span>
        <span class="gen-tip" role="tooltip" data-i18n="ui.genomic.dist_tip">Daily confirmed positive cases (upward bars) and sequenced genomes from the phylogeny tips (inverted bars), stratified by Mongbwalu, Bunia/Rwampara, and other health zones. The top axis tracks sequencing coverage: genomes as a percentage of confirmed cases on each day.</span>
      </span>
      <span class="gen-toggles">
        <button type="button" id="gen-dist-imputed" class="gen-toggle" aria-pressed="true" data-i18n="ui.genomic.imputed" data-i18n-title="ui.genomic.imputed_title" title="Show cases with imputed onset dates">Imputed</button>
        <button type="button" id="gen-dist-beyond" class="gen-toggle" aria-pressed="false" data-i18n="ui.genomic.look_beyond" data-i18n-title="ui.genomic.look_beyond_title" title="Include onset dates after the tree's latest tip">Look Beyond</button>
      </span>
    </div>
    <div class="gen-strata-legend" id="gen-dist-legend" aria-hidden="true">
      <span class="gen-strata-item"><span class="gen-strata-swatch" data-cat="mongbwalu"></span><span data-i18n="ui.genomic.strata_mongbwalu">Mongbwalu</span></span>
      <span class="gen-strata-item"><span class="gen-strata-swatch" data-cat="bunia_rwampara"></span><span data-i18n="ui.genomic.strata_bunia_rwampara">Bunia / Rwampara</span></span>
      <span class="gen-strata-item"><span class="gen-strata-swatch" data-cat="other"></span><span data-i18n="ui.genomic.strata_other">Other</span></span>
      <span class="gen-strata-item"><span class="gen-strata-swatch gen-strata-line" data-cat="pct"></span><span data-i18n="ui.genomic.strata_pct">Genomes / cases %</span></span>
    </div>
    <div class="gen-body gen-chart gen-dist-chart" id="gen-dist-body"></div>
  </section>
  <section class="gen-card" id="gen-corr-card">
    <div class="gen-card-head">
      <span class="gen-title" tabindex="0">
        <h2 data-i18n="ui.genomic.corr_title">Cases vs sequenced genomes</h2>
        <span class="gen-info" aria-hidden="true">i</span>
        <span class="gen-tip" role="tooltip" data-i18n="ui.genomic.corr_tip">Each point is a health zone: total confirmed positive cases (onset) versus genomes in the phylogeny. Zones well below the proportional reference line have disproportionately few sequences relative to their case burden.</span>
      </span>
    </div>
    <div class="gen-body gen-chart gen-corr-chart" id="gen-corr-body"></div>
  </section>
  <section class="gen-card" id="gen-ne-card">
    <div class="gen-card-head">
      <span class="gen-title" tabindex="0">
        <h2 data-i18n="ui.genomic.ne_title">Effective population size</h2>
        <span class="gen-info" aria-hidden="true">i</span>
        <span class="gen-tip" role="tooltip" data-i18n="ui.genomic.ne_tip">Estimated effective population size (Nₑ) of the outbreak through time (up to the latest sample in the phylogeny). A rising curve indicates a growing epidemic; a plateau or decline indicates slowing transmission. SkyGrid is a flexible non-parametric estimate, Exp assumes an exponential-growth model. Shaded regions represent the 95% credible intervals.</span>
      </span>
      <span class="gen-toggles">
        <button type="button" id="gen-ne-skygrid" class="gen-toggle" aria-pressed="true" data-i18n="ui.genomic.skygrid">SkyGrid</button>
        <button type="button" id="gen-ne-exp" class="gen-toggle" aria-pressed="true" data-i18n="ui.genomic.exp">Exp</button>
      </span>
    </div>
    <div class="gen-body gen-chart" id="gen-ne-body"></div>
    <p class="gen-ne-stale-note" id="gen-ne-stale-note" data-i18n="ui.genomic.ne_stale_note" hidden></p>
  </section>
</div>"""

# PearTree bundle exposes window.PearTreeEmbed; it MUST load before genomic.js,
# which calls PearTreeEmbed.embed() to render the phylogeny.
_SCRIPTS = (
    '<script src="__ASSETS_PREFIX__peartree.bundle.min.js"></script>\n'
    '<script src="__ASSETS_PREFIX__genomic.js"></script>'
)


def build_page(payload: dict) -> str:
    return render_page(VIEW_ID, payload, page_body=_BODY,
                       extra_scripts=_SCRIPTS, extra_head=_HEAD)
