import importlib
import json

surv = importlib.import_module("common.surveillance")
chrome = importlib.import_module("common.chrome")

MINIMAL = {"geometry": {"type": "FeatureCollection", "features": []}, "zone_data": {}, "layers": []}


def _ct_tables(tmp_path, date="2026-10-15"):
    t = tmp_path / "outputs" / date / "tables"
    t.mkdir(parents=True)
    (t / "weekly_national.csv").write_text(
        ",new_cases,new_cases_prev_contact,new_cases_contact_after,new_cases_became_source,"
        "new_source_cases,new_contacts,pct_prev_contact,pct_became_source\n"
        "2026-05-04,8,0.0,0.0,0.0,2.0,2.0,0.0,0.0\n"          # before the report's x axis: dropped
        "2026-05-11,19,1.0,0.0,5.0,0,0,5.3,26.3\n"             # < 20 cases: no percentages
        "2026-05-18,200,2.0,1.0,40.0,0,0,1.0,20.0\n", encoding="utf-8")
    (t / "followup_visits_weekly.csv").write_text(
        "wk,visits,pct_result\n2026-05-11,100,80.0\n", encoding="utf-8")
    (t / "fu21_complete_hz_month.csv").write_text(
        "src_province,src_health_zone,lc_month,n,k\n"
        "Ituri,Bunia,2026-05,200,50\n"
        "Ituri,Bunia,2026-06,9,9\n"                             # small cell: suppressed
        "Ituri,Tiny,2026-05,12,3\n", encoding="utf-8")
    (t / "dashboard_fu21_by_month.csv").write_text(
        "month,k,n\n2026-04,5,5\n2026-05,53,212\n2026-06,9,9\n", encoding="utf-8")
    (t / "province_table.csv").write_text(
        "area,cases,deaths,pct_cases_source,pct_cases_prev_contact,source_cases,contacts,med_contacts,"
        "pct_fu_complete,fu_n,sar_k,sar_n,sar_wilson_lo,sar_wilson_hi,sar_boot_lo,sar_boot_hi,"
        "fu_wilson_lo,fu_wilson_hi,fu_boot_lo,fu_boot_hi\n"
        "Ituri,6565,2390,8.7,0.4,724,9080,7,29.1,100,1,10,0,1,0,1,24,33,24,33\n"
        "National,8953,3300,13.1,0.536133,1169,14324,7,22.24,12899,1,10,0,1,0,1,21,23,21,23\n",
        encoding="utf-8")
    (t / "dashboard_meta.json").write_text(json.dumps(
        {"data_cut": date, "last_full_week": "2026-10-05", "n_cases_contact_any_time": 104,
         "fu21_contacts": 12899, "fu21_complete": 2869}), encoding="utf-8")
    return t


def test_weekly_series_trims_early_weeks_and_hides_small_week_percentages(tmp_path):
    t = _ct_tables(tmp_path)
    ct = surv.load_contact_tracing(t)
    w = ct["weekly"]
    assert w["weeks"] == ["2026-05-11", "2026-05-18"]
    assert w["new_cases"] == [19, 200]
    assert w["pct_prev_contact"] == [None, 1.0]       # 19 cases < 20: no percentage
    assert w["pct_became_source"] == [None, 20.0]


def test_headline_known_contacts_uses_the_unrounded_percentage(tmp_path):
    ct = surv.load_contact_tracing(_ct_tables(tmp_path))
    assert ct["headline"]["prev_contact_n"] == 48     # 0.536% of 8,953, not 0.5% (= 45)
    assert ct["headline"]["any_time_n"] == 104
    assert all(r["area"] != "National" for r in ct["provinces"])
    assert "_pct_prev_raw" not in json.dumps(ct)


def test_fu21_suppresses_small_cells_and_small_national_months(tmp_path):
    fu = surv.load_contact_tracing(_ct_tables(tmp_path))["fu21"]
    assert fu["months"] == ["2026-05"]                 # April (5) and June (9) national totals < 10
    # total counts shown cells only, so the suppressed 9 can't be recovered by subtraction
    assert fu["zones"]["Bunia"] == {"k": [50], "n": [200], "total": 200}
    assert fu["zones"]["Tiny"]["n"] == [12]
    assert fu["default_zones"] == ["Bunia"]            # Tiny is below the 150-contact zone threshold
    assert "9" not in json.dumps(fu["zones"]["Bunia"]["n"])


