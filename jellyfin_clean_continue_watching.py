#!/usr/bin/env python3
"""
Clean up "Continue Watching" from Jellyfin.

Supports:
  - Dry run mode (--dry-run) to preview changes without modifying anything.
  - Interactive mode (-i / --interactive) to prompt for each item individually.
  - Reset ticks mode (--mode reset-ticks, default): resets playback position to 0
    so the item drops off "Continue Watching" WITHOUT triggering Trakt watch history sync.
  - Mark played mode (--mode mark-played): marks the item as fully played.
  - Filtering by minimum watched percentage (--min-percent, e.g. only episodes >85% completed).
  - Filtering by item type (--type Episode, Movie, All).
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def make_request(url: str, api_key: str, method: str = "GET", data: dict = None):
    # Attach ApiKey query parameter as fallback in case reverse proxies strip Authorization headers
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    if "ApiKey" not in qs and "api_key" not in qs:
        qs["ApiKey"] = [api_key]
        new_query = urllib.parse.urlencode(qs, doseq=True)
        url = urllib.parse.urlunparse(parsed._replace(query=new_query))

    # Pass modern MediaBrowser Authorization header and legacy X-Emby-Token
    headers = {
        "Authorization": f'MediaBrowser Client="CleanContinueWatching", Device="Script", DeviceId="clean-cw-cli", Version="1.0.0", Token="{api_key}"',
        "X-Emby-Token": api_key,
        "Accept": "application/json",
    }
    encoded_data = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        encoded_data = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read()
            if content:
                return json.loads(content.decode("utf-8"))
            return {}
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        if err.code == 401:
            print(
                f"[-] HTTP 401 Unauthorized when requesting: {url}\n"
                "    Check that:\n"
                "    1. The API key is valid (Dashboard -> Advanced -> API Keys).\n"
                "    2. If your API key is not an Administrator, pass '--user-id <YOUR_USER_ID>' explicitly\n"
                "       (fetching /Users requires admin privileges).\n"
                "    3. If behind a reverse proxy (Caddy/Nginx), ensure headers are forwarded.",
                file=sys.stderr,
            )
        else:
            print(f"[-] HTTP Error {err.code}: {err.reason} - {err_body}", file=sys.stderr)
        raise
    except urllib.error.URLError as err:
        print(f"[-] Connection Error: {err.reason}", file=sys.stderr)
        raise


def get_user_id(server_url: str, api_key: str, user_id: str = None) -> str:
    """Validate or auto-discover user ID."""
    if user_id:
        return user_id.replace("-", "").strip()

    # Try auto-detecting users
    try:
        users = make_request(f"{server_url}/Users", api_key)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print(
                "\n[!] Could not auto-detect users via /Users (401/403).\n"
                "    This happens if your API key is not an administrator.\n"
                "    Fix: Pass --user-id <YOUR_USER_ID> directly.\n"
                "    (Find it in Jellyfin Web by clicking your user icon; the URL will show ?userId=...)\n",
                file=sys.stderr,
            )
        sys.exit(1)

    if not users:
        print("[-] Could not retrieve users. Please specify --user-id manually.", file=sys.stderr)
        sys.exit(1)

    if len(users) == 1:
        selected = users[0]
        print(f"[*] Auto-selected user: {selected.get('Name')} ({selected.get('Id')})")
        return selected["Id"]

    print("[!] Multiple users found. Please specify --user-id from the following list:")
    for u in users:
        print(f"    - {u.get('Name')}: {u.get('Id')}")
    sys.exit(1)


def format_title(item: dict) -> str:
    """Format human-readable title for episode or movie."""
    item_type = item.get("Type", "Item")
    if item_type == "Episode":
        series = item.get("SeriesName", "Unknown Series")
        season = item.get("ParentIndexNumber")
        episode = item.get("IndexNumber")
        ep_name = item.get("Name", "Untitled")
        s_str = f"S{season:02d}" if season is not None else "S??"
        e_str = f"E{episode:02d}" if episode is not None else "E??"
        return f"[Episode] {series} - {s_str}{e_str} - {ep_name}"
    elif item_type == "Movie":
        year = item.get("ProductionYear")
        year_str = f" ({year})" if year else ""
        return f"[Movie] {item.get('Name', 'Untitled')}{year_str}"
    return f"[{item_type}] {item.get('Name', 'Untitled')}"


def main():
    parser = argparse.ArgumentParser(
        description="Clean up Jellyfin Continue Watching / Resume items with Trakt-safe options."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("JELLYFIN_URL", "http://localhost:8096"),
        help="Jellyfin server base URL (default: env JELLYFIN_URL or http://localhost:8096)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("JELLYFIN_API_KEY"),
        help="Jellyfin API Key (default: env JELLYFIN_API_KEY)",
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get("JELLYFIN_USER_ID"),
        help="Jellyfin User ID (default: env JELLYFIN_USER_ID or auto-detected if only 1 user)",
    )
    parser.add_argument(
        "--mode",
        choices=["reset-ticks", "mark-played"],
        default="reset-ticks",
        help=(
            "Action to take: 'reset-ticks' (default, Trakt-safe; clears resume progress without marking played), "
            "or 'mark-played' (marks item as watched, which may trigger Trakt sync)."
        ),
    )
    parser.add_argument(
        "--type",
        choices=["All", "Movie", "Episode"],
        default="All",
        help="Item type to clean up: 'All' (default, movies and episodes), 'Movie', or 'Episode'",
    )
    parser.add_argument(
        "--min-percent",
        type=float,
        default=0.0,
        help="Only target items watched past this percentage threshold (0-100, default: 0 = all)",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Prompt before processing each item individually (y/N/a/q).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview matching items and actions without modifying anything on the server.",
    )

    args = parser.parse_args()

    if not args.api_key:
        parser.error("API key is required. Pass --api-key or set JELLYFIN_API_KEY.")

    server_url = args.url.rstrip("/")
    user_id = get_user_id(server_url, args.api_key, args.user_id)

    # Fetch resume items
    query_params = {"MediaTypes": "Video"}
    if args.type in ("Episode", "Movie"):
        query_params["IncludeItemTypes"] = args.type
    elif args.type == "All":
        query_params["IncludeItemTypes"] = "Movie,Episode"

    qs = urllib.parse.urlencode(query_params)
    resume_url = f"{server_url}/Users/{user_id}/Items/Resume?{qs}"

    print(f"[*] Querying resume items from {server_url}...")
    try:
        res = make_request(resume_url, args.api_key)
    except Exception as e:
        print(f"[-] Failed to fetch resume items: {e}", file=sys.stderr)
        sys.exit(1)

    items = res.get("Items", [])
    if not items:
        print("[+] No resume items found in Continue Watching.")
        return

    # Filter items based on min_percent and type
    matched_items = []
    for item in items:
        user_data = item.get("UserData", {})
        pos_ticks = user_data.get("PlaybackPositionTicks", 0)
        run_ticks = item.get("RunTimeTicks", 0)
        pct = (pos_ticks / run_ticks * 100) if run_ticks > 0 else 0.0

        if pct < args.min_percent:
            continue

        matched_items.append((item, pct))

    if not matched_items:
        print(f"[+] Found {len(items)} items in Continue Watching, but none met the criteria (min-percent: {args.min_percent}%).")
        return

    action_label = "RESET RESUME TICKS (Trakt-safe)" if args.mode == "reset-ticks" else "MARK AS PLAYED"
    prefix = "[DRY RUN] Would perform" if args.dry_run else "[ACTION] Performing"

    print(f"\nTargeting {len(matched_items)} item(s) (Mode: {args.mode}):\n" + "-" * 70)

    all_confirmed = False
    updated_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, (item, pct) in enumerate(matched_items, 1):
        item_id = item["Id"]
        title = format_title(item)
        print(f"[{idx}/{len(matched_items)}] {title}")
        print(f"    Item ID:    {item_id}")
        print(f"    Progress:   {pct:.1f}%")

        if args.interactive and not all_confirmed:
            try:
                prompt_desc = f"{action_label.lower()} (dry run)" if args.dry_run else action_label.lower()
                choice = input(f"    -> {prompt_desc}? [y/N/a/q]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n[!] Aborted by user.")
                return

            if choice in ("q", "quit"):
                print("\n[!] Aborted by user.")
                return
            elif choice in ("a", "all"):
                all_confirmed = True
            elif choice not in ("y", "yes"):
                print("    -> Skipped.\n")
                skipped_count += 1
                continue

        if args.dry_run:
            print(f"    -> {prefix} {action_label} (no changes made).\n")
            updated_count += 1
            continue

        try:
            if args.mode == "reset-ticks":
                url = f"{server_url}/UserItems/{item_id}/UserData?userId={user_id}"
                make_request(url, args.api_key, method="POST", data={"PlaybackPositionTicks": 0})
            elif args.mode == "mark-played":
                url = f"{server_url}/Users/{user_id}/PlayedItems/{item_id}"
                make_request(url, args.api_key, method="POST")
            print(f"    -> Successfully applied: {action_label}!\n")
            updated_count += 1
        except Exception as e:
            print(f"    -> Failed: {e}\n", file=sys.stderr)
            failed_count += 1

    print("-" * 70)
    if args.dry_run:
        print(f"[*] Dry run complete. {updated_count} item(s) would be cleared, {skipped_count} skipped.")
        print("[*] Re-run without --dry-run to apply these changes.")
    else:
        print(f"[+] Complete. {updated_count} item(s) processed, {skipped_count} skipped.")
        if failed_count > 0:
            print(f"[!] {failed_count} item(s) encountered errors.")


if __name__ == "__main__":
    main()
