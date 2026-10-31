"""
"Current snapshot" page (formerly the default/"map" tab) -> output/index.html.

Two panes, like Trends and Spatial Risk: the map on the left (layer and legend
widgets still float over it) and a summary rail on the right, wider than the
map by default and resizable via #snapshot-split-handle. The rail summarises
the other tabs for the selected health zone, or nationally when nothing is
selected; snapshot.js draws it from PAYLOAD.snapshot_summary
(common/snapshot_summary.py) plus the shared payload's case counts, invasion
risk and public-health context.
"""

from __future__ import annotations

from common.chrome import render_page

VIEW_ID = "map"

_BODY = """<div id="snapshot-split-handle" role="separator" aria-orientation="vertical"
     data-i18n-aria="ui.snap.aria_split" aria-label="Resize map and summary panels"
     tabindex="0"></div>
<aside id="snapshot-panel" aria-labelledby="snap-title">
  <div id="snap-head">
    <div id="snap-head-text">
      <h2 id="snap-title">National overview</h2>
      <p id="snap-sub"></p>
    </div>
    <button type="button" id="snap-clear" hidden>← National overview</button>
  </div>
  <div id="snap-body"></div>
</aside>"""

# charts.js before snapshot.js (which calls DashboardCharts.*), both after
# engine.js (i18n helpers, map, selection state).
_SCRIPTS = (
    '<script src="__ASSETS_PREFIX__charts.js"></script>\n'
    '<script src="__ASSETS_PREFIX__snapshot.js"></script>'
)


def build_page(payload: dict) -> str:
    return render_page(VIEW_ID, payload, page_body=_BODY, extra_scripts=_SCRIPTS)
