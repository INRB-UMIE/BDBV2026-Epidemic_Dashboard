"""
Shared data-loading functions for the DRC Ebola Bundibugyo 2026 dashboard.

Moved out of the former single-file build_dashboard_public.py as part of the
multi-page split. Logic here is unchanged from the original script; only the
organisation (which module a function lives in) has changed.

Paths (SCRIPT_DIR, DATA_ROOT, etc.) are re-exported from common.paths so
downstream page/common modules can `from common.paths import *`-style import
without needing to know this module recomputes them.
"""

from __future__ import annotations

import base64
import csv
import json
import difflib
import math
import os
import re
import ssl
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import STRtree, set_precision
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import polygonize, polylabel, unary_union
from shapely.validation import make_valid

from common.paths import (
    SCRIPT_DIR, DATA_ROOT, BUILD_DIR, BUILD_GEOJSON, BUILD_MANIFEST,
    BUILD_LONG_DIR, EXTERNAL_DATA, FLOWMINDER_PROCESSED,
    FLOWMINDER_SHORT_TRIPS_PROCESSED, OSRM_PROCESSED, OSRM_TRAVEL_TIME_CSV,
    OSRM_ROAD_DISTANCE_CSV, DATA_REPO, METADATA_CSV, IC_MODEL_CSV,
    CAVEATS_CSV, INVASION_RISK_CSV, DASHBOARD_PLOTS_DIR, SIT_REPS_DIR,
    METHODS_DOCX, METHODS_DOCX_FR, METHODS_HTML_FR, TERMS_TXT, TERMS_TXT_FR,
    BRANDING_DIR, BRANDING_URLS, THEME_CSS, LOCALES_DIR, SUPPORTED_LANGS,
    OUTPUT_DIR, GENOMIC_DIR,
)

# `from common.data_sources import *` (used by common/payload.py) only pulls
# in names that don't start with an underscore *unless* __all__ is defined --
# and this module deliberately has many `_private`-looking helpers/constants
# that payload.py's build_shared_payload() still needs directly (e.g.
# _extra_layer_from_def, _sort_layers_for_dropdown). __all__ below is every
# name defined at module level in this file, public and private alike, so
# the wildcard import in payload.py re-exports all of them.
__all__ = [
    'SIMPLIFY_TOL',
    'COORD_DECIMALS',
    'PROVINCE_SNAP_GRID',
    'PROVINCE_SLIVER_MAX',
    'CENTRE_TOL',
    'TRAVEL_FROM_ZONE',
    'EPICENTER_ITURI_SINGLE',
    'EPICENTER_ITURI_COHORT',
    'EPICENTER_NK_COHORT',
    'EPICENTER_SOURCE_NOMS',
    'EPICENTER_FILL',
    'ASOF_FALLBACK',
    'INSP_BASE_URL',
    'INSP_FALLBACK_URL',
    'LATEST_SITREP_JSON',
    'INSP_FETCH_TIMEOUT_S',
    'INSP_FETCH_USER_AGENT',
    'INSP_SITREP_FETCH',
    '_SITREP_SLUG_MODERN_RE',
    '_SITREP_SLUG_LEGACY_RE',
    '_INSP_SITREP_PATH_RE',
    '_NAME_TO_NOM',
    '_NOM_TO_NAME',
    'PARTNER_ORDER',
    'PARTNER_GROUPS',
    'PARTNER_SCALE',
    '_parse_sitrep_date',
    '_format_asof',
    '_parse_csv_stem_date',
    '_insp_live_fetch_enabled',
    '_insp_http_get',
    '_normalize_insp_sitrep_url',
    '_sitrep_num_from_slug',
    '_is_bdbv_insp_sitrep_slug',
    '_collect_insp_sitrep_urls_from_text',
    '_fetch_insp_sitrep_urls_wp',
    '_fetch_insp_sitrep_urls_homepage',
    '_pick_latest_sitrep_url',
    '_pick_sitrep_url_for_date',
    '_sitrep_date_from_slug',
    'fetch_latest_insp_sitrep_url',
    '_latest_insp_url_from_local',
    'detect_asof',
    'detect_asof_date',
    'latest_insp_url',
    '_NORM_RE',
    '_norm',
    '_html_escape',
    '_f',
    '_i',
    '_round_coords',
    '_zone_centre',
    '_polygonal',
    '_clean_coverage',
    '_strip_slivers',
    'load_features_from_geojson',
    'build_province_boundaries',
    '_load_build_geojson_properties',
    '_NATIONAL_INSP_KEYS',
    '_national_totals_from_build_geojson',
    '_TRACKER_CAVEAT_METRIC_ALIASES',
    '_TRACKER_CAVEAT_MARKS',
    '_TRACKER_CAVEAT_WARNING_COLS',
    '_normalize_tracker_caveat_metric',
    'load_tracker_caveats',
    '_IC_MODEL_DEFAULTS',
    '_IC_MODEL_COL_ALIASES',
    '_resolve_ic_model_column',
    '_parse_ic_model_scalar',
    'load_ic_model_estimates',
    '_slugify_plot_key',
    '_read_plot_svg',
    '_svg_plot_title',
    '_load_lab_name_map',
    '_lab_label_from_stem',
    'load_dashboard_plots',
    '_parse_optional_float',
    '_parse_optional_int',
    '_parse_boolish',
    '_parse_flexible_date',
    '_SPATIOTEMPORAL_DATE_RE',
    '_latest_spatiotemporal_key_outputs_dir',
    'load_invasion_risk_estimates',
    'load_bayes_import_force_pairwise',
    'load_harmonised_confirmed_cases',
    '_latest_spatiotemporal_pairwise_csv',
    'reconcile_invasion_active_cases',
    'assert_harmonised_coverage',
    '_CONFIRMED_TS_LONG',
    '_CONFIRMED_TS_PROCESSED',
    '_CONFIRMED_TS_SKIP_NOMS',
    '_read_insp_cumulative_confirmed_df',
    '_parse_confirmed_count',
    'load_confirmed_cases_timeseries',
    'compute_confirmed_recency_timeseries',
    '_PHR_DATASET',
    '_PHR_NON_TEXT',
    '_PHR_ZONE_METRICS',
    '_PHR_METRIC_LABELS',
    '_phr_metric_label',
    '_phr_category',
    '_phr_scope_tag',
    '_parse_phr_date',
    '_sort_phr_pillars',
    '_extract_phr_block',
    '_phr_metric_candidates',
    '_phr_extract_from_phr',
    '_load_public_health_context_for_lang',
    'load_public_health_context',
    '_load_local_csv_fields',
    '_extract_matrix_column',
    '_extract_matrix_row_sums',
    '_load_flowminder_short_trips_vector',
    '_build_matrix_zone_aliases',
    '_matrix_header_to_nom',
    '_read_matrix_zone_order',
    '_load_square_matrix_csv',
    'load_zone_matrices',
    '_flowminder_processed_dir',
    '_matrix_count_value',
    '_sparse_out_by_origin',
    '_sparse_in_by_dest',
    '_FLOWMINDER_DATED_MATRIX_RE',
    '_MONTH_NAME_EN',
    '_MONTH_NAME_FR',
    '_yyyymm_prev',
    '_format_month_en',
    '_format_month_fr',
    '_flowminder_period_labels',
    'discover_latest_flowminder_yyyymm',
    'flowminder_dated_matrix_paths',
    'load_flowminder_sparse_from_paths',
    'load_flowminder_mar_sparse',
    'load_flowminder_latest_sparse',
    'load_metadata',
    'compute_global_sitrep_totals',
    'write_effective_confirmed_cases',
    'build_active_case_markers',
    'build_genome_sequence_markers',
    '_EMAIL_RE',
    '_BULLET_PREFIXES',
    '_strip_bullet',
    'load_methods_html',
    '_TERMS_SECTION_RE',
    '_TERMS_LASTUPDATED_RE',
    '_TERMS_LASTUPDATED_FR_RE',
    '_TERMS_HEADER_SKIP_RE',
    'load_methods_html_lang',
    'load_terms_html',
    'load_terms_html_lang',
    '_LOGO_MIME',
    'load_logo_data_uri',
    'load_partners',
    '_SKIP_PROPERTY_KEYS',
    '_NON_NUMERIC_STRINGS',
    '_EXCLUDE_LEAVES',
    'LAYER_CONFIG_YAML',
    '_load_layer_config',
    '_prettify_label',
    'discover_geojson_layers',
    'extract_geojson_fields',
    'EXTRA_LAYER_DEFS_TRAVEL',
    '_make_layer_def',
    '_FLOWMINDER_SHORT_TRIPS_GROUP',
    '_FLOWMINDER_SHORT_TRIPS_LAYER_DEFS',
    'FLOW_ARC_LAYER_DEF',
    'EXTRA_LAYER_DEFS',
    '_extra_layer_from_def',
    'PROJECTION_MASK_LAYERS',
    'PROJECTION_MASK_FIELD',
    'PROJECTION_MASK_MIN',
    'LAYER_GROUP_ORDER',
    '_sort_layers_for_dropdown',
    '_load_locale_yaml',
    'load_locales',
    'localize_layers',
    'build_i18n_payload',
    'load_data_build_info',
    'load_genomic_products',
    'canonicalize_genomic_zones',
    'load_onset_imputed_series',
]

# ---------------------------------------------------------------------------
# visual constants
# ---------------------------------------------------------------------------

SIMPLIFY_TOL = 0.001     # ~110 m at the equator; ~10× fewer vertices than raw
COORD_DECIMALS = 5

# --- province-outline dissolve cleanup (build_province_boundaries) ---------
# All three are in EPSG:4326 native units (degrees / square degrees), NOT metres.
# 1 deg^2 ~ 12,300 km^2 near the equator.
PROVINCE_SNAP_GRID = 1e-5     # set_precision grid, degrees (~1 m). In
                             # [COORD_DECIMALS quantum, SIMPLIFY_TOL): snaps shared
                             # zone edges together to close seam gaps, without
                             # visibly moving the province outline.
PROVINCE_SLIVER_MAX = 1e-3   # deg^2: drop interior rings AND detached parts below
                             # this. Observed slivers <= ~4e-4 deg^2; the real part
                             # of every province is >= ~0.8 deg^2 -- a >1000x gap.

CENTRE_TOL = 0.0001      # ~11 m: search precision for the pole of inaccessibility

TRAVEL_FROM_ZONE = "Mongbwalu"
# Canonical ``nom`` values for outbreak epicentres (Flowminder outflow sources).
EPICENTER_ITURI_SINGLE = ("Bunia", "Mongbwalu", "Rwampara")
EPICENTER_ITURI_COHORT = ("Bunia", "Mongbwalu", "Rwampara", "Nyankunde")
EPICENTER_NK_COHORT = ("Beni", "Butembo", "Katwa")
EPICENTER_SOURCE_NOMS = EPICENTER_ITURI_SINGLE
EPICENTER_FILL = "#7695E1"
ASOF_FALLBACK = ""
INSP_BASE_URL = "https://insp.cd/"
INSP_FALLBACK_URL = INSP_BASE_URL
LATEST_SITREP_JSON = SIT_REPS_DIR / "latest_sitrep.json"
INSP_FETCH_TIMEOUT_S = float(os.environ.get("INSP_FETCH_TIMEOUT", "25"))
INSP_FETCH_USER_AGENT = "BDBV2026-Dashboard-Build/1.0"
# Set INSP_SITREP_FETCH=0 to skip live INSP requests (offline / reproducible builds).
INSP_SITREP_FETCH = os.environ.get("INSP_SITREP_FETCH", "1").strip().lower() not in (
    "0", "false", "no", "off",
)

# Slugs for the Bundibugyo Ebola sitrep series on insp.cd (not generic MVE carousel pages).
# INSP has renamed the sitrep slug twice: ``sitrep-n072-mvb_25-07-2026`` up to
# #072, then ``sitrep-n092-mvebdb-14-08-2026`` from #073 on. Match any ``mv*``
# disease token and either separator so the next rename of that token does not
# silently strand us on an old sitrep again (see tests/test_insp_sitrep_url.py).
_SITREP_SLUG_MODERN_RE = re.compile(r"sitrep-n(\d{1,3})-(mv[a-z]*)[-_]", re.I)
_SITREP_SLUG_LEGACY_RE = re.compile(r"sitrep-mve-n-(\d{1,3})-(\d{4})", re.I)
# Trailing report date on a modern slug: ``sitrep-n092-mvebdb-14-08-2026``.
_SITREP_SLUG_DATE_RE = re.compile(r"[-_](\d{2})-(\d{2})-(\d{4})$")
_INSP_SITREP_PATH_RE = re.compile(
    r"(?:https?://(?:www\.)?insp\.cd)?(/sitrep-[\w-]+/?)",
    re.I,
)

# Maps metadata CSV names → build GeoJSON nom values where they differ.
# NOTE: the 2026-07 shapefile update renamed 13 zones to match what this
# metadata CSV already called them (e.g. "Mongbwalu" was an alias for the old
# canonical "Mongbalu"; the shapefile switch made "Mongbwalu" canonical), so
# those entries were removed as redundant. The remaining entries are either
# unrelated metadata-CSV spelling variants, or (Nsona-Pangu, Pendjua) updated
# to point at the new canonical noms.
_NAME_TO_NOM = {
    "Gungu (Secteur)": "Gungu",
    "Idiofa (Secteur)": "Idiofa",
    "Kabondo-Dianda": "Kabondo Dianda",
    "Kasongo-Lunda": "Kasongo Lunda",
    "Lubunga": "Lubunga (Tshopo)",
    "Nsona-Pangu": "Nsona Mpangu",
    "Nyirangongo": "Nyiragongo",
    "Pendjua": "Pendjwa",
}
_NOM_TO_NAME = {v: k for k, v in _NAME_TO_NOM.items()}

PARTNER_ORDER = [
    "INSP.png", "inrb.png", "UMIE.jpeg", "africa-cdc.png", "WHO.jpg",
    "northeastern.png", "psi.jpg", "oxford.jpg", "global-health.png",
]

# The footer strip is unboxed (see Data/Branding/dashboard-theme.css), so the
# gaps between logos are what group them: tight within a group, wide between.
# Group index per logo -- 0 DRC national, 1 continental and global, 2 academic,
# 3 data-science initiative.
PARTNER_GROUPS = {
    "INSP.png": 0, "inrb.png": 0, "UMIE.jpeg": 0,
    "africa-cdc.png": 1, "WHO.jpg": 1,
    "northeastern.png": 2, "psi.jpg": 2, "oxford.jpg": 2,
    "global-health.png": 3,
}

