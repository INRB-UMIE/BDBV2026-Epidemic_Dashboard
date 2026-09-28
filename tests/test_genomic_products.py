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


def test_apply_tree_genome_counts_replaces_geojson_snapshot():
    zone_data = {
        "Bunia": {"name": "Bunia", "genomic_sequence_count": 3},
        "Aru": {"name": "Aru", "genomic_sequence_count": 9},
        "Katwa": {"name": "Katwa"},
    }
    tips = [
        {"health_zone": "Bunia"},
        {"health_zone": "Bunia"},
        {"health_zone": "Katwa"},
        {"health_zone": "Nowhere"},
    ]
    applied = ds.apply_tree_genome_counts(zone_data, tips)
    assert applied == {"Bunia": 2, "Katwa": 1}
    assert zone_data["Bunia"]["genomic_sequence_count"] == 2
    assert "genomic_sequence_count" not in zone_data["Aru"]
    markers = ds.build_genome_sequence_markers(
        zone_data, {"Bunia": (30.0, 1.5), "Katwa": (29.0, 1.2)}
    )
    by_nom = {m["nom"]: m["count"] for m in markers}
    assert by_nom == {"Bunia": 2, "Katwa": 1}


def test_load_genomic_products_absent_returns_empty(tmp_path, monkeypatch):
    _isolate_from_siblings(monkeypatch, tmp_path, tmp_path / "missing")
    assert ds.load_genomic_products() == {}          # build stays green if the sibling is absent


def test_canonicalize_nia_nia_ogonek_matches_map_nom():
    genomic = {
        "tips": [{"id": "PP_007LUHR.1", "health_zone": "Nia-Nią"}],
        "tree": 'BIA[&date="2026-08-25",health_zone="Nia-Nią"]',
    }
    ds.canonicalize_genomic_zones(genomic, {"Nia Nia", "Bunia"})
    assert genomic["tips"][0]["health_zone"] == "Nia Nia"
    assert 'health_zone="Nia Nia"' in genomic["tree"]
    assert "Nia-Nią" not in genomic["tree"]
