"""Current Snapshot summary rail: payload digest + page wiring."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "Scripts"))

from common.chrome import _PAGE_SCOPED_PAYLOAD_KEYS  # noqa: E402
from common.snapshot_summary import build_snapshot_summary  # noqa: E402


def _payload():
    return {
        "zone_data": {"Bunia": {"genomic_sequence_count": 3}, "Nizi": {}},
        "trends": {
            "asof": "2026-10-15",
            "incomplete_from": "2026-10-10",
            "cases": {
                "national": {"start": "2026-10-01", "obs": [1, 2], "imp": [0, 1]},
                "health_zones": {"Bunia": {"start": "2026-10-01", "obs": [1, 0], "imp": [0, 0]}},
            },
            "positivity": {
                "national": {"dates": ["2026-10-01"], "mean": [0.41234], "lo": [0.3], "hi": [0.5]},
                "health_zones": {},
            },
        },
        "surveillance": {
            "contact_tracing": {
                "data_cut": "2026-10-15",
                "headline": {"contacts": 10, "fu_contacts": 8, "fu_complete": 2},
                "national": {"area": "National"},
                "provinces": [{"area": "Ituri", "contacts": 5}],
                "fu21": {"zones": {"Bunia": {"k": [1, None, 2], "n": [4, None, 4], "total": 8}}},
                "weekly_by_zone": {"Bunia": {"new_cases": [3, 2], "prev_contact": [1, 0], "became_source": [0, 1]}},
            },
            "testing": {
                "asof": "2026-10-15",
                "national": {"total_n": 100, "total_pos": 40},
                "provinces": {"Ituri": {"total_n": 60, "total_pos": 20}},
                "health_zones": {"Bunia": {"total_n": 50, "total_pos": 10}},
                "labs": [
                    {"code": "A", "label": "Lab A", "health_zone": "Bunia", "province": "Ituri",
                     "dates": ["2026-09-01", "2026-10-10"], "n": [5, 7], "pos": [1, 3],
                     "total_n": 12, "total_pos": 4, "first": "2026-09-01", "last": "2026-10-10"},
                    {"code": "B", "label": "Lab B", "health_zone": None, "province": None,
                     "dates": [], "n": [], "pos": [], "total_n": 30, "total_pos": 9},
                ],
            },
        },
        "genomic": {"tips": [{}, {}, {}, {}], "meta": {"updated": "2026-08-08"}},
    }


def test_summary_zone_block():
    s = build_snapshot_summary(_payload())
    bunia = s["zones"]["Bunia"]
    assert bunia["curve"]["obs"] == [1, 0]
    assert bunia["testing"] == {"n": 50, "pos": 10}
    assert bunia["labs"] == ["A"]
    assert bunia["ct"] == {"fu_k": 3, "fu_n": 8, "cases": 5, "prev_contact": 1, "became_source": 1}


def test_summary_labs_recent_window_and_order():
    s = build_snapshot_summary(_payload())
    assert [l["code"] for l in s["labs"]] == ["B", "A"]          # by total samples
    a = next(l for l in s["labs"] if l["code"] == "A")
    assert (a["recent_n"], a["recent_pos"]) == (7, 3)              # only 2026-10-10 is within 14 days


def test_summary_national_and_sequences():
    s = build_snapshot_summary(_payload())
    assert s["national"]["testing"] == {"n": 100, "pos": 40}
    assert s["national"]["curve"]["pos"]["mean"] == [0.412]
    assert s["sequences"] == 4                                     # tree tips, not zone sums
    assert s["ct"]["provinces"]["Ituri"]["contacts"] == 5
    assert s["asof"]["sequences"] == "2026-08-08"


def test_summary_survives_missing_sources():
    s = build_snapshot_summary({"zone_data": {"X": {"genomic_sequence_count": 2}}})
    assert s["zones"] == {} and s["labs"] == [] and s["ct"] is None
    assert s["national"]["curve"] is None
    assert s["sequences"] == 2


def test_summary_is_scoped_to_the_snapshot_page():
    assert _PAGE_SCOPED_PAYLOAD_KEYS["snapshot_summary"] == {"map"}


def test_snapshot_page_loads_its_script_and_rail():
    from pages import snapshot
    html = snapshot._BODY + snapshot._SCRIPTS
    assert 'id="snapshot-panel"' in html and 'id="snapshot-split-handle"' in html
    assert html.index("charts.js") < html.index("snapshot.js")
    build = (REPO / "Scripts" / "build_dashboard.py").read_text(encoding="utf-8")
    assert '"snapshot.js"' in build, "build_dashboard.py must copy snapshot.js into assets/"


def test_snapshot_locale_keys_match():
    import yaml
    en = yaml.safe_load((REPO / "locales" / "en.yaml").read_text(encoding="utf-8"))["ui"]["snap"]
    fr = yaml.safe_load((REPO / "locales" / "fr.yaml").read_text(encoding="utf-8"))["ui"]["snap"]
    assert set(en) == set(fr)
    js = (REPO / "Scripts" / "assets" / "snapshot.js").read_text(encoding="utf-8")
    import re
    used = set(re.findall(r'\btrf?\("([a-z_]+)"', js))
    missing = sorted(used - set(en))
    assert not missing, f"snapshot.js names ui.snap keys missing from the locales: {missing}"