# Equal pixel height is not equal visual weight: a solid tile or a heavy
# letterform outweighs a thin wordmark at the same height. The old bounding box
# hid that; unboxed, each mark needs its own factor on --partner-h.
PARTNER_SCALE = {
    "INSP.png": 1.0, "inrb.png": 1.0, "WHO.jpg": 1.0,
    "UMIE.jpeg": 0.95, "africa-cdc.png": 0.95,
    "psi.jpg": 0.9, "northeastern.png": 0.85, "oxford.jpg": 0.82,
    # wide ~3.5:1 wordmark, so a lower height factor keeps its footprint in line
    "global-health.png": 0.72,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_sitrep_date(value) -> datetime.date | None:
    """Parse INSP sitrep ``_date`` strings from build GeoJSON.

    Supports ISO (``2026-05-28``), day-first (``28/05/2026``), and month-first
    short US-style (``5/28/26``) as used in the data pipeline.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    if "/" not in s:
        return None
    parts = s.split("/")
    if len(parts) != 3:
        return None
    try:
        a, b, y = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    year = y + 2000 if y < 100 else y
    if a > 12:
        try:
            return datetime(year, b, a).date()
        except ValueError:
            return None
    if b > 12:
        try:
            return datetime(year, a, b).date()
        except ValueError:
            return None
    # Ambiguous d/m vs m/d: prefer day-first (INSP DRC convention).
    for month, day in ((b, a), (a, b)):
        try:
            return datetime(year, month, day).date()
        except ValueError:
            continue
    return None


def _format_asof(d: datetime.date) -> str:
    return d.strftime("%d %b %Y").lstrip("0")


def _parse_csv_stem_date(stem: str) -> datetime.date | None:
    """Parse ``YYYY-MM-DD`` from Epidemiological Data CSV filenames."""
    try:
        return datetime.strptime(stem, "%Y-%m-%d").date()
    except ValueError:
        return None


def _insp_live_fetch_enabled() -> bool:
    return INSP_SITREP_FETCH


def _insp_http_get(url: str) -> str | None:
    """GET *url*; return response body text or None on failure."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": INSP_FETCH_USER_AGENT, "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(
            req, timeout=INSP_FETCH_TIMEOUT_S, context=ssl.create_default_context(),
        ) as resp:
            encoding = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(encoding, errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  NOTE: INSP fetch failed for {url}: {exc}")
        return None


def _normalize_insp_sitrep_url(path_or_url: str) -> str | None:
    """Return a canonical https://insp.cd/.../ URL for a sitrep path or slug."""
    s = path_or_url.strip()
    if not s:
        return None
    if s.startswith("http"):
        base = s.rstrip("/") + "/"
        if "insp.cd" not in base.lower():
            return None
        return base
    if not s.startswith("/"):
        s = "/" + s
    slug = s.strip("/").split("?")[0].split("#")[0]
    if not slug.lower().startswith("sitrep-"):
        return None
    return f"{INSP_BASE_URL}{slug}/"


def _sitrep_num_from_slug(slug: str) -> int | None:
    slug = slug.strip("/").lower()
    m = _SITREP_SLUG_MODERN_RE.search(slug)
    if m:
        return int(m.group(1))
    m = _SITREP_SLUG_LEGACY_RE.search(slug)
    if m:
        return int(m.group(1))
    return None


def _sitrep_date_from_slug(slug: str) -> datetime.date | None:
    """Report date embedded in a modern sitrep slug (``...-14-08-2026``)."""
    m = _SITREP_SLUG_DATE_RE.search(slug.strip("/").lower())
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
    except ValueError:
        return None


def _is_bdbv_insp_sitrep_slug(slug: str) -> bool:
    """True for Bundibugyo Ebola sitrep permalinks (excludes unrelated MVE pages)."""
    s = slug.strip("/").lower()
    if _SITREP_SLUG_MODERN_RE.search(s):
        return True
    m = _SITREP_SLUG_LEGACY_RE.search(s)
    # Legacy ``sitrep-mve-n-NNN-YYYY`` is shared with other diseases; keep high numbers.
    return m is not None and int(m.group(1)) >= 8


def _collect_insp_sitrep_urls_from_text(text: str) -> dict[int, str]:
    """Extract sitrep URLs keyed by sitrep number (highest wins per number)."""
    found: dict[int, str] = {}
    for m in _INSP_SITREP_PATH_RE.finditer(text):
        url = _normalize_insp_sitrep_url(m.group(1))
        if not url:
            continue
        slug = url[len(INSP_BASE_URL):].strip("/")
        if not _is_bdbv_insp_sitrep_slug(slug):
            continue
        num = _sitrep_num_from_slug(slug)
        if num is None:
            continue
        found[num] = url
    return found


def _fetch_insp_sitrep_urls_wp() -> dict[int, str]:
    """WordPress REST API: recent posts whose slug matches the Ebola sitrep series."""
    urls = (
        f"{INSP_BASE_URL}wp-json/wp/v2/posts"
        f"?search=SitRep&per_page=50&orderby=date&order=desc",
        f"{INSP_BASE_URL}wp-json/wp/v2/posts"
        f"?search=MVB&per_page=30&orderby=date&order=desc",
    )
    found: dict[int, str] = {}
    for api_url in urls:
        body = _insp_http_get(api_url)
        if not body:
            continue
        try:
            posts = json.loads(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(posts, list):
            continue
        for post in posts:
            if not isinstance(post, dict):
                continue
            slug = str(post.get("slug") or "")
            link = post.get("link")
            if not _is_bdbv_insp_sitrep_slug(slug):
                continue
            num = _sitrep_num_from_slug(slug)
            if num is None:
                continue
            url = _normalize_insp_sitrep_url(str(link) if link else slug)
            if url:
                found[num] = url
    return found


def _fetch_insp_sitrep_urls_homepage() -> dict[int, str]:
    body = _insp_http_get(INSP_BASE_URL)
    if not body:
        return {}
    return _collect_insp_sitrep_urls_from_text(body)


def _pick_latest_sitrep_url(candidates: dict[int, str]) -> str | None:
    if not candidates:
        return None
    # Prefer the modern per-outbreak series over the legacy ``sitrep-mve-n-NNN``
    # naming that is shared with other diseases; else highest sitrep number.
    # Match on the series *shape*, not on one era's disease token: keying off
    # "-mvb_" meant that once INSP moved to "-mvebdb-", the newest slug carrying
    # the old marker (#072) beat every newer sitrep in the candidate set.
    for num in sorted(candidates, reverse=True):
        slug = candidates[num][len(INSP_BASE_URL):].strip("/").lower()
        if _SITREP_SLUG_MODERN_RE.search(slug):
            return candidates[num]
    best_num = max(candidates)
    return candidates[best_num]


def _pick_sitrep_url_for_date(
    candidates: dict[int, str], asof: datetime.date
) -> str | None:
    """The published sitrep the displayed data actually came from.

    The header renders this link and the as-of date as one phrase ("Latest
    INSP Sit Rep - 11 Aug 2026"), so linking the newest sitrep INSP has
    published would point at a report whose numbers are not on the dashboard
    -- transcription runs days behind publication. Match the report date
    instead, and never return one newer than the data.
    """
    dated = {}
    for num, url in candidates.items():
        d = _sitrep_date_from_slug(url[len(INSP_BASE_URL):])
        if d is not None:
            dated[num] = d
    exact = [num for num, d in dated.items() if d == asof]
    if exact:
        return candidates[max(exact)]
    # No exact hit (a date convention drifted, or the data predates the
    # scrape window): the newest report that is not ahead of the data.
    older = [num for num, d in dated.items() if d < asof]
    if older:
        return candidates[max(older)]
    return None


def fetch_latest_insp_sitrep_url(asof: datetime.date | None = None) -> str | None:
    """Live INSP lookup: WordPress API, then homepage HTML scrape.

    With ``asof`` the pick is anchored to the data's report date rather than
    to whatever INSP published most recently.
    """
    merged: dict[int, str] = {}
    for source, fetcher in (
        ("wp-json", _fetch_insp_sitrep_urls_wp),
        ("homepage", _fetch_insp_sitrep_urls_homepage),
    ):
        found = fetcher()
        if found:
            print(f"  INSP sitrep fetch ({source}): "
                  f"#{max(found)} among {len(found)} candidate(s)")
            merged.update(found)
    if asof is not None:
        anchored = _pick_sitrep_url_for_date(merged, asof)
        if anchored:
            if merged and max(merged) > (_sitrep_num_from_slug(
                    anchored[len(INSP_BASE_URL):]) or 0):
                print(f"  NOTE: INSP has published up to #{max(merged)}; the "
                      f"dashboard's data stops at {_format_asof(asof)}, so the "
                      f"header links that report, not the newest one")
            return anchored
        # Deliberately do NOT fall back to the newest published sitrep here:
        # that is the bug this anchoring exists to prevent. Returning None
        # lets the caller drop to the local override / INSP index instead.
        print("  WARNING: no INSP sitrep matches the data's as-of date "
              f"({_format_asof(asof)}); leaving the link unanchored")
        return None
    return _pick_latest_sitrep_url(merged)


def _latest_insp_url_from_local() -> str | None:
    """Offline fallbacks: optional pointer file, then raw PDF filenames."""
    if LATEST_SITREP_JSON.exists():
        try:
            url = json.loads(LATEST_SITREP_JSON.read_text()).get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
        except Exception:
            pass
    raw_dir = EXTERNAL_DATA / "insp_sitrep" / "raw"
    if raw_dir.exists():
        nums = []
        for p in raw_dir.glob("SitRep_MVE_*-*.pdf"):
            m = re.search(r"SitRep_MVE_(\d+)-(\d+)", p.stem)
            if m:
                nums.append((int(m.group(1)), int(m.group(2))))
        if nums:
            num, year = max(nums)
            return f"{INSP_BASE_URL}sitrep-mve-n-{num:03d}-{year}/"
    return None


def detect_asof_date() -> datetime.date | None:
    """The 'latest case report' date the dashboard displays, as a date.

    Checks local sit-rep CSVs first, then falls back to _date fields in the
    build GeoJSON."""
    if SIT_REPS_DIR.exists():
        dated = []
        for p in SIT_REPS_DIR.iterdir():
            if not p.is_file() or p.suffix.lower() != ".csv":
                continue
            d = _parse_csv_stem_date(p.stem)
            if d is not None:
                dated.append((d, p))
        if dated:
            d, _ = max(dated)
            return d
    if BUILD_GEOJSON.exists():
        with open(BUILD_GEOJSON) as f:
            raw = json.load(f)
        dates = set()
        for feat in raw["features"]:
            insp = feat["properties"].get("insp_sitrep") or {}
            for v in insp.values():
                if isinstance(v, dict) and "_date" in v:
                    parsed = _parse_sitrep_date(v["_date"])
                    if parsed is not None:
                        dates.add(parsed)
        if dates:
            return max(dates)
    return None


def detect_asof() -> str:
    d = detect_asof_date()
    return _format_asof(d) if d is not None else ASOF_FALLBACK


def latest_insp_url(asof: datetime.date | None = None) -> str:
    """Permalink for the sitrep the displayed data came from.

    ``asof`` anchors the choice to the data (see _pick_sitrep_url_for_date);
    without it this falls back to the newest sitrep published. Live fetch
    first, then local overrides, then the INSP home page.
    """
    if _insp_live_fetch_enabled():
        live = fetch_latest_insp_sitrep_url(asof)
        if live:
            print(f"  insp sitrep URL (live): {live}")
            return live
        print("  WARNING: live INSP sitrep fetch found no URL; using local fallbacks")
    else:
        print("  NOTE: INSP live sitrep fetch disabled (INSP_SITREP_FETCH=0)")
    local = _latest_insp_url_from_local()
    if local:
        print(f"  insp sitrep URL (local): {local}")
        return local
    return INSP_FALLBACK_URL


_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm(s) -> str:
    return _NORM_RE.sub("", str(s).lower()) if s else ""


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else v


def _i(x):
    v = _f(x)
    return None if v is None else int(round(v))


def _round_coords(geom_dict: dict, ndigits: int) -> dict:
    def _walk(o):
        if isinstance(o, (list, tuple)):
            if o and isinstance(o[0], (int, float)):
                return [round(float(c), ndigits) for c in o]
            return [_walk(x) for x in o]
        return o

    g = dict(geom_dict)
    g["coordinates"] = _walk(g.get("coordinates"))
    return g


def _strip_slivers(geom, min_area: float):
    """Drop interior rings and detached parts below ``min_area`` (square degrees).

    ``unary_union`` of imperfectly-aligned zone polygons leaves two kinds of
    artefact: tiny interior rings (holes at seam gaps) and tiny detached exterior
    parts (fragments where edges cross rather than coincide). DRC provinces have
    no legitimate donut holes and no legitimate small island exclaves, so both are
    safe to drop below a threshold that sits in the wide empirical gap between
    sliver and real-part areas.

    Returns ``(cleaned_geom, dropped_ring_max, dropped_part_max)`` -- the largest
    dropped ring/part area seen (0.0 if none), for the caller to log and sanity-check.
    """
    dropped_ring_max = 0.0
    dropped_part_max = 0.0

    def clean_polygon(poly):
        nonlocal dropped_ring_max
        keep = []
        for ring in poly.interiors:
            area = Polygon(ring).area
            if area >= min_area:
                keep.append(ring)
            else:
                dropped_ring_max = max(dropped_ring_max, area)
        return Polygon(poly.exterior, keep)

    if geom.geom_type == "Polygon":
        return clean_polygon(geom), dropped_ring_max, dropped_part_max

    if geom.geom_type == "MultiPolygon":
        parts = list(geom.geoms)
        kept = [p for p in parts if p.area >= min_area]
        if not kept:
            # Defensive: never erase a province. Keep the largest part; only the
            # genuinely-dropped remainder counts toward dropped_part_max.
            largest = max(parts, key=lambda p: p.area)
            kept = [largest]
            dropped = [p for p in parts if p is not largest]
        else:
            dropped = [p for p in parts if p.area < min_area]
        for p in dropped:
            dropped_part_max = max(dropped_part_max, p.area)
        keep_parts = [clean_polygon(p) for p in kept]
        if len(keep_parts) == 1:
            return keep_parts[0], dropped_ring_max, dropped_part_max
        return MultiPolygon(keep_parts), dropped_ring_max, dropped_part_max

    # Unexpected non-areal geometry (e.g. a GeometryCollection from a degenerate
    # union). Inputs are pre-filtered to Polygon/MultiPolygon so this should be
    # unreachable; fail the build loudly rather than emit non-Polygon GeoJSON the
    # province-outline layer can't reliably render while reporting a clean 0.0.
    raise ValueError(
        f"_strip_slivers got unexpected geometry type {geom.geom_type!r}"
    )


# ---------------------------------------------------------------------------
# geometry: read DRC health-zone polygons, match per-zone metadata rows
# ---------------------------------------------------------------------------

def _zone_centre(geom):
    """Return a well-inside anchor point for a zone's label/marker/arrows.

    Uses the pole of inaccessibility (``polylabel``) -- the interior point
    farthest from any edge -- instead of the area-weighted ``.centroid``. The
    centroid is *not* guaranteed to lie inside the polygon and drifts outside on
    crescent-shaped or otherwise concave zones (and into the gaps of
    MultiPolygons); the pole of inaccessibility is always inside and reads as
    visually central. ``polylabel`` only accepts a single Polygon, so for
    MultiPolygons we anchor on the largest-area part. Falls back to
    ``representative_point()`` (also always inside) if polylabel ever fails.
    """
    target = (max(geom.geoms, key=lambda p: p.area)
              if geom.geom_type == "MultiPolygon" else geom)
    try:
        return polylabel(target, tolerance=CENTRE_TOL)
    except Exception:
        return target.representative_point()


def _polygonal(geom):
    """Repair to a valid Polygon/MultiPolygon, discarding any non-areal debris.

    Dissolving atomic faces and then rounding coordinates can leave a polygon
    self-touching (invalid) or, rarely, a GeometryCollection with a stray line;
    this normalises the result back to clean polygonal geometry.
    """
    geom = make_valid(geom)
    if geom.geom_type in {"Polygon", "MultiPolygon"}:
        return geom
    if geom.geom_type == "GeometryCollection":
        parts = [g for g in geom.geoms if g.geom_type in {"Polygon", "MultiPolygon"}]
        if parts:
            return unary_union(parts)
    return geom


def _clean_coverage(geoms: list) -> list:
    """Rebuild overlapping zone polygons into a clean, non-overlapping coverage.

    The source health-zone polygons are *not* a valid polygonal coverage -- they
    overlap each other (precision slivers plus a tail of larger disagreements).
    Because the map strokes every zone separately, each side of an overlapping
    pair paints a slightly different border, so shared edges render as doubled,
    offset lines.

    Fix: node every zone boundary together, ``polygonize`` the plane into atomic
    faces, then hand each face to the zone it overlaps most and dissolve. Overlap
    regions collapse to a single owner, so neighbours end up sharing exactly one
    border line. Pre-existing *gaps* in the source are left as-is (a face inside
    no zone is simply dropped) -- filling them is deliberately out of scope here.

    Returns a list aligned 1:1 with ``geoms``; a zone that somehow keeps no face
    falls back to its original geometry. Note this changes each zone's area only
    marginally (median ~0.005%, worst-case ~2-3% for the most overlap-affected
    zones) since it only redistributes the contested slivers.
    """
    boundaries = unary_union([g.boundary for g in geoms])
    faces = list(polygonize(boundaries))
    tree = STRtree(geoms)
    zone_faces: dict[int, list] = {}
    for face in faces:
        best, best_overlap = None, 0.0
        for j in tree.query(face):
            g = geoms[j]
            if not g.intersects(face):
                continue
            overlap = g.intersection(face).area
            if overlap > best_overlap:
                best_overlap, best = overlap, int(j)
        if best is not None:
            zone_faces.setdefault(best, []).append(face)
    return [
        make_valid(unary_union(zone_faces[i])) if i in zone_faces else geoms[i]
        for i in range(len(geoms))
    ]


def load_features_from_geojson() -> tuple[list[dict], dict[str, tuple[float, float]]]:
    """Load zone polygons from the build GeoJSON, keyed by nom."""
    with open(BUILD_GEOJSON) as f:
        raw = json.load(f)

    # Collect valid zone geometries first: the source polygons overlap each
    # other, so we clean them into a single coverage (shared borders drawn once)
    # before simplifying and emitting features.
    raw_geoms: list = []
    metas: list[tuple[str, str | None]] = []
    for feat in raw["features"]:
        geom = make_valid(shape(feat["geometry"]))
        if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        raw_geoms.append(geom)
        metas.append((feat["properties"]["nom"], feat["properties"].get("province")))

    clean_geoms = _clean_coverage(raw_geoms)

    feats: list[dict] = []
    centroids: dict[str, tuple[float, float]] = {}
    for (nom, province), geom in zip(metas, clean_geoms):
        if geom.is_empty:
            continue
        # Anchor on the cleaned geometry (guaranteed inside what is rendered).
        centre_pt = _zone_centre(geom)
        # Intentionally NOT simplifying per-feature here: _clean_coverage() just
        # made the zones share exact border vertices, and an independent
        # per-polygon simplify would drop different vertices on each side of a
        # shared edge -- re-introducing the doubled borders. (Per-feature
        # simplify at SIMPLIFY_TOL only trimmed <0.2% of vertices anyway.) To
        # shrink the payload, simplify the whole coverage at once via
        # shapely.coverage_simplify() (needs shapely>=2.1), not zone by zone.
        gdict = mapping(geom)
        if COORD_DECIMALS is not None:
            gdict = _round_coords(gdict, COORD_DECIMALS)
            # Rounding a dissolved coverage can self-intersect the ring; repair.
            gdict = mapping(_polygonal(shape(gdict)))
        props = {"nom": nom, "name": _NOM_TO_NAME.get(nom, nom)}
        if province:
            props["province"] = province
        feats.append({
            "type": "Feature",
            "geometry": gdict,
            "properties": props,
        })
        centroids[nom] = (float(centre_pt.x), float(centre_pt.y))
    return feats, centroids


def build_province_boundaries() -> dict:
    """Union health-zone polygons into one clean outline per province.

    Also the authoritative province roster: ``payload.py`` derives
    ``province_names`` from these features (plot generation) and ``engine.js``
    builds the Trends search dropdown from them. A dropped province silently
    disappears from plots + search, so the province-count invariant below is
    asserted, not merely hoped for.
    """
    if not BUILD_GEOJSON.exists():
        return {"type": "FeatureCollection", "features": []}

    with open(BUILD_GEOJSON) as f:
        raw = json.load(f)

    # Distinct provinces in the RAW source, before any geometry filtering. The
    # invariant compares output against THIS set (not ``by_province`` keys): a
    # province whose zones are all dropped by the make_valid/geom-type filter
    # would never enter ``by_province``, so the count would still match while the
    # province silently vanished.
    raw_provinces = {
        (feat.get("properties") or {}).get("province")
        for feat in (raw.get("features") or [])
        if (feat.get("properties") or {}).get("province")
    }

    by_province: dict[str, list] = {}
    for feat in raw.get("features") or []:
        prov = (feat.get("properties") or {}).get("province")
        if not prov:
            continue
        # make_valid -> set_precision (snap shared edges together) -> make_valid.
        # Snapping can itself re-introduce invalidity, hence the second repair.
        geom = make_valid(shape(feat["geometry"]))
        geom = make_valid(set_precision(geom, PROVINCE_SNAP_GRID))
        if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        by_province.setdefault(prov, []).append(geom)

    out: list[dict] = []
    max_dropped_ring = 0.0
    max_dropped_part = 0.0
    for prov in sorted(by_province):
        merged = unary_union(by_province[prov])
        if merged.is_empty:
            continue
        merged, ring_max, part_max = _strip_slivers(merged, PROVINCE_SLIVER_MAX)
        max_dropped_ring = max(max_dropped_ring, ring_max)
        max_dropped_part = max(max_dropped_part, part_max)
        if merged.is_empty:
            continue
        if SIMPLIFY_TOL > 0:
            merged = merged.simplify(SIMPLIFY_TOL, preserve_topology=True)
        if merged.is_empty:
            continue
        gdict = mapping(merged)
        if COORD_DECIMALS is not None:
            gdict = _round_coords(gdict, COORD_DECIMALS)
        out.append({
            "type": "Feature",
            "geometry": gdict,
            "properties": {"province": prov},
        })

    # Province-count invariant (the load-bearing guard): every raw province must
    # survive to exactly one output feature. Fail loudly -- a dropped province
    # silently breaks plot generation and Trends search, not just the outline.
    out_provinces = {f["properties"]["province"] for f in out}
    missing = raw_provinces - out_provinces
    if missing:
        raise ValueError(
            f"build_province_boundaries dropped provinces {sorted(missing)}; "
            "the geometry pipeline must preserve every province (plots + search "
            "derive their province list from this output)."
        )

    # Sliver-cleanup visibility: print the largest ring/part dropped so a
    # shrinking empirical gap (a genuine large hole/island nearing the threshold)
    # is noticeable in the build log. The printed values are the real per-build
    # signal to watch.
    print(
        f"  province sliver cleanup: largest dropped ring {max_dropped_ring:.2e} "
        f"deg^2, largest dropped part {max_dropped_part:.2e} deg^2 "
        f"(threshold {PROVINCE_SLIVER_MAX:.0e})"
    )
    # Regression guard on _strip_slivers itself (NOT a per-build data check): it
    # must never report having dropped something at/above its own threshold. True
    # by construction today; trips only if a future edit breaks that contract.
    # A raise (not assert) so it survives `python -O`.
    if not (max_dropped_ring < PROVINCE_SLIVER_MAX and max_dropped_part < PROVINCE_SLIVER_MAX):
        raise ValueError(
            f"_strip_slivers reported dropping at/above its threshold: ring "
            f"{max_dropped_ring:.2e}, part {max_dropped_part:.2e} deg^2 "
            f"(threshold {PROVINCE_SLIVER_MAX:.0e})"
        )

    return {"type": "FeatureCollection", "features": out}


def _load_build_geojson_properties() -> dict[str, dict]:
    """Return {nom: properties_dict} from the build GeoJSON."""
    with open(BUILD_GEOJSON) as f:
        raw = json.load(f)
    return {feat["properties"]["nom"]: feat["properties"]
            for feat in raw["features"]}


# Tracker / sitrep field name → insp_sitrep block key in drc_health_zones.geojson.
_NATIONAL_INSP_KEYS = (
    ("confirmed_cases", "national_cumulative_confirmed_cases"),
    ("suspected_cases", "national_cumulative_suspected_cases"),
    ("confirmed_deaths", "national_cumulative_confirmed_deaths"),
    ("suspected_deaths", "national_cumulative_suspected_deaths"),
    ("recovered_cases", "national_cumulative_recovered_cases"),
)


def _national_totals_from_build_geojson() -> dict | None:
    """DRC national INSP totals from the build GeoJSON (same shape as sitrep dict)."""
    # Abort if the build artefact path is missing (no national figures available).
    if not BUILD_GEOJSON.exists():
        return None
    # Open the zone polygon file that also carries insp_sitrep properties.
    with open(BUILD_GEOJSON) as f:
        raw = json.load(f)
    # Pull the Feature array; an empty file cannot supply totals.
    features = raw.get("features") or []
    if not features:
        return None
    # National metrics are copied onto every zone; any one feature is sufficient.
    props = features[0].get("properties") or {}
    # INSP sitrep blocks (zone + national) live under this nested dict.
    insp = props.get("insp_sitrep") or {}
    if not isinstance(insp, dict):
        return None
    # Will hold snake_case keys used by the tracker (confirmed_cases, etc.).
    metrics: dict[str, int | None] = {}
    for dst, insp_key in _NATIONAL_INSP_KEYS:
        # Each national metric is a small dict: {metric_name: value, _date: ...}.
        block = insp.get(insp_key)
        if not isinstance(block, dict):
            metrics[dst] = None
            continue
        # Inner key repeats the block name (same pattern as zone cumulative_*).
        metrics[dst] = _i(block.get(insp_key))
    # If every national field is missing, do not pretend we have a sitrep.
    if not any(v is not None for v in metrics.values()):
        return None
    # Coerce None → 0 for arithmetic and JSON output (tracker expects integers).
    conf = int(metrics.get("confirmed_cases") or 0)
    susp = int(metrics.get("suspected_cases") or 0)
    conf_d = int(metrics.get("confirmed_deaths") or 0)
    susp_d = int(metrics.get("suspected_deaths") or 0)
    rec = int(metrics.get("recovered_cases") or 0)
    # Single-country row: national_* in GeoJSON are DRC-only aggregates.
    per_country = [{
        "country": "DRC",
        "confirmed_cases": conf,
        "suspected_cases": susp,
        "confirmed_deaths": conf_d,
        "suspected_deaths": susp_d,
        "recovered_cases": rec,
        "total": conf + susp,
    }]
    # Match compute_global_sitrep_totals() so build_payload can merge blindly.
    return {
        "global_confirmed_cases": conf,
        "global_suspected_cases": susp,
        "global_confirmed_deaths": conf_d,
        "global_suspected_deaths": susp_d,
        "global_recovered_cases": rec,
        "global_total_cases": conf,
        "affected_countries": ["DRC"],
        "affected_country_count": 1,
        "per_country": per_country,
    }


# ---------------------------------------------------------------------------
# Tracker caveats (optional CSV beside national totals in the title panel)
# ---------------------------------------------------------------------------

_TRACKER_CAVEAT_METRIC_ALIASES = {
    "confirmed_cases": (
        "confirmed_cases", "confirmed cases", "confirmed", "conf", "conf_cases",
    ),
    "suspected_cases": (
        "suspected_cases", "suspected cases", "suspected", "susp", "susp_cases",
    ),
    "confirmed_deaths": (
        "confirmed_deaths", "confirmed deaths", "conf_deaths", "conf deaths",
    ),
    "suspected_deaths": (
        "suspected_deaths", "suspected deaths", "susp_deaths", "susp deaths",
    ),
}

_TRACKER_CAVEAT_MARKS = ("*", "†", "‡", "§")

_TRACKER_CAVEAT_WARNING_COLS = (
    "warning", "warnings", "caveat", "caveats", "message", "text", "note",
)


def _normalize_tracker_caveat_metric(raw: str) -> str | None:
    key = re.sub(r"[\s\-]+", "_", str(raw).strip().lower())
    for canonical, aliases in _TRACKER_CAVEAT_METRIC_ALIASES.items():
        if key in aliases:
            return canonical
    return None


def load_tracker_caveats(lang: str = "en") -> list[dict]:
    """Load tracker footnotes from Data/caveats.csv.

    Each row adds an asterisk (or †, ‡, § for further rows) beside the matching
    national metric in the per-country tracker line and a footnote below.

    Expected CSV::

        metric,warning[,warning_fr]
        suspected_cases,National suspected counts include contacts under surveillance.

    ``metric`` must resolve to one of: confirmed_cases, suspected_cases,
    confirmed_deaths, suspected_deaths (aliases like ``susp`` are accepted).
    """
    if not CAVEATS_CSV.exists():
        return []
    df = pd.read_csv(CAVEATS_CSV)
    if df.empty:
        print(f"  WARNING: {CAVEATS_CSV.name} is empty")
        return []
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "metric" not in df.columns:
        print(f"  WARNING: {CAVEATS_CSV.name} needs a 'metric' column")
        return []
    warn_col = next((c for c in _TRACKER_CAVEAT_WARNING_COLS if c in df.columns), None)
    if warn_col is None:
        print(f"  WARNING: {CAVEATS_CSV.name} needs a warning column "
              f"(e.g. warning, message, caveat)")
        return []
    fr_col = "warning_fr" if "warning_fr" in df.columns else None
    out: list[dict] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        metric = _normalize_tracker_caveat_metric(row["metric"])
        if metric is None:
            print(f"  WARNING: unknown tracker caveat metric {row['metric']!r}")
            continue
        if metric in seen:
            print(f"  WARNING: duplicate caveat for {metric}; keeping first row")
            continue
        warning = ""
        if lang == "fr" and fr_col:
            warning = str(row[fr_col]).strip()
        if not warning or warning.lower() in ("nan", "none"):
            warning = str(row[warn_col]).strip()
        if not warning or warning.lower() in ("nan", "none"):
            continue
        mark = _TRACKER_CAVEAT_MARKS[len(out)] if len(out) < len(_TRACKER_CAVEAT_MARKS) else "*"
        out.append({"metric": metric, "mark": mark, "warning": warning})
        seen.add(metric)
    if out and lang == "en":
        print(f"  tracker caveats: {[c['metric'] for c in out]}")
    return out


# ---------------------------------------------------------------------------
# Imperial College model estimates (separate from INSP sitreps)
# ---------------------------------------------------------------------------

_IC_MODEL_DEFAULTS = {
    "ic_model_date": None,
    "ic_model_lowerbound": None,
    "ic_model_upperbound": None,
}

_IC_MODEL_COL_ALIASES = {
    "ic_model_date": ("ic_model_date", "date", "as_of", "asof"),
    "ic_model_lowerbound": (
        "ic_model_lowerbound", "lowerbound", "lower_bound", "lower"),
    "ic_model_upperbound": (
        "ic_model_upperbound", "upperbound", "upper_bound", "upper"),
}


def _resolve_ic_model_column(df: pd.DataFrame, field: str) -> str | None:
    """Return the actual CSV column name for a payload field, if present."""
    for alias in _IC_MODEL_COL_ALIASES[field]:
        if alias in df.columns:
            return alias
    return None


def _parse_ic_model_scalar(value) -> str | int | float | None:
    """Normalize one CSV cell for JSON payload (None → NA in the dashboard)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    # Prefer integers for bounds when whole numbers.
    num = pd.to_numeric(value, errors="coerce")
    if pd.notna(num):
        rounded = float(num)
        if rounded == int(rounded):
            return int(rounded)
        return rounded
    return str(value).strip()


def load_ic_model_estimates(country: str = "DRC") -> dict:
    """Load Imperial College bounds from Data/ic_model_estimates.csv.

    Not tied to sit-rep CSVs or GeoJSON. Exposed as PAYLOAD.ic_model with keys
    ic_model_date, ic_model_lowerbound, ic_model_upperbound (null if missing).

    Expected CSV (column names flexible via aliases):
        country,ic_model_date,ic_model_lowerbound,ic_model_upperbound
        DRC,2026-05-26,500,1200

    If ``country`` is omitted, the first data row is used.
    """
    out = dict(_IC_MODEL_DEFAULTS)
    if not IC_MODEL_CSV.exists():
        print(f"  NOTE: {IC_MODEL_CSV.name} not found; ic_model defaults to NA in UI")
        return out
    df = pd.read_csv(IC_MODEL_CSV)
    if df.empty:
        print(f"  WARNING: {IC_MODEL_CSV.name} is empty")
        return out
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    work = df
    if "country" in df.columns:
        mask = df["country"].astype(str).str.strip().str.upper() == country.upper()
        if mask.any():
            work = df[mask]
        else:
            print(f"  WARNING: no row for country={country!r} in {IC_MODEL_CSV.name}")
    row = work.iloc[0]
    for field in _IC_MODEL_DEFAULTS:
        col = _resolve_ic_model_column(df, field)
        if col is None:
            continue
        parsed = _parse_ic_model_scalar(row[col])
        if field == "ic_model_date" and parsed is not None:
            # Pretty-print ISO dates for the tooltip; leave other strings as-is.
            try:
                d = datetime.strptime(str(parsed)[:10], "%Y-%m-%d").date()
                parsed = d.strftime("%d %b %Y").lstrip("0")
            except ValueError:
                parsed = str(parsed)
        out[field] = parsed
    print(f"  ic_model: date={out['ic_model_date']!r}, "
          f"bounds={out['ic_model_lowerbound']!r}–{out['ic_model_upperbound']!r}")
    return out


def _slugify_plot_key(text: str) -> str:
    """Normalize labels for matching plot filenames (e.g. Kasaï → kasai)."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _read_plot_svg(path: Path) -> str | None:
    if not path.exists():
        return None
    svg = path.read_text(encoding="utf-8").strip()
    if svg.startswith("<?xml"):
        svg = svg.split("?>", 1)[-1].strip()
    return svg or None


def _svg_plot_title(svg: str, fallback: str) -> str:
    # Require a "- <place>" suffix so we match the real chart title rather than
    # a legend/series label that happens to repeat the same base phrase earlier
    # in the SVG markup (e.g. rolling_positivity's "5-day Rolling Test
    # Positivity" legend entry, which has no place suffix and appears before
    # the actual title).
    for prefix in (
        "Daily Cases by Symptom Onset",
        "Cumulative Confirmed Deaths",
        "5-day Rolling Test Positivity",
    ):
        match = re.search(
            r">\s*(" + re.escape(prefix) + r"\s*-\s*[^<]+?)\s*<",
            svg,
            flags=re.I,
        )
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return fallback


def _load_lab_name_map() -> dict[str, str]:
    """Map lab plot keys / codes to display labels."""
    path = DASHBOARD_PLOTS_DIR / "lab_name_map.csv"
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  WARNING: could not read {path.name}: {exc}")
        return out
    if df.shape[1] < 2:
        return out
    key_col, val_col = df.columns[0], df.columns[1]
    for _, row in df.iterrows():
        key = str(row.get(key_col) or "").strip()
        val = str(row.get(val_col) or "").strip()
        if not key or not val:
            continue
        out[_slugify_plot_key(key)] = val
        out[_slugify_plot_key(key.replace(" ", ""))] = val
        out[key.upper()] = val
    return out


def _lab_label_from_stem(stem: str, name_map: dict[str, str]) -> str:
    raw = stem[4:] if stem.lower().startswith("lab_") else stem
    slug = _slugify_plot_key(raw)
    if slug in name_map:
        return name_map[slug]
    compact = slug.replace("-", "")
    if compact in name_map:
        return name_map[compact]
    upper = raw.upper().replace("_", "-")
    if upper in name_map:
        return name_map[upper]
    # Fall back to the plot-name token (e.g. inrbk → INRBK).
    return re.sub(r"[-_]+", "-", raw).upper()


def _lab_code_from_stem(stem: str, manifest_labs: dict) -> str | None:
    """Match a lab_*.svg stem back to the manifest lab_code (e.g. lab_lpspbn → LPSPBN)."""
    raw = stem[4:] if stem.lower().startswith("lab_") else stem
    for suffix in ("_samples", "_positivity"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    slug = _slugify_plot_key(raw)
    for code in manifest_labs:
        if _slugify_plot_key(code) == slug:
            return code
    return None


def _load_plot_type_family(
    type_dir: Path,
    filename_prefix: str,
    national_title_default: str,
    label_title_fmt: str,
    province_by_slug: dict[str, str],
    nom_by_slug: dict[str, str],
    manifest_meta: dict,
) -> tuple[dict | None, dict[str, dict], dict[str, dict]]:
    """Load one plot type's national/province/health-zone SVGs from
    ``type_dir`` (already resolved to e.g. .../confirmed_cases_and_positivity
    or .../cumulative_deaths).

    Handles both the current layout (national/provincial/healthzone
    subfolders under type_dir) and the older flat layout (files directly in
    type_dir, health zones under a bare "healthzone" subfolder). Province
    entries missing from disk are filled in from ``manifest_meta``
    (province -> {file, title, caption}), matching load_dashboard_plots'
    manifest handling.
    """
    national = None
    national_path = type_dir / "national" / f"{filename_prefix}national.svg"
    if not national_path.exists():
        national_path = type_dir / f"{filename_prefix}national.svg"
    nat_svg = _read_plot_svg(national_path)
    if nat_svg:
        national = {
            "id": "national",
            "label": "National",
            "file": str(national_path.relative_to(DASHBOARD_PLOTS_DIR)),
            "title": _svg_plot_title(nat_svg, national_title_default),
            "caption": "",
            "svg": nat_svg,
        }

    provincial_dir = type_dir / "provincial"
    if not provincial_dir.exists():
        provincial_dir = type_dir
    province_plots: dict[str, dict] = {}
    for svg_path in sorted(provincial_dir.glob(f"{filename_prefix}*.svg")):
        slug = svg_path.stem.removeprefix(filename_prefix)
        if slug == "national":
            continue
        svg = _read_plot_svg(svg_path)
        if not svg:
            continue
        label = province_by_slug.get(slug) or slug.replace("-", " ").title()
        province_plots[label] = {
            "id": label,
            "label": label,
            "slug": slug,
            "file": str(svg_path.relative_to(DASHBOARD_PLOTS_DIR)),
            "title": _svg_plot_title(svg, label_title_fmt.format(label=label)),
            "caption": "",
            "svg": svg,
        }

    # Manifest entries fill gaps only (province not already found on disk).
    for province, meta in (manifest_meta or {}).items():
        if not isinstance(meta, dict) or province in province_plots:
            continue
        filename = meta.get("file")
        if not filename:
            continue
        svg_path = DASHBOARD_PLOTS_DIR / filename
        svg = _read_plot_svg(svg_path)
        if not svg:
            continue
        province_plots[province] = {
            "id": province,
            "label": province,
            "slug": _slugify_plot_key(province),
            "file": filename,
            "title": meta.get("title") or label_title_fmt.format(label=province),
            "caption": meta.get("caption") or "",
            "svg": svg,
        }

    hz_plots: dict[str, dict] = {}
    hz_dir = type_dir / "healthzone"
    if hz_dir.exists():
        for svg_path in sorted(hz_dir.glob(f"{filename_prefix}*.svg")):
            slug = svg_path.stem.removeprefix(filename_prefix)
            svg = _read_plot_svg(svg_path)
            if not svg:
                continue
            nom = nom_by_slug.get(slug) or slug.replace("-", " ").title()
            hz_plots[nom] = {
                "id": nom,
                "label": nom,
                "slug": slug,
                "file": str(svg_path.relative_to(DASHBOARD_PLOTS_DIR)),
                "title": _svg_plot_title(svg, label_title_fmt.format(label=nom)),
                "caption": "",
                "svg": svg,
            }

    return national, province_plots, hz_plots


# Pre-built onset / lab plots for the Epidemiological trends panel.
def load_dashboard_plots(
    zone_noms: list[str] | None = None,
    provinces: list[str] | None = None,
) -> dict | None:
    """Load national, province, health-zone, and lab SVG plots.

    Two on-disk layouts are supported, auto-detected via manifest.json's
    top-level "date" field.

    Current (per-date, split by plot type then spatial scope)::

        dashboard_plots/
          manifest.json                              (has a "date")
          <date>/dashboard_plots/
            confirmed_cases_and_positivity/
              national/daily_onset_national.svg
              provincial/daily_onset_<province>.svg
              healthzone/daily_onset_<zone>.svg
            lab_plots/lab_<code>.svg

    Older, flat layout (used whenever the dated/typed folder above isn't
    found -- e.g. manifest.json has no "date", or local test data)::

        dashboard_plots/
          daily_onset_<province>.svg
          national/daily_onset_national.svg
          healthzone/daily_onset_<zone>.svg
          lab/lab_<code>.svg
          lab_name_map.csv   (optional)

    manifest.json province plots are read from
    ``plots.confirmed_cases_and_positivity.<province>`` and
    ``plots.cumulative_deaths.<province>`` (the whole ``plots`` dict is
    treated as the confirmed-cases entries for older manifests that predate
    the plot-type nesting) and only used to fill gaps left by the
    ``daily_onset_*.svg`` / ``cumulative_deaths_*.svg`` globs below.

    The data repo also produces a parallel "cumulative_deaths" plot type
    alongside "confirmed_cases_and_positivity" (same national/provincial/
    healthzone split, no lab plots); it's returned under the
    ``cumulative_deaths`` key.

    ``manifest.indexes`` (``by_health_zone`` / ``by_province``) is passed
    through for location-based lab subsetting, and each lab entry is
    enriched from ``manifest.plots.lab_plots`` with ``lab_code``,
    ``health_zone``, and ``province``.
    """
    if not DASHBOARD_PLOTS_DIR.exists():
        print(f"  NOTE: {DASHBOARD_PLOTS_DIR} not found; trends plots unavailable")
        return None

    manifest: dict = {}
    manifest_path = DASHBOARD_PLOTS_DIR / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  WARNING: invalid {manifest_path.name}: {exc}")

    # Resolve the actual plots base dir: <DASHBOARD_PLOTS_DIR>/<date>/dashboard_plots
    # when manifest.json points at one and it exists on disk, else fall back
    # to the older flat layout directly under DASHBOARD_PLOTS_DIR.
    manifest_date = manifest.get("date")
    plots_base = DASHBOARD_PLOTS_DIR
    if manifest_date:
        dated_base = DASHBOARD_PLOTS_DIR / str(manifest_date) / "dashboard_plots"
        if dated_base.exists():
            plots_base = dated_base

    # Within plots_base, each plot type lives under its own folder in the
    # current layout; older data has confirmed-cases plots directly in
    # plots_base with no plot-type wrapper (and no cumulative_deaths at all).
    cases_dir = plots_base / "confirmed_cases_and_positivity"
    if not cases_dir.exists():
        cases_dir = plots_base
    deaths_dir = plots_base / "cumulative_deaths"
    positivity_dir = plots_base / "rolling_positivity"
    # Lab plots' folder was renamed lab -> lab_plots.
    lab_dir = plots_base / "lab_plots"
    if not lab_dir.exists():
        lab_dir = plots_base / "lab"

    zone_noms = list(zone_noms or [])
    provinces = list(provinces or [])
    nom_by_slug = {_slugify_plot_key(n): n for n in zone_noms if n}
    province_by_slug = {_slugify_plot_key(p): p for p in provinces if p}

    manifest_plots = manifest.get("plots") or {}
    cases_meta = manifest_plots.get("confirmed_cases_and_positivity")
    if not isinstance(cases_meta, dict):
        cases_meta = manifest_plots  # older, pre-plot-type-nesting manifest shape
    deaths_meta = manifest_plots.get("cumulative_deaths")
    if not isinstance(deaths_meta, dict):
        deaths_meta = {}
    positivity_meta = manifest_plots.get("rolling_positivity")
    if not isinstance(positivity_meta, dict):
        positivity_meta = {}

    national, province_plots, hz_plots = _load_plot_type_family(
        cases_dir, "daily_onset_",
        "Daily Cases by Symptom Onset - National",
        "Daily Cases by Symptom Onset - {label}",
        province_by_slug, nom_by_slug, cases_meta,
    )

    deaths_national: dict | None = None
    deaths_province_plots: dict[str, dict] = {}
    deaths_hz_plots: dict[str, dict] = {}
    if deaths_dir.exists():
        deaths_national, deaths_province_plots, deaths_hz_plots = _load_plot_type_family(
            deaths_dir, "cumulative_deaths_",
            "Cumulative Confirmed Deaths - National",
            "Cumulative Confirmed Deaths - {label}",
            province_by_slug, nom_by_slug, deaths_meta,
        )

    positivity_national: dict | None = None
    positivity_province_plots: dict[str, dict] = {}
    positivity_hz_plots: dict[str, dict] = {}
    if positivity_dir.exists():
        positivity_national, positivity_province_plots, positivity_hz_plots = _load_plot_type_family(
            positivity_dir, "rolling_positivity_",
            "5-day Rolling Test Positivity - National",
            "5-day Rolling Test Positivity - {label}",
            province_by_slug, nom_by_slug, positivity_meta,
        )

    lab_name_map = _load_lab_name_map()
    manifest_labs = manifest_plots.get("lab_plots")
    if not isinstance(manifest_labs, dict):
        manifest_labs = {}
    labs: list[dict] = []
    if manifest_labs:
        for lab_code, meta in manifest_labs.items():
            if not isinstance(meta, dict):
                continue
            plot_file = meta.get("file")
            if not plot_file:
                continue
            svg = _read_plot_svg(DASHBOARD_PLOTS_DIR / plot_file)
            if not svg:
                continue
            label = meta.get("lab_name_long") or lab_code
            lab_id = f"lab_{_slugify_plot_key(lab_code)}"
            labs.append({
                "id": lab_id,
                "lab_code": lab_code,
                "label": label,
                "slug": _slugify_plot_key(lab_code),
                "health_zone": meta.get("health_zone"),
                "province": meta.get("province"),
                "file": plot_file,
                "title": meta.get("title") or _svg_plot_title(
                    svg, f"Samples Analysed and Test Positivity — {label}"
                ),
                "caption": meta.get("caption") or "",
                "svg": svg,
            })
    elif lab_dir.exists():
        for svg_path in sorted(lab_dir.glob("lab_*.svg")):
            if svg_path.stem.endswith(("_samples", "_positivity")):
                continue
            svg = _read_plot_svg(svg_path)
            if not svg:
                continue
            lab_id = svg_path.stem  # lab_inrbk
            lab_code = _lab_code_from_stem(lab_id, manifest_labs)
            meta = manifest_labs.get(lab_code) if lab_code else {}
            if not isinstance(meta, dict):
                meta = {}
            label = meta.get("lab_name_long") or _lab_label_from_stem(lab_id, lab_name_map)
            plot_title = meta.get("title") or _svg_plot_title(
                svg, f"Samples Analysed and Test Positivity — {label}"
            )
            labs.append({
                "id": lab_id,
                "lab_code": lab_code or meta.get("lab_code"),
                "label": label,
                "slug": _slugify_plot_key(lab_id.removeprefix("lab_")),
                "health_zone": meta.get("health_zone"),
                "province": meta.get("province"),
                "file": str(svg_path.relative_to(DASHBOARD_PLOTS_DIR)),
                "title": plot_title,
                "caption": meta.get("caption") or "",
                "svg": svg,
            })
    if labs:
        labs.sort(key=lambda x: str(x["label"]).lower())

    if (not national and not province_plots and not hz_plots and not labs
            and not deaths_national and not deaths_province_plots and not deaths_hz_plots
            and not positivity_national and not positivity_province_plots and not positivity_hz_plots):
        print(f"  WARNING: no loadable plots under {plots_base.relative_to(DASHBOARD_PLOTS_DIR.parent)}/")
        return None

    print(
        "  dashboard plots: "
        + f"national={'yes' if national else 'no'}"
        + f", {len(province_plots)} province(s)"
        + f", {len(hz_plots)} health zone(s)"
        + f", {len(labs)} lab(s)"
        + f", deaths national={'yes' if deaths_national else 'no'}"
        + f", deaths {len(deaths_province_plots)} province(s)"
        + f", deaths {len(deaths_hz_plots)} health zone(s)"
        + f", positivity national={'yes' if positivity_national else 'no'}"
        + f", positivity {len(positivity_province_plots)} province(s)"
        + f", positivity {len(positivity_hz_plots)} health zone(s)"
        + f" from {plots_base.relative_to(DASHBOARD_PLOTS_DIR.parent)}/"
    )
    return {
        "series": manifest.get("series") or [],
        "incomplete_styling": manifest.get("incomplete_styling") or {},
        "indexes": manifest.get("indexes") or {},
        "national": national,
        "provinces": province_plots,
        # Backward-compatible alias used by older panel code.
        "plots": province_plots,
        "health_zones": hz_plots,
        "labs": labs,
        "labs_by_code": {
            lab["lab_code"]: lab for lab in labs if lab.get("lab_code")
        },
        "cumulative_deaths": {
            "national": deaths_national,
            "provinces": deaths_province_plots,
            "health_zones": deaths_hz_plots,
        },
        "rolling_positivity": {
            "national": positivity_national,
            "provinces": positivity_province_plots,
            "health_zones": positivity_hz_plots,
        },
    }


def _parse_optional_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    text = str(value).strip()
    if not text or text.upper() in {"NA", "NAN", "NULL", "NONE", "."}:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _parse_optional_int(value) -> int | None:
    num = _parse_optional_float(value)
    if num is None:
        return None
    return int(round(num))


def _parse_boolish(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    return text in {"TRUE", "T", "1", "YES", "Y"}


def _parse_flexible_date(value):
    """Parse cutoff dates from CSV (DD/MM/YYYY, YYYY-MM-DD, etc.)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "date") and callable(getattr(value, "date", None)):
        try:
            return value.date() if hasattr(value, "hour") else value
        except Exception:
            pass
    text = str(value).strip()
    if not text or text.upper() in {"NA", "NAN", "NULL", "NONE", "."}:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text[:32], fmt).date()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
        if pd.notna(parsed):
            return parsed.date()
    except Exception:
        pass
    return None


_SPATIOTEMPORAL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _latest_spatiotemporal_key_outputs_dir() -> Path | None:
    """Newest ``<outputs>/<date>/spatiotemporal/key_outputs/`` dir with risk scores.

    ``DASHBOARD_PLOTS_DIR`` already points at
    BDBV2026-Processed_Sensitive_Data/outputs (see paths.py); this scans its
    dated subfolders independently of that dir's own dashboard_plots
    manifest.json ``date`` pointer, since the spatiotemporal Bayes pipeline
    runs on its own (sparser) cadence and its latest date may not match.
    """
    if not DASHBOARD_PLOTS_DIR.exists():
        return None
    candidates: list[tuple[str, Path]] = []
    for p in DASHBOARD_PLOTS_DIR.iterdir():
        if not p.is_dir() or not _SPATIOTEMPORAL_DATE_RE.match(p.name):
            continue
        key_outputs = p / "spatiotemporal" / "key_outputs"
        if (key_outputs / "bayes_risk_scores_all_zones.csv").exists():
            candidates.append((p.name, key_outputs))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[-1][1]


def load_invasion_risk_estimates(effective_active_noms: set[str] | None = None) -> dict | None:
    """Load Bayesian invasion-risk scores for the Epidemiological trends tab.

    Prefers ``horizon == 1`` (next forecast window). Zone names are expected to
    match GeoJSON ``nom`` values.

    Primary source: the newest dated
    ``spatiotemporal/key_outputs/bayes_risk_scores_all_zones.csv`` under
    BDBV2026-Processed_Sensitive_Data/outputs -- the model-selected
    ("featured") method's per-zone forecast for that pipeline run. That CSV
    has no ``cutoff_date`` column (unlike the legacy
    Data/invasion_risk_model_estimates.csv it replaces), so it's backfilled
    from the sibling run_info.json.

    NOTE: the backfill uses run_info.json's ``training_window_end``, not its
    ``linelist_cutoff_date``. The latter is only the WEEK-ANCHOR start of the
    final training week (run_all.R: "training_cutoff is the WEEK ANCHOR...");
    the actual last calendar day of training data is ``training_window_end``
    (== training_cutoff + 6), which is what run_all.R itself calls out as
    "the human-facing training cutoff" -- and what the dashboard displays
    verbatim as "Data up to {cutoff_date}". Using the week-anchor there was a
    bug: it understated data recency by up to 6 days. The forecast window
    shown alongside it (forecast_start_date/forecast_end_date) is derived
    here from that corrected cutoff_date -- NOT from run_info.json's own
    ``forecast_target_windows``, which has its own bug: window_start there is
    training_window_end + 1, but window_end is training_cutoff + 7*h (the
    week-anchor, 6 days earlier than training_window_end), so the two ends of
    the "window" use different anchors. That collapses to a same-day window
    for horizon=1 and understates the span by 6 days for horizon=2. See the
    comment at forecast_start_date/forecast_end_date below.

    Falls back to the legacy CSV if no spatiotemporal output is found (e.g.
    local dev without BDBV2026-Processed_Sensitive_Data checked out); in that
    fallback, cutoff_date/forecast_end_date keep the old CSV-column /
    arithmetic behaviour (no run_info.json equivalent exists there).
    """
    source_path: Path | None = None
    cutoff_override = None
    key_outputs_dir = _latest_spatiotemporal_key_outputs_dir()
    if key_outputs_dir is not None:
        source_path = key_outputs_dir / "bayes_risk_scores_all_zones.csv"
        run_info_path = key_outputs_dir / "run_info.json"
        if run_info_path.exists():
            try:
                run_info = json.loads(run_info_path.read_text(encoding="utf-8"))
                cutoff_override = run_info.get("training_window_end")
            except (json.JSONDecodeError, OSError) as exc:
                print(f"  WARNING: could not read {run_info_path.name}: {exc}")
        print(f"  invasion risk source: {source_path}")

    if source_path is None:
        if not INVASION_RISK_CSV.exists():
            print(
                "  NOTE: no spatiotemporal Bayes output found and "
                f"{INVASION_RISK_CSV.name} not found; "
                "Epidemiological trends tab unavailable"
            )
            return None
        source_path = INVASION_RISK_CSV
        print(f"  invasion risk source (legacy fallback): {source_path}")

    df = pd.read_csv(source_path)
    if df.empty:
        print(f"  WARNING: {source_path.name} is empty")
        return None
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    if "health_zone" not in df.columns:
        print(f"  WARNING: {source_path.name} missing health_zone column")
        return None

    if "cutoff_date" not in df.columns and cutoff_override:
        df["cutoff_date"] = cutoff_override

    # S5: mask the downloadable CSV to match the map — null the invasion fields
    # for zones the dashboard renders as active (effective>0), across ALL horizon
    # rows. Reverses the old "download_csv left untouched" behaviour, by decision.
    if effective_active_noms:
        _norm = df["health_zone"].astype(str).str.strip().map(
            lambda n: _NAME_TO_NOM.get(n, n))
        mask = _norm.isin(effective_active_noms)
        for col in (*_INVASION_AFFECTED_MASK_FIELDS, "p_case_high"):
            if col in df.columns:
                df.loc[mask, col] = None

    # Keep a full-file snapshot for CSV download (all horizons / columns).
    download_csv = df.to_csv(index=False)

    horizon_used = None
    if "horizon" in df.columns:
        as_str = df["horizon"].astype(str).str.strip()
        for candidate in ("1", "2"):
            subset = df[as_str == candidate]
            if not subset.empty:
                df = subset
                horizon_used = int(candidate)
                break

    cutoff_dates = []
    if "cutoff_date" in df.columns:
        for raw in df["cutoff_date"].tolist():
            parsed = _parse_flexible_date(raw)
            if parsed is not None:
                cutoff_dates.append(parsed)
    cutoff_date = max(cutoff_dates) if cutoff_dates else None

    horizon_windows = []
    window_col = next(
        (c for c in ("forecasting_window", "horizon_window") if c in df.columns),
        None,
    )
    if window_col is not None:
        for raw in df[window_col].tolist():
            hw = _parse_optional_float(raw)
            if hw is not None:
                horizon_windows.append(hw)
    elif horizon_used is not None:
        horizon_windows.append(float(horizon_used))
    horizon_window = None
    if horizon_windows:
        # Prefer the modal / first unique value for the filtered horizon slice.
        uniq = sorted({int(round(x)) for x in horizon_windows})
        horizon_window = uniq[0]

    # NOTE: run_info.json's own forecast_target_windows is NOT used here.
    # write_run_info.R computes window_start = training_window_end + 1 but
    # window_end = training_cutoff + 7*h -- two different anchors (the actual
    # last training day vs. its week-anchor, 6 days earlier). For horizon=1
    # that collapses window_start == window_end (both land on the same day),
    # and for horizon=2 it understates the span by 6 days. Rather than
    # surfacing that upstream inconsistency, derive both dates ourselves from
    # a single, consistent anchor: cutoff_date (already training_window_end
    # for the spatiotemporal source -- see above). Forecasting starts the day
    # after training ends and runs for horizon_window full weeks.
    forecast_start_date = None
    forecast_end_date = None
    if cutoff_date is not None:
        if key_outputs_dir is not None:
            # Only for the new source, where cutoff_date is reliably the last
            # training day -- the legacy CSV's cutoff_date has unverified
            # semantics, so leave forecast_start_date unset there (JS falls
            # back to its pre-existing cutoff_date-as-start behaviour).
            forecast_start_date = cutoff_date + timedelta(days=1)
        if horizon_window is not None:
            forecast_end_date = cutoff_date + timedelta(weeks=int(horizon_window))

    zones: dict[str, dict] = {}
    for _, row in df.iterrows():
        nom = str(row.get("health_zone") or "").strip()
        if not nom:
            continue
        zones[nom] = {
            "health_zone": nom,
            "province": str(row.get("province") or "").strip(),
            "was_active_before": _parse_boolish(row.get("was_active_before")),
            "p_case_invasion": _parse_optional_float(row.get("p_case_invasion")),
            "p_case_lo": _parse_optional_float(row.get("p_case_lo")),
            "p_case_hi": _parse_optional_float(
                row["p_case_hi"] if "p_case_hi" in df.columns else row.get("p_case_high")
            ),
            "rr_nat": _parse_optional_float(row.get("rr_nat")),
            "rr_nat_rank": _parse_optional_int(row.get("rr_nat_rank")),
            "rr_ituri": _parse_optional_float(row.get("rr_ituri")),
            "rr_ituri_rank": _parse_optional_int(row.get("rr_ituri_rank")),
            "rr_nordkivu": _parse_optional_float(row.get("rr_nordkivu")),
            "rr_nordkivu_rank": _parse_optional_int(row.get("rr_nordkivu_rank")),
            "rr_hautuele": _parse_optional_float(row.get("rr_hautuele")),
            "rr_hautuele_rank": _parse_optional_int(row.get("rr_hautuele_rank")),
            "priority": _parse_optional_float(row.get("priority")),
            "priority_rank": _parse_optional_int(row.get("priority_rank")),
            "surveillance_gap": _parse_optional_float(row.get("surveillance_gap")),
            "access_gap": _parse_optional_float(row.get("access_gap")),
            "social_vulnerability": _parse_optional_float(
                row.get("social_vulnerability")
            ),
            "method": str(row.get("method") or "").strip(),
        }

    methods = sorted({z["method"] for z in zones.values() if z.get("method")})
    method_note = methods[0] if len(methods) == 1 else "; ".join(methods)
    print(
        f"  invasion risk: {len(zones)} zones"
        + (f" (horizon={horizon_used})" if horizon_used is not None else "")
        + (f", cutoff={cutoff_date.isoformat()}" if cutoff_date else "")
        + (f", horizon_window={horizon_window}w" if horizon_window is not None else "")
        + (f", method={method_note!r}" if method_note else "")
    )
    return {
        "horizon": horizon_used,
        "horizon_window": horizon_window,
        "forecasting_window": horizon_window,
        "cutoff_date": cutoff_date.isoformat() if cutoff_date else None,
        "forecast_start_date": (
            forecast_start_date.isoformat() if forecast_start_date else None
        ),
        "forecast_end_date": (
            forecast_end_date.isoformat() if forecast_end_date else None
        ),
        "method": method_note,
        "method_label": "Mobility-epidemiological model of risk",
        "method_url": (
            "https://www.epidemiological.org/t/"
            "real-time-spatiotemporal-risk-modelling-of-the-bundibugyo-ebola-virus-outbreak-2026/16"
        ),
        "download_csv": download_csv,
        "p_case_invasion_label": (
            "Probability of invasion (defined as the probability of observing "
            "one new case within the next forecast window)"
        ),
        "scopes": [
            {"id": "national", "label": "National", "rr": "rr_nat", "rank": "rr_nat_rank", "province": None},
            {"id": "ituri", "label": "Ituri", "rr": "rr_ituri", "rank": "rr_ituri_rank", "province": "Ituri"},
            {"id": "nordkivu", "label": "Nord-Kivu", "rr": "rr_nordkivu", "rank": "rr_nordkivu_rank", "province": "Nord-Kivu"},
            {"id": "hautuele", "label": "Haut-Uele", "rr": "rr_hautuele", "rank": "rr_hautuele_rank", "province": "Haut-Uele"},
        ],
        "zones": zones,
    }


def _latest_spatiotemporal_pairwise_csv() -> Path | None:
    """Pairwise import-force CSV from the SAME dated folder as the risk table.

    Reuses _latest_spatiotemporal_key_outputs_dir() so the arrows and the
    invasion-risk table always come from one pipeline run. The reports CSV is
    a sibling of key_outputs: <date>/spatiotemporal/reports/.
    """
    ko = _latest_spatiotemporal_key_outputs_dir()
    if ko is None:
        return None
    csv = ko.parent / "reports" / "bayes_pairwise_import_force.csv"
    return csv if csv.exists() else None


def load_bayes_import_force_pairwise() -> dict | None:
    """Directed pairwise import-force (horizon 1) for spatial-risk arrow widths.

    Emits a sparse ``in_by_dest`` map keyed by health-zone ``nom``; each value
    is a list of ``[origin_nom, foi, share_of_dest]`` triples sorted by ``foi``
    descending. engine.js normalizes width per selected zone
    (``foi / max foi for that zone``). Returns None if the file is absent, so
    the build falls back to the confirmed-cases arrows.
    """
    csv_path = _latest_spatiotemporal_pairwise_csv()
    if csv_path is None:
        print("  NOTE: no bayes_pairwise_import_force.csv found; "
              "spatial-risk arrows fall back to confirmed cases")
        return None
    df = pd.read_csv(csv_path)
    if df.empty:
        print(f"  WARNING: {csv_path.name} is empty")
        return None
    df.columns = [str(c).strip() for c in df.columns]
    required = {"origin_zone", "dest_zone", "horizon", "foi", "share_of_dest"}
    missing = required - set(df.columns)
    if missing:
        print(f"  WARNING: {csv_path.name} missing columns: {sorted(missing)}")
        return None

    # Numeric compare (NOT stringified) — a blank cell makes pandas parse the
    # column as float, so "1" would read as "1.0" and a string match would drop
    # every row and silently disable the feature. See test_loader_handles_float_horizon.
    df = df[pd.to_numeric(df["horizon"], errors="coerce") == 1].copy()
    df["foi"] = pd.to_numeric(df["foi"], errors="coerce")
    df["share_of_dest"] = pd.to_numeric(df["share_of_dest"], errors="coerce")
    df = df.dropna(subset=["foi"])
    df = df[df["foi"] > 0]
    if df.empty:
        print(f"  WARNING: {csv_path.name} has no positive horizon==1 rows")
        return None

    in_by_dest: dict[str, list] = {}
    for dest, grp in df.groupby("dest_zone", sort=False):
        if pd.isna(dest):
            continue
        dest_nom = str(dest).strip()
        if not dest_nom:
            continue
        grp = grp.sort_values("foi", ascending=False)
        edges = []
        for _, r in grp.iterrows():
            ov = r["origin_zone"]
            if pd.isna(ov):
                continue
            origin = str(ov).strip()
            if not origin:
                continue
            share = r["share_of_dest"]
            edges.append([
                origin,
                float(r["foi"]),
                float(share) if pd.notna(share) else None,
            ])
        if edges:
            in_by_dest[dest_nom] = edges

    # beta = foi / import_force is a single global constant (spec: "derivable
    # from any row"); take the first positive-import_force row rather than a
    # median, so genuine data drift would surface as a wrong value instead of
    # being averaged away. Informational only — engine.js never reads it.
    beta = None
    if "import_force" in df.columns:
        imp = pd.to_numeric(df["import_force"], errors="coerce")
        good = df.loc[imp > 0]
        if not good.empty:
            first = good.iloc[0]
            beta = float(first["foi"] / float(imp.loc[good.index[0]]))

    # Provenance: the dated outputs folder (<date>/spatiotemporal/reports/...),
    # so a maintainer can confirm arrows and the invasion-risk table share a run.
    yyyymmdd = csv_path.parents[2].name

    n_edges = sum(len(v) for v in in_by_dest.values())
    print(f"  import-force pairwise: {len(in_by_dest)} dest zones, "
          f"{n_edges} h=1 edges"
          + (f", beta={beta:.4g}" if beta is not None else ""))
    return {
        "in_by_dest": in_by_dest,
        "horizon": 1,
        "beta": beta,
        "yyyymmdd": yyyymmdd,
        "source": csv_path.name,
    }


def load_harmonised_confirmed_cases(valid_noms: set[str]) -> dict[str, int]:
    """Per-zone harmonised (line-list ∪ sitrep) cumulative confirmed cases.

    Read from the newest dated
    ``spatiotemporal/key_outputs/harmonised_confirmed_cases.csv`` (same dir as
    ``bayes_risk_scores_all_zones.csv``). Keys are GeoJSON ``nom`` after
    ``_NAME_TO_NOM`` normalisation. Returns {} when the file is absent (the
    dashboard then falls back to sitrep-only ``effective``). Warns on any
    ``health_zone`` that does not match a GeoJSON ``nom``.
    """
    ko = _latest_spatiotemporal_key_outputs_dir()
    if ko is None:
        print("  NOTE: no spatiotemporal key_outputs dir; "
              "harmonised confirmed cases unavailable")
        return {}
    csv_path = ko / "harmonised_confirmed_cases.csv"
    if not csv_path.exists():
        print(f"  NOTE: {csv_path.name} not found; "
              "harmonised confirmed cases unavailable")
        return {}
    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]
    required = {"health_zone", "cumulative_confirmed_cases"}
    missing = required - set(df.columns)
    if missing:
        print(f"  WARNING: {csv_path.name} missing columns: {sorted(missing)}")
        return {}
    out: dict[str, int] = {}
    for _, row in df.iterrows():
        raw = str(row.get("health_zone") or "").strip()
        if not raw:
            continue
        nom = _NAME_TO_NOM.get(raw, raw)
        val = pd.to_numeric(row.get("cumulative_confirmed_cases"), errors="coerce")
        if pd.isna(val):
            continue
        out[nom] = int(val)
        if nom not in valid_noms:
            print(f"  WARNING: harmonised zone '{raw}'->'{nom}' "
                  "not in GeoJSON nom set (dropped from map)")
    print(f"  harmonised confirmed cases: {len(out)} zones")
    return out


# National + provincial invasion outputs the model masks to NA for an
# already-affected zone -- we clear the same set when reconciling one in.
_INVASION_AFFECTED_MASK_FIELDS = (
    "p_case_invasion", "p_case_lo", "p_case_hi",
    "rr_nat", "rr_nat_rank",
    "rr_ituri", "rr_ituri_rank",
    "rr_nordkivu", "rr_nordkivu_rank",
    "rr_hautuele", "rr_hautuele_rank",
    "priority", "priority_rank",
)


def _compact_ranks(rows: list[dict], rank_key: str) -> None:
    """Renumber ``rank_key`` over ``rows``, closing the gaps left by removed zones
    while preserving the model's original ordering and ties.

    Re-ranks from the ORIGINAL rank values (not the rounded rr_nat / priority
    values the payload carries), so it reproduces the model's unrounded
    tie-breaking exactly: the payload rounds priority to 4dp (many collisions the
    model's rank does not share), so re-ranking off the stored value would
    diverge.

    ``new_rank = 1 + (rows with a strictly smaller original rank)`` is the whole
    computation -- this is dplyr ``min_rank`` applied to the original ranks: it
    re-packs toward 1..N, but tied zones share the lower rank and a tie therefore
    still leaves the usual min_rank gap after it (so e.g. two zones tied last
    among N land at N-1, not N) -- matching what the model itself emits. Rows with
    a None rank are skipped.
    """
    orig = sorted(r[rank_key] for r in rows if r.get(rank_key) is not None)
    for r in rows:
        v = r.get(rank_key)
        if v is None:
            continue
        r[rank_key] = 1 + sum(1 for x in orig if x < v)


def reconcile_invasion_active_cases(invasion_risk: dict | None,
                                    zone_data: dict) -> dict | None:
    """Move at-risk zones that already have confirmed cases into the affected set.

    The invasion model's ``was_active_before`` reflects the (sitrep-lagged) case
    data available when the model ran; the model runs on the line-list cadence
    and consumes a sitrep snapshot that trails real cases by 1-3 days. The
    dashboard builds later, so its per-zone ``confirmed_cases`` can already show a
    case the model hadn't ingested -- leaving that zone in the ranked at-risk
    table with an invasion probability it shouldn't have. Because national
    relative risk is normalised across the at-risk set (rr_nat = mu / mean(mu)),
    such a zone also distorts every other zone's rr_nat and rank.

    Reconcile one-directionally (at-risk -> affected, never the reverse; matches
    the model's "affected once a case appears" definition), mask its invasion
    outputs like the model does, then renormalise rr_nat and re-rank
    rr_nat_rank / priority_rank over the cleaned set. The raw ``download_csv`` is
    masked in load_invasion_risk_estimates (S5) so the downloaded CSV matches
    the reconciled map. See
    docs/superpowers/specs/2026-08-04-invasion-active-case-reconciliation-design.md.

    Mutates and returns ``invasion_risk`` (returns it unchanged when there is
    nothing to load or reconcile).
    """
    if not invasion_risk:
        return invasion_risk
    zones = invasion_risk.get("zones") or {}

    reconciled = []
    for nom, row in zones.items():
        if row.get("was_active_before"):
            continue
        try:
            conf = float((zone_data.get(nom) or {}).get("confirmed_cases") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf > 0:
            row["was_active_before"] = True
            for field in _INVASION_AFFECTED_MASK_FIELDS:
                if field in row:
                    row[field] = None
            reconciled.append(nom)

    if not reconciled:
        return invasion_risk

    # Cleaned national at-risk set (zones still carrying a national rr_nat).
    at_risk = [row for row in zones.values()
               if not row.get("was_active_before") and row.get("rr_nat") is not None]

    # rr_nat = mu / mean(mu over at-risk); rr_nat is proportional to mu, so
    # renormalising by the cleaned-set mean of the OLD rr_nat values (which
    # equals new_mean / old_mean) yields mu / new_mean -- the corrected rr_nat.
    rr_vals = [row["rr_nat"] for row in at_risk]
    mean_rr = (sum(rr_vals) / len(rr_vals)) if rr_vals else 0
    if mean_rr:
        for row in at_risk:
            row["rr_nat"] = row["rr_nat"] / mean_rr
    _compact_ranks(at_risk, "rr_nat_rank")

    priority_rows = [row for row in zones.values()
                     if not row.get("was_active_before") and row.get("priority") is not None]
    _compact_ranks(priority_rows, "priority_rank")

    print(f"  reconciled {len(reconciled)} zone(s) at-risk->affected from latest "
          f"confirmed cases: {', '.join(sorted(reconciled))}")
    return invasion_risk


def assert_harmonised_coverage(invasion_risk: dict | None,
                               zone_data: dict,
                               harmonised: dict) -> None:
    """Guard for the §5 invariant: every ``was_active_before`` zone must carry
    effective_confirmed_cases > 0. Enforced (raise) only when the harmonised
    artifact is present; when it is absent (pre-upstream-artifact interim) the
    same gap is expected, so warn instead of breaking the build — the engine's
    defensive no-data fill keeps those zones visible."""
    if not invasion_risk:
        return
    broken = [
        raw for raw, row in (invasion_risk.get("zones") or {}).items()
        if row.get("was_active_before")
        and int((zone_data.get(_NAME_TO_NOM.get(raw, raw)) or {})
                .get("effective_confirmed_cases") or 0) <= 0
    ]
    if not broken:
        return
    if harmonised:
        raise ValueError(
            "Active-before zones with no harmonised/effective count "
            f"(invariant broken, would render white): {sorted(broken)}")
    print("  WARNING: harmonised artifact absent; active zones with no count "
          f"render via the defensive no-data fill until it ships: {sorted(broken)}")


# ---------------------------------------------------------------------------
# INSP cumulative confirmed time series (Trends tab map slider)
# ---------------------------------------------------------------------------

_CONFIRMED_TS_LONG = (
    BUILD_LONG_DIR / "insp_sitrep__cumulative_confirmed_cases.csv"
)
_CONFIRMED_TS_PROCESSED = (
    EXTERNAL_DATA / "insp_sitrep" / "processed"
    / "insp_sitrep__cumulative_confirmed_cases__daily.csv"
)
_CONFIRMED_TS_SKIP_NOMS = frozenset({"DRC", "NA", "Sans Fiche", ""})


def _read_insp_cumulative_confirmed_df() -> pd.DataFrame | None:
    """Load long-format INSP cumulative confirmed cases (build/long or processed)."""
    for path in (_CONFIRMED_TS_LONG, _CONFIRMED_TS_PROCESSED):
        if not path.exists():
            continue
        df = pd.read_csv(path)
        lower = {str(c).strip().lower(): c for c in df.columns}
        if "nom" in lower and "date" in lower:
            nom_col = lower["nom"]
            date_col = lower["date"]
            val_col = next(
                (lower[k] for k in lower if k not in ("nom", "date")),
                None,
            )
            if val_col is None:
                continue
        else:
            df = pd.read_csv(path, header=None, names=["nom", "date", "value"])
            nom_col, date_col, val_col = "nom", "date", "value"
        out = df[[nom_col, date_col, val_col]].copy()
        out.columns = ["nom", "date", "value"]
        return out
    return None


def _parse_confirmed_count(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s.upper() in ("NA", "ND", "NAN", "NONE"):
        return None
    num = pd.to_numeric(s, errors="coerce")
    if pd.isna(num):
        return None
    return int(round(float(num)))


def load_confirmed_cases_timeseries(valid_noms: set[str]) -> dict | None:
    """Build carry-forward cumulative confirmed series for the Trends tab slider.

    Untracked zones (no row before a date) are 0. Tracked zones carry forward
    the last known cumulative count when a sitrep date has no update (or ND).
    """
    df = _read_insp_cumulative_confirmed_df()
    if df is None or df.empty:
        print("  NOTE: INSP cumulative confirmed time series not found; "
              "Trends map slider unavailable")
        return None

    df = df.copy()
    df["nom"] = df["nom"].astype(str).str.strip()
    df["nom"] = df["nom"].map(lambda n: _NAME_TO_NOM.get(n, n))
    df = df[~df["nom"].isin(_CONFIRMED_TS_SKIP_NOMS)]
    df = df[df["nom"].isin(valid_noms)]

    parsed_dates: list[tuple[date, str]] = []
    for raw in df["date"].astype(str).str.strip().unique():
        d = _parse_sitrep_date(raw)
        if d is not None:
            parsed_dates.append((d, raw))
    if not parsed_dates:
        print("  WARNING: no parseable dates in cumulative confirmed series")
        return None

    parsed_dates.sort(key=lambda x: x[0])
    iso_dates = [d.isoformat() for d, _ in parsed_dates]
    raw_by_iso = {d.isoformat(): raw for d, raw in parsed_dates}

    by_nom_date: dict[str, dict[str, int]] = {}
    for _, row in df.iterrows():
        d = _parse_sitrep_date(row["date"])
        if d is None:
            continue
        v = _parse_confirmed_count(row["value"])
        if v is None:
            continue
        by_nom_date.setdefault(row["nom"], {})[d.isoformat()] = v

    by_nom: dict[str, list[int]] = {}
    max_confirmed = 0
    min_positive: int | None = None
    for nom, date_vals in sorted(by_nom_date.items()):
        series: list[int] = []
        last: int | None = None
        for iso in iso_dates:
            if iso in date_vals:
                last = date_vals[iso]
            if last is None:
                series.append(0)
            else:
                series.append(last)
                max_confirmed = max(max_confirmed, last)
                if last > 0:
                    min_positive = (
                        last if min_positive is None else min(min_positive, last)
                    )
        by_nom[nom] = series

    if not by_nom:
        print("  WARNING: cumulative confirmed series has no zone-level rows")
        return None

    print(f"  confirmed time series: {len(iso_dates)} date(s), "
          f"{len(by_nom)} zone(s), max={max_confirmed}")
    return {
        "dates": iso_dates,
        "date_labels": {iso: raw_by_iso[iso] for iso in iso_dates},
        "by_nom": by_nom,
        "max_confirmed": max_confirmed,
        "min_positive": min_positive or 1,
    }


# ---------------------------------------------------------------------------
# INSP confirmed-case recency categories (Trends tab "Recency" toggle)
# ---------------------------------------------------------------------------

# Category integers used across the payload / engine.js:
#   1 active  (<= near_days since last case)
#   2 recent  (near_days < d <= mid_days)
#   3 dormant (d > mid_days)
#   4 never   (no confirmed case yet as of the frame)
_RECENCY_LABELS = {
    "1": "active",
    "2": "recent",
    "3": "dormant",
    "4": "never",
}


def compute_confirmed_recency_timeseries(
    confirmed_ts: dict | None,
    near_days: int = 14,
    mid_days: int = 42,
) -> dict | None:
    """Derive per-zone, per-frame confirmed-case *recency* categories.

    Pure transform of the ``confirmed_timeseries`` dict produced by
    ``load_confirmed_cases_timeseries`` -- no I/O. For each zone and each frame
    date, classify by days since the zone's most recent *new* confirmed case
    (the last date its carry-forward cumulative count increased), measured from
    that frame's date. Returns ``None`` when the input is missing/empty so the
    Trends toggle silently stays unavailable, matching the slider's posture.
    """
    if not confirmed_ts:
        return None
    dates = confirmed_ts.get("dates") or []
    by_nom_cum = confirmed_ts.get("by_nom") or {}
    if not dates or not by_nom_cum:
        return None

    # Parse frame dates once; day arithmetic is exact even for irregular frames.
    parsed: list[date] = []
    for iso in dates:
        d = _parse_sitrep_date(iso)
        if d is None:
            return None
        parsed.append(d)

    by_nom: dict[str, list[int]] = {}
    days_by_nom: dict[str, list[int]] = {}
    for nom, series in by_nom_cum.items():
        cats: list[int] = []
        days: list[int] = []
        last_event_idx: int | None = None
        prev = 0
        for i, raw in enumerate(series):
            cum = int(raw or 0)
            # A *new* case = the cumulative count went up since the previous
            # frame. A nonzero value at the first frame is a baseline event.
            if cum > prev:
                last_event_idx = i
            prev = cum
            if last_event_idx is None:
                cats.append(4)
                days.append(-1)
            else:
                d = (parsed[i] - parsed[last_event_idx]).days
                days.append(d)
                if d <= near_days:
                    cats.append(1)
                elif d <= mid_days:
                    cats.append(2)
                else:
                    cats.append(3)
        by_nom[nom] = cats
        days_by_nom[nom] = days

    return {
        "dates": list(dates),
        "by_nom": by_nom,
        "days_by_nom": days_by_nom,
        "thresholds": {"near": near_days, "mid": mid_days},
        "labels": dict(_RECENCY_LABELS),
    }


# ---------------------------------------------------------------------------
# Public health response context (INSP SitRep pillars → Context tab)
# ---------------------------------------------------------------------------

_PHR_DATASET = "public_health_response"
_PHR_NON_TEXT = {"ND", "NA", ""}

_PHR_ZONE_METRICS = (
    "epidemiological_coordination",
    "epidemiological_monitoring",
    "epidemiological_management",
    "epidemiological_laboratory",
    "epidemiological_infection_prevention_controle",
    "epidemiological_logistics",
    "epidemiological_security",
    "epidemiological_community_engagement",
    "epidemiological_protection_sexual_exploitation_abuse",
)

_PHR_METRIC_LABELS: dict[str, str] = {
    "epidemiological_coordination": "Coordination",
    "epidemiological_monitoring": "Surveillance & monitoring",
    "epidemiological_management": "Case management",
    "epidemiological_laboratory": "Laboratory",
    "epidemiological_infection_prevention_controle": "Infection prevention & control",
    "epidemiological_logistics": "Logistics",
    "epidemiological_security": "Security",
    "epidemiological_community_engagement": "Community engagement",
    "epidemiological_protection_sexual_exploitation_abuse": (
        "Protection from sexual exploitation & abuse"
    ),
}


def _phr_metric_label(metric: str) -> str:
    key = metric.removeprefix("national_").removeprefix("provincial_")
    return _PHR_METRIC_LABELS.get(key, _prettify_label(key))


def _phr_category(metric: str) -> str:
    """Stable pillar slug for CSS category styling (strip roll-up prefixes)."""
    return metric.removeprefix("national_").removeprefix("provincial_")


def _phr_scope_tag(scope: str, province: str | None = None) -> str:
    if scope == "national":
        return "NATIONAL"
    if scope == "provincial" and province:
        return province.upper()
    return scope.upper()


def _parse_phr_date(value) -> datetime.date | None:
    """Parse PHR ``_date`` values (ISO, slash forms, and INSP ``DD-MM-YYYY``)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) >= 10 and s[2:3] == "-" and s[5:6] == "-":
        try:
            return datetime.strptime(s[:10], "%d-%m-%Y").date()
        except ValueError:
            pass
    return _parse_sitrep_date(s)


def _sort_phr_pillars(pillars: list[dict]) -> list[dict]:
    """Newest ``date`` first; pillar label breaks ties. Ignores pillar metric order."""
    return sorted(
        pillars,
        key=lambda p: (
            _parse_phr_date(p.get("date")) or date.min,
            p.get("label") or "",
        ),
        reverse=True,
    )


def _extract_phr_block(block: object) -> tuple[str | None, str | None]:
    """Return (narrative text, date string) from one GeoJSON metric object."""
    if not isinstance(block, dict):
        return None, None
    date_raw = block.get("_date")
    date = str(date_raw).strip() if date_raw not in (None, "") else None
    text = None
    for key, val in block.items():
        if key == "_date":
            continue
        if val is None:
            continue
        s = str(val).strip()
        if s and s not in _PHR_NON_TEXT:
            text = s
            break
    return text, date


def _phr_metric_candidates(base_metric: str, scope: str, lang: str) -> list[str]:
    """GeoJSON metric keys to try: bilingual ``_{lang}`` first, then legacy unsuffixed."""
    if scope == "national":
        return [f"national_{base_metric}_{lang}", f"national_{base_metric}"]
    if scope == "provincial":
        return [f"provincial_{base_metric}_{lang}", f"provincial_{base_metric}"]
    return [f"{base_metric}_{lang}", base_metric]


def _phr_extract_from_phr(phr: dict, base_metric: str, scope: str, lang: str) -> tuple[str | None, str | None]:
    for metric in _phr_metric_candidates(base_metric, scope, lang):
        text, date = _extract_phr_block(phr.get(metric))
        if text:
            return text, date
    return None, None


def _load_public_health_context_for_lang(
    props_by_nom: dict[str, dict],
    sample_phr: dict,
    lang: str,
) -> dict:
    rollups: list[dict] = []
    for base_metric in _PHR_ZONE_METRICS:
        text, date = _phr_extract_from_phr(sample_phr, base_metric, "national", lang)
        if not text:
            continue
        parsed = _parse_phr_date(date)
        rollups.append({
            "metric": base_metric,
            "category": _phr_category(base_metric),
            "label": _phr_metric_label(base_metric),
            "text": text,
            "date": date,
            "date_iso": parsed.isoformat() if parsed else None,
            "scope": "national",
            "scope_tag": _phr_scope_tag("national"),
        })

    seen_provincial: set[tuple[str, str]] = set()
    for nom in sorted(props_by_nom):
        props = props_by_nom[nom]
        province = props.get("province")
        if not province:
            continue
        phr = props.get(_PHR_DATASET) or {}
        if not isinstance(phr, dict):
            continue
        for base_metric in _PHR_ZONE_METRICS:
            key = (province, base_metric)
            if key in seen_provincial:
                continue
            text, date = _phr_extract_from_phr(phr, base_metric, "provincial", lang)
            if not text:
                continue
            seen_provincial.add(key)
            parsed = _parse_phr_date(date)
            rollups.append({
                "metric": base_metric,
                "category": _phr_category(base_metric),
                "label": _phr_metric_label(base_metric),
                "text": text,
                "date": date,
                "date_iso": parsed.isoformat() if parsed else None,
                "scope": "provincial",
                "scope_tag": _phr_scope_tag("provincial", province),
                "province": province,
            })

    rollups = _sort_phr_pillars(rollups)

    by_nom: dict[str, list[dict]] = {}
    for nom, props in props_by_nom.items():
        phr = props.get(_PHR_DATASET) or {}
        if not isinstance(phr, dict):
            continue
        pillars: list[dict] = []
        for base_metric in _PHR_ZONE_METRICS:
            text, date = _phr_extract_from_phr(phr, base_metric, "zone", lang)
            if not text:
                continue
            parsed = _parse_phr_date(date)
            pillars.append({
                "metric": base_metric,
                "category": _phr_category(base_metric),
                "label": _phr_metric_label(base_metric),
                "text": text,
                "date": date,
                "date_iso": parsed.isoformat() if parsed else None,
                "scope": "zone",
            })
        if pillars:
            by_nom[nom] = _sort_phr_pillars(pillars)

    return {"national": rollups, "by_nom": by_nom}


def load_public_health_context() -> dict[str, dict]:
    """Extract INSP pillar narratives from the build GeoJSON for the Context tab.

    Returns per-language payloads keyed by ``en`` / ``fr``. GeoJSON metrics use
    bilingual keys (e.g. ``epidemiological_coordination_en``); legacy unsuffixed
    keys are still accepted as a fallback.
    """
    empty = {lang: {"national": [], "by_nom": {}} for lang in SUPPORTED_LANGS}
    if not BUILD_GEOJSON.exists():
        print(f"  NOTE: {BUILD_GEOJSON.name} not found; context tab unavailable")
        return empty

    props_by_nom = _load_build_geojson_properties()
    if not props_by_nom:
        return empty

    sample_phr = (next(iter(props_by_nom.values())).get(_PHR_DATASET) or {})
    if not isinstance(sample_phr, dict) or not sample_phr:
        print(f"  NOTE: no {_PHR_DATASET} block in build GeoJSON; context tab empty")
        return empty

    by_lang: dict[str, dict] = {}
    for lang in SUPPORTED_LANGS:
        ctx = _load_public_health_context_for_lang(props_by_nom, sample_phr, lang)
        by_lang[lang] = ctx
        n_national = sum(1 for p in ctx["national"] if p.get("scope") == "national")
        n_provincial = sum(1 for p in ctx["national"] if p.get("scope") == "provincial")
        print(
            f"  public health context ({lang}): {n_national} national + "
            f"{n_provincial} provincial pillar(s), "
            f"{len(ctx['by_nom'])} zone(s) with local narrative"
        )
    return by_lang


# ---------------------------------------------------------------------------
# per-zone payload
# ---------------------------------------------------------------------------

def _load_local_csv_fields() -> dict[str, dict]:
    """Load fields only available in the local metadata CSV (not in the build),
    keyed by nom (using _NAME_TO_NOM to translate CSV name → build nom)."""
    if not METADATA_CSV.exists():
        print(f"  WARNING: {METADATA_CSV} not found, local-only fields unavailable")
        return {}
    df = pd.read_csv(METADATA_CSV)
    df = df.dropna(subset=["ref_dhis2"]).copy()
    df["name"] = df["name"].astype(str)

    if "relative_risk" not in df.columns and "projected_true_infections" in df.columns:
        proj = pd.to_numeric(df["projected_true_infections"], errors="coerce")
        proj_max = proj.max()
        if pd.notna(proj_max) and proj_max > 0:
            df["relative_risk"] = np.log1p(proj.fillna(0)) / np.log1p(proj_max)
        else:
            df["relative_risk"] = np.nan

    fields_f = [
        "relative_risk",
    ]
    fields_i: list[str] = []
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        name = row["name"]
        nom = _NAME_TO_NOM.get(name, name)
        rec: dict = {}
        for c in fields_f:
            if c in df.columns:
                rec[c] = _f(row.get(c))
        for c in fields_i:
            if c in df.columns:
                rec[c] = _i(row.get(c))
        out[nom] = rec
    return out


def _extract_matrix_column(csv_path: Path, target_col: str) -> dict[str, float | None]:
    """Extract a single named column from a zone-to-zone matrix CSV.
    Returns {nom: value}."""
    if not csv_path.exists():
        print(f"  WARNING: {csv_path} not found")
        return {}
    df = pd.read_csv(csv_path)
    nom_col = "nom" if "nom" in df.columns else df.columns[1]
    col = None
    target_dotted = target_col.replace(" ", ".")
    for c in df.columns:
        if c == target_col or c == target_dotted:
            col = c
            break
    if col is None:
        print(f"  WARNING: column {target_col!r} not found in {csv_path.name}")
        return {}
    return {str(row[nom_col]): _f(row[col]) for _, row in df.iterrows()}


def _extract_matrix_row_sums(csv_path: Path) -> dict[str, float | None]:
    """Sum each row of a zone-to-zone matrix (excluding the nom column).
    Returns {nom: row_sum}."""
    if not csv_path.exists():
        print(f"  WARNING: {csv_path} not found")
        return {}
    df = pd.read_csv(csv_path)
    if "nom" in df.columns:
        noms = df["nom"].astype(str)
        numeric = df.drop(columns=["nom"]).apply(pd.to_numeric, errors="coerce")
    else:
        noms = df.iloc[:, 1].astype(str)
        numeric = df.iloc[:, 2:].apply(pd.to_numeric, errors="coerce")
    sums = numeric.sum(axis=1)
    return {noms.iloc[i]: _f(sums.iloc[i]) for i in range(len(df))}


def _load_flowminder_short_trips_vector(
    csv_path: Path,
    flat_field: str,
) -> dict[str, float | None]:
    """Load a long-format flowminder_short_trips vector into {nom: value}."""
    if not csv_path.exists():
        print(f"  WARNING: {csv_path} not found")
        return {}
    df = pd.read_csv(csv_path)
    if "nom" not in df.columns:
        print(f"  WARNING: {csv_path.name} missing nom column")
        return {}
    value_cols = [c for c in df.columns if c != "nom"]
    if len(value_cols) != 1:
        print(f"  WARNING: {csv_path.name} expected one value column, got {value_cols}")
        return {}
    value_col = value_cols[0]
    out: dict[str, float | None] = {}
    for _, row in df.iterrows():
        raw_nom = str(row["nom"]).strip()
        nom = _NAME_TO_NOM.get(raw_nom, raw_nom)
        out[nom] = _f(row[value_col])
    return out


def _build_matrix_zone_aliases(zones: list[str]) -> dict[str, str]:
    """Map matrix CSV row/column labels to canonical GeoJSON ``nom`` values."""
    aliases: dict[str, str] = {}
    for nom in zones:
        aliases[nom] = nom
        aliases[nom.replace(" ", ".")] = nom
        aliases[nom.replace("-", ".")] = nom
    for meta_name, nom in _NAME_TO_NOM.items():
        aliases[meta_name] = nom
        aliases[meta_name.replace(" ", ".")] = nom
    return aliases


def _matrix_header_to_nom(header: str, aliases: dict[str, str]) -> str | None:
    if header in aliases:
        return aliases[header]
    dotted = header.replace(".", " ")
    if dotted in aliases:
        return aliases[dotted]
    return None


def _read_matrix_zone_order(csv_path: Path) -> list[str]:
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path)
    nom_col = "nom" if "nom" in df.columns else df.columns[1]
    return [str(v) for v in df[nom_col].tolist()]


def _load_square_matrix_csv(
    csv_path: Path,
    zones: list[str],
) -> list[list[float | None]]:
    """Load a zone×zone matrix aligned to ``zones`` (rows = origin, cols = dest)."""
    n = len(zones)
    empty = [[None] * n for _ in range(n)]
    if not csv_path.exists():
        print(f"  WARNING: {csv_path} not found")
        return empty
    df = pd.read_csv(csv_path)
    nom_col = "nom" if "nom" in df.columns else df.columns[1]
    skip_cols = {df.columns[0], nom_col}
    aliases = _build_matrix_zone_aliases(zones)
    zone_idx = {z: i for i, z in enumerate(zones)}

    col_to_zone_idx: dict[str, int] = {}
    for col in df.columns:
        if col in skip_cols:
            continue
        dest = _matrix_header_to_nom(str(col), aliases)
        if dest and dest in zone_idx:
            col_to_zone_idx[str(col)] = zone_idx[dest]

    out = [[None] * n for _ in range(n)]
    for _, row in df.iterrows():
        origin = str(row[nom_col])
        oi = zone_idx.get(origin)
        if oi is None:
            resolved = aliases.get(origin) or aliases.get(origin.replace(".", " "))
            oi = zone_idx.get(resolved) if resolved else None
        if oi is None:
            continue
        for col_name, di in col_to_zone_idx.items():
            out[oi][di] = _f(row[col_name])
    return out


def load_zone_matrices(zones: list[str]) -> dict:
    """Square zone matrices for client-side origin switching (rows = from, cols = to)."""
    travel = _load_square_matrix_csv(OSRM_TRAVEL_TIME_CSV, zones)
    road = _load_square_matrix_csv(OSRM_ROAD_DISTANCE_CSV, zones)
    return {
        "zones": zones,
        "default_origin": "Mongbwalu",
        "datasets": {
            "osrm__travel_time": {"values": travel, "scale": 60},
            "osrm__road_distance": {"values": road, "scale": 1},
        },
    }


def _flowminder_processed_dir() -> Path:
    """Resolve Flowminder processed matrices (env override, data/, or legacy path)."""
    for candidate in (
        FLOWMINDER_PROCESSED,
        EXTERNAL_DATA / "flowminder" / "processed",
        BUILD_DIR.parent / "Data" / "Flowminder" / "Processed",
    ):
        if candidate.is_dir():
            return candidate.resolve()
    return FLOWMINDER_PROCESSED.resolve()


def _matrix_count_value(v: float | None) -> int | float | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if float(v) <= 0:
        return None
    fv = float(v)
    return int(fv) if fv == int(fv) else round(fv, 2)


def _sparse_out_by_origin(
    matrix: list[list[float | None]],
    zones: list[str],
) -> dict[str, list[list]]:
    """Non-zero OD pairs per origin row: {origin: [[dest, count], ...]}."""
    out: dict[str, list[list]] = {}
    for oi, origin in enumerate(zones):
        pairs: list[list] = []
        for di, dest in enumerate(zones):
            if oi == di:
                continue
            v = _matrix_count_value(matrix[oi][di])
            if v is not None:
                pairs.append([dest, v])
        if pairs:
            out[origin] = pairs
    return out


def _sparse_in_by_dest(
    matrix: list[list[float | None]],
    zones: list[str],
) -> dict[str, list[list]]:
    """Non-zero OD pairs per destination column: {dest: [[origin, count], ...]}."""
    out: dict[str, list[list]] = {}
    for di, dest in enumerate(zones):
        pairs: list[list] = []
        for oi, origin in enumerate(zones):
            if oi == di:
                continue
            v = _matrix_count_value(matrix[oi][di])
            if v is not None:
                pairs.append([origin, v])
        if pairs:
            out[dest] = pairs
    return out


_FLOWMINDER_DATED_MATRIX_RE = re.compile(
    r"^flowminder__(inflow|outflow)_(\d{6})__static\.matrix\.csv$"
)
_MONTH_NAME_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_MONTH_NAME_FR = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def _yyyymm_prev(yyyymm: str) -> tuple[int, int]:
    year = int(yyyymm[:4])
    month = int(yyyymm[4:6])
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _format_month_en(year: int, month: int) -> str:
    return f"{_MONTH_NAME_EN[month - 1]} {year}"


def _format_month_fr(year: int, month: int) -> str:
    return f"{_MONTH_NAME_FR[month - 1]} {year}"


def _flowminder_period_labels(yyyymm: str) -> dict[str, str]:
    """Human labels for a Flowminder ``_YYYYMM`` snapshot (window end month)."""
    end_y, end_m = int(yyyymm[:4]), int(yyyymm[4:6])
    start_y, start_m = _yyyymm_prev(yyyymm)
    start_en = _format_month_en(start_y, start_m)
    end_en = _format_month_en(end_y, end_m)
    start_fr = _format_month_fr(start_y, start_m)
    end_fr = _format_month_fr(end_y, end_m)
    return {
        "yyyymm": yyyymm,
        "choropleth_en": (
            f"Relocated persons between {start_en} and {end_en} (Flowminder)"
        ),
        "choropleth_fr": (
            f"Personnes relocalisées entre {start_fr} et {end_fr} (Flowminder)"
        ),
        "info_en": f"relocated persons {start_en}–{end_en} (Flowminder)",
        "info_fr": f"personnes relocalisées {start_fr}–{end_fr} (Flowminder)",
        "arcs_en": f"Flowminder in- and out-flow ({end_en})",
        "arcs_fr": f"Flux Flowminder entrants et sortants ({end_fr})",
        "end_month_en": end_en,
        "end_month_fr": end_fr,
    }


def discover_latest_flowminder_yyyymm(proc: Path | None = None) -> str | None:
    """Return the latest ``YYYYMM`` that has both inflow and outflow matrices."""
    directory = proc or _flowminder_processed_dir()
    if not directory.is_dir():
        return None
    by_tag: dict[str, set[str]] = {}
    for path in directory.iterdir():
        m = _FLOWMINDER_DATED_MATRIX_RE.match(path.name)
        if not m:
            continue
        direction, yyyymm = m.group(1), m.group(2)
        by_tag.setdefault(yyyymm, set()).add(direction)
    complete = [tag for tag, dirs in by_tag.items() if {"inflow", "outflow"} <= dirs]
    return max(complete) if complete else None


def flowminder_dated_matrix_paths(yyyymm: str, proc: Path | None = None) -> tuple[Path, Path]:
    directory = proc or _flowminder_processed_dir()
    return (
        directory / f"flowminder__inflow_{yyyymm}__static.matrix.csv",
        directory / f"flowminder__outflow_{yyyymm}__static.matrix.csv",
    )


def load_flowminder_sparse_from_paths(
    in_path: Path,
    out_path: Path,
    *,
    label: str = "flowminder",
) -> dict:
    """Sparse in/out catalogs for arc rendering from a pair of OD matrices."""
    zones = _read_matrix_zone_order(in_path) or _read_matrix_zone_order(out_path)
    if not zones:
        print(f"  WARNING: Flowminder matrices not found ({label})")
        return {
            "zones": [],
            "default_hub": "Mongbwalu",
            "out_by_origin": {},
            "in_by_dest": {},
            "yyyymm": None,
        }
    in_matrix = _load_square_matrix_csv(in_path, zones)
    out_matrix = _load_square_matrix_csv(out_path, zones)
    out_by_origin = _sparse_out_by_origin(out_matrix, zones)
    in_by_dest = _sparse_in_by_dest(in_matrix, zones)
    n_out = sum(len(v) for v in out_by_origin.values())
    n_in = sum(len(v) for v in in_by_dest.values())
    print(
        f"  flowminder sparse ({label}): {len(zones)} zones, "
        f"{n_out} out-pairs, {n_in} in-pairs"
    )
    return {
        "zones": zones,
        "default_hub": "Mongbwalu",
        "out_by_origin": out_by_origin,
        "in_by_dest": in_by_dest,
    }


def load_flowminder_mar_sparse() -> dict:
    """Sparse March 2026 Flowminder in/out matrices (undated ``__static`` pair)."""
    proc = _flowminder_processed_dir()
    return load_flowminder_sparse_from_paths(
        proc / "flowminder__inflow__static.matrix.csv",
        proc / "flowminder__outflow__static.matrix.csv",
        label="mar2026/undated",
    )


def load_flowminder_latest_sparse() -> tuple[dict, str | None]:
    """Load the newest ``_YYYYMM`` Flowminder inflow/outflow pair for flow arcs."""
    proc = _flowminder_processed_dir()
    yyyymm = discover_latest_flowminder_yyyymm(proc)
    if not yyyymm:
        print(f"  WARNING: no dated Flowminder matrices under {proc}")
        return (
            {
                "zones": [],
                "default_hub": "Mongbwalu",
                "out_by_origin": {},
                "in_by_dest": {},
            },
            None,
        )
    in_path, out_path = flowminder_dated_matrix_paths(yyyymm, proc)
    catalog = load_flowminder_sparse_from_paths(
        in_path, out_path, label=f"latest/{yyyymm}"
    )
    catalog["yyyymm"] = yyyymm
    return catalog, yyyymm


def load_metadata(
    centroids: dict[str, tuple[float, float]],
    field_paths: dict[str, list[str]],
) -> tuple[dict[str, dict], dict]:
    """Assemble per-zone metadata from build GeoJSON properties (auto-discovered),
    OSRM matrices, IDP/Flowminder matrices, and local CSV fallback fields."""
    build_props = _load_build_geojson_properties()
    local_fields = _load_local_csv_fields()

    # OSRM matrices
    travel_times = _extract_matrix_column(OSRM_TRAVEL_TIME_CSV, "Mongbwalu")
    road_dists = _extract_matrix_column(OSRM_ROAD_DISTANCE_CSV, "Mongbwalu")

    # IDP and Flowminder matrices (row sums = incoming totals)
    idp_incoming = _extract_matrix_row_sums(
        EXTERNAL_DATA / "IDP" / "processed" / "idp__individuals__static.matrix.csv")
    flowminder_proc = _flowminder_processed_dir()
    flowminder_incoming_mar = _extract_matrix_row_sums(
        flowminder_proc / "flowminder__inflow__static.matrix.csv"
    )
    flowminder_incoming_202604 = _extract_matrix_row_sums(
        flowminder_proc / "flowminder__inflow_202604__static.matrix.csv"
    )

    zone_data: dict[str, dict] = {}
    for nom, props in build_props.items():
        rec: dict = {"name": nom}

        # Centroids
        if nom in centroids:
            lon, lat = centroids[nom]
            rec["centroid_lon"] = lon
            rec["centroid_lat"] = lat

        # Auto-discovered GeoJSON fields
        rec.update(extract_geojson_fields(props, field_paths))

        # Epi: prefer INSP sitrep cumulative (more recent) over WHO epi snapshot.
        # Use explicit None checks — `or` would treat 0 as falsy.
        insp = props.get("insp_sitrep", {})
        epi = props.get("epi", {}).get("cases", {})
        for dst, insp_key, epi_key in (
            ("confirmed_cases",  "cumulative_confirmed_cases",  "confirmed_cases"),
            ("confirmed_deaths", "cumulative_confirmed_deaths", "confirmed_deaths"),
            ("suspected_cases",  "cumulative_suspected_cases",  "suspected_cases"),
            ("suspected_deaths", "cumulative_suspected_deaths", "suspected_deaths"),
        ):
            v = _i(insp.get(insp_key, {}).get(insp_key))
            if v is None:
                v = _i(epi.get(epi_key))
            rec[dst] = v
        rec["total_cases"] = (rec.get("confirmed_cases") or 0) + (rec.get("suspected_cases") or 0)

        # OSRM (travel time is in minutes in the matrix → convert to hours)
        tt = travel_times.get(nom)
        rec["travel_time_to_mongbwalu_h"] = round(tt / 60, 2) if tt else None
        rec["geodesic_to_mongbwalu_km"] = road_dists.get(nom)

        # IDP / Flowminder
        rec["displaced_in_individuals_12mo"] = _i(idp_incoming.get(nom))
        rec["flowminder_in_mar2026"] = _i(flowminder_incoming_mar.get(nom))
        rec["flowminder_in_202604"] = _i(flowminder_incoming_202604.get(nom))

        # Genomic surveillance (embedded per-zone in the build GeoJSON).
        seq_count = _i(
            props.get("genomic_surveillance", {})
            .get("sequence_count", {})
            .get("sequence_count")
        )
        if seq_count and seq_count > 0:
            rec["genomic_sequence_count"] = seq_count

        zone_data[nom] = rec

    # HDX cohort subscriber-day vectors (not yet in build GeoJSON).
    _SHORT_TRIPS_VECTOR_FILES = (
        (
            "flowminder_short_trips__ituri_subscriber_days_followup_20260608__ituri_subscriber_days_followup_20260608",
            "flowminder_short_trips__ituri_subscriber_days_followup_20260608__static.csv",
        ),
        (
            "flowminder_short_trips__ituri_subscriber_days_prior_20260503__ituri_subscriber_days_prior_20260503",
            "flowminder_short_trips__ituri_subscriber_days_prior_20260503__static.csv",
        ),
        (
            "flowminder_short_trips__nk_subscriber_days_followup_20260608__nk_subscriber_days_followup_20260608",
            "flowminder_short_trips__nk_subscriber_days_followup_20260608__static.csv",
        ),
        (
            "flowminder_short_trips__nk_subscriber_days_prior_20260503__nk_subscriber_days_prior_20260503",
            "flowminder_short_trips__nk_subscriber_days_prior_20260503__static.csv",
        ),
    )
    for flat_field, filename in _SHORT_TRIPS_VECTOR_FILES:
        values = _load_flowminder_short_trips_vector(
            FLOWMINDER_SHORT_TRIPS_PROCESSED / filename,
            flat_field,
        )
        for nom, value in values.items():
            zone_data.setdefault(nom, {"name": nom})
            zone_data[nom][flat_field] = value

    # Local-CSV-only fields (applied after zone_data loop for zones only in build_props)
    for nom, rec in zone_data.items():
        local = local_fields.get(nom, {})
        rec["relative_risk"] = local.get("relative_risk")

    # Case totals
    totals: dict = {}
    for col in ("confirmed_cases", "confirmed_deaths",
                "suspected_cases", "suspected_deaths"):
        totals[col] = sum(int(r.get(col) or 0) for r in zone_data.values())
    totals["affected_zones"] = sum(
        1 for r in zone_data.values()
        if (int(r.get("confirmed_cases") or 0) + int(r.get("suspected_cases") or 0)) > 0)

    return zone_data, totals


def compute_global_sitrep_totals() -> dict | None:
    """Tracker outbreak totals: sit-rep CSV if present, else GeoJSON national_*.

    Primary source is the newest dated CSV in Data/Epidemiological Data/ (supports
    multiple countries). When that is unavailable, uses INSP national cumulative
    fields from drc_health_zones.geojson (DRC only; not summed from zones).

    When a sit-rep's Total row underreports relative to per-country rows, we credit
    the excess to the largest country (CSV path only).
    """
    # Template merged at the end of the CSV path; unused on GeoJSON fallback.
    out = {
        "global_confirmed_cases": 0, "global_suspected_cases": 0,
        "global_confirmed_deaths": 0, "global_suspected_deaths": 0,
        "global_recovered_cases": 0,
        "global_total_cases": 0,
        "affected_countries": [], "affected_country_count": 0,
        "per_country": [],
    }
    # No local sit-rep folder → skip CSV and use build GeoJSON national totals.
    if not SIT_REPS_DIR.exists():
        return _national_totals_from_build_geojson()
    # Collect paths whose filenames parse as YYYY-MM-DD.csv.
    dated = []
    for p in SIT_REPS_DIR.iterdir():
        if not p.is_file() or p.suffix.lower() != ".csv":
            continue
        try:
            dated.append((datetime.strptime(p.stem, "%Y-%m-%d").date(), p))
        except ValueError:
            continue
    # Folder exists but has no dated CSVs → national totals from GeoJSON.
    if not dated:
        return _national_totals_from_build_geojson()
    _, path = max(dated)
    sr_all = pd.read_csv(path)
    sr_all.columns = [c.strip().lower() for c in sr_all.columns]
    total_mask = sr_all["country"].astype(str).str.strip().str.lower() == "total"
    total_row = sr_all[total_mask].iloc[0] if total_mask.any() else None
    sr = sr_all[~total_mask].copy()
    sr["country"] = sr["country"].astype(str).str.strip()
    metric_cols = ["confirmed cases", "suspected cases", "confirmed deaths", "suspected deaths"]
    for c in metric_cols:
        sr[c] = pd.to_numeric(sr[c], errors="coerce").fillna(0).astype(int)
    grouped = sr.groupby("country", as_index=False)[metric_cols].sum()
    grouped["total"] = grouped["confirmed cases"]
    grouped = grouped[grouped["total"] > 0].sort_values("total", ascending=False)

    def total_metric(col):
        if total_row is None:
            return None
        v = pd.to_numeric(total_row[col], errors="coerce")
        return None if pd.isna(v) else int(v)

    def credit_excess(col):
        per_zone_sum = int(grouped[col].sum())
        total_val = total_metric(col)
        if total_val is None or grouped.empty:
            return per_zone_sum if total_val is None else total_val
        if total_val <= per_zone_sum:
            return per_zone_sum
        primary = grouped["total"].idxmax()
        grouped.loc[primary, col] += (total_val - per_zone_sum)
        return total_val

    final_conf   = credit_excess("confirmed cases")
    final_susp   = credit_excess("suspected cases")
    final_conf_d = credit_excess("confirmed deaths")
    final_susp_d = credit_excess("suspected deaths")

    per_country = []
    for _, r in grouped.iterrows():
        per_country.append({
            "country": str(r["country"]),
            "confirmed_cases": int(r["confirmed cases"]),
            "suspected_cases": int(r["suspected cases"]),
            "confirmed_deaths": int(r["confirmed deaths"]),
            "suspected_deaths": int(r["suspected deaths"]),
            "total": int(r["confirmed cases"]) + int(r["suspected cases"]),
        })
    out.update({
        "global_confirmed_cases":  final_conf,
        "global_suspected_cases":  final_susp,
        "global_confirmed_deaths": final_conf_d,
        "global_suspected_deaths": final_susp_d,
        "global_total_cases":      final_conf,
        "affected_countries":      [c["country"] for c in per_country],
        "affected_country_count":  len(per_country),
        "per_country":             per_country,
    })
    geo_nat = _national_totals_from_build_geojson()
    if geo_nat is not None:
        out["global_recovered_cases"] = geo_nat.get("global_recovered_cases", 0)
    return out


def write_effective_confirmed_cases(zone_data: dict[str, dict],
                                    harmonised: dict[str, int]) -> None:
    """Write ``effective_confirmed_cases = max(harmonised, sitrep)`` into EVERY
    zone rec, defaulting to 0. Must run before build_active_case_markers so the
    markers (and later the engine) read it. A zone left undefined re-triggers the
    white-zone bug in the engine, so the default-0 write for all zones is required.
    """
    for nom, rec in zone_data.items():
        h = harmonised.get(nom, 0) or 0
        s = rec.get("confirmed_cases") or 0
        rec["effective_confirmed_cases"] = max(int(h), int(s))


def build_active_case_markers(zone_data: dict[str, dict],
                              centroids: dict[str, tuple[float, float]]
                              ) -> list[dict]:
    """One marker per zone with ≥1 confirmed case (from GeoJSON-derived fields).

    Suspected-only zones are excluded — markers track confirmed burden only.
    """
    out: list[dict] = []
    for nom, rec in zone_data.items():
        if nom not in centroids:
            continue
        conf = int(rec.get("effective_confirmed_cases") or 0)
        if conf <= 0:
            continue
        susp = int(rec.get("suspected_cases") or 0)
        lon, lat = centroids[nom]
        out.append({
            "nom": nom,
            "name": _NOM_TO_NAME.get(nom, nom),
            "lat": lat,
            "lon": lon,
            "confirmed": conf,
            "suspected": susp,
            "confirmed_deaths": int(rec.get("confirmed_deaths") or 0),
            "suspected_deaths": int(rec.get("suspected_deaths") or 0),
            "total": conf + susp,
        })
    return out


def build_genome_sequence_markers(
    zone_data: dict[str, dict],
    centroids: dict[str, tuple[float, float]],
) -> list[dict]:
    """One marker per zone with at least one genome sequence.

    Reads ``genomic_sequence_count`` from ``zone_data``, which load_metadata()
    already populates from the build GeoJSON's embedded genomic_surveillance
    properties (no separate CSV read needed)."""
    out: list[dict] = []
    for nom, rec in zone_data.items():
        if nom not in centroids:
            continue
        count = rec.get("genomic_sequence_count")
        if not count or count <= 0:
            continue
        lon, lat = centroids[nom]
        out.append({
            "nom": nom,
            "name": _NOM_TO_NAME.get(nom, nom),
            "lat": lat,
            "lon": lon,
            "count": count,
        })
    return out


# ---------------------------------------------------------------------------
# methods + terms text
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_BULLET_PREFIXES = ("•", "•", "−", "—", "-")


def _strip_bullet(s: str) -> str:
    for prefix in _BULLET_PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):].lstrip()
    return s.lstrip()


# The modal renders "Contributors, Data, and Methods" in its own header, so a
# source document that opens with that title shows it twice. Same idea as
# _TERMS_HEADER_SKIP_RE below, which drops the equivalent line from the terms
# text. Only an exact title match is dropped: the English document opens with
# an h2 "Contributors", which is its first section (peer to "Data" and
# "Methods") and has to survive.
_METHODS_TITLE_RE = re.compile(
    r"^(?:contributors,?\s+data,?\s+(?:and|&)\s+methods"
    r"|contributeurs,?\s+données,?\s+et\s+méthodes)"
    r"[\s.:;,]*$",
    re.IGNORECASE,
)
_LEADING_HEADING_RE = re.compile(
    r"\A\s*<(h[1-4])\b([^>]*)>(.*?)</\1>\s*", re.DOTALL | re.IGNORECASE,
)
_ANY_HEADING_RE = re.compile(r"<(h[1-6])\b[^>]*>", re.IGNORECASE)


def _drop_repeated_title(html: str) -> str:
    """Drop a leading heading that only repeats the dialog's own title."""
    m = _LEADING_HEADING_RE.match(html)
    if not m:
        return html
    text = re.sub(r"<[^>]+>", "", m.group(3)).replace("&amp;", "&")
    if _METHODS_TITLE_RE.match(" ".join(text.split())):
        return html[m.end():]
    return html


def _normalise_leading_heading_level(html: str) -> str:
    """Demote a lone leading h2 to h3 when the other sections are h3.

    The English docx marks "Contributors" as Heading 1 but "Data" and
    "Methods" as Heading 2, so the three peer sections rendered h2/h3/h3 and
    the first displayed a size larger than its own peers -- reading as a
    repeat of the dialog title rather than as a section.

    Deliberately narrow: only a leading h2 that is the document's ONLY h2, in
    a document that does use h3 sections. A document using h2 consistently is
    using the level on purpose and is left alone.
    """
    levels = [m.group(1).lower() for m in _ANY_HEADING_RE.finditer(html)]
    if len(levels) < 2 or levels[0] != "h2":
        return html
    if levels.count("h2") != 1 or "h3" not in levels:
        return html
    m = _LEADING_HEADING_RE.match(html)
    if not m or m.group(1).lower() != "h2":
        return html
    return f"<h3{m.group(2)}>{m.group(3)}</h3>\n" + html[m.end():]


def load_methods_html(path: Path | None = None) -> str:
    """Render Contributors_Methods_Data_website.docx as an HTML snippet.

    Headings 1/2/3 -> h2/h3/h4. Bold-only paragraphs are promoted to h2 as a
    fallback for documents that mark sections with bold runs only. Bullet
    glyphs (•, −, —) at the start of a paragraph are folded into a <ul>.
    Hyperlinks are preserved with target=_blank. Email addresses become
    mailto: links.
    """
    docx_path = path or METHODS_DOCX
    if not docx_path.exists():
        print(f"  WARNING: {docx_path} not found; the Contributors dialog will be empty")
        return ""
    # A missing dependency is a broken build environment, not content. This
    # used to return an error message as HTML, which shipped into the payload
    # and rendered inside the public Contributors dialog -- the build reported
    # success while the deployed site showed "python-docx not installed" to
    # anyone who opened it. Fail here instead. Only ImportError is caught: any
    # other failure out of these modules is a real bug and should surface with
    # its own traceback rather than being reported as a missing install.
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise RuntimeError(
            f"python-docx is required to render {docx_path.name} but is not "
            "installed in the environment running this build. It is declared "
            "in requirements.txt -- run `pip install -r requirements.txt`. "
            "Refusing to continue: the Contributors dialog would otherwise "
            "ship empty or carry an internal error message."
        ) from exc
    d = Document(docx_path)
    rid_to_url: dict[str, str] = {}
    for rid, rel in d.part.rels.items():
        if "hyperlink" in rel.reltype.lower():
            rid_to_url[rid] = getattr(rel, "target_ref", None) or rel._target

    def _linkify(html: str) -> str:
        return _EMAIL_RE.sub(
            lambda m: f'<a href="mailto:{m.group(1)}">{m.group(1)}</a>',
            html,
        )

    def _runs_to_html(node) -> str:
        out: list[str] = []
        for child in node.iterchildren():
            tag = child.tag
            if tag == qn("w:r"):
                txt = "".join(t.text or "" for t in child.iter(qn("w:t")))
                if txt:
                    out.append(_linkify(_html_escape(txt)))
            elif tag == qn("w:hyperlink"):
                rid = child.get(qn("r:id")) or child.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                txt = "".join(t.text or "" for t in child.iter(qn("w:t")))
                url = rid_to_url.get(rid, "")
                if txt and url:
                    out.append(
                        f'<a href="{_html_escape(url)}" target="_blank" rel="noopener">'
                        f"{_html_escape(txt)}</a>"
                    )
                elif txt:
                    out.append(_linkify(_html_escape(txt)))
        return "".join(out)

    def _table_html(tbl_el) -> str:
        rows_html: list[str] = []
        for ri, tr in enumerate(tbl_el.iterfind(qn("w:tr"))):
            cells_html: list[str] = []
            for tc in tr.iterfind(qn("w:tc")):
                pieces = []
                for p in tc.iterfind(qn("w:p")):
                    s = _runs_to_html(p)
                    if s:
                        pieces.append(s)
                cells_html.append("<br/>".join(pieces))
            tag = "th" if ri == 0 else "td"
            rows_html.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells_html) + "</tr>")
        return "<table class='methods-table'>" + "".join(rows_html) + "</table>"

    def _is_bold_heading(p) -> bool:
        runs = [r for r in p.runs if (r.text or "").strip()]
        return bool(runs) and all(bool(r.bold) for r in runs)

    parts: list[str] = []
    in_ul = False
    for child in d.element.body.iterchildren():
        tag = child.tag
        if tag == qn("w:tbl"):
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            parts.append(_table_html(child))
            continue
        if tag != qn("w:p"):
            continue
        para = Paragraph(child, d.part)
        txt = (para.text or "").strip()
        style = para.style.name if para.style else "Normal"
        if not txt:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            continue
        html_body = _runs_to_html(child)
        is_bullet = any(txt.startswith(p) for p in _BULLET_PREFIXES[:-1])
        if is_bullet:
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{_strip_bullet(html_body)}</li>")
            continue
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        if style.startswith("Title") or style.startswith("Heading 1"):
            parts.append(f"<h2>{html_body}</h2>")
        elif style.startswith("Heading 2"):
            parts.append(f"<h3>{html_body}</h3>")
        elif style.startswith("Heading 3"):
            parts.append(f"<h4>{html_body}</h4>")
        elif _is_bold_heading(para):
            parts.append(f"<h2>{html_body}</h2>")
        else:
            parts.append(f"<p>{html_body}</p>")
    if in_ul:
        parts.append("</ul>")
    return _normalise_leading_heading_level(_drop_repeated_title("\n".join(parts)))


