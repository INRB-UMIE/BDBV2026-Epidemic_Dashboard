"""
"Current snapshot" page (formerly the default/"map" tab) -> output/index.html.

This is intentionally thin right now: the shared payload and JS engine cover
all four views, so building this page is just picking the right view id.
Once the engine is split further (see README), this module becomes the
natural place for snapshot-only payload trimming (e.g. dropping
trends/invasion_risk/phr_context, which only Trends/Spatial-risk/
Context use).
"""

from __future__ import annotations

from common.chrome import render_page

VIEW_ID = "map"


def build_page(payload: dict) -> str:
    return render_page(VIEW_ID, payload)
