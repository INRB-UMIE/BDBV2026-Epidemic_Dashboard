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


# --- Deaths packer ----------------------------------------------------------

DEATHS_CSV = (
    "country,reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
    "DRC,2026-05-01,1,1,national,NA,NA\n"
    # 05-02 and 05-03 absent -- daily must be 0 and cumulative CARRIED FORWARD at 1
    "DRC,2026-05-04,2,3,national,NA,NA\n"
    # duplicate date: last row WINS (not summed) -- unlike cases
    "DRC,2026-05-04,9,4,national,NA,NA\n"
    "DRC,2026-05-01,0,0,healthzone,NA,Rwampara\n"   # all-zero location is KEPT
)


def test_deaths_forward_fills_overwrites_duplicates_and_keeps_zero_locations(tmp_path):
    (tmp_path / "cumulative_positive_deaths.csv").write_text(DEATHS_CSV, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv", canon=lambda s: s)

    nat = out["national"]["national"]
    assert nat["start"] == "2026-05-01"
    assert nat["cum"] == [1, 1, 1, 4]     # carried forward across the gap; duplicate overwrote 3 -> 4
    assert nat["daily"] == [1, 0, 0, 9]   # gap days are 0; duplicate overwrote 2 -> 9
    # deaths have NO zero-total skip (that rule is cases-only, spec 6.1/6.3)
    assert out["healthzone"]["Rwampara"] == {"start": "2026-05-01", "cum": [0], "daily": [0]}


def test_deaths_duplicate_date_overwrites_not_accumulates(tmp_path):
    # If the last-row-wins overwrite were changed to accumulate (like cases),
    # this single-day series would read cum=7, daily=7 instead of 4/4.
    csv_text = (
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-05-01,3,3,national,NA,NA\n"
        "2026-05-01,4,4,national,NA,NA\n"
    )
    (tmp_path / "cumulative_positive_deaths.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv")

    assert out["national"]["national"] == {"start": "2026-05-01", "cum": [4], "daily": [4]}


def test_deaths_gap_carries_forward_not_zero_or_interpolated(tmp_path):
    # Across a multi-day gap, cum must repeat the LAST observed value on every
    # gap day -- not reset to 0 and not interpolate toward the next value.
    csv_text = (
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-05-01,5,5,national,NA,NA\n"
        # 05-02..05-04 absent
        "2026-05-05,1,20,national,NA,NA\n"
    )
    (tmp_path / "cumulative_positive_deaths.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv")

    nat = out["national"]["national"]
    assert nat["cum"] == [5, 5, 5, 5, 20]     # carried forward at 5, not 0 and not interpolated
    assert nat["daily"] == [5, 0, 0, 0, 1]


def test_deaths_no_epoch_or_leading_trim(tmp_path):
    # Cases restrict `start` to the first positive date >= 2026-01-01 (or fall
    # back to the earliest positive when none qualifies). Deaths must NOT
    # inherit that rule at all: a row dated 2025-12-31 stays as `start`
    # verbatim even though a later, in-epoch positive (2026-01-01) exists --
    # if the epoch rule were wrongly applied here, `start` would jump to
    # 2026-01-01 instead. No trimming of leading zero-days either.
    csv_text = (
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2025-12-30,0,0,national,NA,NA\n"
        "2025-12-31,2,2,national,NA,NA\n"
        "2026-01-01,3,5,national,NA,NA\n"
    )
    (tmp_path / "cumulative_positive_deaths.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv")

    assert out["national"]["national"] == {
        "start": "2025-12-30",
        "cum": [0, 2, 5],
        "daily": [0, 2, 3],
    }


def test_deaths_blank_counts_are_read_as_zero(tmp_path):
    # Mirrors _i0 behaviour already proven for cases: blank/non-numeric count
    # columns must read as 0, not raise or corrupt the packed series.
    csv_text = (
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-05-01,1,1,national,NA,NA\n"
        "2026-05-02,,,national,NA,NA\n"
        "2026-05-03,notanumber,notanumber,national,NA,NA\n"
    )
    (tmp_path / "cumulative_positive_deaths.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv")

    assert out["national"]["national"] == {
        "start": "2026-05-01",
        "cum": [1, 0, 0],
        "daily": [1, 0, 0],
    }


# --- canon scoping (health zones only) --------------------------------------

def test_canon_applies_to_health_zones_only_not_provinces(tmp_path):
    # canon maps onto canonical health-zone noms (built from the health-zone
    # geojson). Provinces are a different namespace -- several DRC provinces
    # happen to share a name with a health zone (Ituri, Tshopo, Kinshasa...),
    # so running provinces through canon too would silently rewrite a
    # province's spelling to its zone twin's if the two ever drifted. Using a
    # canon that visibly rewrites everything proves province keys are left
    # alone while health-zone keys go through it.
    csv_text = (
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-05-02,FALSE,4,province,Ituri,NA\n"
        "2026-05-02,FALSE,1,healthzone,NA,Bunia\n"
    )
    (tmp_path / "status_aggregated.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv", canon=lambda s: "REWRITTEN")

    assert sorted(out["province"]) == ["Ituri"]           # untouched by canon
    assert sorted(out["healthzone"]) == ["REWRITTEN"]     # passed through canon


# --- spatial_scale case/whitespace normalisation -----------------------------

def test_spatial_scale_is_normalised_for_case_and_whitespace(tmp_path):
    # The packer does (row.get("spatial_scale") or "").strip().lower(), but
    # every other fixture in this file already uses pre-lowercased,
    # unpadded values -- so that normalisation is otherwise never exercised.
    csv_text = (
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-05-01,1,1,National,NA,NA\n"
        "2026-05-01,2,2, HealthZone ,NA,Bunia\n"
    )
    (tmp_path / "cumulative_positive_deaths.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv")

    assert out["national"]["national"] == {"start": "2026-05-01", "cum": [1], "daily": [1]}
    assert out["healthzone"]["Bunia"] == {"start": "2026-05-01", "cum": [2], "daily": [2]}


# --- positivity packer (sparse) ---------------------------------------------

POS_CSV = (
    "country,date_of_symptom_onset_imputed,confirmed_case,total_samples_analysed_daily,"
    "spatial_scale,province,health_zone,rolling_confirmed,rolling_total,"
    "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
    "NA,2026-05-01,1,1,national,NA,NA,1,1,0.206549314377238,0.1,0.9\n"
    # 05-02 absent: must stay ABSENT, not zero-filled (spec 6.4)
    "NA,2026-05-03,0,1,national,NA,NA,0,1,0.5,0.25,0.75\n"
    # duplicate date: last row WINS
    "NA,2026-05-03,0,1,national,NA,NA,0,1,0.6,0.3,0.8\n"
    "NA,2026-05-01,1,1,healthzone,NA,Nyankunde,1,1,1,0.2,1\n"
)


def test_positivity_is_sparse_overwrites_and_keeps_full_precision(tmp_path):
    (tmp_path / "rolling_positivity.csv").write_text(POS_CSV, encoding="utf-8")

    out = ds._pack_trends_positivity(tmp_path / "rolling_positivity.csv", canon=lambda s: s)

    nat = out["national"]["national"]
    assert nat["dates"] == ["2026-05-01", "2026-05-03"]     # 05-02 NOT invented
    assert nat["mean"] == [0.206549314377238, 0.6]          # full precision; duplicate overwrote
    assert nat["lo"] == [0.1, 0.3]
    assert nat["hi"] == [0.9, 0.8]
    assert out["healthzone"]["Nyankunde"]["mean"] == [1.0]  # proportion, NOT scaled to 100 here


def test_positivity_gap_stays_absent_not_densified(tmp_path):
    # A multi-day gap must leave the missing dates out of `dates` entirely --
    # unlike deaths (carry-forward) and cases (zero-fill), positivity never
    # invents an entry for a day the CSV doesn't have a row for.
    csv_text = (
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-05-01,1,national,NA,NA,0.1,0.05,0.15\n"
        # 05-02 through 05-09 absent -- an 8-day gap
        "2026-05-10,1,national,NA,NA,0.2,0.1,0.3\n"
    )
    (tmp_path / "rolling_positivity.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_positivity(tmp_path / "rolling_positivity.csv")

    nat = out["national"]["national"]
    assert nat["dates"] == ["2026-05-01", "2026-05-10"]
    assert len(nat["dates"]) == 2
    assert nat["mean"] == [0.1, 0.2]


def test_positivity_mean_survives_at_full_precision(tmp_path):
    # A value that would visibly change under any rounding (e.g. round(x, 4)
    # or round(x, 6)) must come back byte-identical to the source string.
    csv_text = (
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-05-01,1,national,NA,NA,0.123456789012345,0.01,0.99\n"
    )
    (tmp_path / "rolling_positivity.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_positivity(tmp_path / "rolling_positivity.csv")

    assert out["national"]["national"]["mean"] == [0.123456789012345]


def test_positivity_unparseable_mean_is_skipped_entirely(tmp_path):
    # A row whose daily_positivity_mean can't be parsed must be dropped from
    # the series -- not turned into a None entry, and not turned into 0.
    csv_text = (
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-05-01,1,national,NA,NA,0.4,0.2,0.6\n"
        "2026-05-02,1,national,NA,NA,NA,0.2,0.6\n"
        "2026-05-03,1,national,NA,NA,notanumber,0.2,0.6\n"
        "2026-05-04,1,national,NA,NA,0.5,0.2,0.6\n"
    )
    (tmp_path / "rolling_positivity.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_positivity(tmp_path / "rolling_positivity.csv")

    nat = out["national"]["national"]
    assert nat["dates"] == ["2026-05-01", "2026-05-04"]
    assert nat["mean"] == [0.4, 0.5]


def test_positivity_lo_hi_may_be_none_while_mean_present(tmp_path):
    # lo/hi are allowed to be missing independently of mean. The packer must
    # not crash, and must preserve None positionally so lo/hi/dates/mean
    # stay index-aligned.
    csv_text = (
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-05-01,1,national,NA,NA,0.4,,0.6\n"
        "2026-05-02,1,national,NA,NA,0.5,0.2,\n"
    )
    (tmp_path / "rolling_positivity.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_positivity(tmp_path / "rolling_positivity.csv")

    nat = out["national"]["national"]
    assert nat["dates"] == ["2026-05-01", "2026-05-02"]
    assert nat["mean"] == [0.4, 0.5]
    assert nat["lo"] == [None, 0.2]
    assert nat["hi"] == [0.6, None]


def test_positivity_no_epoch_or_leading_trim(tmp_path):
    # Cases restrict `start` to the first positive date >= 2026-01-01. Deaths
    # already prove that rule doesn't apply there; positivity must ALSO be
    # untouched by it -- and it has no `start`/trim concept at all, so a
    # pre-epoch date must simply be the first entry in `dates`, alongside a
    # genuine in-epoch date so the cases-packer's fallback-to-earliest-positive
    # behaviour can't accidentally make this test pass with a wrongly-applied
    # trim in place.
    csv_text = (
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2025-12-31,1,national,NA,NA,0.3,0.1,0.5\n"
        "2026-01-01,1,national,NA,NA,0.4,0.1,0.5\n"
    )
    (tmp_path / "rolling_positivity.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_positivity(tmp_path / "rolling_positivity.csv")

    nat = out["national"]["national"]
    assert nat["dates"] == ["2025-12-31", "2026-01-01"]
    assert nat["mean"] == [0.3, 0.4]


LAB_CSV = (
    "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
    "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
    "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
    "INRBK,INRB Kinshasa,NA,NA,2026-05-14,2026-05-14,4,6,4,6,0.666,0.3,0.9\n"
    "INRBK,INRB Kinshasa,NA,NA,2026-05-16,2026-05-14,1,1,5,7,0.714,0.36,0.92\n"
    "LBARU,Aru,Aru,Ituri,2026-06-01,2026-06-01,1,2,1,2,0.5,0.2,0.8\n"
)


def test_labs_pack_per_lab_with_a_shared_global_x_range(tmp_path):
    (tmp_path / "lab_positivity_aggregated.csv").write_text(LAB_CSV, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    # Shared across ALL labs so they stay comparable (spec 6.5), not per-lab.
    assert lab_x == {"start": "2026-05-14", "end": "2026-06-01"}

    assert [l["code"] for l in labs] == ["INRBK", "LBARU"]      # sorted by lab_name
    inrbk = labs[0]
    assert inrbk["label"] == "INRB Kinshasa"
    assert inrbk["id"] == "lab_inrbk"
    assert inrbk["earliest"] == "2026-05-14"
    assert inrbk["dates"] == ["2026-05-14", "2026-05-16"]       # sparse, not zero-filled
    assert inrbk["n"] == [6, 1]
    assert inrbk["max_total"] == 6                              # per-lab, drives the 2nd axis
    assert inrbk["health_zone"] is None and inrbk["province"] is None
    assert labs[1]["health_zone"] == "Aru" and labs[1]["province"] == "Ituri"


def test_labs_x_range_is_global_union_not_per_lab(tmp_path):
    # Three labs with clearly non-overlapping spans. A per-lab implementation
    # would give each lab its own narrow range; lab_x must be the union across
    # ALL of them (spec 6.5), because it's what makes the per-lab charts
    # visually comparable.
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "AAA,Lab A,NA,NA,2026-02-01,2026-02-01,1,1,1,1,0.5,0.2,0.8\n"
        "BBB,Lab B,NA,NA,2026-05-01,2026-05-01,1,1,1,1,0.5,0.2,0.8\n"
        "CCC,Lab C,NA,NA,2026-08-01,2026-08-01,1,1,1,1,0.5,0.2,0.8\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert lab_x == {"start": "2026-02-01", "end": "2026-08-01"}


def test_labs_max_total_is_per_lab_not_global(tmp_path):
    # Two labs with very different sample counts. Each lab's max_total must
    # reflect only its own counts -- a globalised implementation would give
    # both labs the same (larger) max_total.
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "SMALL,Small Lab,NA,NA,2026-05-01,2026-05-01,1,3,1,3,0.3,0.1,0.5\n"
        "SMALL,Small Lab,NA,NA,2026-05-02,2026-05-01,1,2,2,5,0.4,0.2,0.6\n"
        "BIG,Big Lab,NA,NA,2026-05-01,2026-05-01,1,50,1,50,0.2,0.1,0.3\n"
        "BIG,Big Lab,NA,NA,2026-05-02,2026-05-01,1,80,2,130,0.3,0.2,0.4\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    by_code = {l["code"]: l for l in labs}
    assert by_code["SMALL"]["max_total"] == 3
    assert by_code["BIG"]["max_total"] == 80


def test_labs_max_total_floors_at_one(tmp_path):
    # All-zero counts must not leave max_total at 0 -- that would divide by
    # zero when the positivity overlay is scaled onto the samples axis.
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "ZERO,Zero Lab,NA,NA,2026-05-01,2026-05-01,0,0,0,0,0.0,0.0,0.0\n"
        "ZERO,Zero Lab,NA,NA,2026-05-02,2026-05-01,0,0,0,0,0.0,0.0,0.0\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["max_total"] == 1


def test_labs_x_start_falls_back_to_first_analysis_date_when_earliest_sample_blank(tmp_path):
    # When earliest_analysed_sample is blank/invalid, the packer must fall
    # back to the lab's own first analysis date for the purposes of the
    # global x-range, and the stored `earliest` field itself must be None
    # (not silently substituted).
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "NOEARLY,No Early Lab,NA,NA,2026-07-10,NA,1,4,1,4,0.4,0.2,0.6\n"
        "NOEARLY,No Early Lab,NA,NA,2026-07-12,NA,1,2,2,6,0.5,0.2,0.6\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["earliest"] is None
    assert lab_x == {"start": "2026-07-10", "end": "2026-07-12"}


def test_labs_label_falls_back_to_lab_name_when_long_name_blank(tmp_path):
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "NOLONG,,NA,NA,2026-05-01,2026-05-01,1,3,1,3,0.3,0.1,0.5\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["label"] == "NOLONG"


def test_labs_dates_stay_sparse_across_a_gap(tmp_path):
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "GAPPY,Gappy Lab,NA,NA,2026-05-01,2026-05-01,1,3,1,3,0.3,0.1,0.5\n"
        "GAPPY,Gappy Lab,NA,NA,2026-05-10,2026-05-01,1,2,2,5,0.4,0.2,0.6\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["dates"] == ["2026-05-01", "2026-05-10"]
    assert labs[0]["n"] == [3, 2]


def test_labs_x_start_uses_earliest_sample_when_it_predates_first_analysis(tmp_path):
    # earliest_analysed_sample can be well before the lab's first analysis
    # row (samples collected before they were processed). lab_x["start"]
    # must use that earlier date, not just the first row in `dates`.
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "EARLY,Early Lab,NA,NA,2026-06-15,2026-05-01,1,4,1,4,0.4,0.2,0.6\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["earliest"] == "2026-05-01"
    assert labs[0]["dates"] == ["2026-06-15"]
    assert lab_x == {"start": "2026-05-01", "end": "2026-06-15"}


def test_labs_x_is_none_when_no_lab_has_a_usable_mean(tmp_path):
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "BAD,Bad Lab,NA,NA,2026-05-01,2026-05-01,1,3,1,3,notanumber,0.1,0.5\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, lab_x = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs == []
    assert lab_x is None


# --- shared _trends_scale_loc coverage (per-packer canon + unknown scale) ---

def test_deaths_canon_applies_to_health_zones_only_not_provinces(tmp_path):
    # Same proof as the cases-side test, but for _pack_trends_deaths. A
    # reviewer previously mutated only the deaths packer's canon line and the
    # full suite stayed green because nothing exercised it per-packer.
    csv_text = (
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-05-02,1,4,province,Ituri,NA\n"
        "2026-05-02,1,1,healthzone,NA,Bunia\n"
    )
    (tmp_path / "cumulative_positive_deaths.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv", canon=lambda s: "REWRITTEN")

    assert sorted(out["province"]) == ["Ituri"]           # untouched by canon
    assert sorted(out["healthzone"]) == ["REWRITTEN"]     # passed through canon


def test_positivity_canon_applies_to_health_zones_only_not_provinces(tmp_path):
    # Same proof as the cases-side test, but for _pack_trends_positivity.
    csv_text = (
        "date_of_symptom_onset_imputed,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-05-02,province,Ituri,NA,0.4,0.2,0.6\n"
        "2026-05-02,healthzone,NA,Bunia,0.5,0.2,0.6\n"
    )
    (tmp_path / "rolling_positivity.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_positivity(tmp_path / "rolling_positivity.csv", canon=lambda s: "REWRITTEN")

    assert sorted(out["province"]) == ["Ituri"]           # untouched by canon
    assert sorted(out["healthzone"]) == ["REWRITTEN"]     # passed through canon


def test_unrecognised_spatial_scale_is_dropped(tmp_path):
    # A spatial_scale value outside {national, province, healthzone} (e.g. a
    # future "district" level) must be silently dropped via the
    # _UNKNOWN_SCALE sentinel, not raise or land in one of the three buckets.
    csv_text = (
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-05-02,FALSE,4,district,NA,NA\n"
        "2026-05-02,FALSE,1,national,NA,NA\n"
    )
    (tmp_path / "status_aggregated.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv")

    assert out["province"] == {}
    assert out["healthzone"] == {}
    assert out["national"]["national"]["obs"] == [1]      # only the recognised row counted


def test_deaths_blank_counts_are_read_as_zero_for_non_national_location(tmp_path):
    # test_deaths_blank_counts_are_read_as_zero only exercises the national
    # scale; blank/non-numeric counts must read as 0 for a province/
    # health-zone location too, not just national.
    csv_text = (
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-05-01,1,1,healthzone,NA,Bunia\n"
        "2026-05-02,,,healthzone,NA,Bunia\n"
        "2026-05-03,notanumber,notanumber,healthzone,NA,Bunia\n"
    )
    (tmp_path / "cumulative_positive_deaths.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_deaths(tmp_path / "cumulative_positive_deaths.csv")

    assert out["healthzone"]["Bunia"] == {
        "start": "2026-05-01",
        "cum": [1, 0, 0],
        "daily": [1, 0, 0],
    }


# --- load_trends_series assembler -------------------------------------------

import json


def _seed_snapshot(tmp_path):
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")
    (snap / "cumulative_positive_deaths.csv").write_text(DEATHS_CSV, encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(POS_CSV, encoding="utf-8")
    (snap / "lab_positivity_aggregated.csv").write_text(LAB_CSV, encoding="utf-8")
    # A newer decoy dir the manifest does NOT point at -- must be ignored.
    decoy = out / "2026-05-11"
    decoy.mkdir(parents=True)
    (decoy / "status_aggregated.csv").write_text(
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-05-01,FALSE,999,national,NA,NA\n", encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps({"date": "2026-05-10", "incomplete_styling": {"days": 5}}), encoding="utf-8")
    return out


def test_load_trends_series_shares_x_limits_and_freezes_the_cutoff(tmp_path, monkeypatch):
    out = _seed_snapshot(tmp_path)
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", out)

    res = ds.load_trends_series(known_noms={"Bunia"})

    assert res["asof"] == "2026-05-10"              # manifest snapshot, not the newer decoy
    assert res["cases"]["national"]["obs"] != [999]  # decoy really was ignored
    assert res["incomplete_days"] == 5              # read from the manifest, not hardcoded 7
    assert res["incomplete_from"] == "2026-05-05"   # snapshot - 5 days, frozen at BUILD time

    # National x-limits span cases U deaths U positivity -- spec 6.6.
    assert res["x_limits"]["national"]["national"] == {"start": "2026-05-01", "end": "2026-05-05"}
    assert res["lab_x"] == {"start": "2026-05-14", "end": "2026-06-01"}


def test_load_trends_series_returns_none_when_the_snapshot_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", tmp_path / "nope")
    assert ds.load_trends_series() is None


# --- discriminating tests: incomplete_days defaulting ------------------------

def test_load_trends_series_incomplete_days_defaults_to_seven_without_manifest_key(tmp_path):
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"date": "2026-05-10"}), encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert res["incomplete_days"] == 7
    assert res["incomplete_from"] == "2026-05-03"


def test_load_trends_series_incomplete_days_defaults_to_seven_for_non_numeric_value(tmp_path):
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps({"date": "2026-05-10", "incomplete_styling": {"days": "not-a-number"}}),
        encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert res["incomplete_days"] == 7


def test_load_trends_series_incomplete_days_defaults_to_seven_for_non_positive_value(tmp_path):
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps({"date": "2026-05-10", "incomplete_styling": {"days": 0}}),
        encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert res["incomplete_days"] == 7


# --- discriminating test: cutoff is frozen from the snapshot date, not wall clock --

def test_load_trends_series_incomplete_from_uses_snapshot_date_not_wall_clock(tmp_path):
    # A far-future snapshot date well past this conversation's "today". If the
    # implementation ever switched to date.today() this would still coincidentally
    # look plausible near the real build date, but would NOT match this exact
    # assertion -- and it must keep passing regardless of what day this test runs.
    out = tmp_path / "outputs"
    snap = out / "2030-01-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps({"date": "2030-01-10", "incomplete_styling": {"days": 3}}),
        encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert res["asof"] == "2030-01-10"
    assert res["incomplete_from"] == "2030-01-07"


# --- discriminating tests: x-limits union ------------------------------------

def test_load_trends_series_x_limits_union_all_three_families(tmp_path):
    # Each family contributes a different extreme of the span: cases the
    # earliest date, positivity the latest. A mutation that computed x_limits
    # from cases alone (or deaths alone) would report a narrower span.
    out = tmp_path / "outputs"
    snap = out / "2026-06-01"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-03-01,FALSE,1,national,NA,NA\n", encoding="utf-8")
    (snap / "cumulative_positive_deaths.csv").write_text(
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-03-10,1,1,national,NA,NA\n", encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-03-20,1,national,NA,NA,0.5,0.2,0.8\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"date": "2026-06-01"}), encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert res["x_limits"]["national"]["national"] == {"start": "2026-03-01", "end": "2026-03-20"}


def test_load_trends_series_x_limits_include_a_location_present_in_only_one_family(tmp_path):
    # A health zone with positivity data but no cases/deaths rows at all must
    # still get an x-limits entry -- an implementation that intersected the
    # three families (or unioned only cases/deaths keys) would drop it.
    out = tmp_path / "outputs"
    snap = out / "2026-06-01"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-03-01,FALSE,1,national,NA,NA\n", encoding="utf-8")
    (snap / "cumulative_positive_deaths.csv").write_text(
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-03-01,1,1,national,NA,NA\n", encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-04-05,1,healthzone,NA,OnlyPos,0.4,0.2,0.6\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"date": "2026-06-01"}), encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert "OnlyPos" not in res["cases"]["health_zones"]
    assert "OnlyPos" not in res["deaths"]["health_zones"]
    assert res["x_limits"]["healthzone"]["OnlyPos"] == {"start": "2026-04-05", "end": "2026-04-05"}


def test_load_trends_series_x_limits_deaths_span_sets_both_extremes(tmp_path):
    # Deaths' own start/end must feed lo/hi, not just its location key. Cases
    # and positivity both sit STRICTLY INSIDE deaths' range here, so if the
    # deaths span were dropped from the lo/hi accumulation (while deaths stayed
    # in the location-membership union), the result would narrow to the cases/
    # positivity range instead of spanning out to deaths' own dates.
    out = tmp_path / "outputs"
    snap = out / "2026-06-01"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-03-05,FALSE,1,national,NA,NA\n", encoding="utf-8")
    (snap / "cumulative_positive_deaths.csv").write_text(
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-02-01,1,1,national,NA,NA\n"
        "2026-04-01,1,2,national,NA,NA\n", encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-03-10,1,national,NA,NA,0.4,0.2,0.6\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"date": "2026-06-01"}), encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    # deaths' 2026-02-01 start and 2026-04-01 end lie OUTSIDE both the cases
    # (2026-03-05) and positivity (2026-03-10) dates on either side.
    assert res["x_limits"]["national"]["national"] == {"start": "2026-02-01", "end": "2026-04-01"}


def test_load_trends_series_x_limits_include_a_location_present_only_in_deaths(tmp_path):
    # A health zone with deaths data but no cases/positivity rows at all must
    # still get an x-limits entry -- mirrors the positivity-only coverage
    # above, for the deaths family.
    out = tmp_path / "outputs"
    snap = out / "2026-06-01"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-03-01,FALSE,1,national,NA,NA\n", encoding="utf-8")
    (snap / "cumulative_positive_deaths.csv").write_text(
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n"
        "2026-03-01,1,1,national,NA,NA\n"
        "2026-04-05,1,1,healthzone,NA,OnlyDeaths\n", encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n"
        "2026-03-01,1,national,NA,NA,0.4,0.2,0.6\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"date": "2026-06-01"}), encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert "OnlyDeaths" not in res["cases"]["health_zones"]
    assert "OnlyDeaths" not in res["positivity"]["health_zones"]
    assert res["x_limits"]["healthzone"]["OnlyDeaths"] == {"start": "2026-04-05", "end": "2026-04-05"}


# --- discriminating test: missing CSVs are tolerated -------------------------

def test_load_trends_series_tolerates_missing_csvs(tmp_path):
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(CASES_CSV, encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"date": "2026-05-10"}), encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert res is not None
    assert res["cases"]["national"] is not None
    assert res["deaths"] == {"national": None, "provinces": {}, "health_zones": {}}
    assert res["positivity"] == {"national": None, "provinces": {}, "health_zones": {}}
    assert res["labs"] == []
    assert res["lab_x"] is None


# --- discriminating test: all four families empty guards return None --------

def test_load_trends_series_returns_none_when_snapshot_dir_has_none_of_the_four_csvs(tmp_path):
    # The snapshot DIRECTORY genuinely exists and the manifest resolves it --
    # unlike test_..._returns_none_when_the_snapshot_is_absent, which exercises
    # the EARLIER `snap is None` branch for a missing directory. This exercises
    # the separate `if not cases and not deaths and not positivity and not
    # labs: return None` guard once a snapshot dir is found but is empty of
    # every one of the four source CSVs.
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({"date": "2026-05-10"}), encoding="utf-8")

    assert ds.load_trends_series(outputs_dir=out) is None


def test_load_trends_series_is_not_none_when_csvs_are_present_but_header_only(tmp_path):
    # Distinct from the case above: every CSV file EXISTS but has zero data
    # rows. Each packer still returns its scale skeleton ({"national": {},
    # "province": {}, "healthzone": {}}), which is truthy even though every
    # sub-dict is empty -- so the "all four families empty" guard does NOT
    # fire here, and the result comes back usable (all slices empty) rather
    # than None. This pins that distinction rather than leaving it accidental.
    out = tmp_path / "outputs"
    snap = out / "2026-05-10"
    snap.mkdir(parents=True)
    (snap / "status_aggregated.csv").write_text(
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n", encoding="utf-8")
    (snap / "cumulative_positive_deaths.csv").write_text(
        "reporting_date,daily_deaths,cumulative_deaths,spatial_scale,province,health_zone\n",
        encoding="utf-8")
    (snap / "rolling_positivity.csv").write_text(
        "date_of_symptom_onset_imputed,confirmed_case,spatial_scale,province,health_zone,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n", encoding="utf-8")
    (snap / "lab_positivity_aggregated.csv").write_text(
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,earliest_analysed_sample,"
        "confirmed_case,total_samples_analysed_daily,rolling_confirmed,rolling_total,"
        "daily_positivity_mean,daily_positivity_lower,daily_positivity_upper\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"date": "2026-05-10"}), encoding="utf-8")

    res = ds.load_trends_series(outputs_dir=out)

    assert res is not None
    assert res["cases"] == {"national": None, "provinces": {}, "health_zones": {}}
    assert res["deaths"] == {"national": None, "provinces": {}, "health_zones": {}}
    assert res["positivity"] == {"national": None, "provinces": {}, "health_zones": {}}
    assert res["labs"] == []
    assert res["lab_x"] is None
    assert res["x_limits"] == {"national": {}, "province": {}, "healthzone": {}}


# --- mojibake repair -------------------------------------------------------
# Upstream has shipped a lab whose name's UTF-8 bytes were decoded with the
# wrong codec before being written back: "Laboratoire Provincial de Sant\u221a\u00a9
# Publique de Bunia". Observed on BDBV2026-Processed_Sensitive_Data's
# dev_matching_dashboard branch (snapshot 2026-07-29), which the PR-preview
# build reads; main was clean at the time. lab_name_long is the only free-text
# field the Trends tab renders from that source.

def test_mojibake_repair_fixes_the_real_upstream_lab_name():
    damaged = "Laboratoire Provincial de Sant\u221a\u00a9 Publique de Bunia"
    assert ds._fix_mojibake(damaged) == "Laboratoire Provincial de Sant\u00e9 Publique de Bunia"


def test_mojibake_repair_handles_latin1_damage_not_just_macroman():
    # MacRoman and Latin-1 damage are bijective in BOTH directions, so trying
    # codecs in order and round-trip-checking "repairs" this one with MacRoman
    # into combining-mark soup that round-trips perfectly. The codec must be
    # chosen by the damage signature.
    assert ds._fix_mojibake("Sant\u00c3\u00a9") == "Sant\u00e9"


def test_mojibake_repair_leaves_clean_names_untouched():
    for name in ("Laboratoire de Bunia", "Laboratoire de Sant\u00e9", "Kinshasa", "", None):
        assert ds._fix_mojibake(name) == name


def test_labs_packer_repairs_the_damaged_name(tmp_path):
    csv_text = (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,"
        "earliest_analysed_sample,confirmed_case,total_samples_analysed_daily,"
        "rolling_confirmed,rolling_total,daily_positivity_mean,"
        "daily_positivity_lower,daily_positivity_upper\n"
        "LPSPBN,Laboratoire Provincial de Sant\u221a\u00a9 Publique de Bunia,Bunia,Ituri,"
        "2026-05-14,2026-05-14,1,2,1,2,0.5,0.2,0.8\n"
    )
    (tmp_path / "lab_positivity_aggregated.csv").write_text(csv_text, encoding="utf-8")

    labs, _ = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["label"] == "Laboratoire Provincial de Sant\u00e9 Publique de Bunia"
    assert "\u221a" not in labs[0]["label"]


def test_damaged_location_names_are_repaired_before_canon(tmp_path):
    # A damaged zone name would match no canonical nom, so it would survive as
    # its own broken entry in the scope dropdown.
    csv_text = (
        "date_of_symptom_onset_imputed,onset_date_was_imputed,confirmed_case,"
        "spatial_scale,province,health_zone\n"
        "2026-05-02,FALSE,4,healthzone,NA,Sant\u221a\u00a9ville\n"
    )
    (tmp_path / "status_aggregated.csv").write_text(csv_text, encoding="utf-8")

    out = ds._pack_trends_cases(tmp_path / "status_aggregated.csv")

    assert list(out["healthzone"]) == ["Sant\u00e9ville"]


# --- literal "NA" in free-text lab fields ----------------------------------
# These CSVs come from R, which writes a missing value as the two characters
# NA. Read back in Python that is a truthy string, so it beats an `or`
# fallback: a lab with no long name was titled "NA" instead of its code.
# Observed on main (LPST, 1 of 20 labs) and dev_matching_dashboard (LBMAM and
# 9 others, 10 of 16). The generator's read.csv yields a real NA, so its SVGs
# correctly title those charts "LPST" / "LBMAM".

def _lab_csv(long_name, health_zone, province):
    return (
        "lab_name,lab_name_long,health_zone,province,lab_analysis_date,"
        "earliest_analysed_sample,confirmed_case,total_samples_analysed_daily,"
        "rolling_confirmed,rolling_total,daily_positivity_mean,"
        "daily_positivity_lower,daily_positivity_upper\n"
        "LBMAM,%s,%s,%s,2026-05-14,2026-05-14,1,2,1,2,0.5,0.2,0.8\n"
        % (long_name, health_zone, province)
    )


def test_lab_named_NA_falls_back_to_its_code(tmp_path):
    (tmp_path / "lab_positivity_aggregated.csv").write_text(
        _lab_csv("NA", "Mambasa", "Ituri"), encoding="utf-8")

    labs, _ = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["label"] == "LBMAM"          # not "NA"
    assert labs[0]["health_zone"] == "Mambasa"  # a real value is still kept


def test_lab_with_NA_location_fields_reports_none(tmp_path):
    (tmp_path / "lab_positivity_aggregated.csv").write_text(
        _lab_csv("NA", "NA", "NA"), encoding="utf-8")

    labs, _ = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["label"] == "LBMAM"
    assert labs[0]["health_zone"] is None
    assert labs[0]["province"] is None


def test_lab_long_name_is_used_when_present(tmp_path):
    (tmp_path / "lab_positivity_aggregated.csv").write_text(
        _lab_csv("Laboratoire Mambasa", "Mambasa", "Ituri"), encoding="utf-8")

    labs, _ = ds._pack_trends_labs(tmp_path / "lab_positivity_aggregated.csv")

    assert labs[0]["label"] == "Laboratoire Mambasa"


def test_or_none_treats_NA_and_blank_as_absent():
    for absent in ("NA", "na", " NA ", "", "   ", None):
        assert ds._or_none(absent) is None
    for present in ("Mambasa", "Ituri", "Nia Nia", "0"):
        assert ds._or_none(present) == present.strip()