_TERMS_SECTION_RE = re.compile(r"^(\d+)\.\s+(.+)$")
_TERMS_LASTUPDATED_RE = re.compile(r"^Last updated:\s*(.+)$", re.IGNORECASE)
_TERMS_LASTUPDATED_FR_RE = re.compile(r"^Dernière mise à jour\s*:\s*(.+)$", re.IGNORECASE)
_TERMS_HEADER_SKIP_RE = re.compile(
    r"^(terms of use|conditions d'utilisation)$", re.IGNORECASE,
)


def load_methods_html_lang(lang: str = "en") -> str:
    """Load methods content for ``lang`` (docx preferred; French HTML fallback)."""
    if lang == "fr":
        if METHODS_DOCX_FR.exists():
            return load_methods_html(METHODS_DOCX_FR)
        if METHODS_HTML_FR.exists():
            print(f"  methods HTML (fr): {METHODS_HTML_FR.name}")
            # This file (unlike the docx) does open with the dialog's title.
            return _normalise_leading_heading_level(
                _drop_repeated_title(METHODS_HTML_FR.read_text(encoding="utf-8").strip())
            )
        print("  WARNING: no French methods document; falling back to English")
    return load_methods_html(METHODS_DOCX)


def load_terms_html(path: Path | None = None) -> tuple[str, str]:
    terms_path = path or TERMS_TXT
    if not terms_path.exists():
        return "", ""
    last_updated = ""
    parts: list[str] = []
    for line in terms_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or _TERMS_HEADER_SKIP_RE.match(line):
            continue
        m = _TERMS_LASTUPDATED_RE.match(line) or _TERMS_LASTUPDATED_FR_RE.match(line)
        if m:
            last_updated = m.group(1).strip()
            continue
        m = _TERMS_SECTION_RE.match(line)
        if m:
            parts.append(f"<h3>{_html_escape(m.group(1))}. {_html_escape(m.group(2))}</h3>")
            continue
        text = _html_escape(line)
        text = _EMAIL_RE.sub(
            lambda mm: f"<a href='mailto:{mm.group(1)}'>{mm.group(1)}</a>",
            text,
        )
        parts.append(f"<p>{text}</p>")
    return "\n".join(parts), last_updated


