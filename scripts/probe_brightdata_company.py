#!/usr/bin/env python3
"""Probe Bright Data LinkedIn Company dataset for company_size."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

COMPANY_DATASET_ID = "gd_l1vikfnt1wgvvqz95w"


async def main() -> int:
    import httpx

    api_key = os.getenv("BRIGHTDATA_API_KEY")
    if not api_key:
        print("BRIGHTDATA_API_KEY missing")
        return 1

    company_url = "https://www.linkedin.com/company/unity/"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    trigger_url = "https://api.brightdata.com/datasets/v3/trigger"
    params = {
        "dataset_id": COMPANY_DATASET_ID,
        "include_errors": "true",
        "type": "url_collection",
    }

    print(f"Triggering company scrape for: {company_url}")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(trigger_url, params=params, headers=headers, json=[{"url": company_url}])
        print("Trigger status:", resp.status_code)
        if resp.status_code != 200:
            print(resp.text[:500])
            return 1
        snapshot_id = resp.json().get("snapshot_id")
        print("Snapshot:", snapshot_id)

        progress_url = f"https://api.brightdata.com/datasets/v3/progress/{snapshot_id}"
        for _ in range(60):
            await asyncio.sleep(5)
            prog = await client.get(progress_url, headers=headers)
            status = prog.json().get("status")
            print("Status:", status)
            if status == "ready":
                break
            if status == "failed":
                print("Failed")
                return 1

        snap = await client.get(
            f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}",
            headers=headers,
        )
        print("Snapshot HTTP:", snap.status_code)
        data = snap.json()
        if isinstance(data, list):
            row = data[0] if data else {}
        else:
            row = data
        size_fields = {
            k: row.get(k)
            for k in sorted(row.keys())
            if any(t in k.lower() for t in ("size", "employee", "staff"))
        }
        print("Size-related fields:", json.dumps(size_fields, ensure_ascii=False, indent=2))
        print("Sample keys:", sorted(row.keys())[:20], "...")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
