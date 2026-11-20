"""
Reports tab data: every PDF in INRB-UMIE/BDBV2026-Reports, grouped by folder.

Each top-level folder of the reports repo is one report type (Contact_Tracing,
Genomic, Rt, ...). New folders and new PDFs appear on the tab at the next build
with no code change. PDF filenames are ``YYYY-MM-DD_<title>_<EN|FR>.pdf``; the
date and language come from the name, the middle part is only a display title.
Files that don't match that pattern are skipped (with a note).

Source order: the GitHub contents API (same source and same jsDelivr links the
Genomic and Surveillance tabs already use), then a local checkout
(``REPORTS_DIR`` or a sibling ``BDBV2026-Reports/`` folder) if GitHub can't be
reached. If neither works the tab shows an empty state; the build still passes.

Set ``REPORTS_FETCH=0`` to skip GitHub and use the local checkout only.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from common.data_sources import (
    GENOMIC_REPORTS_REF as REPORTS_REF,
    GENOMIC_REPORTS_REPO as REPORTS_REPO,
    INSP_FETCH_TIMEOUT_S,
)
from common.paths import SCRIPT_DIR

REPORT_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<title>.+)_(?P<lang>EN|FR)\.pdf$", re.IGNORECASE,
)
REPORTS_FETCH = os.environ.get("REPORTS_FETCH", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
_USER_AGENT = "BDBV2026-Dashboard-Build/1.0"


def pdf_url(folder: str, name: str) -> str:
    """jsDelivr serves the PDF as application/pdf, so the browser opens it
    itself rather than showing GitHub's HTML preview page."""
    return f"https://cdn.jsdelivr.net/gh/{REPORTS_REPO}@{REPORTS_REF}/{folder}/{name}"


def _api_get(path: str):
    url = f"https://api.github.com/repos/{REPORTS_REPO}/contents/{path}?ref={REPORTS_REF}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(
        req, timeout=INSP_FETCH_TIMEOUT_S, context=ssl.create_default_context(),
    ) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _list_from_github() -> dict[str, list[tuple[str, int]]] | None:
    """``{folder: [(filename, size_bytes), ...]}`` or None if GitHub fails."""
    try:
        root = _api_get("")
        if not isinstance(root, list):
            return None
        out: dict[str, list[tuple[str, int]]] = {}
        for item in root:
            if item.get("type") != "dir" or str(item.get("name", "")).startswith("."):
                continue
            folder = item["name"]
            items = _api_get(folder)
            if not isinstance(items, list):
                continue
            out[folder] = [
                (i["name"], int(i.get("size") or 0)) for i in items
                if i.get("type") == "file" and str(i.get("name", "")).lower().endswith(".pdf")
            ]
        return out
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
        print(f"  NOTE: reports listing from GitHub failed: {exc}")
        return None


def _local_dir() -> Path | None:
    env = os.environ.get("REPORTS_DIR", "").strip()
    for p in ([Path(env)] if env else []) + [SCRIPT_DIR.parent.parent / "BDBV2026-Reports"]:
        if p.is_dir():
            return p
    return None


def _list_from_local() -> dict[str, list[tuple[str, int]]] | None:
    root = _local_dir()
    if root is None:
        return None
    out: dict[str, list[tuple[str, int]]] = {}
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        out[d.name] = [(f.name, f.stat().st_size) for f in sorted(d.iterdir())
                       if f.is_file() and f.suffix.lower() == ".pdf"]
    print(f"  reports: using local checkout {root}")
    return out


def group_reports(files: list[tuple[str, int]], folder: str) -> list[dict]:
    """Group one folder's PDFs into reports, newest first.

    Files sharing a date are one report in several languages (a second file of
    the same language and date starts its own report instead of overwriting).
    """
    groups: list[dict] = []
    for name, size in sorted(files):
        m = REPORT_RE.match(name.strip())
        if not m:
            print(f"  NOTE: reports/{folder}/{name} doesn't match YYYY-MM-DD_<title>_<EN|FR>.pdf; skipped")
            continue
        try:
            datetime.date.fromisoformat(m.group("date"))
        except ValueError:
            print(f"  NOTE: reports/{folder}/{name} has an invalid date; skipped")
            continue
        lang = m.group("lang").lower()
        entry = {
            "url": pdf_url(folder, name),
            "size": size,
            "title": m.group("title").replace("-", " ").replace("_", " ").strip(),
        }
        for g in groups:
            if g["date"] == m.group("date") and lang not in g["files"]:
                g["files"][lang] = entry
                break
        else:
            groups.append({"date": m.group("date"), "files": {lang: entry}})
    groups.sort(key=lambda g: g["date"], reverse=True)
    return groups


def sort_folders(folders: list[dict]) -> list[dict]:
    """Folders with the most recent report first (ties by folder name)."""
    return sorted(folders, key=lambda f: (
        [-int(c) for c in f["reports"][0]["date"].split("-")], f["id"].lower()))


def load_reports() -> dict | None:
    """Payload slice for the Reports tab, or None when no source is reachable."""
    listing = _list_from_github() if REPORTS_FETCH else None
    source = "github"
    if listing is None:
        listing = _list_from_local()
        source = "local"
    if listing is None:
        print("  reports: no source available; Reports tab will be empty")
        return None
    folders = []
    for folder in listing:
        reports = group_reports(listing[folder], folder)
        if reports:
            folders.append({"id": folder, "reports": reports})
    folders = sort_folders(folders)
    print(f"  reports ({source}): {len(folders)} folders, "
          f"{sum(len(f['reports']) for f in folders)} reports")
    return {"repo": REPORTS_REPO, "folders": folders}