def load_terms_html_lang(lang: str = "en") -> tuple[str, str]:
    if lang == "fr" and TERMS_TXT_FR.exists():
        return load_terms_html(TERMS_TXT_FR)
    if lang == "fr":
        print("  WARNING: no French terms document; falling back to English")
    return load_terms_html(TERMS_TXT)


# ---------------------------------------------------------------------------
# partner logos
# ---------------------------------------------------------------------------

_LOGO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def load_logo_data_uri(filename: str) -> str:
    path = BRANDING_DIR / filename
    if not path.exists():
        return ""
    mime = _LOGO_MIME.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def load_partners() -> list[dict]:
    if not BRANDING_DIR.exists():
        return []
    url_map: dict[str, str] = {}
    if BRANDING_URLS.exists():
        for line in BRANDING_URLS.read_text(encoding="utf-8").splitlines():
            if "," not in line:
                continue
            fname, url = line.split(",", 1)
            url_map[fname.strip()] = url.strip()
    out: list[dict] = []
    for fname in PARTNER_ORDER:
        uri = load_logo_data_uri(fname)
        if uri:
            out.append({
                "alt": Path(fname).stem.upper(),
                "href": url_map.get(fname, ""),
                "data_uri": uri,
                "group": PARTNER_GROUPS.get(fname, 0),
                "scale": PARTNER_SCALE.get(fname, 1.0),
            })
    return out


