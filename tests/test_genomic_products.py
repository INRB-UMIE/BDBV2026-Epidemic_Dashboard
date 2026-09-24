import importlib, json
from pathlib import Path

ds = importlib.import_module("common.data_sources")


def _seed(dirpath: Path):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "ituri-tree.ptree").write_text("#NEXUS\nBEGIN TREES;\ntree T = ((A,B),C);\nEND;\n")
    (dirpath / "ituri-tips.json").write_text(json.dumps([{"id": "A", "health_zone": "Bunia", "date": "2026-05-01"}]))
    (dirpath / "ituri-meta.json").write_text(json.dumps({"mostRecentDate": "2026-06-23", "updated": "2026-08-12", "tipCount": 1}))
    (dirpath / "skygrid.json").write_text(json.dumps({"time": [1, 2], "ne": [3, 4]}))
    (dirpath / "exponential.json").write_text(json.dumps({"growth": 0.07}))


def _isolate_from_siblings(monkeypatch, tmp_path, genomic_dir):
    monkeypatch.setattr(ds, "GENOMIC_DIR", genomic_dir)
    monkeypatch.setattr(ds, "PHYLOGENIES_DIR", tmp_path / "no-phylo")
    monkeypatch.setattr(ds, "BEAST_NE_DIR", tmp_path / "no-beast")


def test_load_genomic_products_reads_all(tmp_path, monkeypatch):
    d = tmp_path / "gen"
    _seed(d)
    _isolate_from_siblings(monkeypatch, tmp_path, d)
    out = ds.load_genomic_products()
    assert out["tree"].startswith("#NEXUS")            # inline NEXUS text (PearTree `tree` key)
    assert out["tips"][0]["health_zone"] == "Bunia"
    assert out["meta"]["mostRecentDate"] == "2026-06-23"
    assert out["data_build_date"] == "2026-08-12"      # meta.updated, surfaced as the tab's vintage
    assert out["skygrid"]["ne"] == [3, 4]
    assert out["exponential"]["growth"] == 0.07


def test_load_genomic_products_absent_returns_empty(tmp_path, monkeypatch):
    _isolate_from_siblings(monkeypatch, tmp_path, tmp_path / "missing")
    assert ds.load_genomic_products() == {}          # build stays green if the sibling is absent
