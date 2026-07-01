from __future__ import annotations

from app.db import repositories as repo
from app.db.engine import SessionLocal

from . import sse_helper as sse


def test_excel_listing_keeps_normalized_facts_and_gallery(client):
    with SessionLocal() as db:
        car = repo.get_used_car(db, "car_real_01")
    assert car is not None
    assert car.make == "Mercedes Benz"
    assert car.model == "A-Class"
    assert car.trim == "A180"
    assert car.engine_cc == 1_600
    assert car.color == "Metallic Grey"
    assert car.monthly_payment_kes == 45_481
    assert car.finance_term_months == 60
    assert car.source_listing_id == "7614"
    assert car.source_url.startswith("https://www.carduka.com/cars/")
    assert len(car.image_urls) >= 3
    assert all("prodapi.ncbagroup.com" in url for url in car.image_urls)


def test_agent_selects_engine_and_images_from_allowlisted_facts(client, auth):
    sid = "sess-rich-facts"
    search = sse.chat(
        client, auth, "Find a Mercedes Benz A-Class under 2M", sid
    )
    cars = next(
        component for component in sse.components(search)
        if component["type"] == "car_card_list"
    )["props"]["cars"]
    assert cars[0]["id"] == "car_real_01"

    detail = sse.chat(client, auth, "What is its CC, and show me the pictures?", sid)
    component = next(
        item for item in sse.components(detail) if item["type"] == "vehicle_detail"
    )
    assert component["props"]["facts"]["engine"]["engine_cc"] == 1_600
    assert component["props"]["facts"]["images"]["image_count"] >= 3
    assert len(component["props"]["image_urls"]) >= 3
    completed = [
        data for event, data in detail
        if event == "tool"
        and data["name"] == "select_vehicle_facts"
        and data["status"] == "completed"
    ]
    assert completed
    assert set(completed[0]["detail"]["fields"]) >= {"engine", "images"}
