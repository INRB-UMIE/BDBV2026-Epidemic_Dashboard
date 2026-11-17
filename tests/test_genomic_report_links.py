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


def test_ct_report_picks_newest_and_falls_back_to_english(monkeypatch):
    monkeypatch.setattr(ds, "_list_genomic_report_filenames_from_github", lambda path=None: (
        ["2026-10-14_Contact-Tracing_EN.pdf", "2026-11-12_Contact-Tracing_EN.pdf", "notes.pdf"]
        if path == ds.CT_REPORTS_PATH else []))
    locales = {
        "en": {"ui": {"surv": {"intro": 'Latest report: <a href="{report_url}">{report_date}</a>.'}}},
        "fr": {"ui": {"surv": {"intro": 'Dernier rapport : <a href="{report_url}">{report_date}</a>.'}}},
    }
    ds.inject_ct_report_links(locales)
    en, fr = locales["en"]["ui"]["surv"]["intro"], locales["fr"]["ui"]["surv"]["intro"]
    assert "Contact_Tracing/2026-11-12_Contact-Tracing_EN.pdf" in en and ">12 Nov 2026<" in en
    assert "2026-11-12_Contact-Tracing_EN.pdf" in fr and ">12 nov. 2026<" in fr   # no FR yet: English report
    assert "cdn.jsdelivr.net" in en and "{report" not in en + fr


def test_ct_report_uses_fallback_when_github_unreachable(monkeypatch):
    monkeypatch.setattr(ds, "_list_genomic_report_filenames_from_github", lambda path=None: None)
    r = ds.resolve_latest_ct_report()
    assert r["en"]["url"].endswith("/Contact_Tracing/2026-10-14_Contact-Tracing_EN.pdf")
    assert r["fr"]["date"] == "2026-10-14"
