#!/usr/bin/env python3
"""
Fetch contract notices from AusTender OCDS API for the current Australian financial year.
Saves to src/_data/contracts.json for use by 11ty.
"""

import json
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
import os
import sys

API_BASE = "https://api.tenders.gov.au/ocds/findByDates/contractPublished"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "../src/_data/contracts.json")

# Max contracts to display per month (by value, descending)
MAX_PER_MONTH = 200


def fetch_contracts(from_date, to_date):
    url = f"{API_BASE}/{from_date}/{to_date}"
    print(f"Fetching: {url}")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
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

            # Build the AusTender website URL from the award UUID
            url_id = ""
            if awards:
                award_id = awards[0].get("id", "")
                # award_id format: "CN4265965-e7b05659e78b4bbd93f5f6f3c6b8bd77"
                parts = award_id.split("-", 1)
                if len(parts) == 2 and len(parts[1]) == 32:
                    h = parts[1]
                    url_id = f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

            published = release.get("date", "")[:10]
            month_key = published[:7] if published else ""  # e.g. "2026-08"

            contracts.append({
                "id": contract.get("id") or release.get("ocid", ""),
                "url_id": url_id,
                "title": title,
                "agency": agency,
                "supplier": supplier_name,
                "value_aud": value_aud,
                "published": published,
                "month": month_key,
                "start_date": start_date,
                "end_date": end_date,
            })
        except Exception:
            continue
    return contracts


def fy_weeks(now):
    """
    Return list of (from_dt, to_dt) weekly date ranges for the current Australian financial year.
    Weekly windows keep each API call well under the 100-record page limit.
    Also returns the FY label string.
    """
    from datetime import date, timedelta
    year = now.year
    month = now.month
    fy_start_year = year if month >= 7 else year - 1
    fy_label = f"{fy_start_year}-{str(fy_start_year + 1)[2:]}"

    fy_start = date(fy_start_year, 7, 1)
    today = now.date()

    weeks = []
    cursor = fy_start
    while cursor <= today:
        week_end = min(cursor + timedelta(days=6), today)
        from_dt = f"{cursor.isoformat()}T00:00:00Z"
        to_dt = f"{week_end.isoformat()}T23:59:59Z"
        weeks.append((from_dt, to_dt))
        cursor = week_end + timedelta(days=1)

    return weeks, fy_label


def month_label(month_key):
    """Convert '2026-08' to 'August 2026'."""
    try:
        return datetime.strptime(month_key, "%Y-%m").strftime("%B %Y")
    except Exception:
        return month_key


def group_by_month(contracts):
    """
    Group contracts by month. Each month gets:
      - label, count, total_value (across ALL contracts in month)
      - top MAX_PER_MONTH contracts by value for display
    Returns list sorted newest month first.
    """
    buckets = defaultdict(list)
    for c in contracts:
        buckets[c["month"]].append(c)

    months = []
    for mk in sorted(buckets.keys(), reverse=True):
        group = buckets[mk]
        total_value = sum(c["value_aud"] or 0 for c in group)
        top_contracts = sorted(group, key=lambda c: c["value_aud"] or 0, reverse=True)[:MAX_PER_MONTH]
        months.append({
            "month": mk,
            "label": month_label(mk),
            "count": len(group),
            "total_value": round(total_value, 2),
            "contracts": top_contracts,
        })
    return months


def main():
    now = datetime.now(timezone.utc)
    week_ranges, fy_label = fy_weeks(now)

    # Fetch one API call per week — keeps each call well under the 100-record page limit
    all_contracts = []
    seen_ids = set()
    for from_dt, to_dt in week_ranges:
        raw = fetch_contracts(from_dt, to_dt)
        if raw is None:
            print(f"Failed to fetch {from_dt[:10]} to {to_dt[:10]}, skipping.", file=sys.stderr)
            continue
        week_contracts = extract_contracts(raw)
        # Deduplicate in case of any overlap at week boundaries
        for c in week_contracts:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                all_contracts.append(c)

    if not all_contracts:
        print("No contract data retrieved. Aborting.", file=sys.stderr)
        sys.exit(1)

    contracts = all_contracts
    months = group_by_month(contracts)

    output = {
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fy": fy_label,
        "total": len(contracts),
        "months": months,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved {len(contracts)} contracts across {len(months)} months to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
