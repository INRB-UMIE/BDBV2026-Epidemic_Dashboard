"""
"Reports" page -> output/reports.html.

A map-free page (body class "mapless-view", see common/chrome.py) listing every
PDF in the BDBV2026-Reports repo as cards grouped by folder. reports.js draws
the cards from PAYLOAD.reports (common/reports.py); the page itself is just an
empty shell, so a build with no reports still renders (with an empty state).
"""

from __future__ import annotations

from common.chrome import render_page

VIEW_ID = "reports"

_BODY = """<div id="rep-page">
  <div id="rep-inner">
    <div class="surv-intro">
      <p data-i18n="ui.reports.intro">Reports from the INRB response team, grouped by type. Each opens as a PDF in a new tab.</p>
    </div>
    <div id="rep-list"></div>
  </div>
</div>"""

_SCRIPTS = '<script src="__ASSETS_PREFIX__reports.js"></script>'


def build_page(payload: dict) -> str:
    return render_page(VIEW_ID, payload, page_body=_BODY, extra_scripts=_SCRIPTS)
