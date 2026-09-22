import importlib
from pathlib import Path

ds = importlib.import_module("common.data_sources")

# Transcribed from BDBV2026-Processing_Code@main 4-make-dashboard-plots.R.
# confirmed_case ONLY -- blank/not_a_case/suspected/probable are decoys here.
CASES_CSV = (
    "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
    "blank,not_a_case,suspected_case,probable_case,spatial_scale,province,health_zone\n"
    # national: a leading zero-day that must be TRIMMED
    "2026-05-01,FALSE,0,99,99,99,99,national,NA,NA\n"
    "2026-05-02,FALSE,2,0,0,0,0,national,NA,NA\n"
    "2026-05-02,TRUE,1,0,0,0,0,national,NA,NA\n"
    # duplicate row for the same (date, flag) -- must ACCUMULATE to 3
    "2026-05-02,FALSE,1,0,0,0,0,national,NA,NA\n"
    # 2026-05-03 absent entirely -- must be zero-FILLED
    "2026-05-04,FALSE,5,0,0,0,0,national,NA,NA\n"
    # a trailing zero-day that must be KEPT
    "2026-05-05,FALSE,0,0,0,0,0,national,NA,NA\n"
    "2026-05-02,FALSE,4,0,0,0,0,province,Ituri,NA\n"
    "2026-05-02,FALSE,1,0,0,0,0,healthzone,NA,  BUNIA \n"
    # zero-total zone -- must be SKIPPED entirely (not emitted as all-zeros)
    "2026-05-02,FALSE,0,50,50,50,50,healthzone,NA,Nyarambe\n"
    # unparseable / blank dates are dropped
    ",FALSE,7,0,0,0,0,national,NA,NA\n"
    # blank confirmed_case on an otherwise valid row: R's to_int() reads this
    # as 0, so it must NOT crash and must NOT change any count
    "2026-05-04,FALSE,,0,0,0,0,national,NA,NA\n"
)


def test_cases_packs_accumulates_trims_and_zero_fills(tmp_path):
    (tmp_path / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv", canon=lambda s: {"bunia": "Bunia"}.get(s.strip().lower(), s.strip()))

    nat = out["national"]["national"]
    assert nat["start"] == "2026-05-02"          # 05-01 zero-day trimmed off the front
    assert nat["obs"] == [3, 0, 5, 0]            # duplicate accumulated; 05-03 zero-filled; 05-05 kept
    assert nat["imp"] == [1, 0, 0, 0]

    assert out["province"]["Ituri"] == {"start": "2026-05-02", "obs": [4], "imp": [0]}
    assert out["healthzone"]["Bunia"] == {"start": "2026-05-02", "obs": [1], "imp": [0]}
    assert "Nyarambe" not in out["healthzone"]   # zero-total location skipped (spec 6.1)


def test_blank_counts_are_read_as_zero_not_crashes(tmp_path):
    # R's to_int() returns 0L for blank/NA/non-numeric. _i() returns None for
    # those, and `int += None` raises -- so counts must go through _i0().
    csv_text = (
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-05-01,FALSE,1,national,NA,NA\n"
        "2026-05-02,FALSE,,national,NA,NA\n"
        "2026-05-03,FALSE,notanumber,national,NA,NA\n"
    )
    (tmp_path / "status_aggregated.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv")

    assert out["national"]["national"] == {"start": "2026-05-01", "obs": [1, 0, 0], "imp": [0, 0, 0]}


def test_positive_dates_before_the_outbreak_epoch_are_excluded(tmp_path):
    # earliest_positive_date() restricts the start to positives >= 2026-01-01
    # when any qualifies, and complete_date_series() then drops every row
    # before that start -- so a stray 2025 case does not appear at all.
    csv_text = (
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2025-12-30,FALSE,2,national,NA,NA\n"
        "2026-05-02,FALSE,3,national,NA,NA\n"
    )
    (tmp_path / "status_aggregated.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv")

    # Starts at the in-epoch date, NOT 2025-12-30, and the 2025 count is gone.
    assert out["national"]["national"] == {"start": "2026-05-02", "obs": [3], "imp": [0]}


def test_epoch_falls_back_when_no_positive_date_is_in_the_outbreak_window(tmp_path):
    # pool <- if (length(outbreak_positives)) outbreak_positives else positive_dates
    # With everything before the epoch, the fallback keeps the whole series
    # rather than producing an empty pool.
    csv_text = (
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2025-12-30,FALSE,2,national,NA,NA\n"
        "2025-12-31,FALSE,3,national,NA,NA\n"
    )
    (tmp_path / "status_aggregated.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv")

    assert out["national"]["national"] == {"start": "2025-12-30", "obs": [2, 3], "imp": [0, 0]}


def test_blank_and_na_locations_are_dropped(tmp_path):
    # _trends_loc() drops province/health_zone values that are empty or the
    # literal string "NA". Without this, "NA" becomes a location of its own.
    csv_text = (
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-05-02,FALSE,4,province,Ituri,NA\n"
        "2026-05-02,FALSE,7,province,NA,NA\n"
        "2026-05-02,FALSE,9,province,,NA\n"
        "2026-05-02,FALSE,5,healthzone,NA,   \n"
    )
    (tmp_path / "status_aggregated.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv")

    assert sorted(out["province"]) == ["Ituri"]   # not "NA", not ""
    assert out["healthzone"] == {}                # whitespace-only dropped
