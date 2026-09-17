import importlib

chrome = importlib.import_module("common.chrome")

MINIMAL = {"geometry": {"type": "FeatureCollection", "features": []}, "zone_data": {}, "layers": []}


def test_genomic_not_in_stub_views():
    assert "genomic-epidemiology" not in chrome.STUB_VIEWS


def test_page_body_and_scripts_injected_only_when_contributed():
    html = chrome.render_page("genomic-epidemiology", MINIMAL,
                              page_body='<div id="genomic-panel">RAIL</div>',
                              extra_scripts='<script src="__ASSETS_PREFIX__genomic.js"></script>')
    assert '<div id="genomic-panel">RAIL</div>' in html
    assert 'src="assets/genomic.js"' in html                 # __ASSETS_PREFIX__ expanded
    assert "__PAGE_BODY__" not in html and "__EXTRA_SCRIPTS__" not in html


def test_non_contributing_page_is_clean():
    html = chrome.render_page("trends", MINIMAL)
    assert "__PAGE_BODY__" not in html and "__EXTRA_SCRIPTS__" not in html
    assert "genomic.js" not in html
    assert 'id="genomic-panel"' not in html


def test_genomic_page_has_no_stub_markup():
    html = chrome.render_page("genomic-epidemiology", MINIMAL, page_body='<div id="genomic-panel"></div>')
    assert "stub-view" not in html            # body no longer carries the stub class
    # The genomic stub is gone (the other two tabs' stubs still live in the shared
    # template, so a bare "Coming soon" check would false-positive on them).
    assert "stub-genomic-epidemiology" not in html


def test_genomic_module_contributes_rail_and_script():
    page = importlib.import_module("pages.genomic_epidemiology")
    html = page.build_page(MINIMAL)
    assert 'id="genomic-panel"' in html
    assert 'id="gen-tree-body"' in html and 'id="gen-dist-body"' in html
    assert 'id="gen-corr-body"' in html
    assert 'id="genomic-resize"' in html                      # drag handle present
    assert 'id="gen-ne-skygrid"' in html and 'id="gen-ne-exp"' in html   # Ne toggles present
    assert 'id="gen-ne-stale-note"' in html
    assert 'id="gen-dist-imputed"' in html and 'id="gen-dist-beyond"' in html   # distribution controls
    # Cases/genomes card must appear before the Ne card in the rail markup.
    assert html.index('id="gen-dist-card"') < html.index('id="gen-ne-card"')
    assert html.index('id="gen-corr-card"') < html.index('id="gen-ne-card"')
    assert 'gen-dist-csv' not in html                                          # data is not downloadable
    assert 'src="assets/genomic.js"' in html
    assert "stub-genomic-epidemiology" not in html
