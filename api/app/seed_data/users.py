"""Two pre-seeded demo users. Passwords are demo-only and intentionally simple."""
from __future__ import annotations

# (username, password) the login screen quick-selects.
DEMO_CREDENTIALS = {
    "david": "demo1234",
    "sarah": "demo1234",
}

USERS = [
    {
        "id": "usr_david",
        "username": "david",
        "full_name": "David Mwangi",
        "location": "Nairobi",
        "password": "demo1234",
        "profile_context": (
            "Budget around KES 3,000,000. Prefers SUVs and station wagons for family use. "
            "Has been browsing Subaru Foresters."
        ),
    },
    {
        "id": "usr_sarah",
        "username": "sarah",
        "full_name": "Sarah Wanjiru",
        "location": "Kiambu",
        "password": "demo1234",
        "profile_context": (
            "Wants to sell her 2016 Toyota Fielder. New to the marketplace; may also browse "
            "upgrades afterwards."
        ),
    },
]
