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
