"""
Shared path/config constants for the dashboard build.

NOTE: this file lives in Scripts/common/, one level deeper than the original
build_dashboard_public.py (which lived directly in Scripts/). SCRIPT_DIR is
computed with an extra .parent so it still resolves to the Scripts/ directory,
keeping every other path (DATA_ROOT, BUILD_DIR, etc.) identical to before.
"""

from __future__ import annotations

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPT_DIR.parent

DATA_ROOT = Path(os.environ.get("DATA_ROOT") or (SCRIPT_DIR.parent / "Data")).resolve()
OUTPUT_DIR = SCRIPT_DIR.parent / "output"

BUILD_DIR = Path(os.environ.get("BUILD_DIR") or
                 (SCRIPT_DIR.parent.parent / "BDBV2026-Data" / "build")).resolve()
BUILD_GEOJSON    = BUILD_DIR / "drc_health_zones.geojson"
BUILD_MANIFEST   = BUILD_DIR / "manifest.json"
BUILD_LONG_DIR   = BUILD_DIR / "long"
EXTERNAL_DATA    = BUILD_DIR.parent / "data"
FLOWMINDER_PROCESSED = (
    Path(os.environ["FLOWMINDER_DIR"]).resolve()
    if os.environ.get("FLOWMINDER_DIR")
    else (BUILD_DIR.parent / "data" / "flowminder" / "processed")
)
FLOWMINDER_SHORT_TRIPS_PROCESSED = (
    EXTERNAL_DATA / "flowminder_short_trips" / "processed"
)
# NOTE: read directly from data/osrm/processed/, not build/long/. Matrices are
# deliberately excluded from tools.build_geojson (see that script's docstring),
# so build/long/osrm__*.csv is never regenerated and goes stale silently.
OSRM_PROCESSED   = EXTERNAL_DATA / "osrm" / "processed"
OSRM_TRAVEL_TIME_CSV = OSRM_PROCESSED / "osrm__travel_time__static.matrix.csv"
OSRM_ROAD_DISTANCE_CSV = OSRM_PROCESSED / "osrm__road_distance__static.matrix.csv"
DATA_REPO        = os.environ.get("DATA_REPO", "INRB-UMIE/BDBV2026-Data").strip()

METADATA_CSV     = DATA_ROOT / "health_zone_metadata.csv"
IC_MODEL_CSV     = DATA_ROOT / "ic_model_estimates.csv"
CAVEATS_CSV      = DATA_ROOT / "caveats.csv"
INVASION_RISK_CSV = DATA_ROOT / "invasion_risk_model_estimates.csv"
# Independently overridable (not just derived from DATA_ROOT) so the build
# can point straight at a checked-out/mounted copy of the processed-data
# repo's outputs/ directory (manifest.json + <date>/dashboard_plots/...)
# instead of requiring that content to be copied into Data/dashboard_plots/
# first. Default assumes BDBV2026-Processed_Sensitive_Data is cloned as a
# sibling of this repo, same convention as BUILD_DIR/BDBV2026-Data above.
DASHBOARD_PLOTS_DIR = Path(
    os.environ.get("DASHBOARD_PLOTS_DIR") or
    (SCRIPT_DIR.parent.parent / "BDBV2026-Processed_Sensitive_Data" / "outputs")
).resolve()
# Genomic-epi phylo products (tree/tips/meta/skygrid/exponential), produced by the
# sibling repo INRB-UMIE/BDBV2026-Genomic_Epi. Default assumes it is cloned as a
# sibling of this repo (same convention as BUILD_DIR/DASHBOARD_PLOTS_DIR above);
# override with the GENOMIC_DIR env var.
GENOMIC_DIR = Path(
    os.environ.get("GENOMIC_DIR") or
    (SCRIPT_DIR.parent.parent / "BDBV2026-Genomic_Epi" / "public" / "data")
).resolve()
# Latest HIPSTR/BEAST trees from BDBV2026-Phylogenetic_Analyses (dated subfolders).
# Override with PHYLOGENIES_DIR. Ne curves come from BEAST_NE_DIR (same sibling repo);
# GENOMIC_DIR remains a fallback for legacy Genomic_Epi products only.
PHYLOGENIES_DIR = Path(
    os.environ.get("PHYLOGENIES_DIR") or
    (SCRIPT_DIR.parent.parent / "BDBV2026-Phylogenetic_Analyses" / "data" / "phylogenies")
).resolve()
# BEAST Ne trajectory exports (SkyGrid / exponential) under outputs/beast/<date>/.
# Override with BEAST_NE_DIR.
BEAST_NE_DIR = Path(
    os.environ.get("BEAST_NE_DIR") or
    (SCRIPT_DIR.parent.parent / "BDBV2026-Phylogenetic_Analyses" / "outputs" / "beast")
).resolve()
SIT_REPS_DIR     = DATA_ROOT / "Epidemiological Data"
METHODS_DOCX     = DATA_ROOT / "Methods" / "Contributors_Methods_Data_website.docx"
METHODS_DOCX_FR  = DATA_ROOT / "Methods" / "Contributors_Methods_Data_website_fr.docx"
METHODS_HTML_FR  = DATA_ROOT / "Methods" / "Contributors_Methods_Data_website_fr.html"
TERMS_TXT        = DATA_ROOT / "ToS" / "Terms of Use.txt"
TERMS_TXT_FR     = DATA_ROOT / "ToS" / "Terms of Use_fr.txt"
BRANDING_DIR     = DATA_ROOT / "Branding"
BRANDING_URLS    = BRANDING_DIR / "urls.txt"
THEME_CSS        = BRANDING_DIR / "dashboard-theme.css"
LOCALES_DIR      = SCRIPT_DIR.parent / "locales"
SUPPORTED_LANGS  = ("en", "fr")

# Pages produced by the multi-page build. Keys are the "view id" used
# throughout the JS engine (activeView / body class / data-initial-view);
# values are the output filenames (relative to OUTPUT_DIR and REPO_ROOT).
PAGE_FILENAMES = {
    "map": "index.html",
    "trends": "trends.html",
    "epi-trends": "spatial-risk.html",
    "context": "context.html",
    "clinical-symptoms": "clinical-symptoms.html",
    "surveillance-testing": "surveillance-testing.html",
    "genomic-epidemiology": "genomic-epidemiology.html",
}

ASSETS_DIRNAME = "assets"