def test_only_aggregate_tables_are_read_never_derived(tmp_path):
    t = _ct_tables(tmp_path)
    derived = t.parent / "derived"
    derived.mkdir()
    (derived / "results.json").write_text(json.dumps({"SECRET_PERSON_LEVEL": 1}), encoding="utf-8")
    (derived / "persons.csv").write_text("person_id\nSECRET_PERSON_LEVEL\n", encoding="utf-8")
    ct = surv.load_contact_tracing(t)
    assert "SECRET_PERSON_LEVEL" not in json.dumps(ct)


def test_latest_tables_dir_picks_newest_dated_folder_with_tables(tmp_path):
    _ct_tables(tmp_path, "2026-10-09")
    _ct_tables(tmp_path, "2026-10-15")
    (tmp_path / "outputs" / "2026-10-20").mkdir()      # newer, but no tables yet
    assert surv.latest_ct_tables_dir(tmp_path / "outputs").parent.name == "2026-10-15"
    assert surv.latest_ct_tables_dir(tmp_path / "missing") is None


def test_testing_series_packs_scales_and_rounds_positivity(tmp_path):
    out = tmp_path / "outputs"
    snap = out / "2026-10-15"
    snap.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({"date": "2026-10-15"}), encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(
        "country,date_of_symptom_onset_imputed,confirmed_case,total_samples_analysed_daily,"
        "spatial_scale,province,health_zone,rolling_confirmed,rolling_total,daily_positivity_mean,"
        "daily_positivity_lower,daily_positivity_upper,health_area\n"
        "NA,2026-05-01,2,5,national,NA,NA,2,5,0.4,0.117621,0.769276,NA\n"
        "NA,2026-05-01,1,3,healthzone,NA,Bunia,1,3,0.333333333,0.06,0.79,NA\n"
        "NA,2026-05-01,1,1,healtharea,NA,Bunia,1,1,1,0.2,1,Aero\n", encoding="utf-8")
    (snap / "lab_positivity_aggregated.csv").write_text(
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "LBNIZ,Laboratoire Nizi,Nizi,Ituri,2026-05-02,2026-05-02,3,10,3,10,0.3,0.1,0.6\n"
        "AUT,NA,NA,NA,2026-05-02,2026-05-02,1,2,1,2,0.5,0.1,0.9\n", encoding="utf-8")

    te = surv.load_testing(out)

    assert te["national"]["n"] == [5] and te["national"]["pos"] == [2]
    assert te["national"]["lo"] == [0.1176]
    assert te["health_zones"]["Bunia"]["mean"] == [0.3333]
    assert "healtharea" not in json.dumps(te) and "Aero" not in json.dumps(te)
    assert [l["code"] for l in te["labs"]] == ["LBNIZ", "AUT"]    # sorted by samples
    assert te["labs"][1]["label"] == "AUT"                        # "NA" long name falls back to code
    assert te["incomplete_from"] == "2026-10-08"


def test_surveillance_is_page_scoped_and_page_is_mapless():
    assert chrome._PAGE_SCOPED_PAYLOAD_KEYS["surveillance"] == {"surveillance-testing"}
    assert "surveillance-testing" not in chrome.STUB_VIEWS
    assert "surveillance-testing" in chrome.MAPLESS_VIEWS
    page = importlib.import_module("pages.surveillance_testing")
    html = page.build_page(dict(MINIMAL, surveillance={"testing": None, "contact_tracing": None}))
    assert "mapless-view" in html and "stub-view" not in html
    assert 'id="surv-page"' in html and 'src="assets/surveillance.js"' in html
    assert "stub-surveillance-testing" not in html
    other = chrome.render_page("trends", dict(MINIMAL, surveillance={"x": 1}))
    assert '"surveillance"' not in other
