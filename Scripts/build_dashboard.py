#!/usr/bin/env python3
"""
Build the DRC Ebola Bundibugyo 2026 dashboard as four HTML pages (Current
snapshot, Spatial risk, Epidemiological trends, Context) from publicly
available inputs.

This is the master/orchestrator script in the multi-page dashboard
structure (see README "Multi-page structure"). It:

  1. Loads all source data and builds the one shared JSON payload
     (common/payload.py) -- still shared across all four pages for now,
     since the JS engine reads fields from all of them regardless of which
     page is open (e.g. the Trends page reads PAYLOAD.confirmed_timeseries,
     the Context page reads PAYLOAD.phr_context, etc).
  2. Writes the shared static assets once: assets/dashboard.css (base
     stylesheet + optional brand theme layer) and assets/engine.js (the
     shared JS engine).
  3. Calls each page module in Scripts/pages/ to render its page and writes
     the result to output/<page>.html.

Usage
-----
    python build_dashboard.py

Layout
------
    project_root/
    ├── Scripts/
    │   ├── build_dashboard.py         (this file -- master/orchestrator)
    │   ├── common/                    shared data loading, payload, chrome
    │   ├── assets/                    shared dashboard.css + engine.js (source)
    │   └── pages/                     one module per page (snapshot, spatial_risk,
    │                                   trends, context)
    ├── Data/                          (see original docstring in
    │                                   common/data_sources.py for the full
    │                                   Data/ layout)
    └── output/
        ├── index.html                 Current snapshot (was the "map" tab)
        ├── spatial-risk.html          Spatial risk (was the "epi-trends" tab)
        ├── trends.html                Epidemiological trends
        ├── spatial-risk.html          Spatial risk
        ├── context.html               Public health context
        ├── clinical-symptoms.html     Clinical symptoms (coming soon)
        ├── surveillance-testing.html  Surveillance and testing (coming soon)
        ├── genomic-epidemiology.html  Genomic epidemiology (coming soon)
        └── assets/
            ├── dashboard.css
            └── engine.js

Set the ``DATA_ROOT`` environment variable to override the default Data/
location (useful when testing from a different working directory).

Inputs are tolerated when missing: the corresponding layers / sections are
hidden and a warning is printed.
"""

from __future__ import annotations

import os
import re

from common.paths import OUTPUT_DIR, ASSETS_DIRNAME, PAGE_FILENAMES, SCRIPT_DIR
from common.payload import build_shared_payload
from common.theme import load_theme_css
from pages import (
    snapshot, spatial_risk, trends, context,
    clinical_symptoms, surveillance_testing, genomic_epidemiology,
)

PAGE_MODULES = [
    snapshot, trends, spatial_risk, context,
    clinical_symptoms, surveillance_testing, genomic_epidemiology,
]


# CARTO's raster basemaps require an API key as of 2026; engine.js ships this
# placeholder and the real key is substituted in below. The key is a public
# client-side credential -- it is served to every visitor in engine.js whichever
# way it gets there -- so this indirection buys rotation and repo hygiene, not
# secrecy. Keep in sync with the CARTO_KEY line in Scripts/assets/engine.js.
CARTO_KEY_PLACEHOLDER = "{{CARTO_BASEMAP_KEY}}"

# CARTO keys are URL-safe tokens. Validating here (rather than trusting the
# environment) is what stops a stray quote or newline in the variable from
# escaping the JS string literal the key is substituted into.
CARTO_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _inject_carto_key(engine_js: str) -> str:
    """Substitute CARTO_BASEMAP_KEY into engine.js.

    Unset is a supported state, not an error: the placeholder is replaced with
    an empty string, engine.js then sends no ``key`` parameter, and the map
    renders under CARTO's "API key required" watermark. That is the right
    default for local builds -- the map still works, and nobody spends the
    shared quota by accident while iterating.
    """
    if CARTO_KEY_PLACEHOLDER not in engine_js:
        raise RuntimeError(
            f"{CARTO_KEY_PLACEHOLDER} not found in Scripts/assets/engine.js -- the "
            "basemap key substitution has drifted from the source it patches. "
            "Failing loudly rather than shipping a silently keyless basemap."
        )

    key = os.environ.get("CARTO_BASEMAP_KEY", "").strip()
    if key and not CARTO_KEY_RE.match(key):
        raise RuntimeError(
            "CARTO_BASEMAP_KEY is set but is not a URL-safe token "
            "(expected only letters, digits, '-' and '_'); refusing to inject it."
        )
    if not key:
        print(
            "  warning: CARTO_BASEMAP_KEY not set -- basemap tiles will carry "
            "CARTO's 'API key required' watermark"
        )
    return engine_js.replace(CARTO_KEY_PLACEHOLDER, key)


def _write_shared_assets(assets_dir) -> tuple[int, int]:
    base_css = (SCRIPT_DIR / "assets" / "dashboard.css").read_text(encoding="utf-8")
    theme_css = load_theme_css()
    css = base_css if not theme_css else f"{base_css}\n\n/* --- theme overrides --- */\n{theme_css}\n"
    (assets_dir / "dashboard.css").write_text(css, encoding="utf-8")

    engine_js = _inject_carto_key(
        (SCRIPT_DIR / "assets" / "engine.js").read_text(encoding="utf-8")
    )
    (assets_dir / "engine.js").write_text(engine_js, encoding="utf-8")

    # Page-scoped script for the genomic tab (only that page references it, but
    # it's written unconditionally alongside engine.js).
    genomic_js = (SCRIPT_DIR / "assets" / "genomic.js").read_text(encoding="utf-8")
    (assets_dir / "genomic.js").write_text(genomic_js, encoding="utf-8")

    # Shared chart primitives (charts.js) + the Trends page script. charts.js is
    # written unconditionally alongside engine.js; trends.js is referenced only
    # by trends.html.
    for name in ("charts.js", "trends.js"):
        (assets_dir / name).write_text(
            (SCRIPT_DIR / "assets" / name).read_text(encoding="utf-8"), encoding="utf-8")

    # Vendored PearTree phylogeny renderer (~1.5 MB, genomic-page-only; the tag
    # is emitted only on genomic-epidemiology.html). Copied byte-for-byte -- it's
    # a pre-built minified bundle, not source we edit here.
    peartree = (SCRIPT_DIR / "assets" / "peartree.bundle.min.js").read_bytes()
    (assets_dir / "peartree.bundle.min.js").write_bytes(peartree)

    return len(css.encode("utf-8")), len(engine_js.encode("utf-8"))


def main() -> int:
    payload = build_shared_payload()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assets_dir = OUTPUT_DIR / ASSETS_DIRNAME
    assets_dir.mkdir(parents=True, exist_ok=True)

    css_bytes, js_bytes = _write_shared_assets(assets_dir)
    print(f"\n  wrote {assets_dir / 'dashboard.css'} ({css_bytes / 1e3:.0f} KB)")
    print(f"  wrote {assets_dir / 'engine.js'} ({js_bytes / 1e3:.0f} KB)")

    total_bytes = 0
    for module in PAGE_MODULES:
        html = module.build_page(payload)
        out_path = OUTPUT_DIR / PAGE_FILENAMES[module.VIEW_ID]
        out_path.write_text(html, encoding="utf-8")
        total_bytes += len(html.encode("utf-8"))
        print(f"  wrote {out_path} ({len(html.encode('utf-8')) / 1e6:.2f} MB)")

    grand_total = total_bytes + css_bytes + js_bytes
    print(f"\ntotal: {grand_total / 1e6:.1f} MB across {len(PAGE_MODULES)} pages + shared assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
