"""DEV-ONLY one-off: parse carduka-com-2026-06-29.xlsx into a normalized Python module.

Run from api/ with the venv active:
    python scripts/parse_listings.py > app/seed_data/real_cars.py

This is NOT imported at runtime — the committed app/seed_data/real_cars.py is the
artifact the seeder consumes, so openpyxl and the .xlsx never enter the Docker image.

The six rows flagged below as "sold" are SIMULATED sales derived from real active
listings (synthesized sold_price_kes/sold_at), not real CarDuka transaction data.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import openpyxl

XLSX = Path(__file__).resolve().parents[2] / "carduka-com-2026-06-29.xlsx"

# row index (1-based, excluding header) -> simulated sale (% of cash price, days ago)
SOLD = {2: (0.95, 24), 4: (0.96, 33), 7: (0.94, 14), 15: (0.97, 19), 17: (0.93, 41), 18: (0.95, 28)}

_BODY = [
    ("hilux", "Pickup"), ("rav", "SUV"), ("harrier", "SUV"), ("prado", "SUV"),
    ("cayenne", "SUV"), ("discovery", "SUV"), ("juke", "SUV"), ("vezel", "SUV"),
    ("3008", "SUV"), ("rx200", "SUV"), ("a-class", "Hatchback"), ("demio", "Hatchback"),
    ("mira", "Hatchback"), ("fit", "Hatchback"), ("ad", "Station Wagon"),
    ("axio", "Sedan"), ("320i", "Sedan"), ("3 series", "Sedan"),
]


def _col(hdr, row, name):
    try:
        return row[hdr.index(name)]
    except (ValueError, IndexError):
        return None


def _int(text) -> int | None:
    if text is None:
        return None
    m = re.search(r"(\d[\d,]*)", str(text).replace(" ", ""))
    return int(m.group(1).replace(",", "")) if m else None


def _body_type(model: str, cfg: str) -> str:
    blob = f"{model} {cfg}".lower()
    for key, bt in _BODY:
        if key in blob:
            return bt
    return "Sedan"


def _source_image(url: str) -> str | None:
    for candidate in str(url).splitlines():
        candidate = candidate.strip()
        if not candidate or "logo" in candidate:
            continue
        if "www.carduka.com/_next/image" in candidate:
            encoded = parse_qs(urlparse(candidate).query).get("url", [""])[0]
            candidate = unquote(encoded)
        if "prodapi.ncbagroup.com" in candidate:
            return candidate
    return None


def _images(hdr, row) -> list[str]:
    found: list[str] = []
    for name in ["image"] + [f"image{i}" for i in range(2, 11)] + ["image_1"]:
        value = _col(hdr, row, name)
        if not value:
            continue
        for raw in str(value).splitlines():
            image = _source_image(raw)
            if image and image not in found:
                found.append(image)
    return found[:12]


def _model_and_trim(configuration: str) -> tuple[str, str | None]:
    value = " ".join(configuration.split())
    lower = value.lower()
    multiword = (
        "land cruiser prado", "3 series", "a-class",
    )
    for model in multiword:
        if lower.startswith(model):
            canonical = value[:len(model)]
            trim = value[len(model):].strip() or None
            return canonical, trim
    parts = value.split(maxsplit=1)
    canonical = {
        "ad": "AD", "axio": "AXIO", "juke": "JUKE", "rx200t": "RX200T",
        "rav-4": "RAV-4", "hilux": "HILUX", "harrier": "HARRIER",
        "demio": "DEMIO",
    }.get(parts[0].lower(), parts[0].title())
    return canonical, parts[1] if len(parts) > 1 else None


def _description(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    # Public seller copy sometimes embeds personal mobile numbers. Keep all vehicle
    # facts while directing users to the source listing for contact.
    text = re.sub(r"(?<!\d)(?:\+?254|0)7\d{8}(?!\d)", "[contact via listing]", text)
    return text[:4_000]


def _features(description: str) -> list[str]:
    parts = re.split(r"(?:\s[-•✅♦️]+\s*|\s{2,})", description)
    result = []
    for part in parts:
        item = part.strip(" -•✅♦️")
        if 3 <= len(item) <= 120 and item not in result:
            result.append(item)
    return result[:25]


def _term_months(value: object) -> int | None:
    match = re.search(r"for\s+(\d+)\s+years?", str(value or ""), re.I)
    return int(match.group(1)) * 12 if match else None


def main() -> None:
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = list(rows[0])

    active: list[dict] = []
    sold: list[dict] = []
    for i, row in enumerate(rows[1:], 1):
        title = str(_col(hdr, row, "data") or "")
        make = (str(_col(hdr, row, "name") or "")).strip()
        cfg = (str(_col(hdr, row, "vehicleConfiguration") or "")).strip()
        ym = re.match(r"(\d{4})", title)
        year = int(ym.group(1)) if ym else 2015
        model, trim = _model_and_trim(cfg) if cfg else ("Unknown", None)
        price = _int(_col(hdr, row, "data3")) or _int(_col(hdr, row, "priceCurrency"))
        mileage = _int(_col(hdr, row, "data4")) or _int(_col(hdr, row, "data_10")) or 0
        trans = (str(_col(hdr, row, "vehicletransmission") or "automatic")).strip().title()
        if trans.lower() == "cvt":
            trans = "Automatic"
        fuel = (str(_col(hdr, row, "fueltype") or "petrol")).strip().title()
        loc = (str(_col(hdr, row, "data7") or "Nairobi")).split(",")[0].strip()
        desc = _description(
            _col(hdr, row, "car_description") or _col(hdr, row, "description")
        )
        images = _images(hdr, row)
        finance_monthly = _int(_col(hdr, row, "data2"))
        finance_term_months = _term_months(_col(hdr, row, "data2"))
        source_listing_id = str(_col(hdr, row, "listing_id") or "")
        source_listing_id = re.sub(r"\D", "", source_listing_id) or None
        location_detail = str(_col(hdr, row, "data7") or "").strip()
        if not make or not price:
            continue
        rec = {
            "id": f"car_real_{i:02d}",
            "make": make,
            "model": model,
            "year": year,
            "price_kes": price,
            "mileage_km": mileage,
            "transmission": trans,
            "fuel": fuel,
            "location": loc or "Nairobi",
            "condition": "Good",
            "body_type": _body_type(model, cfg),
            "image_url": images[0] if images else "",
            "image_urls": images,
            "description": desc,
            "trim": trim,
            "color": str(_col(hdr, row, "color") or "").strip().title() or None,
            "engine_cc": _int(_col(hdr, row, "data_9") or _col(hdr, row, "data6")),
            "monthly_payment_kes": finance_monthly,
            "finance_term_months": finance_term_months,
            "seller_name": str(_col(hdr, row, "data_7") or _col(hdr, row, "data5") or "").strip() or None,
            "location_detail": location_detail or None,
            "source_listing_id": source_listing_id,
            "source_url": str(_col(hdr, row, "item_page_link") or "").strip() or None,
            "grade_code": str(_col(hdr, row, "data_11") or _col(hdr, row, "data13") or "").strip() or None,
            "specs": {
                "title": str(_col(hdr, row, "item_page_title") or title).strip(),
                "features": _features(desc),
                "purchase_options": [
                    value for value in (
                        _col(hdr, row, "data_5") or _col(hdr, row, "data10"),
                        _col(hdr, row, "data_8") or _col(hdr, row, "data9"),
                    ) if value
                ],
            },
        }
        if i in SOLD:
            pct, days = SOLD[i]
            rec["sold_price_kes"] = int(price * pct)
            rec["sold_days_ago"] = days
            sold.append(rec)
        else:
            active.append(rec)

    out = sys.stdout
    out.write('"""Real CarDuka listings parsed from carduka-com-2026-06-29.xlsx '
              '(generated by scripts/parse_listings.py).\n\n'
              'REAL_ACTIVE are genuine scraped listings (real prices, descriptions, NCBA CDN\n'
              'image URLs). REAL_SOLD are SIMULATED sales derived from real listings\n'
              '(synthesized sold_price_kes/sold_at) used only as price-verdict comparables —\n'
              'NOT real CarDuka transaction data.\n"""\n')
    out.write("from __future__ import annotations\n\n")
    out.write("REAL_ACTIVE = [\n")
    for r in active:
        out.write(f"    {r!r},\n")
    out.write("]\n\n")
    out.write("REAL_SOLD = [\n")
    for r in sold:
        out.write(f"    {r!r},\n")
    out.write("]\n")


if __name__ == "__main__":
    main()
