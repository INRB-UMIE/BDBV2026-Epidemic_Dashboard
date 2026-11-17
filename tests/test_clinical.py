import importlib
import json

clin = importlib.import_module("common.clinical")
chrome = importlib.import_module("common.chrome")

MINIMAL = {"geometry": {"type": "FeatureCollection", "features": []}, "zone_data": {}, "layers": []}


def _seed(tmp_path):
    out = tmp_path / "outputs"
    c = out / "2026-11-17" / "clinical"
    c.mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({"date": "2026-11-17"}), encoding="utf-8")
    (c / "clinical_summary.csv").write_text(
        '"spatial_scale","location","n_cases","n_symptoms_recorded","n_hospitalised","n_dead_at_sampling",'
        '"n_health_workers","n_los","los_median","los_q25","los_q75","n_onset_admit","onset_admit_median",'
        '"onset_admit_q25","onset_admit_q75"\n'
        '"national","National",200,150,60,50,12,55,8,3,14,50,4,2,7\n'
        '"province","Tshopo",60,40,NA,12,NA,NA,NA,NA,NA,NA,NA,NA,NA\n', encoding="utf-8")
    (c / "clinical_symptoms.csv").write_text(
        '"spatial_scale","location","breakdown","group","symptom_code","symptom_label_en","symptom_label_fr",'
        '"label_confirmed","n_with_symptom","n_symptoms_recorded","pct","suppressed"\n'
        '"national","National","all","all","DT","DT","DT",FALSE,20,150,13.3,FALSE\n'
        '"national","National","all","all","FV","Fever","Fièvre",TRUE,100,150,66.7,FALSE\n'
        '"national","National","sex","female","FV","Fever","Fièvre",TRUE,NA,80,NA,TRUE\n'
        '"national","National","sex","female","DT","DT","DT",FALSE,12,80,15,FALSE\n', encoding="utf-8")
    (c / "clinical_length_of_stay.csv").write_text(
        '"spatial_scale","location","status_at_sampling","stay_bin","bin_lo","bin_hi","n","suppressed"\n'
        '"national","National","all","0",0,0,NA,TRUE\n'
        '"national","National","all","1-60",1,60,48,FALSE\n', encoding="utf-8")
    (c / "clinical_age_sex.csv").write_text(
        '"spatial_scale","location","age_band","sex","n","n_dead_at_sampling","suppressed"\n'
        '"national","National","0-9","female",30,NA,TRUE\n'
        '"national","National","0-9","male",25,10,FALSE\n', encoding="utf-8")
    (c / "clinical_health_workers.csv").write_text(
        '"spatial_scale","location","breakdown","group","n","suppressed"\n'
        '"national","National","onset_month","2026-05",NA,TRUE\n'
        '"national","National","onset_month","2026-06",12,FALSE\n'
        '"national","National","role","nurse",12,FALSE\n'
        '"national","National","role","doctor",NA,TRUE\n', encoding="utf-8")
    (c / "clinical_meta.json").write_text(json.dumps({"min_cell_count": 10, "symptom_age_groups": ["0-4"],
                                                      "unconfirmed_symptom_codes": ["DT"]}), encoding="utf-8")
    return out


def test_clinical_loader_keeps_suppression_flags(tmp_path):
    d = clin.load_clinical(_seed(tmp_path))
    assert d["asof"] == "2026-11-17"
    assert set(d["locations"]) == {"national", "province:Tshopo"}
    assert d["order"] == ["FV", "DT"]                          # most frequent nationally first
    assert d["labels"]["DT"]["confirmed"] is False and d["labels"]["FV"]["fr"] == "Fièvre"
    nat = d["locations"]["national"]
    assert nat["summary"]["los_median"] == 8.0 and nat["summary"]["n_cases"] == 200
    assert d["locations"]["province:Tshopo"]["summary"]["n_hospitalised"] is None
    fem = nat["symptoms"]["sex"]["female"]
    assert fem["pct"] == [None, 15.0] and fem["s"] == [1, 0] and fem["den"] == 80
    assert nat["los"]["all"]["n"] == [None, 48] and nat["los"]["all"]["s"] == [1, 0]
    assert nat["pyramid"]["female"] == [30] and nat["pyramid"]["female_dead"] == [None] and nat["pyramid"]["s_female"] == [1]
    assert nat["hcw"]["n"] == [None, 12] and nat["hcw"]["s"] == [1, 0]
    assert nat["hcw"]["roles"] == {"nurse": 12, "doctor": None} and nat["hcw"]["roles_s"]["doctor"] is True
    assert d["meta"]["unconfirmed_symptom_codes"] == ["DT"]


def test_clinical_loader_none_without_step9_tables(tmp_path):
    out = tmp_path / "outputs"
    (out / "2026-11-17").mkdir(parents=True)
    (out / "manifest.json").write_text(json.dumps({"date": "2026-11-17"}), encoding="utf-8")
    assert clin.load_clinical(out) is None


def test_clinical_page_is_real_mapless_and_scoped():
    assert "clinical-symptoms" not in chrome.STUB_VIEWS
    assert "clinical-symptoms" in chrome.MAPLESS_VIEWS
    assert chrome._PAGE_SCOPED_PAYLOAD_KEYS["clinical"] == {"clinical-symptoms"}
    page = importlib.import_module("pages.clinical_symptoms")
    html = page.build_page(dict(MINIMAL, clinical={"asof": "x", "locations": {}}))
    assert 'id="clin-page"' in html and 'src="assets/clinical.js"' in html
    for card in ("clin-symptoms", "clin-los", "clin-pyramid", "clin-hcw"):
        assert 'id="%s"' % card in html
    other = chrome.render_page("trends", dict(MINIMAL, clinical={"asof": "SCOPED-OUT"}))
    assert "SCOPED-OUT" not in other
