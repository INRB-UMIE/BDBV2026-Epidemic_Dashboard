import importlib

chrome = importlib.import_module("common.chrome")


def test_trends_key_is_page_scoped_to_the_trends_view():
    assert chrome._PAGE_SCOPED_PAYLOAD_KEYS["trends"] == {"trends"}


def test_only_the_trends_page_carries_the_trends_slice():
    payload = {"trends": {"asof": "2026-09-20"}, "asof": "2026-09-20"}
    for view_id in ("map", "epi-trends", "context", "genomic-epidemiology"):
        scoped = {
            k: v for k, v in payload.items()
            if k not in chrome._PAGE_SCOPED_PAYLOAD_KEYS
            or view_id in chrome._PAGE_SCOPED_PAYLOAD_KEYS[k]
        }
        assert "trends" not in scoped, view_id
    scoped = {
        k: v for k, v in payload.items()
        if k not in chrome._PAGE_SCOPED_PAYLOAD_KEYS
        or "trends" in chrome._PAGE_SCOPED_PAYLOAD_KEYS[k]
    }
    assert "trends" in scoped
