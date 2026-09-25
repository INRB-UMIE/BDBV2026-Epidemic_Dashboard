"""
"Epidemiological trends" page (formerly the "trends" tab) -> output/trends.html.

See pages/snapshot.py for why this is currently a thin wrapper around the
shared payload + engine. Note this view still needs the Leaflet map (province
outlines / health-zone clicks drive the plot selection) -- see README.
"""

from __future__ import annotations

from common.chrome import render_page

VIEW_ID = "trends"

# charts.js MUST load before trends.js (which calls DashboardCharts.*), and both
# after engine.js, which owns the scope/selection state they read.
_SCRIPTS = (
    '<script src="__ASSETS_PREFIX__charts.js"></script>\n'
    '<script src="__ASSETS_PREFIX__trends.js"></script>'
)


def build_page(payload: dict) -> str:
    return render_page(VIEW_ID, payload, extra_scripts=_SCRIPTS)
