import importlib
from pathlib import Path

ds = importlib.import_module("common.data_sources")

CSV = (
    "country,date_of_symptom_onset_imputed,confirmed_case,total_samples_analysed_daily,"
    "spatial_scale,province,health_zone,rolling_confirmed,rolling_total,"
    "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
    "NA,2026-05-01,2,3,healthzone,NA,Bunia,2,3,0.5,0.1,0.9\n"
    "NA,2026-05-01,1,1,healthzone,NA,  BUNIA ,1,1,1,0.2,1\n"
    "NA,2026-05-02,0,1,healthzone,NA,Mongbwalu,0,1,0,0,0.8\n"
    "NA,2026-05-01,4,5,national,NA,NA,4,5,0.8,0.3,1\n"
    "NA,2026-05-02,1,2,national,NA,NA,1,2,0.5,0.1,0.9\n"
    "NA,2026-05-01,9,9,province,Ituri,NA,9,9,1,0.5,1\n"
    "NA,not-a-date,1,1,healthzone,NA,Bunia,1,1,1,0.2,1\n"
)


def test_rolling_positivity_aggregates_confirmed_case(tmp_path):
    path = tmp_path / "rolling_positivity.csv"
    path.write_text(CSV, encoding="utf-8")
    res = ds.load_rolling_positivity_case_series(
        csv_path=path,
        known_noms={"Bunia", "Mongbwalu"},
        tree_most_recent="2026-08-16",
    )
    assert res["case_source"] == "rolling_positivity.confirmed_case"
    assert res["source"] == "rolling_positivity"
    assert res["beyond_tree_from"] == "2026-08-16"
    # Two healthzone rows for Bunia on 2026-05-01 (2 + 1), case-folded to Bunia
    assert res["by_zone"]["Bunia"]["2026-05-01"] == {"observed": 3, "imputed": 0}
    assert res["by_zone"]["Mongbwalu"]["2026-05-02"] == {"observed": 0, "imputed": 0}
    # National rows preferred over summing zones / provinces
    assert res["national"]["2026-05-01"] == {"observed": 4, "imputed": 0}
    assert res["national"]["2026-05-02"] == {"observed": 1, "imputed": 0}
    assert res["dates"] == ["2026-05-01", "2026-05-02"]


def test_rolling_positivity_absent_returns_empty(tmp_path):
    assert ds.load_rolling_positivity_case_series(csv_path=tmp_path / "missing.csv") == {}


def test_rolling_positivity_sums_zones_when_no_national(tmp_path):
    path = tmp_path / "rolling_positivity.csv"
    path.write_text(
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,health_zone\n"
        "2026-06-01,2,healthzone,Bunia\n"
        "2026-06-01,3,healthzone,Gety\n",
        encoding="utf-8",
    )
    res = ds.load_rolling_positivity_case_series(
        csv_path=path, known_noms={"Bunia", "Gety"},
    )
    assert res["national"]["2026-06-01"]["observed"] == 5
