"""Used-car listings (~30 active + sold comparables) modelled on real CarDuka stock.

Prices in KES. Sold rows carry sold_price_kes/sold_at and feed the AI price verdict.
The five hero models — Toyota Fielder, Subaru Forester, Lexus LX, Toyota Premio,
Nissan Note — appear in both active and sold sets so verdicts have real evidence.
"""
from __future__ import annotations

_IMG = "https://images.carduka.co.ke/demo/{slug}.jpg"


def _img(make: str, model: str) -> str:
    slug = f"{make}-{model}".lower().replace(" ", "-")
    return _IMG.format(slug=slug)


# ── Active listings (for sale) ──
ACTIVE_CARS = [
    # Subaru Forester — several under 2.5M so "under 2.5M" search returns cards.
    {"id": "car_for_01", "make": "Subaru", "model": "Forester", "year": 2016, "price_kes": 2_350_000, "mileage_km": 98000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Excellent"},
    {"id": "car_for_02", "make": "Subaru", "model": "Forester", "year": 2015, "price_kes": 2_150_000, "mileage_km": 112000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Good"},
    {"id": "car_for_03", "make": "Subaru", "model": "Forester", "year": 2017, "price_kes": 2_480_000, "mileage_km": 86000, "transmission": "Automatic", "location": "Mombasa", "body_type": "SUV", "condition": "Excellent"},
    {"id": "car_for_04", "make": "Subaru", "model": "Forester", "year": 2014, "price_kes": 1_880_000, "mileage_km": 134000, "transmission": "Automatic", "location": "Nakuru", "body_type": "SUV", "condition": "Good"},
    # Toyota Fielder
    {"id": "car_fld_01", "make": "Toyota", "model": "Fielder", "year": 2017, "price_kes": 1_650_000, "mileage_km": 92000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Station Wagon", "condition": "Excellent"},
    {"id": "car_fld_02", "make": "Toyota", "model": "Fielder", "year": 2016, "price_kes": 1_480_000, "mileage_km": 105000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Station Wagon", "condition": "Good"},
    {"id": "car_fld_03", "make": "Toyota", "model": "Fielder", "year": 2018, "price_kes": 1_820_000, "mileage_km": 74000, "transmission": "Automatic", "location": "Kisumu", "body_type": "Station Wagon", "condition": "Excellent"},
    {"id": "car_fld_04", "make": "Toyota", "model": "Fielder", "year": 2015, "price_kes": 1_350_000, "mileage_km": 128000, "transmission": "Automatic", "location": "Mombasa", "body_type": "Station Wagon", "condition": "Good"},
    # Toyota Premio
    {"id": "car_prm_01", "make": "Toyota", "model": "Premio", "year": 2016, "price_kes": 1_950_000, "mileage_km": 96000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Sedan", "condition": "Excellent"},
    {"id": "car_prm_02", "make": "Toyota", "model": "Premio", "year": 2015, "price_kes": 1_750_000, "mileage_km": 118000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Sedan", "condition": "Good"},
    {"id": "car_prm_03", "make": "Toyota", "model": "Premio", "year": 2017, "price_kes": 2_100_000, "mileage_km": 81000, "transmission": "Automatic", "location": "Thika", "body_type": "Sedan", "condition": "Excellent"},
    {"id": "car_prm_04", "make": "Toyota", "model": "Premio", "year": 2014, "price_kes": 1_520_000, "mileage_km": 140000, "transmission": "Automatic", "location": "Eldoret", "body_type": "Sedan", "condition": "Good"},
    # Nissan Note
    {"id": "car_not_01", "make": "Nissan", "model": "Note", "year": 2017, "price_kes": 1_180_000, "mileage_km": 78000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Hatchback", "condition": "Excellent"},
    {"id": "car_not_02", "make": "Nissan", "model": "Note", "year": 2016, "price_kes": 1_050_000, "mileage_km": 94000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Hatchback", "condition": "Good"},
    {"id": "car_not_03", "make": "Nissan", "model": "Note", "year": 2018, "price_kes": 1_320_000, "mileage_km": 62000, "transmission": "Automatic", "location": "Mombasa", "body_type": "Hatchback", "condition": "Excellent"},
    {"id": "car_not_04", "make": "Nissan", "model": "Note", "year": 2015, "price_kes": 950_000, "mileage_km": 116000, "transmission": "Automatic", "location": "Nakuru", "body_type": "Hatchback", "condition": "Good"},
    # Lexus LX (premium)
    {"id": "car_lx_01", "make": "Lexus", "model": "LX", "year": 2016, "price_kes": 11_500_000, "mileage_km": 88000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Excellent"},
    {"id": "car_lx_02", "make": "Lexus", "model": "LX", "year": 2015, "price_kes": 9_800_000, "mileage_km": 104000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Good"},
    {"id": "car_lx_03", "make": "Lexus", "model": "LX", "year": 2018, "price_kes": 14_200_000, "mileage_km": 56000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Excellent"},
    # A few others for breadth
    {"id": "car_axo_01", "make": "Toyota", "model": "Axio", "year": 2016, "price_kes": 1_280_000, "mileage_km": 99000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Sedan", "condition": "Good"},
    {"id": "car_vit_01", "make": "Suzuki", "model": "Vitara", "year": 2017, "price_kes": 2_050_000, "mileage_km": 71000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Excellent"},
    {"id": "car_dem_01", "make": "Mazda", "model": "Demio", "year": 2016, "price_kes": 980_000, "mileage_km": 88000, "transmission": "Automatic", "location": "Mombasa", "body_type": "Hatchback", "condition": "Good"},
    {"id": "car_xtr_01", "make": "Nissan", "model": "X-Trail", "year": 2016, "price_kes": 2_650_000, "mileage_km": 92000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Excellent"},
    {"id": "car_har_01", "make": "Toyota", "model": "Harrier", "year": 2015, "price_kes": 3_450_000, "mileage_km": 101000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Good"},
]

# ── Sold comparables (price-verdict evidence; same hero models) ──
# sold_days_ago is converted to an absolute sold_at at seed time.
SOLD_CARS = [
    {"id": "car_for_s1", "make": "Subaru", "model": "Forester", "year": 2016, "price_kes": 2_300_000, "sold_price_kes": 2_250_000, "mileage_km": 101000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Excellent", "sold_days_ago": 21},
    {"id": "car_for_s2", "make": "Subaru", "model": "Forester", "year": 2015, "price_kes": 2_150_000, "sold_price_kes": 2_080_000, "mileage_km": 118000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Good", "sold_days_ago": 40},
    {"id": "car_for_s3", "make": "Subaru", "model": "Forester", "year": 2017, "price_kes": 2_500_000, "sold_price_kes": 2_420_000, "mileage_km": 84000, "transmission": "Automatic", "location": "Mombasa", "body_type": "SUV", "condition": "Excellent", "sold_days_ago": 12},
    {"id": "car_for_s4", "make": "Subaru", "model": "Forester", "year": 2016, "price_kes": 2_280_000, "sold_price_kes": 2_200_000, "mileage_km": 95000, "transmission": "Automatic", "location": "Nakuru", "body_type": "SUV", "condition": "Good", "sold_days_ago": 33},
    {"id": "car_fld_s1", "make": "Toyota", "model": "Fielder", "year": 2017, "price_kes": 1_650_000, "sold_price_kes": 1_600_000, "mileage_km": 90000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Station Wagon", "condition": "Excellent", "sold_days_ago": 18},
    {"id": "car_fld_s2", "make": "Toyota", "model": "Fielder", "year": 2016, "price_kes": 1_500_000, "sold_price_kes": 1_450_000, "mileage_km": 108000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Station Wagon", "condition": "Good", "sold_days_ago": 27},
    {"id": "car_prm_s1", "make": "Toyota", "model": "Premio", "year": 2016, "price_kes": 1_950_000, "sold_price_kes": 1_880_000, "mileage_km": 99000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Sedan", "condition": "Excellent", "sold_days_ago": 15},
    {"id": "car_not_s1", "make": "Nissan", "model": "Note", "year": 2017, "price_kes": 1_180_000, "sold_price_kes": 1_140_000, "mileage_km": 80000, "transmission": "Automatic", "location": "Nairobi", "body_type": "Hatchback", "condition": "Excellent", "sold_days_ago": 22},
    {"id": "car_lx_s1", "make": "Lexus", "model": "LX", "year": 2016, "price_kes": 11_800_000, "sold_price_kes": 11_300_000, "mileage_km": 90000, "transmission": "Automatic", "location": "Nairobi", "body_type": "SUV", "condition": "Excellent", "sold_days_ago": 30},
]


def with_images(rows: list[dict]) -> list[dict]:
    return [{**r, "image_url": _img(r["make"], r["model"])} for r in rows]
