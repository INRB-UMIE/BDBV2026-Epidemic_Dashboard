"""Newest dated Genomic PDFs from BDBV2026-Reports drive the rail note links."""

import importlib
from datetime import date

ds = importlib.import_module("common.data_sources")


def test_parse_genomic_report_filename():
    assert ds.parse_genomic_report_filename(
        "2026-09-23_Report-Genomics_EN.pdf"
    ) == (date(2026, 9, 23), "en")
    assert ds.parse_genomic_report_filename(
        "2026-09-23_Rapport-Genomique_FR.pdf"
    ) == (date(2026, 9, 23), "fr")
    assert ds.parse_genomic_report_filename("notes.md") is None
    assert ds.parse_genomic_report_filename("2026-09-23_Report.pdf") is None


def test_pick_latest_genomic_report_files_prefers_newest_date_per_lang():
    picked = ds.pick_latest_genomic_report_files([
        "2026-09-01_Report-Genomics_EN.pdf",
        "2026-09-23_Report-Genomics_EN.pdf",
        "2026-09-10_Rapport-Genomique_FR.pdf",
        "2026-09-23_Rapport-Genomique_FR.pdf",
        "readme.txt",
    ])
    assert picked == {
        "en": "2026-09-23_Report-Genomics_EN.pdf",
        "fr": "2026-09-23_Rapport-Genomique_FR.pdf",
    }


def test_genomic_report_pdf_url_uses_jsdelivr_not_github_blob():
    url = ds.genomic_report_pdf_url("2026-09-23_Report-Genomics_EN.pdf")
    assert url.startswith("https://cdn.jsdelivr.net/gh/INRB-UMIE/BDBV2026-Reports@")
    assert url.endswith("/Genomic/2026-09-23_Report-Genomics_EN.pdf")
    assert "/blob/" not in url


def test_inject_genomic_report_links_fills_placeholder(monkeypatch):
    monkeypatch.setattr(
        ds,
        "resolve_latest_genomic_report_urls",
        lambda: {
            "en": "https://cdn.jsdelivr.net/gh/x@main/Genomic/a_EN.pdf",
            "fr": "https://cdn.jsdelivr.net/gh/x@main/Genomic/a_FR.pdf",
        },
    )
    locales = {
        "en": {"ui": {"genomic": {"latest_report": 'Find <a href="{report_url}">here</a>.'}}},
        "fr": {"ui": {"genomic": {"latest_report": 'Voir <a href="{report_url}">ici</a>.'}}},
    }
    urls = ds.inject_genomic_report_links(locales)
    assert "a_EN.pdf" in locales["en"]["ui"]["genomic"]["latest_report"]
    assert "a_FR.pdf" in locales["fr"]["ui"]["genomic"]["latest_report"]
    assert "{report_url}" not in locales["en"]["ui"]["genomic"]["latest_report"]
    assert urls["en"].endswith("a_EN.pdf")
