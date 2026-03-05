#!/usr/bin/env python3
"""
Sync model pricing from upstream LiteLLM cost map.

Pulls the latest model_prices_and_context_window.json from BerriAI/litellm
on GitHub, validates it, and updates the vendored copy in agentcost/cost/.

Usage:
    # Sync from upstream (default: LiteLLM main branch)
    python -m agentcost.cost.sync_upstream

    # Sync from a specific branch/tag (pin to known-good version)
    python -m agentcost.cost.sync_upstream --ref v1.82.0

    # Dry-run: show what would change without writing
    python -m agentcost.cost.sync_upstream --dry-run

    # Sync from a local file (e.g. manually downloaded)
    python -m agentcost.cost.sync_upstream --file /path/to/downloaded.json

Design:
    - Validates JSON before writing (prevents the Feb 2026 LiteLLM incident)
    - Generates a diff summary: models added/removed/price-changed
    - Never overwrites overrides.json (that's user-controlled)
    - Keeps a .sync_meta.json with last sync timestamp and commit SHA
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).parent
_TARGET = _DATA_DIR / "model_prices.json"
_META = _DATA_DIR / ".sync_meta.json"

UPSTREAM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/{ref}/"
    "model_prices_and_context_window.json"
)
DEFAULT_REF = "main"


def _fetch_url(url: str) -> bytes:
    """Fetch URL content. Uses urllib (stdlib) to avoid external deps."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agentcost-sync/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.URLError as e:
        print(f"ERROR: Failed to fetch {url}: {e}", file=sys.stderr)
        sys.exit(1)


def _validate(data: dict) -> list[str]:
    """Validate cost map structure. Returns list of warnings."""
    warnings = []

    if not isinstance(data, dict):
        warnings.append("Root is not a dict")
        return warnings

    if len(data) < 100:
        warnings.append(f"Suspiciously small: only {len(data)} entries (expected 2000+)")

    # Spot-check some well-known models
    expected = ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4-5-20250929"]
    for m in expected:
        if m not in data:
            warnings.append(f"Missing expected model: {m}")

    # Check a few entries have required fields
    sample_count = 0
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        if sample_count >= 10:
            break
        if "input_cost_per_token" not in val and "output_cost_per_token" not in val:
            warnings.append(f"Entry '{key}' missing cost fields")
        sample_count += 1

    return warnings


def _diff_summary(old: dict, new: dict) -> dict:
    """Compare old and new cost maps. Returns summary of changes."""
    old_keys = {k for k, v in old.items() if isinstance(v, dict)}
    new_keys = {k for k, v in new.items() if isinstance(v, dict)}

    added = new_keys - old_keys
    removed = old_keys - new_keys
    common = old_keys & new_keys

    price_changed = []
    for k in common:
        old_in = old[k].get("input_cost_per_token", 0)
        new_in = new[k].get("input_cost_per_token", 0)
        old_out = old[k].get("output_cost_per_token", 0)
        new_out = new[k].get("output_cost_per_token", 0)
        if old_in != new_in or old_out != new_out:
            price_changed.append(k)

    return {
        "added": sorted(added),
        "removed": sorted(removed),
        "price_changed": sorted(price_changed),
        "total_old": len(old_keys),
        "total_new": len(new_keys),
    }


def sync(
    ref: str = DEFAULT_REF,
    dry_run: bool = False,
    file_path: str | None = None,
) -> dict:
    """
    Sync model pricing from upstream.

    Returns:
        Dict with sync result: {status, diff, warnings}
    """
    # Load new data
    if file_path:
        print(f"Loading from local file: {file_path}")
        with open(file_path) as f:
            raw = f.read()
    else:
        url = UPSTREAM_URL.format(ref=ref)
        print(f"Fetching from: {url}")
        raw = _fetch_url(url).decode("utf-8")

    # Parse and validate
    try:
        new_data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        return {"status": "error", "error": f"Invalid JSON: {e}"}

    warnings = _validate(new_data)
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")

    # Load current data for diff
    old_data = {}
    if _TARGET.exists():
        try:
            with open(_TARGET) as f:
                old_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    diff = _diff_summary(old_data, new_data)

    print(f"\nDiff summary:")
    print(f"  Models before: {diff['total_old']}")
    print(f"  Models after:  {diff['total_new']}")
    print(f"  Added:         {len(diff['added'])}")
    print(f"  Removed:       {len(diff['removed'])}")
    print(f"  Price changed: {len(diff['price_changed'])}")

    if diff["added"] and len(diff["added"]) <= 20:
        print(f"\n  New models: {', '.join(diff['added'][:20])}")
    if diff["price_changed"] and len(diff["price_changed"]) <= 10:
        print(f"  Price changes: {', '.join(diff['price_changed'][:10])}")

    if dry_run:
        print("\n[DRY RUN] No files written.")
        return {"status": "dry_run", "diff": diff, "warnings": warnings}

    # Write updated cost map
    with open(_TARGET, "w") as f:
        json.dump(new_data, f, indent=2, sort_keys=True)

    # Write sync metadata
    meta = {
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "ref": ref,
        "source": file_path or UPSTREAM_URL.format(ref=ref),
        "model_count": len(new_data),
        "added": len(diff["added"]),
        "removed": len(diff["removed"]),
        "price_changed": len(diff["price_changed"]),
    }
    with open(_META, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nSynced {len(new_data)} models to {_TARGET.name}")
    return {"status": "ok", "diff": diff, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(
        description="Sync model pricing from upstream LiteLLM"
    )
    parser.add_argument(
        "--ref",
        default=DEFAULT_REF,
        help="Git ref to fetch from (default: main)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show diff without writing files",
    )
    parser.add_argument(
        "--file",
        help="Sync from a local JSON file instead of GitHub",
    )
    args = parser.parse_args()
    sync(ref=args.ref, dry_run=args.dry_run, file_path=args.file)


if __name__ == "__main__":
    main()
