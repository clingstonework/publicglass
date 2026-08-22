#!/usr/bin/env python3
"""
Fetch recent contract notices from AusTender OCDS API.
Saves to src/_data/contracts.json for use by 11ty.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
import os
import sys

API_BASE = "https://api.tenders.gov.au/ocds/findByDates/contractPublished"
DAYS_BACK = 30
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "../src/_data/contracts.json")


def fetch_contracts(from_date, to_date):
    url = f"{API_BASE}/{from_date}/{to_date}"
    print(f"Fetching: {url}")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def extract_contracts(raw):
    """Flatten OCDS releases into simple contract records."""
    contracts = []
    releases = raw if isinstance(raw, list) else raw.get("releases", [])
    for release in releases:
        try:
            awards = release.get("awards", [])
            tender = release.get("tender", {})
            buyer = release.get("buyer", {})
            for award in awards:
                suppliers = award.get("suppliers", [])
                supplier_name = suppliers[0].get("name", "") if suppliers else ""
                value = award.get("value", {})
                contracts.append({
                    "id": release.get("ocid", ""),
                    "title": tender.get("title") or award.get("title", ""),
                    "agency": buyer.get("name", ""),
                    "supplier": supplier_name,
                    "value_aud": value.get("amount", 0),
                    "published": release.get("date", "")[:10],
                    "start_date": award.get("contractPeriod", {}).get("startDate", "")[:10] if award.get("contractPeriod", {}).get("startDate") else "",
                    "end_date": award.get("contractPeriod", {}).get("endDate", "")[:10] if award.get("contractPeriod", {}).get("endDate") else "",
                })
        except Exception:
            continue
    return contracts


def main():
    now = datetime.now(timezone.utc)
    from_dt = (now - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT00:00:00Z")
    to_dt = now.strftime("%Y-%m-%dT23:59:59Z")

    raw = fetch_contracts(from_dt, to_dt)
    if raw is None:
        print("Failed to fetch data. Aborting.", file=sys.stderr)
        sys.exit(1)

    contracts = extract_contracts(raw)

    # Sort by value descending
    contracts.sort(key=lambda c: c["value_aud"] or 0, reverse=True)

    output = {
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "from_date": from_dt[:10],
        "to_date": to_dt[:10],
        "total": len(contracts),
        "contracts": contracts[:200]  # cap at 200 records
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved {len(contracts)} contracts to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
