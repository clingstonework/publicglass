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
            release_contracts = release.get("contracts", [])
            parties = release.get("parties", [])

            # Agency is the party with role "procuringEntity"
            agency = ""
            for party in parties:
                if "procuringEntity" in party.get("roles", []):
                    agency = party.get("name", "")
                    break

            # Supplier from first award
            supplier_name = ""
            if awards:
                suppliers = awards[0].get("suppliers", [])
                supplier_name = suppliers[0].get("name", "") if suppliers else ""

            # Title, value, and dates are in the contracts array
            contract = release_contracts[0] if release_contracts else {}
            title = contract.get("description", "")
            period = contract.get("period", {})
            value_raw = contract.get("value", {}).get("amount", 0)
            try:
                value_aud = float(value_raw) if value_raw else 0
            except (ValueError, TypeError):
                value_aud = 0

            start_date = period.get("startDate", "")[:10] if period.get("startDate") else ""
            end_date = period.get("endDate", "")[:10] if period.get("endDate") else ""

            contracts.append({
                "id": contract.get("id") or release.get("ocid", ""),
                "title": title,
                "agency": agency,
                "supplier": supplier_name,
                "value_aud": value_aud,
                "published": release.get("date", "")[:10],
                "start_date": start_date,
                "end_date": end_date,
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
        "contracts": contracts[:200]
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved {len(contracts)} contracts to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
