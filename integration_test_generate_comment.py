#!/usr/bin/env python3
"""Standalone integration test for /api/comments/generate.

Usage examples:
  python integration_test_generate_comment.py \
        --email you@example.com --password secret

  ACCESS_TOKEN=xyz python integration_test_generate_comment.py

Required:
  Either set ACCESS_TOKEN env-var or pass --email and --password so the script
  can obtain a token via /api/users/token.
"""
import os
import sys
import json
import argparse
import datetime as dt
from typing import Optional

import requests

BACKEND_BASE = os.getenv("BACKEND_URL", "https://junior-api-915940312680.us-west1.run.app").rstrip("/")
LOGIN_URL     = f"{BACKEND_BASE}/api/users/token"
GENERATE_URL  = f"{BACKEND_BASE}/api/comments/generate"

SAMPLE_POST = (
    "Exciting times ahead! Our AI division just closed a major funding round "
    "and we're hiring NLP and data-engineering experts to scale the platform."
)

def get_token(email: str, password: str) -> str:
    resp = requests.post(LOGIN_URL, json={"email": email, "password": password}, timeout=20)
    if resp.status_code != 200:
        print("Login failed:", resp.status_code, resp.text, file=sys.stderr)
        sys.exit(1)
    return resp.json().get("access_token")


def call_generate(token: str, post_text: str) -> requests.Response:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "post_text": post_text,
        "source_linkedin_url": "https://linkedin.com/posts/placeholder",
        "comment_date": dt.datetime.utcnow().isoformat() + "Z",
    }
    return requests.post(GENERATE_URL, json=payload, headers=headers, timeout=30)


def main(argv: Optional[list] = None):
    parser = argparse.ArgumentParser(description="Integration test for /comments/generate")
    parser.add_argument("--email", help="Backend email (if no ACCESS_TOKEN env var)")
    parser.add_argument("--password", help="Backend password (if no ACCESS_TOKEN env var)")
    parser.add_argument("--post", help="Custom post text to feed the generator")
    args = parser.parse_args(argv)

    token = os.getenv("ACCESS_TOKEN")
    if not token:
        if not (args.email and args.password):
            parser.error("Provide --email & --password or set ACCESS_TOKEN env var")
        token = get_token(args.email, args.password)
        print("✅ Obtained token via /users/token")
    else:
        print("✅ Using ACCESS_TOKEN from environment")

    post_text = args.post or SAMPLE_POST
    resp = call_generate(token, post_text)
    print("Status:", resp.status_code)
    if resp.headers.get("Content-Type", "").startswith("application/json"):
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    else:
        print(resp.text)

    if resp.status_code != 200:
        sys.exit(1)


if __name__ == "__main__":
    main() 