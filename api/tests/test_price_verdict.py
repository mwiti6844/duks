from __future__ import annotations

from . import sse_helper as sse


def test_price_verdict_uses_sold_comparables(client, auth):
    sid = "sess-verdict"
    sse.chat(client, auth, "Find me a Toyota Harrier under 6M", sid)
    events = sse.chat(client, auth, "Is the price fair?", sid)
    verdict = next(c for c in sse.components(events) if c["type"] == "price_verdict")
    props = verdict["props"]
    assert props["verdict"] in {"fair", "below_market", "above_market"}
    # Evidence must be real sold-listing ids, not invented.
    assert props["evidence"]
    assert all(e["sale_id"].startswith("car_") for e in props["evidence"])
    assert "comparable_median_kes" in props