# ---------------------------------------------------------------------------
# layer auto-discovery from GeoJSON properties
# ---------------------------------------------------------------------------

# Keys in GeoJSON properties that are metadata, not data layers.
_SKIP_PROPERTY_KEYS = {"nom", "zscode", "province"}

# Leaf values that are non-numeric strings to treat as missing.
_NON_NUMERIC_STRINGS = {"ND", "NA", ""}

# Leaf keys that are always excluded (non-numeric identifiers).
_EXCLUDE_LEAVES = {"poe_names"}

LAYER_CONFIG_YAML = SCRIPT_DIR.parent / "layer_config.yaml"


def _load_layer_config() -> dict:
    """Load layer_config.yaml. Returns empty-ish defaults if missing."""
    if not LAYER_CONFIG_YAML.exists():
        print(f"  WARNING: {LAYER_CONFIG_YAML} not found, using defaults")
        return {}
    try:
        import yaml
    except ImportError:
        print("  WARNING: PyYAML not installed, layer_config.yaml ignored")
        return {}
    with open(LAYER_CONFIG_YAML) as f:
        return yaml.safe_load(f) or {}


def _prettify_label(s: str) -> str:
    """Turn a snake_case key into a human-readable label."""
    return s.replace("_", " ").strip().capitalize()


