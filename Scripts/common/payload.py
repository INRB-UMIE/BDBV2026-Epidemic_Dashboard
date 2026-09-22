"""
Builds the single shared JSON payload consumed by every dashboard page.

This is deliberately unsplit for now: the JS engine (Scripts/assets/engine.js)
still expects one combined PAYLOAD object across all four pages (map,
epi-trends/spatial-risk, trends, context each read fields from it — e.g. the
Trends view reads PAYLOAD.confirmed_timeseries, the Context view reads
PAYLOAD.phr_context, etc.). Trimming this into per-page payloads is a natural
follow-up once each page's JS is actually independent of the others; see
README "Multi-page structure" section.
"""

from __future__ import annotations

from datetime import datetime, timezone

from common.data_sources import *  # noqa: F401,F403 -- re-export all loaders/constants
from common.paths import (
    BUILD_GEOJSON, OSRM_TRAVEL_TIME_CSV, DATA_ROOT, BUILD_DIR,
)


def build_shared_payload() -> dict:
    print(f"BUILD_DIR  = {BUILD_DIR}")
    print(f"DATA_ROOT  = {DATA_ROOT}")

    features, centroids_by_nom = load_features_from_geojson()
    print(f"  loaded {len(features)} zone polygons from {BUILD_GEOJSON.name}")

    # Auto-discover layers from GeoJSON properties
    discovered_layers, field_paths = discover_geojson_layers(BUILD_GEOJSON)
    print(f"  auto-discovered {len(discovered_layers)} layers from GeoJSON")

    zone_data, case_totals = load_metadata(centroids_by_nom, field_paths)
    print(f"  assembled metadata for {len(zone_data)} zones")

    # Harmonised (line-list ∪ sitrep) confirmed counts from the model, topped up
    # with the dashboard's (fresher) live sitrep. MUST precede build_active_case_markers.
    harmonised_confirmed = load_harmonised_confirmed_cases(set(zone_data))
    write_effective_confirmed_cases(zone_data, harmonised_confirmed)

    initial_view = None
    if "Bunia" in centroids_by_nom:
        lon, lat = centroids_by_nom["Bunia"]
        initial_view = {"lat": lat, "lon": lon, "zoom": 8}

    # Extra layers (computed fields, matrices, local CSV) go first,
    # then auto-discovered GeoJSON layers. Extra defs override discovery labels
    # for the same flat field (e.g. Flowminder short-trip outflow snapshots).
    extra_layers = [_extra_layer_from_def(defn) for defn in EXTRA_LAYER_DEFS]
    extra_fields = {layer["field"] for layer in extra_layers if layer.get("field")}
    discovered_layers = [
        layer for layer in discovered_layers if layer["field"] not in extra_fields
    ]
    layers = _sort_layers_for_dropdown(extra_layers + discovered_layers)
    for layer in layers:
        if layer.get("label_template"):
            continue
        if "{origin}" in layer.get("label", ""):
            layer["label_template"] = layer["label"]
            layer["label"] = layer["label"].replace("{origin}", TRAVEL_FROM_ZONE)

    phr_context_by_lang = load_public_health_context()
    i18n = build_i18n_payload(layers, phr_context_by_lang)
    methods_html = i18n["methods_html"]["en"]
    print(f"  methods HTML: {len(methods_html)} chars")
    terms_html = i18n["terms_html"]["en"]
    terms_updated = i18n["terms_updated"]["en"]
    print(f"  terms HTML: {len(terms_html)} chars (updated {terms_updated!r})")
    partners = load_partners()
    print(f"  partner logos: {[p['alt'] for p in partners]}")
    # Tracker totals: CSV → GeoJSON national_* (inside compute_global_sitrep_totals).
    sitrep = compute_global_sitrep_totals()
    # Last resort only if CSV and GeoJSON national blocks are both unavailable.
    if sitrep is None:
        sitrep = {
            "global_confirmed_cases":  case_totals.get("confirmed_cases", 0),
            "global_suspected_cases":  case_totals.get("suspected_cases", 0),
            "global_confirmed_deaths": case_totals.get("confirmed_deaths", 0),
            "global_suspected_deaths": case_totals.get("suspected_deaths", 0),
            "global_recovered_cases":  0,
            "global_total_cases":      case_totals.get("confirmed_cases", 0),
            "affected_countries": ["DRC"],
            "affected_country_count": 1,
            "per_country": [{
                "country": "DRC",
                "confirmed_cases":  case_totals.get("confirmed_cases", 0),
                "suspected_cases":  case_totals.get("suspected_cases", 0),
                "confirmed_deaths": case_totals.get("confirmed_deaths", 0),
                "suspected_deaths": case_totals.get("suspected_deaths", 0),
                "recovered_cases":  0,
                "total": case_totals.get("confirmed_cases", 0)
                         + case_totals.get("suspected_cases", 0),
            }],
        }
    totals = {**case_totals, **sitrep}
    ic_model = load_ic_model_estimates()
    tracker_caveats = i18n["tracker_caveats"]["en"]
    print(f"  case totals: confirmed={totals.get('confirmed_cases', 0)}, "
          f"suspected={totals.get('suspected_cases', 0)}, "
          f"affected zones={totals.get('affected_zones', 0)}")
    active_case_markers = build_active_case_markers(zone_data, centroids_by_nom)
    print(f"  active-case markers: {len(active_case_markers)} zones "
          f"(confirmed ≥ 1 from GeoJSON)")
    genome_sequence_markers = build_genome_sequence_markers(zone_data, centroids_by_nom)
    print(f"  genome-sequence markers: {len(genome_sequence_markers)} zones")

    province_boundaries = build_province_boundaries()
    print(f"  province boundaries: {len(province_boundaries['features'])} provinces")

    trends = load_trends_series(known_noms=set(zone_data))
    if trends:
        print(f"  trends: asof {trends['asof']}, "
              f"{len(trends['cases']['health_zones'])} zones, "
              f"{len(trends['labs'])} labs, "
              f"incomplete from {trends['incomplete_from']}")
    _eff_active = {n for n, r in zone_data.items()
                   if int(r.get("effective_confirmed_cases") or 0) > 0}
    invasion_risk = load_invasion_risk_estimates(effective_active_noms=_eff_active)
    # Reconcile the model's at-risk set against the freshest per-zone case counts:
    # a zone whose first confirmed case reached the sitrep after the model ran can
    # otherwise linger in the ranked at-risk table (and skew every other zone's
    # relative risk / rank). See reconcile_invasion_active_cases().
    invasion_risk = reconcile_invasion_active_cases(invasion_risk, zone_data)
    assert_harmonised_coverage(invasion_risk, zone_data, harmonised_confirmed)
    confirmed_timeseries = load_confirmed_cases_timeseries(set(zone_data.keys()))
    confirmed_recency = compute_confirmed_recency_timeseries(confirmed_timeseries)

    # Genomic-epi slice (page-scoped to the genomic tab in chrome.py): phylo
    # products from the BDBV2026-Genomic_Epi sibling + the observed/imputed onset
    # series aggregated from the canonical linelist. Empty dict when the producer
    # sibling isn't present, so the build stays green without it.
    genomic = load_genomic_products()
    if genomic:
        # Reconcile tip health_zone spellings to the canonical noms (producer typos
        # like 'Nyakunde'->'Nyankunde' otherwise break map<->tree selection + case scope).
        canonicalize_genomic_zones(genomic, set(zone_data))
        genomic["onset_distribution"] = load_onset_imputed_series(
            known_noms=set(zone_data),
            tree_most_recent=(genomic.get("meta") or {}).get("mostRecentDate"),
        )
        print(f"  genomic: {len(genomic.get('tips', []))} tips, "
              f"onset {len(genomic.get('onset_distribution', {}).get('dates', []))} dates")

    asof_date = detect_asof_date()
    asof = _format_asof(asof_date) if asof_date is not None else ASOF_FALLBACK
    print(f"  asof: {asof}")
    data_build = load_data_build_info()

    matrix_zones = _read_matrix_zone_order(OSRM_TRAVEL_TIME_CSV)
    if not matrix_zones:
        matrix_zones = sorted(zone_data.keys())
    matrices = load_zone_matrices(matrix_zones)
    print(f"  zone matrices: {len(matrix_zones)} zones, "
          f"{len(matrices['datasets'])} datasets")
    flow_latest, flow_yyyymm = load_flowminder_latest_sparse()
    flow_catalogs = {"flowminder_latest": flow_latest}
    import_force_pairwise = load_bayes_import_force_pairwise()
    flow_arc_layer = _extra_layer_from_def(FLOW_ARC_LAYER_DEF)
    if flow_yyyymm:
        period = _flowminder_period_labels(flow_yyyymm)
        flow_arc_layer["label"] = period["arcs_en"]
        flow_arc_layer["yyyymm"] = flow_yyyymm
        # Keep EN/FR layer label maps in sync with whichever _YYYYMM is latest.
        for lang, key in (("en", "arcs_en"), ("fr", "arcs_fr")):
            locale = i18n["strings"].setdefault(lang, {})
            labels = locale.setdefault("layer_labels", {})
            labels["flow::od"] = period[key]

    # Wall-clock time this build ran, shown in the header as "dashboard last
    # updated" -- distinct from `asof` (the epi data's sitrep date) and from
    # `data_build` (the companion BDBV2026-Data repo's release tag).
    dashboard_built_at = datetime.now(timezone.utc).isoformat()

    return {
        "asof": asof,
        "dashboard_built_at": dashboard_built_at,
        "travel_from": TRAVEL_FROM_ZONE,
        "matrices": matrices,
        "matrix_default_origin": matrices.get("default_origin", "Mongbwalu"),
        "flow_catalogs": flow_catalogs,
        "flow_arc_layer": flow_arc_layer,
        "flow_arcs_available": bool(flow_catalogs["flowminder_latest"].get("zones")),
        "flow_default_hub": flow_catalogs["flowminder_latest"].get(
            "default_hub", "Mongbwalu"),
        "flowminder_latest_yyyymm": flow_yyyymm,
        "initial_view": initial_view,
        "insp_sitrep_url": latest_insp_url(asof_date),
        "data_build": data_build,
        "geometry": {"type": "FeatureCollection", "features": features},
        "zone_data": zone_data,
        "layers": layers,
        "epicenter_noms": list(EPICENTER_SOURCE_NOMS),
        "epicenter_fill": EPICENTER_FILL,
        "projection_mask": {
            "layers": sorted(PROJECTION_MASK_LAYERS),
            "field": PROJECTION_MASK_FIELD,
            "min": PROJECTION_MASK_MIN,
        },
        "methods_html": methods_html,
        "terms_html": terms_html,
        "terms_updated": terms_updated,
        "i18n": i18n,
        "partners": partners,
        "totals": totals,
        "ic_model": ic_model,
        "tracker_caveats": tracker_caveats,
        "active_case_markers": active_case_markers,
        "genome_sequence_markers": genome_sequence_markers,
        "genome_markers_available": bool(genome_sequence_markers),
        "province_boundaries": province_boundaries,
        "trends": trends,
        "invasion_risk": invasion_risk,
        "import_force_pairwise": import_force_pairwise,
        "phr_context": phr_context_by_lang.get("en", {"national": [], "by_nom": {}}),
        "phr_context_by_lang": phr_context_by_lang,
        "confirmed_timeseries": confirmed_timeseries,
        "confirmed_recency": confirmed_recency,
        "genomic": genomic,
    }


