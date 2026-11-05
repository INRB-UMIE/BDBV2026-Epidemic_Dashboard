from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ds = importlib.import_module("common.data_sources")


def _make_key_outputs(tmp_path: Path, harmonised_csv: str | None) -> Path:
    ko = tmp_path / "2026-08-03" / "spatiotemporal" / "key_outputs"
    ko.mkdir(parents=True)
    (ko / "bayes_risk_scores_all_zones.csv").write_text("health_zone\nRethy\n")
    if harmonised_csv is not None:
        (ko / "harmonised_confirmed_cases.csv").write_text(harmonised_csv)
    return tmp_path


def test_loader_reads_counts_and_normalises_names(tmp_path, monkeypatch):
    csv = (
        "health_zone,cumulative_confirmed_cases\n"
        "Rethy,5\n"
        "Nsona-Pangu,3\n"   # needs _NAME_TO_NOM -> "Nsona Mpangu"
    )
    out = _make_key_outputs(tmp_path, csv)
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", out)
    monkeypatch.setattr(ds, "SPATIAL_INVASION_RISK_DIR", tmp_path / "no-sir-repo")
    result = ds.load_harmonised_confirmed_cases({"Rethy", "Nsona Mpangu"})
    assert result == {"Rethy": 5, "Nsona Mpangu": 3}


def test_loader_returns_empty_when_absent(tmp_path, monkeypatch):
    out = _make_key_outputs(tmp_path, None)
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", out)
    monkeypatch.setattr(ds, "SPATIAL_INVASION_RISK_DIR", tmp_path / "no-sir-repo")
    assert ds.load_harmonised_confirmed_cases({"Rethy"}) == {}


def test_write_effective_defaults_zero_and_takes_max():
    zone_data = {
        "Rethy": {"confirmed_cases": None},        # sitrep null
        "Bunia": {"confirmed_cases": 900},         # sitrep present
        "Ghost": {"confirmed_cases": None},        # in neither
    }
    harmonised = {"Rethy": 5, "Bunia": 10}         # Bunia harmonised < sitrep
    ds.write_effective_confirmed_cases(zone_data, harmonised)
    assert zone_data["Rethy"]["effective_confirmed_cases"] == 5   # harmonised wins
    assert zone_data["Bunia"]["effective_confirmed_cases"] == 900  # sitrep (fresher) wins
    assert zone_data["Ghost"]["effective_confirmed_cases"] == 0    # default 0, no crash


def test_markers_use_effective_and_keep_sitrep_suspected():
    zone_data = {
        "Rethy": {"confirmed_cases": None, "suspected_cases": 0,
                  "confirmed_deaths": 2, "effective_confirmed_cases": 5},
        "Empty": {"confirmed_cases": None, "suspected_cases": 0,
                  "confirmed_deaths": 0, "effective_confirmed_cases": 0},
    }
    centroids = {"Rethy": (30.5, 2.0), "Empty": (25.0, 1.0)}
    markers = ds.build_active_case_markers(zone_data, centroids)
    by_nom = {m["nom"]: m for m in markers}
    assert "Rethy" in by_nom              # harmonised-only zone now gets a marker
    assert by_nom["Rethy"]["confirmed"] == 5
    assert by_nom["Rethy"]["suspected"] == 0   # sitrep field still emitted
    assert by_nom["Rethy"]["confirmed_deaths"] == 2
    assert "Empty" not in by_nom          # effective 0 -> no marker


def test_coverage_assertion_flags_active_zone_without_count():
    invasion_risk = {"zones": {
        "Rethy": {"was_active_before": True},
        "Aba":   {"was_active_before": False},
    }}
    harmonised = {"Rethy": 5}   # artifact present
    ok = {"Rethy": {"effective_confirmed_cases": 5},
          "Aba":   {"effective_confirmed_cases": 0}}
    ds.assert_harmonised_coverage(invasion_risk, ok, harmonised)     # no raise

    bad = {"Rethy": {"effective_confirmed_cases": 0},     # active but 0 -> invariant broken
           "Aba":   {"effective_confirmed_cases": 0}}
    with pytest.raises(ValueError, match="Rethy"):
        ds.assert_harmonised_coverage(invasion_risk, bad, harmonised)


def test_coverage_assertion_normalises_zone_name_before_lookup():
    # invasion zones keyed by raw health_zone; effective lives on the nom key.
    invasion_risk = {"zones": {"Nsona-Pangu": {"was_active_before": True}}}
    zone_data = {"Nsona Mpangu": {"effective_confirmed_cases": 7}}  # nom key, covered
    ds.assert_harmonised_coverage(invasion_risk, zone_data, {"Nsona Mpangu": 7})  # must NOT raise


def test_coverage_assertion_warns_not_raises_when_artifact_absent(capsys):
    # Pre-Part-C interim: no harmonised artifact -> warn, do not break the build.
    invasion_risk = {"zones": {"Rethy": {"was_active_before": True}}}
    bad = {"Rethy": {"effective_confirmed_cases": 0}}
    ds.assert_harmonised_coverage(invasion_risk, bad, {})   # must NOT raise
    out = capsys.readouterr().out
    assert "Rethy" in out


def test_download_csv_masked_for_effective_active(tmp_path, monkeypatch):
    ko = tmp_path / "2026-08-03" / "spatiotemporal" / "key_outputs"
    ko.mkdir(parents=True)
    (ko / "bayes_risk_scores_all_zones.csv").write_text(
        "health_zone,horizon,was_active_before,p_case_invasion\n"
        "Rethy,1,False,0.34\n"
        "Rethy,2,False,0.53\n"
        "Aba,1,False,0.10\n"
    )
    (ko / "run_info.json").write_text('{"training_window_end": "2026-07-20"}')
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", tmp_path)
    result = ds.load_invasion_risk_estimates(effective_active_noms={"Rethy"})
    dl = result["download_csv"]
    # every Rethy row (all horizons) has p_case_invasion blanked; Aba untouched
    assert ",0.34" not in dl and ",0.53" not in dl
    # pandas to_csv drops the trailing zero (0.10 -> 0.1) on any read/write
    # round-trip, independent of masking -- assert on the value it actually
    # serialises to.
    assert "0.1" in dl