def discover_geojson_layers(
    geojson_path: Path,
) -> tuple[list[dict], dict[str, list[str]]]:
    """Scan a GeoJSON file and return (layer_defs, field_paths).

    layer_defs: list of {"group", "id", "label", "field", "palette", "scale"}
    field_paths: {flat_field_name: [group_key, metric_key, leaf_key]} mapping
                 so load_metadata can extract values generically.

    Reads Data/layer_config.yaml for exclusions, group display names,
    palettes, scales, and ordering.
    """
    cfg = _load_layer_config()
    excludes = set(cfg.get("exclude", []) or [])
    group_cfg = cfg.get("groups", {}) or {}
    group_order = cfg.get("group_order", []) or []

    with open(geojson_path) as f:
        raw = json.load(f)

    # Pass 1: discover all group.metric.leaf paths with at least one numeric value
    numeric_paths: dict[str, tuple[str, str, str]] = {}
    for feat in raw["features"]:
        props = feat["properties"]
        for gkey, gval in props.items():
            if gkey in _SKIP_PROPERTY_KEYS or not isinstance(gval, dict):
                continue
            if gkey in excludes:
                continue
            for mkey, mval in gval.items():
                if not isinstance(mval, dict):
                    continue
                metric_key = f"{gkey}__{mkey}"
                if metric_key in excludes:
                    continue
                for lkey, lval in mval.items():
                    if lkey == "_date" or lkey in _EXCLUDE_LEAVES:
                        continue
                    flat = f"{gkey}__{mkey}__{lkey}"
                    if flat in excludes:
                        continue
                    if flat in numeric_paths:
                        continue
                    if isinstance(lval, (int, float)):
                        numeric_paths[flat] = (gkey, mkey, lkey)
                    elif isinstance(lval, str) and lval not in _NON_NUMERIC_STRINGS:
                        try:
                            float(lval)
                            numeric_paths[flat] = (gkey, mkey, lkey)
                        except ValueError:
                            pass

    # Pass 2: organise into groups, build layer defs
    groups: dict[str, list[tuple[str, str, str, str]]] = {}
    for flat, (gkey, mkey, lkey) in numeric_paths.items():
        label = _prettify_label(lkey)
        groups.setdefault(gkey, []).append((flat, mkey, lkey, label))
    for g in groups:
        groups[g].sort(key=lambda t: t[3])

    # Order groups
    ordered_groups: list[str] = []
    for g in group_order:
        if g in groups:
            ordered_groups.append(g)
    for g in sorted(groups):
        if g not in ordered_groups:
            ordered_groups.append(g)

    layer_defs: list[dict] = []
    field_paths: dict[str, list[str]] = {}
    for gkey in ordered_groups:
        gcfg = group_cfg.get(gkey, {}) or {}
        group_name = gcfg.get("label", gkey.replace("_", " ").title())
        palette = gcfg.get("palette", "viridis")
        scale = gcfg.get("scale", "log")
        legend_round = gcfg.get("legend_round", "int")
        epicenter_highlight = bool(gcfg.get("epicenter_highlight", False))
        for flat, mkey, lkey, label in groups[gkey]:
            layer_id = f"{gkey}::{mkey}"
            if lkey != mkey:
                layer_id = f"{gkey}::{mkey}::{lkey}"
            layer_defs.append({
                "group": group_name,
                "id": layer_id,
                "label": label,
                "field": flat,
                "palette": palette,
                "scale": scale,
                "source": "",
                "legend_round": legend_round,
                "epicenter_highlight": epicenter_highlight,
            })
            field_paths[flat] = [gkey, mkey, lkey]

    return layer_defs, field_paths


