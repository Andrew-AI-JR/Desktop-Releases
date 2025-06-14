import os
import requests
import pytest

BACKEND_BASE = os.getenv("BACKEND_URL", "https://junior-api-915940312680.us-west1.run.app").rstrip("/")
LOGIN_URL = f"{BACKEND_BASE}/api/users/token"
USAGE_URL = f"{BACKEND_BASE}/api/subscription/usage"

EMAIL = os.getenv("BACKEND_EMAIL")
PASSWORD = os.getenv("BACKEND_PASSWORD")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

def login() -> str:
    if not EMAIL or not PASSWORD:
        pytest.skip("BACKEND_EMAIL/BACKEND_PASSWORD env vars not set")
    resp = requests.post(LOGIN_URL, json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    resp.raise_for_status()
    return resp.json()["access_token"]


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_subscription_usage():
    token = ACCESS_TOKEN or login()
    resp = requests.get(USAGE_URL, headers=auth_headers(token), timeout=10)
    assert resp.status_code == 200, f"expected 200 got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "daily_usage" in data and "monthly_usage" in data
    print("Subscription usage:", data) 