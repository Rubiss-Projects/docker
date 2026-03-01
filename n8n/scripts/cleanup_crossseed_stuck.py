#!/usr/bin/env python3
"""Clean up stuck cross-seed torrents from Transmission.

Removes stopped torrents injected by cross-seed that failed piece verification
(0% or near-0% completion) and are stuck because autoResumeMaxDownload blocked
them from resuming.

Also cleans up corresponding .torrent files from cross-seed's output directory
to prevent re-injection on the next scan cycle.

Usage:
    python3 cleanup_crossseed_stuck.py [--dry-run] [--max-percent 5] [--grace-hours 1]
    python3 cleanup_crossseed_stuck.py --json --rpc-url http://transmission:9091/transmission/rpc/
"""

import argparse
import json
import os
import sys
import time
import urllib.request

DEFAULT_RPC_URL = "http://localhost:9091/transmission/rpc/"
DEFAULT_CROSS_SEED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cross-seed", "config", "cross-seeds",
)


def get_session_id(rpc_url):
    """Get Transmission session ID via CSRF handshake."""
    try:
        urllib.request.urlopen(rpc_url)
    except urllib.error.HTTPError as e:
        sid_header = e.headers.get("X-Transmission-Session-Id")
        if sid_header:
            return sid_header
    except Exception as e:
        error_str = str(e)
        if "X-Transmission-Session-Id" in error_str:
            return error_str.split("X-Transmission-Session-Id: ")[1].split("<")[0].strip()
    raise RuntimeError("Failed to get Transmission session ID. Is Transmission running?")


def rpc_call(rpc_url, session_id, method, arguments=None):
    """Make a Transmission RPC call."""
    payload = {"method": method}
    if arguments:
        payload["arguments"] = arguments
    req = urllib.request.Request(
        rpc_url,
        data=json.dumps(payload).encode(),
        headers={
            "X-Transmission-Session-Id": session_id,
            "Content-Type": "application/json",
        },
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("result") != "success":
        raise RuntimeError(f"RPC call failed: {resp}")
    return resp.get("arguments", {})


def find_stuck_torrents(rpc_url, session_id, max_percent, grace_seconds):
    """Find stopped cross-seed torrents below the completion threshold."""
    fields = [
        "id", "name", "status", "percentDone",
        "labels", "hashString", "addedDate",
    ]
    result = rpc_call(rpc_url, session_id, "torrent-get", {"fields": fields})

    now = time.time()
    stuck = []

    for t in result.get("torrents", []):
        # status 0 = stopped
        if t["status"] != 0:
            continue

        # Must have a cross-seed label
        labels = t.get("labels", [])
        if not any("cross-seed" in label.lower() for label in labels):
            continue

        # Must be below completion threshold
        if t["percentDone"] * 100 > max_percent:
            continue

        # Must be older than grace period
        age = now - t.get("addedDate", now)
        if age < grace_seconds:
            continue

        stuck.append(t)

    return stuck


def remove_torrents(rpc_url, session_id, torrent_ids):
    """Remove torrents from Transmission with local data deletion."""
    rpc_call(rpc_url, session_id, "torrent-remove", {
        "ids": torrent_ids,
        "delete-local-data": True,
    })


def cleanup_torrent_files(cross_seed_dir, hashes):
    """Remove .torrent files from cross-seed output directory matching given hashes."""
    if not os.path.isdir(cross_seed_dir):
        print(f"  Warning: cross-seed directory not found: {cross_seed_dir}")
        return 0

    removed = 0
    for filename in os.listdir(cross_seed_dir):
        lower_name = filename.lower()
        for h in hashes:
            if h.lower() in lower_name:
                filepath = os.path.join(cross_seed_dir, filename)
                try:
                    os.remove(filepath)
                    print(f"  Removed: {filename}")
                    removed += 1
                except OSError as e:
                    print(f"  Failed to remove {filename}: {e}")
                break

    return removed


def main():
    parser = argparse.ArgumentParser(
        description="Clean up stuck cross-seed torrents from Transmission",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be removed without actually removing",
    )
    parser.add_argument(
        "--max-percent", type=float, default=5.0,
        help="Max completion %% to consider stuck (default: 5)",
    )
    parser.add_argument(
        "--grace-hours", type=float, default=1.0,
        help="Minimum hours since added before eligible for cleanup (default: 1)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output results as JSON (for n8n workflow integration)",
    )
    parser.add_argument(
        "--rpc-url", type=str, default=DEFAULT_RPC_URL,
        help=f"Transmission RPC URL (default: {DEFAULT_RPC_URL})",
    )
    parser.add_argument(
        "--cross-seed-dir", type=str, default=DEFAULT_CROSS_SEED_DIR,
        help=f"Cross-seed torrents output directory (default: auto-detect)",
    )
    args = parser.parse_args()

    grace_seconds = args.grace_hours * 3600

    if not args.json_output:
        print("Cross-seed stuck torrent cleanup")
        print(f"  Max completion: {args.max_percent}%")
        print(f"  Grace period:   {args.grace_hours}h")
        print(f"  Dry run:        {args.dry_run}")
        print()

    try:
        session_id = get_session_id(args.rpc_url)
    except RuntimeError as e:
        if args.json_output:
            print(json.dumps({"error": str(e), "removed": [], "count": 0}))
            return
        else:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    stuck = find_stuck_torrents(args.rpc_url, session_id, args.max_percent, grace_seconds)

    if not stuck:
        if args.json_output:
            print(json.dumps({"removed": [], "count": 0}))
        else:
            print("No stuck cross-seed torrents found.")
        return

    if not args.json_output:
        print(f"Found {len(stuck)} stuck torrent(s):")
        for t in stuck:
            age_hours = (time.time() - t.get("addedDate", 0)) / 3600
            print(f"  [{t['id']:>4}] {t['percentDone']*100:5.1f}% | {age_hours:6.1f}h old | {t['name']}")
        print()

    if args.dry_run:
        if args.json_output:
            removed_list = [
                {
                    "id": t["id"],
                    "name": t["name"],
                    "percentDone": round(t["percentDone"] * 100, 1),
                    "hashString": t["hashString"],
                    "ageHours": round((time.time() - t.get("addedDate", 0)) / 3600, 1),
                }
                for t in stuck
            ]
            print(json.dumps({"removed": removed_list, "count": len(removed_list), "dryRun": True}))
        else:
            print("Dry run — no changes made.")
        return

    # Remove from Transmission
    ids = [t["id"] for t in stuck]
    hashes = [t["hashString"] for t in stuck]

    if not args.json_output:
        print(f"Removing {len(ids)} torrent(s) from Transmission...")
    remove_torrents(args.rpc_url, session_id, ids)
    if not args.json_output:
        print("  Done.")

    # Clean up .torrent files
    if not args.json_output:
        print(f"Cleaning up .torrent files from cross-seed output directory...")
    torrent_files_removed = cleanup_torrent_files(args.cross_seed_dir, hashes)
    if not args.json_output:
        print(f"  Cleaned up {torrent_files_removed} .torrent file(s).")
        print(f"\nCleanup complete: {len(ids)} torrent(s) removed.")
    else:
        removed_list = [
            {
                "id": t["id"],
                "name": t["name"],
                "percentDone": round(t["percentDone"] * 100, 1),
                "hashString": t["hashString"],
                "ageHours": round((time.time() - t.get("addedDate", 0)) / 3600, 1),
            }
            for t in stuck
        ]
        print(json.dumps({
            "removed": removed_list,
            "count": len(removed_list),
            "torrentFilesCleaned": torrent_files_removed,
        }))


if __name__ == "__main__":
    main()