def extract_geojson_fields(
    props: dict,
    field_paths: dict[str, list[str]],
) -> dict[str, float | int | None]:
    """Given a single feature's properties and the field_paths mapping,
    extract all discovered numeric values into a flat dict."""
    rec: dict[str, float | int | None] = {}
    for flat, (gkey, mkey, lkey) in field_paths.items():
        raw_val = props.get(gkey, {}).get(mkey, {}).get(lkey)
        if isinstance(raw_val, str):
            if raw_val in _NON_NUMERIC_STRINGS:
                rec[flat] = None
                continue
            try:
                raw_val = float(raw_val)
            except ValueError:
                rec[flat] = None
                continue
        rec[flat] = _f(raw_val)
    return rec


# ---------------------------------------------------------------------------
# extra (non-GeoJSON) layers: matrices, local CSV, computed fields
# ---------------------------------------------------------------------------

EXTRA_LAYER_DEFS_TRAVEL = [
    ("Travel distance (OSRM)", "d::travel", "Travel time from {origin} (hours)",   "", "plasma_r", "linear", 1, False, "osrm__travel_time", 60, True),
    ("Travel distance (OSRM)", "d::geo",    "Road distance from {origin} (km)",    "", "plasma_r", "linear", "int", False, "osrm__road_distance", 1, True),
]


def _make_layer_def(
    group: str,
    layer_id: str,
    label: str,
    field: str,
    palette: str,
    scale: str,
    legend_round,
    epicenter_highlight: bool = False,
    source: str = "",
    matrix_id: str = "",
    matrix_scale: float | int | None = None,
    origin_highlight: bool = False,
    viz: str = "",
    flow_catalog: str = "",
    epicenter_noms: list[str] | None = None,
    legend_caption: str = "",
) -> dict:
    layer = {
        "group": group,
        "id": layer_id,
        "label": label,
        "field": field,
        "palette": palette,
        "scale": scale,
        "source": source,
        "legend_round": legend_round,
        "epicenter_highlight": epicenter_highlight,
    }
    if epicenter_noms:
        layer["epicenter_noms"] = list(epicenter_noms)
    if legend_caption:
        layer["legend_caption"] = legend_caption
    if matrix_id:
        layer["matrix_id"] = matrix_id
        layer["matrix_scale"] = 1 if matrix_scale is None else matrix_scale
        layer["origin_highlight"] = origin_highlight
    elif viz:
        layer["viz"] = viz
        if flow_catalog:
            layer["flow_catalog"] = flow_catalog
        if origin_highlight:
            layer["origin_highlight"] = True
    return layer


# Flowminder short-trip layers (Annex A proportions + HDX cohort subscriber-days).
_FLOWMINDER_SHORT_TRIPS_GROUP = "Movements from epicentres (Flowminder)"
_FLOWMINDER_SHORT_TRIPS_LAYER_DEFS = [
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::20260430",
        "Percentage of persons from Ituri epicentre* observed in new health zone by April 30",
        "flowminder_short_trips__outflow_20260430__outflow_20260430",
        "reds", "log", 1,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_ITURI_SINGLE),
        legend_caption="Persons detected in new health zones",
    ),
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::20260507",
        "Percentage of persons from Ituri epicentre* observed in new health zone by May 7",
        "flowminder_short_trips__outflow_20260507__outflow_20260507",
        "reds", "log", 1,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_ITURI_SINGLE),
        legend_caption="Persons detected in new health zones",
    ),
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::20260514",
        "Percentage of persons from Ituri epicentre* observed in new health zone by May 14",
        "flowminder_short_trips__outflow_20260514__outflow_20260514",
        "reds", "log", 1,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_ITURI_SINGLE),
        legend_caption="Persons detected in new health zones",
    ),
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::20260521",
        "Percentage of persons from Ituri epicentre* observed in new health zone by May 21",
        "flowminder_short_trips__outflow_20260521__outflow_20260521",
        "reds", "log", 1,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_ITURI_SINGLE),
        legend_caption="Persons detected in new health zones",
    ),
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::20260524",
        "Percentage of persons from Ituri epicentre* observed in new health zone by May 24",
        "flowminder_short_trips__outflow_20260524__outflow_20260524",
        "reds", "log", 1,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_ITURI_SINGLE),
        legend_caption="Persons detected in new health zones",
    ),
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::ituri_followup",
        "Avg subscriber-days of Ituri epicentre** persons spent in new health zone by June 8",
        "flowminder_short_trips__ituri_subscriber_days_followup_20260608__ituri_subscriber_days_followup_20260608",
        "reds", "log", 2,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_ITURI_COHORT),
        legend_caption="Average subscriber-days",
    ),
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::ituri_prior",
        "Avg subscriber-days of Ituri epicentre** persons spent in new health zone by May 3",
        "flowminder_short_trips__ituri_subscriber_days_prior_20260503__ituri_subscriber_days_prior_20260503",
        "reds", "log", 2,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_ITURI_COHORT),
        legend_caption="Average subscriber-days",
    ),
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::nk_followup",
        "Avg subscriber-days of Nord-Kivu epicentre** persons spent in new health zone by June 8",
        "flowminder_short_trips__nk_subscriber_days_followup_20260608__nk_subscriber_days_followup_20260608",
        "reds", "log", 2,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_NK_COHORT),
        legend_caption="Average subscriber-days",
    ),
    _make_layer_def(
        _FLOWMINDER_SHORT_TRIPS_GROUP,
        "fmst::nk_prior",
        "Avg subscriber-days of Nord-Kivu epicentre** persons spent in new health zone by May 3",
        "flowminder_short_trips__nk_subscriber_days_prior_20260503__nk_subscriber_days_prior_20260503",
        "reds", "log", 2,
        epicenter_highlight=True,
        epicenter_noms=list(EPICENTER_NK_COHORT),
        legend_caption="Average subscriber-days",
    ),
]


