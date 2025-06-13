import os
import json
import datetime
import requests

BACKEND_BASE = os.getenv("BACKEND_URL", "https://junior-api-915940312680.us-west1.run.app").rstrip("/")
LOGIN_URL = f"{BACKEND_BASE}/api/users/token"
GENERATE_URL = f"{BACKEND_BASE}/api/comments/generate"

EMAIL = os.getenv("BACKEND_EMAIL")
PASSWORD = os.getenv("BACKEND_PASSWORD")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

TEST_POST_TEXT = "Great news – our data platform just ingested its trillionth record! We're hiring engineers to help us scale even further."

def _login():
    if not EMAIL or not PASSWORD:
        raise RuntimeError("BACKEND_EMAIL and BACKEND_PASSWORD env vars must be set to obtain a token")
    resp = requests.post(LOGIN_URL, json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("access_token")


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_generate_comment():
    """Round-trip: get token (if necessary) and hit /comments/generate."""
    token = ACCESS_TOKEN or _login()

    payload = {
        "post_text": TEST_POST_TEXT,
        "source_linkedin_url": "https://linkedin.com/posts/XYZ",
        "comment_date": datetime.datetime.utcnow().isoformat() + "Z",
    }

    resp = requests.post(GENERATE_URL, json=payload, headers=_auth_headers(token), timeout=30)

    # Useful debug on failure
    if resp.status_code != 200:
        print("Status:", resp.status_code)
        print("Body :", resp.text)
    assert resp.status_code == 200, "/api/comments/generate did not return 200"

    data = resp.json()
    assert "comment" in data and data["comment"], "Response JSON missing `comment` text"
    print("Generated comment:\n", json.dumps(data, indent=2)) 