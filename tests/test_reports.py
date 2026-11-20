import importlib

rep = importlib.import_module("common.reports")
chrome = importlib.import_module("common.chrome")

MINIMAL = {"geometry": {"type": "FeatureCollection", "features": []}, "zone_data": {}, "layers": []}


def test_group_reports_pairs_languages_by_date_newest_first():
    files = [
        ("2026-09-23_Rapport-Genomique_FR.pdf", 870183),
        ("2026-09-23_Report-Genomics_EN.pdf", 847187),
        ("2026-09-28_Report-Genomics_EN.pdf", 3445877),
    ]
    groups = rep.group_reports(files, "Genomic")
    assert [g["date"] for g in groups] == ["2026-09-28", "2026-09-23"]
    assert sorted(groups[1]["files"]) == ["en", "fr"]
    assert groups[1]["files"]["fr"]["title"] == "Rapport Genomique"
    assert groups[1]["files"]["en"]["size"] == 847187
    assert groups[1]["files"]["en"]["url"].endswith("/Genomic/2026-09-23_Report-Genomics_EN.pdf")


def test_group_reports_same_date_and_language_makes_two_reports():
    files = [("2026-10-01_A_EN.pdf", 1), ("2026-10-01_B_EN.pdf", 2)]
    assert len(rep.group_reports(files, "X")) == 2


def test_group_reports_skips_badly_named_files():
    files = [("notes.pdf", 1), ("2026-13-45_Bad_EN.pdf", 1), ("2026-10-14_Contact-Tracing_EN.pdf", 5)]
    groups = rep.group_reports(files, "Contact_Tracing")
    assert [g["date"] for g in groups] == ["2026-10-14"]


def test_reports_page_is_mapless_and_scoped():
    assert "reports" in chrome.MAPLESS_VIEWS
    assert chrome._PAGE_SCOPED_PAYLOAD_KEYS["reports"] == {"reports"}
    page = importlib.import_module("pages.reports")
    html = page.build_page(dict(MINIMAL, reports={"folders": []}))
    assert 'id="rep-page"' in html and 'src="assets/reports.js"' in html
    assert 'href="reports.html"' in html
    other = chrome.render_page("trends", dict(MINIMAL, reports={"folders": [{"id": "SCOPED-OUT"}]}))
    assert "SCOPED-OUT" not in other


def test_folders_ordered_by_most_recent_report():
    mk = lambda i, d: {"id": i, "reports": [{"date": d, "files": {}}]}
    out = rep.sort_folders([mk("Genomic", "2026-09-28"), mk("Rt", "2026-11-18"),
                            mk("Contact_Tracing", "2026-10-14"), mk("A", "2026-11-18")])
    assert [f["id"] for f in out] == ["A", "Rt", "Contact_Tracing", "Genomic"]