FLOW_ARC_LAYER_DEF = _make_layer_def(
    "Incoming Mobility",
    "flow::od",
    "Flowminder in- and out-flow",
    "",
    "reds",
    "linear",
    "int",
    origin_highlight=True,
    viz="flow_arcs",
    flow_catalog="flowminder_latest",
)

EXTRA_LAYER_DEFS = [
    ("Observed (epi update)", "obs::total",     "Total cases (confirmed + suspected)", "total_cases",      "reds", "log", "int", False),
    ("Observed (epi update)", "obs::confirmed", "Confirmed cases",                     "confirmed_cases",  "reds", "log", "int", False),
    ("Observed (epi update)", "obs::suspected", "Suspected cases",                     "suspected_cases",  "reds", "log", "int", False),
    ("Observed (epi update)", "obs::conf_d",    "Confirmed deaths",                    "confirmed_deaths", "reds", "log", "int", False),
    ("Observed (epi update)", "obs::susp_d",    "Suspected deaths",                    "suspected_deaths", "reds", "log", "int", False),
    ("Modeled projection",    "cal::true",      "Relative risk",                       "relative_risk",    "outbreak", "log", 2, False),
    _make_layer_def(
        "Incoming Mobility",
        "disp::in",
        "Internally displaced persons (IOM)",
        "displaced_in_individuals_12mo",
        "reds", "log", "int",
    ),
    _make_layer_def(
        "Incoming Mobility",
        "flow::in",
        "Relocated persons between Feb 2026 and Mar 2026 (Flowminder)",
        "flowminder_in_mar2026",
        "reds", "log", "int",
        legend_caption="Number of relocated persons",
    ),
    _make_layer_def(
        "Incoming Mobility",
        "flow::in_apr",
        "Relocated persons between March 2026 and April 2026 (Flowminder)",
        "flowminder_in_202604",
        "reds", "log", "int",
        legend_caption="Number of relocated persons",
    ),
    *EXTRA_LAYER_DEFS_TRAVEL,
    *_FLOWMINDER_SHORT_TRIPS_LAYER_DEFS,
]


def _extra_layer_from_def(defn: tuple | dict) -> dict:
    if isinstance(defn, dict):
        return dict(defn)
    (group, lid, label, field, palette, scale, legend_round, epicenter_highlight) = defn[:8]
    kwargs: dict = {}
    if len(defn) > 8 and defn[8]:
        kwargs = {
            "matrix_id": defn[8],
            "matrix_scale": defn[9] if len(defn) > 9 else 1,
            "origin_highlight": defn[10] if len(defn) > 10 else True,
        }
    return _make_layer_def(
        group, lid, label, field, palette, scale, legend_round, epicenter_highlight, **kwargs)

PROJECTION_MASK_LAYERS = {"cal::true"}
PROJECTION_MASK_FIELD = "relative_risk"
PROJECTION_MASK_MIN = 0.005

# Dropdown optgroup order (display names). Unlisted groups keep their relative
# order after these entries.
LAYER_GROUP_ORDER = [
    "Observed (epi update)",
    "Testing capacity",
    "Incoming Mobility",
    "Movements from epicentres (Flowminder)",
]


def _sort_layers_for_dropdown(layers: list[dict]) -> list[dict]:
    rank = {name: i for i, name in enumerate(LAYER_GROUP_ORDER)}
    default_rank = len(LAYER_GROUP_ORDER)
    indexed = sorted(
        enumerate(layers),
        key=lambda item: (rank.get(item[1]["group"], default_rank), item[0]),
    )
    return [layer for _, layer in indexed]


# ---------------------------------------------------------------------------
# i18n (locale YAML + per-language layers / legal text)
# ---------------------------------------------------------------------------

def _load_locale_yaml(lang: str) -> dict:
    path = LOCALES_DIR / f"{lang}.yaml"
    if not path.exists():
        print(f"  WARNING: locale file missing: {path.name}")
        return {}
    try:
        import yaml
    except ImportError:
        print("  WARNING: PyYAML not installed; locale files ignored")
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_locales() -> dict[str, dict]:
    locales = {lang: _load_locale_yaml(lang) for lang in SUPPORTED_LANGS}
    for lang, data in locales.items():
        if data:
            print(f"  locale {lang}: loaded")
    return locales


def localize_layers(layers: list[dict], locale: dict) -> list[dict]:
    """Return a copy of ``layers`` with group/label text from a locale bundle."""
    group_map = locale.get("layer_groups") or {}
    label_map = locale.get("layer_labels") or {}
    out: list[dict] = []
    for layer in layers:
        localized = dict(layer)
        en_group = layer["group"]
        if en_group in group_map:
            localized["group"] = group_map[en_group]
        layer_id = layer["id"]
        label_template = None
        if layer_id in label_map:
            label_template = label_map[layer_id]
        elif "{origin}" in layer.get("label", ""):
            label_template = layer["label"]
        if label_template:
            localized["label_template"] = label_template
            localized["label"] = label_template.replace("{origin}", TRAVEL_FROM_ZONE)
        caption_map = locale.get("layer_legend_captions") or {}
        if layer_id in caption_map:
            localized["legend_caption"] = caption_map[layer_id]
        out.append(localized)
    return out


def build_i18n_payload(layers_en: list[dict], phr_context: dict[str, dict]) -> dict:
    locales = load_locales()
    layers_by_lang = {
        lang: localize_layers(layers_en, locales.get(lang, {}))
        for lang in SUPPORTED_LANGS
    }
    methods_html = {lang: load_methods_html_lang(lang) for lang in SUPPORTED_LANGS}
    terms_html: dict[str, str] = {}
    terms_updated: dict[str, str] = {}
    tracker_caveats: dict[str, list] = {}
    for lang in SUPPORTED_LANGS:
        html, updated = load_terms_html_lang(lang)
        terms_html[lang] = html
        terms_updated[lang] = updated
        tracker_caveats[lang] = load_tracker_caveats(lang)
    print(f"  i18n: {', '.join(SUPPORTED_LANGS)} "
          f"(methods fr={len(methods_html.get('fr', ''))} chars)")
    return {
        "default": "en",
        "langs": list(SUPPORTED_LANGS),
        "strings": locales,
        "layers": layers_by_lang,
        "phr_context": phr_context,
        "methods_html": methods_html,
        "terms_html": terms_html,
        "terms_updated": terms_updated,
        "tracker_caveats": tracker_caveats,
    }


# ---------------------------------------------------------------------------
# payload assembly
# ---------------------------------------------------------------------------

def load_data_build_info() -> dict | None:
    """Data-repo release tag/URL from build/manifest.json (same tag as GitHub Releases)."""
    if not BUILD_MANIFEST.exists():
        print(f"  NOTE: {BUILD_MANIFEST} not found; data_build omitted from payload")
        return None
    try:
        manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  WARNING: could not read {BUILD_MANIFEST.name}: {e}")
        return None
    built_at = manifest.get("built_at")
    commit = manifest.get("commit")
    if not built_at or not commit:
        print(f"  WARNING: {BUILD_MANIFEST.name} missing built_at or commit")
        return None
    date_part = str(built_at).split("T", 1)[0]
    tag = f"build-{date_part}-{commit}"
    url = f"https://github.com/{DATA_REPO}/releases/tag/{tag}"
    print(f"  data_build: {tag}")
    return {
        "repo": DATA_REPO,
        "tag": tag,
        "url": url,
        "built_at": str(built_at),
        "commit": str(commit),
    }


def load_genomic_products(genomic_dir=None):
    """Load the BDBV2026-Genomic_Epi products into a payload slice.

    Returns {} when the sibling repo isn't present, so a build without it stays
    green (the genomic tab is a stub until later phases wire it up). The tree is
    returned as inline NEXUS text (PearTree's embed accepts it under the `tree`
    key), so it needs no separate fetched asset.
    """
    d = Path(genomic_dir) if genomic_dir is not None else GENOMIC_DIR
    tree_path = d / "ituri-tree.ptree"
    if not tree_path.exists():
        return {}
    meta = json.loads((d / "ituri-meta.json").read_text(encoding="utf-8"))
    return {
        "tree": tree_path.read_text(encoding="utf-8"),
        "tips": json.loads((d / "ituri-tips.json").read_text(encoding="utf-8")),
        "meta": meta,
        "skygrid": json.loads((d / "skygrid.json").read_text(encoding="utf-8")),
        "exponential": json.loads((d / "exponential.json").read_text(encoding="utf-8")),
        "data_build_date": meta.get("updated"),
    }


def canonicalize_genomic_zones(genomic: dict, known_noms) -> dict:
    """Correct tip ``health_zone`` spellings to the canonical zone ``nom`` set.

    The genomic tree producer occasionally spells a zone differently from the
    dashboard's build-GeoJSON noms (observed: 'Nyakunde' -> 'Nyankunde', 'Gethy'
    -> 'Gety'). Left unfixed, selecting such a zone on the map highlights no tips
    (``zoneToTips`` is keyed by the tip spelling) and the by-zone case scope misses
    it. Correct BOTH the tips list and the inline NEXUS ``health_zone`` annotations
    so tree colouring, selection, and case scoping all agree. Matching is exact
    (via ``_norm``, catching accent/case) first, then a conservative fuzzy fallback
    for letter-level typos; every correction is logged for review.
    """
    if not genomic:
        return genomic
    known = set(known_noms or ())
    if not known:
        return genomic
    tips = genomic.get("tips") or []
    zones = {(t.get("health_zone") or "").strip()
             for t in tips if (t.get("health_zone") or "").strip()}
    known_by_norm = {_norm(n): n for n in known}
    correction: dict[str, str] = {}
    for z in zones:
        if z in known:
            continue
        exact = known_by_norm.get(_norm(z))
        if exact and exact != z:
            correction[z] = exact
            continue
        near = difflib.get_close_matches(z, known, n=1, cutoff=0.85)
        if near and near[0] != z:
            correction[z] = near[0]
    if not correction:
        return genomic
    for t in tips:
        z = (t.get("health_zone") or "").strip()
        if z in correction:
            t["health_zone"] = correction[z]
    tree = genomic.get("tree")
    if isinstance(tree, str):
        for old, new in correction.items():
            tree = tree.replace(f'health_zone="{old}"', f'health_zone="{new}"')
        genomic["tree"] = tree
    print("  genomic zone canonicalisation: "
          + ", ".join(f"{o!r}->{n!r}" for o, n in sorted(correction.items())))
    return genomic


_ONSET_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# status_aggregated.csv is the SAME table the Trends tab's "Daily Cases by
# Symptom Onset" SVG is rendered from (manifest.json's ``source_csv``). The
# genomic panel reads its confirmed_case column so both charts show identical
# data; the earlier dhis2_linelist_with_imputed_onset.csv path counted EVERY
# linelist row (confirmed + probable + suspected + not_a_case + unclassified),
# so the "Confirmed positive cases" panel read ~6x high.
_STATUS_AGG_CSV_NAME = "status_aggregated.csv"


# --- Trends series packers -------------------------------------------------
# These reproduce BDBV2026-Processing_Code@main's 4-make-dashboard-plots.R
# exactly; see docs/superpowers/specs/2026-09-22-trends-dynamic-charts-design.md
# section 6. Do not "tidy" the asymmetries below -- cases ACCUMULATE duplicate
# rows while deaths/positivity OVERWRITE (last row wins), and only cases skip
# zero-total locations. That is what the generator does.

_TRENDS_SCALES = (("national", None), ("province", "province"), ("healthzone", "health_zone"))
_TRENDS_EPOCH = "2026-01-01"
# Built once rather than per CSV row -- every packer looks a scale up in its
# inner loop.
_TRENDS_SCALE_MAP = dict(_TRENDS_SCALES)
# Distinct from None, which is the *legitimate* key_field for the national
# scale (national rows carry no location column).
_UNKNOWN_SCALE = object()


def _trends_loc(row, key_field):
    """Location name for a row, or None when it should be dropped."""
    if key_field is None:
        return "national"
    name = (row.get(key_field) or "").strip()
    if not name or name.upper() == "NA":
        return None
    return name


def _i0(value):
    """Integer count, with blank/NA/non-numeric read as 0.

    Mirrors the generator's to_int(): R returns 0L for NULL/NA/empty rather
    than erroring, so a blank count column means "no cases", not "crash".
    _i() alone returns None for those, which would blow up the accumulators.
    """
    return _i(value) or 0


def _day_range(start, end):
    """Inclusive list of ISO dates from start to end."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    return [(s + timedelta(days=i)).isoformat() for i in range((e - s).days + 1)]


def _pack_trends_cases(path, canon=None):
    """{scale: {location: {start, obs[], imp[]}}} from status_aggregated.csv."""
    canon = canon or (lambda s: s)
    buckets = {scale: {} for scale, _ in _TRENDS_SCALES}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            scale = (row.get("spatial_scale") or "").strip().lower()
            key_field = _TRENDS_SCALE_MAP.get(scale, _UNKNOWN_SCALE)
            if key_field is _UNKNOWN_SCALE:
                continue
            loc = _trends_loc(row, key_field)
            if loc is None:
                continue
            if key_field == "health_zone":
                # canon maps to canonical health-zone noms, so it applies to
                # zones ONLY. Province names are a different namespace; several
                # DRC provinces share a name with a health zone (Ituri, Tshopo,
                # Kinshasa...), so running provinces through it would silently
                # rewrite a province to a zone's spelling if the two ever drift.
                loc = canon(loc)
            day = (row.get("date_of_symptom_onset_imputed") or "").strip()
            if not _ONSET_DATE_RE.match(day):
                continue
            slot = "imp" if (row.get("onset_date_was_imputed") or "").strip().upper() == "TRUE" else "obs"
            entry = buckets[scale].setdefault(loc, {}).setdefault(day, {"obs": 0, "imp": 0})
            entry[slot] += _i0(row.get("confirmed_case"))   # ACCUMULATE

    packed = {scale: {} for scale, _ in _TRENDS_SCALES}
    for scale, by_loc in buckets.items():
        for loc, by_day in by_loc.items():
            if sum(v["obs"] + v["imp"] for v in by_day.values()) <= 0:
                continue                                    # spec 6.1 skip rule
            positives = [d for d, v in by_day.items() if v["obs"] + v["imp"] > 0]
            in_epoch = [d for d in positives if d >= _TRENDS_EPOCH]
            start = min(in_epoch or positives)
            end = max(by_day)                               # trailing zeros KEPT
            days = _day_range(start, end)
            packed[scale][loc] = {
                "start": start,
                "obs": [by_day.get(d, {}).get("obs", 0) for d in days],
                "imp": [by_day.get(d, {}).get("imp", 0) for d in days],
            }
    return packed


def _pack_trends_deaths(path, canon=None):
    """{scale: {location: {start, cum[], daily[]}}} from cumulative_positive_deaths.csv.

    `daily` is carried in the payload because the chart draws a point ONLY on
    days where daily_deaths > 0 (spec 6.3); it is not otherwise plotted.
    """
    canon = canon or (lambda s: s)
    buckets = {scale: {} for scale, _ in _TRENDS_SCALES}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            scale = (row.get("spatial_scale") or "").strip().lower()
            key_field = _TRENDS_SCALE_MAP.get(scale, _UNKNOWN_SCALE)
            if key_field is _UNKNOWN_SCALE:
                continue
            loc = _trends_loc(row, key_field)
            if loc is None:
                continue
            if key_field == "health_zone":
                # canon maps to canonical health-zone noms, so it applies to
                # zones ONLY. Province names are a different namespace; several
                # DRC provinces share a name with a health zone (Ituri, Tshopo,
                # Kinshasa...), so running provinces through it would silently
                # rewrite a province to a zone's spelling if the two ever drift.
                loc = canon(loc)
            day = (row.get("reporting_date") or "").strip()
            if not _ONSET_DATE_RE.match(day):
                continue
            # OVERWRITE, last row wins -- deliberately unlike _pack_trends_cases
            buckets[scale].setdefault(loc, {})[day] = (
                _i0(row.get("daily_deaths")), _i0(row.get("cumulative_deaths"))
            )

    packed = {scale: {} for scale, _ in _TRENDS_SCALES}
    for scale, by_loc in buckets.items():
        for loc, by_day in by_loc.items():
            if not by_day:
                continue                       # no zero-total skip: only "no rows at all"
            days = _day_range(min(by_day), max(by_day))
            cum, daily, last = [], [], 0
            for d in days:
                if d in by_day:
                    daily.append(by_day[d][0])
                    last = by_day[d][1]
                else:
                    daily.append(0)
                cum.append(last)               # carry forward
            packed[scale][loc] = {"start": days[0], "cum": cum, "daily": daily}
    return packed


def _onset_manifest_dated_dir(base: Path):
    """The dated ``outputs/<date>/`` dir the onset SVGs are read from.

    load_dashboard_plots() resolves the plot snapshot from manifest.json's
    top-level ``date``; matching it here keeps this panel and the Trends SVG on
    one snapshot. Returns None when there is no manifest, date, or matching dir.
    """
    manifest_path = base / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        date = json.loads(manifest_path.read_text(encoding="utf-8")).get("date")
    except (json.JSONDecodeError, OSError):
        return None
    if not date:
        return None
    dated = base / str(date)
    return dated if dated.is_dir() else None


def _latest_status_aggregated(outputs_dir):
    """Path to ``status_aggregated.csv``, or None.

    Prefers the SAME dated dir the onset SVGs use (manifest.json's ``date``) so
    this panel and the Trends SVG share one snapshot; falls back to the newest
    YYYY-MM-DD dir that actually contains the file.
    """
    base = Path(outputs_dir)
    if not base.exists():
        return None
    preferred = _onset_manifest_dated_dir(base)
    if preferred is not None and (preferred / _STATUS_AGG_CSV_NAME).exists():
        return preferred / _STATUS_AGG_CSV_NAME
    dated = sorted(
        (p for p in base.iterdir()
         if p.is_dir() and _ONSET_DATE_RE.match(p.name) and (p / _STATUS_AGG_CSV_NAME).exists()),
        key=lambda p: p.name,
    )
    return (dated[-1] / _STATUS_AGG_CSV_NAME) if dated else None


def load_onset_imputed_series(outputs_dir=None, known_noms=None, tree_most_recent=None):
    """Confirmed cases per date/zone, split observed-vs-imputed onset, for the
    genomic tab's sample-distribution panel. Returns {} if absent.

    Reads ``status_aggregated.csv`` -- the pre-aggregated table the Trends tab's
    "Daily Cases by Symptom Onset" SVG is rendered from -- and takes ONLY its
    ``confirmed_case`` column (the panel is titled "Confirmed positive cases"),
    so the two charts show identical data. Rows are pre-summed per
    ``(date_of_symptom_onset_imputed, onset_date_was_imputed, spatial_scale)``:
    ``national`` rows feed the national series, ``healthzone`` rows feed by_zone.

    Zone strings are joined to canonical ``nom`` via _norm against ``known_noms``
    (the payload's zone_data keys); unmatched names pass through unchanged.
    ``tree_most_recent`` (meta.mostRecentDate) is echoed so the panel can mark the
    "beyond-tree" region (onset dates strictly after it).
    """
    path = _latest_status_aggregated(outputs_dir if outputs_dir is not None else DASHBOARD_PLOTS_DIR)
    if path is None:
        return {}
    nom_by_norm = {_norm(n): n for n in (known_noms or ())}

    def canon(name):
        return nom_by_norm.get(_norm(name), name)

    by_zone, national = {}, {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            d = (row.get("date_of_symptom_onset_imputed") or "").strip()
            if not d:
                continue
            n = _i(row.get("confirmed_case"))
            if not n or n <= 0:
                continue
            bucket = "imputed" if (row.get("onset_date_was_imputed") or "").strip().upper() == "TRUE" else "observed"
            scale = (row.get("spatial_scale") or "").strip().lower()
            if scale == "national":
                national.setdefault(d, {"observed": 0, "imputed": 0})[bucket] += n
            elif scale == "healthzone":
                z = (row.get("health_zone") or "").strip()
                if not z or z.upper() == "NA":
                    continue
                by_zone.setdefault(canon(z), {}).setdefault(d, {"observed": 0, "imputed": 0})[bucket] += n
    return {
        "dates": sorted(national),
        "national": national,
        "by_zone": by_zone,
        "beyond_tree_from": tree_most_recent,
        "source": path.parent.name,
    }


