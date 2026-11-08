#!/usr/bin/env python3
"""
sync_jellyfin_to_trakt.py

Synchronizes missing watch history from Jellyfin to Trakt.tv:
1. Connects to Jellyfin and fetches recently played TV episodes with watch timestamps.
2. Reads your Trakt export JSON and builds an index based on IMDb ID.
3. Identifies episodes watched in Jellyfin that are missing in Trakt.
4. Uses Trakt credentials from Jellyfin's Trakt.xml (with auto-refresh / device login).
5. Adds missing scrobbles to Trakt via POST /sync/history.

Usage:
  python3 sync_jellyfin_to_trakt.py --trakt-export /path/to/trakt_history.zip --dry-run
"""

import argparse
import base64
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

# Official Jellyfin Trakt Plugin OAuth client credentials
TRAKT_API_URL = "https://api.trakt.tv"
TRAKT_CLIENT_ID = base64.b64decode("YmZkZDJlMDMyYzMwYzM1YjM2OGY5N2VmNGVjODE1ODdiODk5YmNiMDI4YjkxYTFkNGJhNTU4OWE0YjZhNzI2Nwo=")
TRAKT_CLIENT_SECRET = base64.b64decode("YmY5ZmNlMzdjZjQ1YzFkZTkxZGEwMDllN2FjNmZjYTkwNWEzNWQ3YTcxOGJmNjVhNTJmOTIxOTkwNzNhMjUwMwo=")

DEFAULT_TRAKT_CONFIG_PATHS = [
    Path.home() / ".local/share/jellyfin/plugins/configurations/Trakt.xml",
    Path("/var/lib/jellyfin/plugins/configurations/Trakt.xml"),
    Path("/config/plugins/configurations/Trakt.xml"),
    Path.home() / ".config/jellyfin/plugins/configurations/Trakt.xml",
    Path("/etc/jellyfin/plugins/configurations/Trakt.xml"),
    Path("Trakt.xml"),
]


def normalize_title(title: Optional[str]) -> str:
    """Normalize show title for comparison (strips year, punctuation, and case)."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"\(\d{4}\)$", "", t)
    t = re.sub(r"[\W_]+", " ", t)
    return t.strip()


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO 8601 string from Jellyfin or Trakt into UTC datetime."""
    clean_str = dt_str.replace("Z", "+00:00")
    # Truncate fractional seconds beyond 6 digits if needed
    if "." in clean_str:
        parts = clean_str.split(".")
        subparts = parts[1].split("+")
        frac = subparts[0][:6]
        tz = "+" + subparts[1] if len(subparts) > 1 else ""
        clean_str = f"{parts[0]}.{frac}{tz}"
    return datetime.fromisoformat(clean_str).astimezone(timezone.utc)


def format_iso_utc(dt: datetime) -> str:
    """Format datetime to Trakt-expected UTC string (YYYY-MM-DDTHH:MM:SS.000Z)."""
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def trakt_request(
    endpoint: str,
    method: str = "GET",
    token: Optional[str] = None,
    data: Optional[dict] = None
) -> Tuple[int, Any]:
    """Execute HTTP request against Trakt API."""
    url = f"{TRAKT_API_URL}{endpoint}" if endpoint.startswith("/") else endpoint
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": TRAKT_CLIENT_ID,
        "User-Agent": "JellyfinTraktSync/1.0"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
        except Exception:
            err_json = err_body
        return e.code, err_json


