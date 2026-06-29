"""Auction listings (~10). ends_at is generated relative to startup at seed time.

Demo-safe tuning: the scripted "Bid 1.8M on the Subaru Forester" must always
succeed, so the Forester auction has current_bid < 1.8M, a min_increment that
makes 1.8M a valid raise, and a reserve below 1.8M. ends_hours_from_now keeps
every countdown comfortably in the future during a demo.
"""
from __future__ import annotations

_IMG = "https://images.carduka.co.ke/demo/auction-{slug}.jpg"


def _img(make: str, model: str, idx: str) -> str:
    slug = f"{make}-{model}-{idx}".lower().replace(" ", "-")
    return _IMG.format(slug=slug)


# ends_hours_from_now -> absolute ends_at computed at seed time.
AUCTIONS = [
    # Hero auction for the scripted 1.8M bid.
    {"id": "auc_for_01", "make": "Subaru", "model": "Forester", "year": 2016, "mileage_km": 99000, "transmission": "Automatic", "location": "Nairobi",
     "reserve_price_kes": 1_700_000, "current_bid_kes": 1_650_000, "min_increment_kes": 25_000, "ends_hours_from_now": 72},
    {"id": "auc_fld_01", "make": "Toyota", "model": "Fielder", "year": 2017, "mileage_km": 91000, "transmission": "Automatic", "location": "Nairobi",
     "reserve_price_kes": 1_350_000, "current_bid_kes": 1_280_000, "min_increment_kes": 20_000, "ends_hours_from_now": 48},
    {"id": "auc_prm_01", "make": "Toyota", "model": "Premio", "year": 2016, "mileage_km": 97000, "transmission": "Automatic", "location": "Mombasa",
     "reserve_price_kes": 1_600_000, "current_bid_kes": 1_520_000, "min_increment_kes": 20_000, "ends_hours_from_now": 96},
    {"id": "auc_not_01", "make": "Nissan", "model": "Note", "year": 2017, "mileage_km": 79000, "transmission": "Automatic", "location": "Nairobi",
     "reserve_price_kes": 980_000, "current_bid_kes": 920_000, "min_increment_kes": 15_000, "ends_hours_from_now": 24},
    {"id": "auc_lx_01", "make": "Lexus", "model": "LX", "year": 2016, "mileage_km": 89000, "transmission": "Automatic", "location": "Nairobi",
     "reserve_price_kes": 10_500_000, "current_bid_kes": 9_800_000, "min_increment_kes": 100_000, "ends_hours_from_now": 120},
    {"id": "auc_har_01", "make": "Toyota", "model": "Harrier", "year": 2015, "mileage_km": 103000, "transmission": "Automatic", "location": "Nairobi",
     "reserve_price_kes": 3_100_000, "current_bid_kes": 2_950_000, "min_increment_kes": 50_000, "ends_hours_from_now": 60},
    {"id": "auc_xtr_01", "make": "Nissan", "model": "X-Trail", "year": 2016, "mileage_km": 94000, "transmission": "Automatic", "location": "Nakuru",
     "reserve_price_kes": 2_400_000, "current_bid_kes": 2_250_000, "min_increment_kes": 50_000, "ends_hours_from_now": 36},
    {"id": "auc_for_02", "make": "Subaru", "model": "Forester", "year": 2015, "mileage_km": 121000, "transmission": "Automatic", "location": "Kisumu",
     "reserve_price_kes": 1_550_000, "current_bid_kes": 1_450_000, "min_increment_kes": 25_000, "ends_hours_from_now": 84},
    {"id": "auc_axo_01", "make": "Toyota", "model": "Axio", "year": 2016, "mileage_km": 100000, "transmission": "Automatic", "location": "Nairobi",
     "reserve_price_kes": 1_150_000, "current_bid_kes": 1_080_000, "min_increment_kes": 15_000, "ends_hours_from_now": 18},
    {"id": "auc_vit_01", "make": "Suzuki", "model": "Vitara", "year": 2017, "mileage_km": 73000, "transmission": "Automatic", "location": "Mombasa",
     "reserve_price_kes": 1_850_000, "current_bid_kes": 1_720_000, "min_increment_kes": 30_000, "ends_hours_from_now": 54},
]


def with_images(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({**r, "image_url": _img(r["make"], r["model"], r["id"][-2:])})
    return out
