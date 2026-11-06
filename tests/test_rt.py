"""Rt estimates loader (common/rt.py) and its page wiring."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "Scripts"))

from common.chrome import _PAGE_SCOPED_PAYLOAD_KEYS  # noqa: E402
from common.rt import latest_rt_file, load_rt_estimates  # noqa: E402

HEADER = "area,area_type,date,rt_mean,rt_lower_95,rt_upper_95\n"


def _write(dirpath: Path, name: str, body: str) -> Path:
    p = dirpath / name
    p.write_text(HEADER + body, encoding="utf-8")
    return p


def test_latest_file_is_chosen_by_run_date_in_name(tmp_path):
    _write(tmp_path, "inrb_dashboard_Rt_data_20261102.csv", "")
    _write(tmp_path, "inrb_dashboard_Rt_data_20261020.csv", "")
    _write(tmp_path, "inrb_dashboard_Rt_data_notadate.csv", "")
    assert latest_rt_file(tmp_path).name == "inrb_dashboard_Rt_data_20261102.csv"


def test_load_packs_national_and_provinces_sorted_by_date(tmp_path):
    _write(tmp_path, "inrb_dashboard_Rt_data_20261102.csv",
           "National,national,2026-10-02,1.2,1.0,1.4\n"
           "National,national,2026-10-01,1.1,0.9,1.3\n"
           "Ituri,province,2026-10-01,0.8,0.6,1.0\n"
           "Ituri,province,2026-10-01,0.85,0.65,1.05\n"     # duplicate: last wins
           "Nowhere,district,2026-10-01,9,9,9\n")            # unknown type ignored
    rt = load_rt_estimates(tmp_path)
    assert rt["run_date"] == "2026-11-02"
    assert rt["national"]["dates"] == ["2026-10-01", "2026-10-02"]
    assert rt["national"]["mean"] == [1.1, 1.2]
    assert rt["provinces"] == {"Ituri": {"dates": ["2026-10-01"], "mean": [0.85], "lo": [0.65], "hi": [1.05]}}
    # Levels with no rows are present but empty: the Trends card hides on them.
    assert rt["health_zones"] == {} and rt["health_areas"] == {}


def test_load_accepts_zone_and_area_levels(tmp_path):
    _write(tmp_path, "inrb_dashboard_Rt_data_20261102.csv",
           "National,national,2026-10-01,1.1,0.9,1.3\n"
           "Bunia,health_zone,2026-10-01,1.3,1.0,1.6\n"
           "Bunia|Simbiliabo,health_area,2026-10-01,1.5,0.8,2.2\n")
    rt = load_rt_estimates(tmp_path)
    assert list(rt["health_zones"]) == ["Bunia"]
    assert list(rt["health_areas"]) == ["Bunia|Simbiliabo"]


def test_missing_file_gives_empty_dict(tmp_path):
    assert load_rt_estimates(tmp_path) == {}


def test_missing_column_fails_loudly(tmp_path):
    (tmp_path / "inrb_dashboard_Rt_data_20261102.csv").write_text("area,date,rt_mean\nNational,2026-10-01,1\n")
    try:
        load_rt_estimates(tmp_path)
    except ValueError as e:
        assert "missing column" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_repo_rt_file_loads():
    rt = load_rt_estimates()
    if not rt:
        return  # no file committed in this checkout
    assert rt["national"]["dates"], "national series empty"
    for name, s in rt["provinces"].items():
        assert len(s["dates"]) == len(s["mean"]) == len(s["lo"]) == len(s["hi"]), name


def test_rt_scoped_to_trends_and_snapshot():
    assert _PAGE_SCOPED_PAYLOAD_KEYS["rt"] == {"trends", "map"}


def test_rt_card_markup_and_locale_keys():
    chrome = (REPO / "Scripts" / "common" / "chrome.py").read_text(encoding="utf-8")
    assert 'id="trends-rt-body"' in chrome and 'data-target="trends-rt"' in chrome
    import yaml
    for lang in ("en", "fr"):
        ui = yaml.safe_load((REPO / "locales" / f"{lang}.yaml").read_text(encoding="utf-8"))["ui"]
        trends_js = (REPO / "Scripts" / "assets" / "trends.js").read_text(encoding="utf-8")
        for key in set(re.findall(r'"ui\.(trends_rt_[a-z_]+|trends_caption_rt)"', trends_js)):
            assert key in ui, f"{lang}: ui.{key} missing"


def test_trends_rt_card_hides_when_level_not_estimated():
    js = (REPO / "Scripts" / "assets" / "trends.js").read_text(encoding="utf-8")
    assert "function rtLevelAvailable(" in js
    assert 'cardEl.style.display = available ? "" : "none"' in js
    # No fallback that shows a province's Rt for a zone/area selection.
    assert "zoneProvince" not in js[js.index("Card 4: reproduction number"):js.index("function renderRt(")]