class TraktAuthManager:
    """Manages Trakt authentication using Jellyfin's Trakt.xml configuration or explicit tokens."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        token_override: Optional[str] = None,
        refresh_override: Optional[str] = None
    ):
        self.token_override = token_override
        self.refresh_override = refresh_override
        self.access_token: Optional[str] = token_override
        self.refresh_token: Optional[str] = refresh_override
        self.linked_user_id: Optional[str] = None
        self.token_expiration: Optional[datetime] = None

        # Only search default config if no explicit token was supplied or if explicit config was passed
        if config_path or not (token_override or refresh_override):
            self.config_path = self._locate_config(config_path)
        else:
            self.config_path = Path(config_path).expanduser().resolve() if config_path else None

    def _locate_config(self, explicit_path: Optional[str]) -> Optional[Path]:
        if explicit_path:
            p = Path(explicit_path).expanduser().resolve()
            if p.exists():
                return p
            raise FileNotFoundError(f"Specified Trakt.xml not found at: {explicit_path}")

        for candidate in DEFAULT_TRAKT_CONFIG_PATHS:
            p = candidate.expanduser().resolve()
            if p.exists():
                return p
        return None

    def load_and_authenticate(self) -> str:
        """Loads credentials and ensures a valid, active access token is returned."""
        # 1. If explicit access token provided, verify it
        if self.access_token and self._is_token_valid():
            print("✓ Active Trakt access token verified.")
            return self.access_token

        # 2. If access token is missing or expired, but refresh token is provided
        if self.refresh_token:
            print("Access token invalid or expired. Attempting refresh using refresh token...")
            if self._refresh_token():
                print("✓ Successfully refreshed Trakt token.")
                return self.access_token
            else:
                print("! Refresh token was rejected or expired.")

        # 3. If no tokens provided, read from Trakt.xml
        if self.config_path:
            print(f"Reading Trakt credentials from: {self.config_path}")
            self._read_xml()

            if self.access_token and self._is_token_valid():
                print("✓ Active Trakt access token verified from config.")
                return self.access_token

            if self.refresh_token:
                print("Config token expired. Attempting refresh using refresh token...")
                if self._refresh_token():
                    print("✓ Successfully refreshed Trakt token.")
                    return self.access_token

        # 4. If all else fails, initiate terminal device authorization flow
        print("\nNo valid Trakt credentials found. Initiating authorization flow...")
        new_token_data = self._device_code_login()
        self.access_token = new_token_data["access_token"]
        self.refresh_token = new_token_data.get("refresh_token")
        if self.config_path:
            self._save_to_xml(new_token_data)
        return self.access_token

    def _read_xml(self):
        tree = ET.parse(self.config_path)
        root = tree.getroot()
        user = root.find(".//TraktUser")
        if user is None:
            raise ValueError(f"No <TraktUser> configuration found inside {self.config_path}")

        access_elem = user.find("AccessToken")
        refresh_elem = user.find("RefreshToken")
        user_id_elem = user.find("LinkedMbUserId")
        exp_elem = user.find("AccessTokenExpiration")

        self.access_token = access_elem.text.strip() if access_elem is not None and access_elem.text else None
        self.refresh_token = refresh_elem.text.strip() if refresh_elem is not None and refresh_elem.text else None
        self.linked_user_id = user_id_elem.text.strip() if user_id_elem is not None and user_id_elem.text else None
        if exp_elem is not None and exp_elem.text:
            try:
                self.token_expiration = parse_iso_datetime(exp_elem.text.strip())
            except Exception:
                self.token_expiration = None

    def _is_token_valid(self) -> bool:
        if not self.access_token:
            return False
        status, _ = trakt_request("/users/me", method="GET", token=self.access_token)
        return status == 200

    def _refresh_token(self) -> bool:
        data = {
            "refresh_token": self.refresh_token,
            "client_id": TRAKT_CLIENT_ID,
            "client_secret": TRAKT_CLIENT_SECRET,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            "grant_type": "refresh_token"
        }
        status, res = trakt_request("/oauth/token", method="POST", data=data)
        if status == 200 and isinstance(res, dict) and "access_token" in res:
            self.access_token = res["access_token"]
            self.refresh_token = res.get("refresh_token", self.refresh_token)
            self._save_to_xml(res)
            return True
        return False

    def _device_code_login(self) -> dict:
        data = {"client_id": TRAKT_CLIENT_ID}
        status, res = trakt_request("/oauth/device/code", method="POST", data=data)
        if status != 200 or not isinstance(res, dict) or "device_code" not in res:
            raise RuntimeError(f"Failed to initiate Trakt device code authorization: {res}")

        device_code = res["device_code"]
        user_code = res["user_code"]
        url = res.get("verification_url", "https://trakt.tv/activate")
        interval = res.get("interval", 5)
        expires_in = res.get("expires_in", 600)

        print("\n" + "=" * 65)
        print("  TRAKT AUTHORIZATION REQUIRED")
        print(f"  1. Go to: {url}")
        print(f"  2. Enter code: {user_code}")
        print("=" * 65)
        print("Waiting for authorization in browser...")

        poll_data = {
            "code": device_code,
            "client_id": TRAKT_CLIENT_ID,
            "client_secret": TRAKT_CLIENT_SECRET
        }
        start = time.time()
        while time.time() - start < expires_in:
            time.sleep(interval)
            p_status, p_res = trakt_request("/oauth/device/token", method="POST", data=poll_data)
            if p_status == 200 and isinstance(p_res, dict) and "access_token" in p_res:
                print("✓ Trakt account linked successfully!")
                return p_res
            elif p_status == 400:
                continue  # Pending
            elif p_status in (404, 409, 410):
                raise RuntimeError(f"Device code expired or invalid: {p_res}")
            elif p_status == 418:
                raise RuntimeError("Authorization denied by user on Trakt.")
            elif p_status == 429:
                time.sleep(2)

        raise TimeoutError("Trakt authorization timed out.")

    def _save_to_xml(self, token_data: dict):
        if not self.config_path or not self.config_path.exists():
            return
        try:
            tree = ET.parse(self.config_path)
            root = tree.getroot()
            user = root.find(".//TraktUser")
            if user is None:
                return

            def set_text(parent, tag, val):
                elem = parent.find(tag)
                if elem is None:
                    elem = ET.SubElement(parent, tag)
                elem.text = val

            set_text(user, "AccessToken", token_data["access_token"])
            if "refresh_token" in token_data:
                set_text(user, "RefreshToken", token_data["refresh_token"])

            expires_in = token_data.get("expires_in", 7776000)
            exp_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            set_text(user, "AccessTokenExpiration", exp_dt.isoformat())

            bak_path = self.config_path.with_suffix(".xml.bak")
            if not bak_path.exists():
                shutil.copyfile(self.config_path, bak_path)

            tree.write(self.config_path, encoding="utf-8", xml_declaration=True)
            print(f"✓ Saved updated tokens to {self.config_path} (backup at {bak_path.name})")
        except Exception as e:
            print(f"! Notice: Could not write updated tokens back to {self.config_path}: {e}")


class TraktExportIndex:
    """Builds a fast lookup index from a Trakt export (supports .zip, directories, or split JSON files)."""

    def __init__(self, export_path: str):
        self.export_path = Path(export_path).expanduser().resolve()
        self.ep_imdb_set: Set[str] = set()
        self.show_imdb_s_e: Set[Tuple[str, int, int]] = set()
        self.show_title_s_e: Set[Tuple[str, int, int]] = set()
        self.total_loaded = 0
        self.files_processed = 0
        self._load()

    def _process_items(self, items: Any, source_name: str):
        if not isinstance(items, list):
            return

        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("type") and item.get("type") != "episode":
                continue
            if not item.get("episode") and not item.get("show"):
                continue

            self.total_loaded += 1
            ep = item.get("episode") or {}
            show = item.get("show") or {}

            # 1. Episode IMDb ID
            ep_imdb = (ep.get("ids") or {}).get("imdb")
            if ep_imdb:
                self.ep_imdb_set.add(str(ep_imdb).lower().strip())

            season = ep.get("season")
            number = ep.get("number")
            if season is not None and number is not None:
                s_num = int(season)
                e_num = int(number)

                # 2. Show IMDb ID + Season + Episode number
                show_imdb = (show.get("ids") or {}).get("imdb")
                if show_imdb:
                    self.show_imdb_s_e.add((str(show_imdb).lower().strip(), s_num, e_num))

                # 3. Fallback: Normalized Show Title + Season + Episode number
                show_title = show.get("title")
                if show_title:
                    norm = normalize_title(show_title)
                    if norm:
                        self.show_title_s_e.add((norm, s_num, e_num))

    def _load(self):
        if not self.export_path.exists():
            raise FileNotFoundError(f"Trakt export path not found: {self.export_path}")

        print(f"Reading Trakt export from: {self.export_path}")

        # Case 1: ZIP file containing split files (e.g. watched-history-1.json)
        if self.export_path.is_file() and (zipfile.is_zipfile(self.export_path) or self.export_path.suffix.lower() == ".zip"):
            with zipfile.ZipFile(self.export_path, "r") as z:
                json_names = [n for n in z.namelist() if n.lower().endswith(".json")]
                # Prioritize watched history files
                history_names = [n for n in json_names if "history" in n.lower()]
                target_names = history_names if history_names else json_names

                if not target_names:
                    raise ValueError(f"No JSON files found inside zip archive: {self.export_path}")

                for name in target_names:
                    with z.open(name) as f:
                        try:
                            data = json.load(f)
                            self._process_items(data, name)
                            self.files_processed += 1
                        except Exception as e:
                            print(f"! Warning: Failed to parse {name} in zip: {e}")

        # Case 2: Directory containing split JSON files
        elif self.export_path.is_dir():
            json_files = list(self.export_path.glob("*.json"))
            history_files = [p for p in json_files if "history" in p.name.lower()]
            target_files = history_files if history_files else json_files

            if not target_files:
                raise ValueError(f"No JSON files found in directory: {self.export_path}")

            for p in target_files:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._process_items(data, p.name)
                    self.files_processed += 1
                except Exception as e:
                    print(f"! Warning: Failed to parse {p.name}: {e}")

        # Case 3: Single JSON file
        elif self.export_path.is_file():
            with open(self.export_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._process_items(data, self.export_path.name)
            self.files_processed += 1

        print(f"✓ Loaded {self.total_loaded} watched episode entries across {self.files_processed} file(s).")
        print(f"  - Indexed {len(self.ep_imdb_set)} episode IMDb IDs")
        print(f"  - Indexed {len(self.show_imdb_s_e)} (Show IMDb, Season, Episode) tuples")

    def is_watched(
        self,
        ep_imdb: Optional[str],
        show_imdb: Optional[str],
        season: Optional[int],
        number: Optional[int],
        show_title: Optional[str]
    ) -> bool:
        """Returns True if the episode is present in the Trakt export."""
        # Check direct episode IMDb ID
        if ep_imdb and str(ep_imdb).lower().strip() in self.ep_imdb_set:
            return True

        # Check Show IMDb ID + Season + Episode number
        if show_imdb and season is not None and number is not None:
            if (str(show_imdb).lower().strip(), int(season), int(number)) in self.show_imdb_s_e:
                return True

        # Fallback: Normalized Show Title + Season + Episode number
        if show_title and season is not None and number is not None:
            norm = normalize_title(show_title)
            if norm and (norm, int(season), int(number)) in self.show_title_s_e:
                return True

        return False


class JellyfinClient:
    """Interacts with the Jellyfin REST API."""

    def __init__(self, base_url: str, api_key: str, user_id: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        if params:
            query = urllib.parse.urlencode({k: str(v) for k, v in params.items()})
            url = f"{url}?{query}"

        headers = {
            "Authorization": f'MediaBrowser Client="JellyfinTraktSync", Device="Script", DeviceId="jellyfin-trakt-sync", Version="1.0.0", Token="{self.api_key}"',
            "X-Emby-Token": self.api_key,
            "X-MediaBrowser-Token": self.api_key,
            "Accept": "application/json",
            "User-Agent": "JellyfinTraktSync/1.0"
        }
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8")
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            # If 401 with headers, try URL parameter fallback ?api_key=
            if e.code == 401 and "api_key=" not in url.lower():
                sep = "&" if "?" in url else "?"
                fallback_url = f"{url}{sep}api_key={urllib.parse.quote(self.api_key)}"
                try:
                    fallback_req = urllib.request.Request(fallback_url, headers=headers, method="GET")
                    with urllib.request.urlopen(fallback_req, timeout=30) as resp:
                        content = resp.read().decode("utf-8")
                        return json.loads(content) if content else {}
                except Exception:
                    pass
            raise RuntimeError(f"Jellyfin API error {e.code} on {endpoint}: {err}")
        except Exception as e:
            raise RuntimeError(f"Connection to Jellyfin failed at {self.base_url}: {e}")

    def test_connection(self):
        info = self._get("/System/Info/Public")
        server_name = info.get("ServerName", "Jellyfin Server")
        version = info.get("Version", "unknown")
        print(f"✓ Connected to Jellyfin: {server_name} (v{version})")

    def resolve_user_id(
        self,
        explicit_id: Optional[str] = None,
        explicit_name: Optional[str] = None,
        fallback_id: Optional[str] = None
    ) -> str:
        """Resolves the user ID via explicit ID, username, Trakt.xml fallback, or auto-selection."""
        if explicit_id:
            self.user_id = explicit_id
            print(f"Using specified Jellyfin User ID: {self.user_id}")
            return self.user_id

        users = self._get("/Users")
        if not isinstance(users, list):
            users = []

        # 1. Match by explicit username
        if explicit_name:
            for u in users:
                if u.get("Name", "").lower() == explicit_name.lower() or u.get("Id", "").lower() == explicit_name.lower():
                    self.user_id = u["Id"]
                    print(f"✓ Selected Jellyfin user: {u.get('Name')} (ID: {self.user_id})")
                    return self.user_id
            available = ", ".join([u.get("Name", "Unknown") for u in users])
            raise ValueError(f"User '{explicit_name}' not found on Jellyfin server. Available users: {available}")

        # 2. Match from Trakt.xml LinkedMbUserId
        if fallback_id:
            self.user_id = fallback_id
            matched_name = next((u.get("Name") for u in users if u.get("Id", "").lower() == fallback_id.lower()), None)
            display = f"{matched_name} ({fallback_id})" if matched_name else fallback_id
            print(f"✓ Selected Jellyfin user from Trakt.xml: {display}")
            return self.user_id

        # 3. Auto-select if only 1 user exists
        if len(users) == 1:
            self.user_id = users[0]["Id"]
            print(f"✓ Auto-selected single Jellyfin user: {users[0].get('Name')} (ID: {self.user_id})")
            return self.user_id

        # 4. Multiple users found without specification
        user_list = "\n".join([f"  • {u.get('Name')} (ID: {u.get('Id')})" for u in users])
        raise ValueError(
            f"Multiple Jellyfin users found. Please specify your user with --user <username>:\n{user_list}"
        )

    def get_all_series(self) -> Dict[str, dict]:
        """Fetch all Series items from Jellyfin to cache provider IDs."""
        params = {
            "Recursive": "true",
            "IncludeItemTypes": "Series",
            "Fields": "ProviderIds"
        }
        res = self._get(f"/Users/{self.user_id}/Items", params)
        series_items = res.get("Items", [])
        return {item["Id"]: item for item in series_items}

    def get_played_episodes(self, cutoff_date: Optional[datetime] = None) -> List[dict]:
        """Fetch all played episodes, optionally filtered by watch timestamp."""
        episodes = []
        limit = 500
        start_index = 0

        while True:
            params = {
                "Recursive": "true",
                "IncludeItemTypes": "Episode",
                "IsPlayed": "true",
                "Fields": "ProviderIds,UserData,SeriesName,SeriesId,IndexNumber,ParentIndexNumber",
                "SortBy": "DatePlayed",
                "SortOrder": "Descending",
                "StartIndex": start_index,
                "Limit": limit
            }
            res = self._get(f"/Users/{self.user_id}/Items", params)
            items = res.get("Items", [])
            if not items:
                break

            stop_pagination = False
            for ep in items:
                user_data = ep.get("UserData") or {}
                last_played = user_data.get("LastPlayedDate")
                if not last_played:
                    continue

                try:
                    played_dt = parse_iso_datetime(last_played)
                except Exception:
                    continue

                if cutoff_date and played_dt < cutoff_date:
                    # Items are sorted descending by DatePlayed; can stop when reaching cutoff
                    stop_pagination = True
                    break

                episodes.append(ep)

            if stop_pagination or len(items) < limit:
                break

            start_index += len(items)

        return episodes


def clean_provider_ids(providers: dict) -> dict:
    """Format provider IDs into Trakt format with proper types."""
    ids = {}
    if not providers:
        return ids

    imdb = providers.get("Imdb") or providers.get("imdb")
    if imdb:
        ids["imdb"] = str(imdb).strip()

    tmdb = providers.get("Tmdb") or providers.get("tmdb")
    if tmdb and str(tmdb).isdigit():
        ids["tmdb"] = int(tmdb)

    tvdb = providers.get("Tvdb") or providers.get("tvdb")
    if tvdb and str(tvdb).isdigit():
        ids["tvdb"] = int(tvdb)

    return ids


def build_trakt_sync_payload(chunk: List[dict]) -> dict:
    """Build the JSON payload for POST /sync/history grouped by show."""
    shows_map = {}
    episodes_list = []

    for item in chunk:
        s_title = item.get("series_title")
        s_ids = item.get("series_ids") or {}
        season = item.get("season")
        number = item.get("number")
        watched_at = item.get("watched_at")
        ep_ids = item.get("episode_ids") or {}

        if season is not None and number is not None and (s_ids or s_title):
            # Group by show IMDb/TVDB/TMDB or title
            key = s_ids.get("imdb") or s_ids.get("tvdb") or s_ids.get("tmdb") or s_title
            if key not in shows_map:
                show_obj = {"title": s_title}
                if s_ids:
                    show_obj["ids"] = s_ids
                show_obj["seasons"] = {}
                shows_map[key] = show_obj

            seasons = shows_map[key]["seasons"]
            if season not in seasons:
                seasons[season] = {"number": season, "episodes": []}
            seasons[season]["episodes"].append({
                "number": number,
                "watched_at": watched_at
            })
        elif ep_ids:
            episodes_list.append({
                "ids": ep_ids,
                "watched_at": watched_at
            })

    formatted_shows = []
    for s in shows_map.values():
        formatted_shows.append({
            "title": s["title"],
            **({"ids": s["ids"]} if "ids" in s else {}),
            "seasons": list(s["seasons"].values())
        })

    payload = {}
    if formatted_shows:
        payload["shows"] = formatted_shows
    if episodes_list:
        payload["episodes"] = episodes_list
    return payload


def filter_missing_interactive(missing: List[dict]) -> List[dict]:
    """Prompts the user to confirm or skip each missing episode individually."""
    confirmed = []
    auto_accept_all = False
    total = len(missing)

    print("\n" + "=" * 65)
    print("                 INTERACTIVE EPISODE REVIEW")
    print("  Controls: [y]es (default) | [n]o (skip) | [a]ccept all | [q]uit")
    print("=" * 65)

    for idx, ep in enumerate(missing, 1):
        if auto_accept_all:
            confirmed.append(ep)
            continue

        s_e = f"S{ep['season']:02d}E{ep['number']:02d}" if ep['season'] is not None and ep['number'] is not None else "Special"
        name_str = f" - \"{ep['episode_name']}\"" if ep.get("episode_name") else ""
        imdb_str = f" [{ep['series_imdb']}]" if ep.get("series_imdb") else ""

        print(f"\n[{idx}/{total}] {ep['series_title']}{imdb_str} {s_e}{name_str}")
        print(f"       Watched: {ep['watched_at']}")

        while True:
            try:
                ans = input("       Sync to Trakt? [Y/n/a/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nInteractive review cancelled by user.")
                return confirmed

            if ans in ("", "y", "yes"):
                confirmed.append(ep)
                break
            elif ans in ("n", "no", "s", "skip"):
                print("       -> Skipped")
                break
            elif ans in ("a", "all"):
                auto_accept_all = True
                confirmed.append(ep)
                print("       -> Accepted this and all remaining episodes.")
                break
            elif ans in ("q", "quit"):
                print(f"\nQuit review. {len(confirmed)} episode(s) selected for sync.")
                return confirmed
            else:
                print("       Please enter 'y', 'n', 'a', or 'q'.")

    return confirmed


def sync_missing_to_trakt(
    missing: List[dict],
    trakt_token: str,
    batch_size: int = 100
) -> Tuple[int, int]:
    """Posts missing episodes to Trakt in rate-limited batches."""
    total_added = 0
    total_not_found = 0
    num_batches = (len(missing) + batch_size - 1) // batch_size

    for i in range(num_batches):
        batch = missing[i * batch_size: (i + 1) * batch_size]
        payload = build_trakt_sync_payload(batch)
        print(f"Posting batch {i + 1}/{num_batches} ({len(batch)} episodes) to Trakt...")

        status, resp = trakt_request("/sync/history", method="POST", token=trakt_token, data=payload)
        if status not in (200, 201):
            print(f"! Error posting batch {i + 1} to Trakt: HTTP {status} - {resp}")
            continue

        added_eps = resp.get("added", {}).get("episodes", 0)
        not_found_shows = resp.get("not_found", {}).get("shows", [])
        not_found_eps = resp.get("not_found", {}).get("episodes", [])
        not_found_count = len(not_found_shows) + len(not_found_eps)

        total_added += added_eps
        total_not_found += not_found_count
        print(f"  ✓ Added: {added_eps} episodes (Not found: {not_found_count})")

        # Honor Trakt write rate limit (1 request per second)
        if i + 1 < num_batches:
            time.sleep(1.0)

    return total_added, total_not_found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync missing TV episode watches from Jellyfin to Trakt.tv."
    )
    parser.add_argument(
        "--trakt-export",
        required=True,
        help="Path to Trakt export (.zip archive, folder of split JSON files, or single .json file)."
    )
    parser.add_argument(
        "--jellyfin-url",
        default=os.getenv("JELLYFIN_URL", "http://localhost:8096"),
        help="Jellyfin server URL (default: http://localhost:8096 or JELLYFIN_URL env var)."
    )
    parser.add_argument(
        "--jellyfin-api-key",
        default=os.getenv("JELLYFIN_API_KEY"),
        help="Jellyfin API key (or JELLYFIN_API_KEY env var)."
    )
    parser.add_argument(
        "--user", "--user-name",
        dest="user_name",
        help="Jellyfin Username (e.g. --user alice). Automatically looked up on the server."
    )
    parser.add_argument(
        "--user-id",
        help="Jellyfin User ID GUID (optional; defaults to user from Trakt.xml or matches --user)."
    )
    parser.add_argument(
        "--trakt-config",
        help="Path to Jellyfin Trakt.xml configuration file (searches default paths if omitted)."
    )
    parser.add_argument(
        "--trakt-token",
        default=os.getenv("TRAKT_TOKEN"),
        help="Direct Trakt access token override (or TRAKT_TOKEN env var)."
    )
    parser.add_argument(
        "--trakt-refresh-token",
        default=os.getenv("TRAKT_REFRESH_TOKEN"),
        help="Direct Trakt refresh token override (or TRAKT_REFRESH_TOKEN env var)."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=120,
        help="Number of days of Jellyfin watch history to inspect (default: 120 = ~4 months; 0 for all)."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for posting to Trakt (default: 100)."
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactively review and confirm/skip each missing episode one by one."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview missing episodes without submitting changes to Trakt."
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Automatically confirm and proceed with sync without interactive prompt."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 65)
    print("        Jellyfin -> Trakt Watch History Sync")
    print("=" * 65)

    # 1. Trakt Export Index
    trakt_index = TraktExportIndex(args.trakt_export)

    # 2. Trakt Authentication
    trakt_auth = TraktAuthManager(
        config_path=args.trakt_config,
        token_override=args.trakt_token,
        refresh_override=args.trakt_refresh_token
    )
    trakt_token = trakt_auth.load_and_authenticate()

    # 3. Jellyfin Client Connection
    if not args.jellyfin_api_key:
        print("\n! Error: Jellyfin API key is required.")
        print("Please provide --jellyfin-api-key <key> or set JELLYFIN_API_KEY environment variable.")
        sys.exit(1)

    jf = JellyfinClient(
        base_url=args.jellyfin_url,
        api_key=args.jellyfin_api_key,
        user_id=args.user_id
    )
    try:
        jf.test_connection()
        jf.resolve_user_id(
            explicit_id=args.user_id,
            explicit_name=args.user_name,
            fallback_id=trakt_auth.linked_user_id
        )
    except Exception as e:
        print(f"\n! Jellyfin connection error: {e}")
        sys.exit(1)

    # 4. Fetch Series metadata & Played episodes
    print("\nFetching library metadata from Jellyfin...")
    series_map = jf.get_all_series()
    print(f"✓ Cached {len(series_map)} series from Jellyfin library.")

    cutoff_date = None
    if args.days > 0:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=args.days)
        print(f"Fetching Jellyfin plays from the last {args.days} days (since {cutoff_date.strftime('%Y-%m-%d')})...")
    else:
        print("Fetching all-time Jellyfin watch history...")

    played_episodes = jf.get_played_episodes(cutoff_date=cutoff_date)
    print(f"✓ Found {len(played_episodes)} played episodes in Jellyfin within time window.")

    # 5. Compare and Find Missing Scrobbles
    print("\nComparing Jellyfin history against Trakt export...")
    missing = []
    already_scrobbled = 0

    for ep in played_episodes:
        series_id = ep.get("SeriesId")
        series = series_map.get(series_id, {})
        series_title = series.get("Name") or ep.get("SeriesName", "Unknown Series")

        series_providers = series.get("ProviderIds") or {}
        ep_providers = ep.get("ProviderIds") or {}

        series_imdb = series_providers.get("Imdb") or series_providers.get("imdb")
        ep_imdb = ep_providers.get("Imdb") or ep_providers.get("imdb")

        season = ep.get("ParentIndexNumber")
        number = ep.get("IndexNumber")

        user_data = ep.get("UserData") or {}
        last_played_raw = user_data.get("LastPlayedDate")
        if not last_played_raw:
            continue

        try:
            played_dt = parse_iso_datetime(last_played_raw)
            watched_at_iso = format_iso_utc(played_dt)
        except Exception:
            watched_at_iso = last_played_raw

        # Matching check
        if trakt_index.is_watched(
            ep_imdb=ep_imdb,
            show_imdb=series_imdb,
            season=season,
            number=number,
            show_title=series_title
        ):
            already_scrobbled += 1
        else:
            missing.append({
                "series_title": series_title,
                "series_imdb": series_imdb,
                "series_ids": clean_provider_ids(series_providers),
                "season": season,
                "number": number,
                "episode_name": ep.get("Name", ""),
                "episode_imdb": ep_imdb,
                "episode_ids": clean_provider_ids(ep_providers),
                "watched_at": watched_at_iso
            })

    print(f"Already scrobbled in Trakt: {already_scrobbled}")
    print(f"Missing scrobbles to add:  {len(missing)}")

    if not missing:
        print("\n✓ Your Trakt history is already up to date with Jellyfin!")
        return

    # Print summary of missing items
    print("\nMissing Episodes Found:")
    print("-" * 65)
    for m in missing[:25]:
        s_e = f"S{m['season']:02d}E{m['number']:02d}" if m['season'] is not None and m['number'] is not None else "Special"
        name = f" - \"{m['episode_name']}\"" if m['episode_name'] else ""
        imdb_tag = f" [{m['series_imdb']}]" if m['series_imdb'] else ""
        print(f" • {m['series_title']}{imdb_tag} {s_e}{name} (Watched: {m['watched_at']})")
    if len(missing) > 25:
        print(f"   ... and {len(missing) - 25} more episodes.")
    print("-" * 65)

    # Interactive confirmation per episode
    if args.interactive:
        missing = filter_missing_interactive(missing)
        if not missing:
            print("\nNo episodes selected for sync. Exiting.")
            return

    if args.dry_run:
        print(f"\n[DRY RUN] {len(missing)} episode(s) would be added to Trakt history. No changes made.")
        return

    # Confirmation prompt (skipped if auto-confirmed via -y)
    if not args.yes:
        try:
            choice = input(f"\nProceed with adding {len(missing)} scrobbles to Trakt? [y/N]: ").strip().lower()
            if choice not in ("y", "yes"):
                print("Aborted by user.")
                return
        except EOFError:
            pass

    # 6. Submit to Trakt
    print("\nSyncing missing scrobbles to Trakt...")
    added, not_found = sync_missing_to_trakt(
        missing=missing,
        trakt_token=trakt_token,
        batch_size=args.batch_size
    )

    print("\n" + "=" * 65)
    print(f"Sync complete! Added: {added} episodes | Not found: {not_found}")
    print("=" * 65)


if __name__ == "__main__":
    main()
