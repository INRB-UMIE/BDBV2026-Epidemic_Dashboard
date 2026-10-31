from __future__ import annotations

import importlib
import json
from pathlib import Path

ds = importlib.import_module("common.data_sources")

RISK_CSV = (
    "health_zone,province,horizon,was_active_before,p_case_invasion,rr_nat\n"
    "Rethy,Ituri,1,FALSE,0.039,44.7\n"
)


def _make_sir_repo(root: Path, date: str = "2026-10-28", latest: dict | None = None) -> Path:
    run = root / "outputs" / date
    run.mkdir(parents=True)
    (run / "bayes_risk_scores_all_zones.csv").write_text(RISK_CSV)
    (run / "run_info.json").write_text(json.dumps({"training_window_end": date}))
    (run / "harmonised_confirmed_cases.csv").write_text(
        "health_zone,cumulative_confirmed_cases\nRethy,7\n")
    if latest is None:
        latest = {
            "latest_analysis_date": date,
            "path": f"outputs/{date}",
            "risk_scores": f"outputs/{date}/bayes_risk_scores_all_zones.csv",
            "run_info": f"outputs/{date}/run_info.json",
        }
    (root / "outputs" / "latest.json").write_text(json.dumps(latest))
    return root


def _isolate(monkeypatch, tmp_path, sir_root: Path):
    monkeypatch.setattr(ds, "SPATIAL_INVASION_RISK_DIR", sir_root)
    monkeypatch.setattr(ds, "DASHBOARD_PLOTS_DIR", tmp_path / "no-processed-repo")


def test_resolves_run_from_latest_json(tmp_path, monkeypatch):
    root = _make_sir_repo(tmp_path / "sir")
    # an older folder that must NOT be picked
    _old = root / "outputs" / "2026-09-20"
    _old.mkdir()
    (_old / "bayes_risk_scores_all_zones.csv").write_text(RISK_CSV)
    _isolate(monkeypatch, tmp_path, root)
    risk, info = ds._latest_invasion_risk_run()
    assert risk.parent.name == "2026-10-28"
    assert info is not None and info.name == "run_info.json"


def test_latest_json_with_only_path(tmp_path, monkeypatch):
    root = _make_sir_repo(tmp_path / "sir", latest={"path": "outputs/2026-10-28"})
    _isolate(monkeypatch, tmp_path, root)
    risk, info = ds._latest_invasion_risk_run()
    assert risk.name == "bayes_risk_scores_all_zones.csv"
    assert info is not None


def test_returns_none_when_no_sources(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path, tmp_path / "missing")
    assert ds._latest_invasion_risk_run() is None


def test_harmonised_cases_follow_latest_json(tmp_path, monkeypatch):
    root = _make_sir_repo(tmp_path / "sir")
    _isolate(monkeypatch, tmp_path, root)
    assert ds.load_harmonised_confirmed_cases({"Rethy"}) == {"Rethy": 7}


def test_loader_backfills_cutoff_from_run_info(tmp_path, monkeypatch):
    root = _make_sir_repo(tmp_path / "sir")
    _isolate(monkeypatch, tmp_path, root)
    out = ds.load_invasion_risk_estimates()
    assert out is not None
    assert out["cutoff_date"] == "2026-10-28"
    assert "Rethy" in out["zones"]
