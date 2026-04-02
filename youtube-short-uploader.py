#!/usr/bin/env python3

import os
import sys
import subprocess
import re
import traceback
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

# =========================
# CONFIG
# =========================

BASE_DIRECTORY = "/Volumes/TheLabyrinth/Tik Tok/"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
# These remain in the script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS_FILE = os.path.join(SCRIPT_DIR, "client_secrets.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
MASTER_LOG_FILE = os.path.join(SCRIPT_DIR, "master_hermes_log.txt")

# Local files (relative to Exports folder)
LOG_FILE_NAME = "hermes_log.txt"
DRY_RUN_LOG_FILE_NAME = "hermes_dry_run_log.txt"
CURRENT_FILE_NAME = "hermes_current_video.txt"

MAX_UPLOADS = 4
MAX_DURATION = 180

TZ = ZoneInfo("America/Los_Angeles")
UPLOAD_TIMES = [time(8, 30), time(11, 30), time(17, 30), time(20, 30)]

XYZ_REGEX = re.compile(r"^(\d+)_")

# =========================
# GLOBAL STATE
# =========================

class Stats:
    api_calls = 0

stats = Stats()

# =========================
# LOGGING
# =========================

def master_log(msg, verbose=False):
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    with open(MASTER_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(full_msg + "\n")
        if verbose:
            f.write(traceback.format_exc() + "\n")

def local_log(msg, dry, exports_path):
    file_name = DRY_RUN_LOG_FILE_NAME if dry else LOG_FILE_NAME
    file_path = os.path.join(exports_path, file_name)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def ensure_file(path):
    if not os.path.exists(path):
        with open(path, "w") as f:
            pass

# =========================
# UTIL
# =========================

def fatal(msg):
    master_log(f"FATAL: {msg}")
    sys.exit(1)

def select_mode():
    print("1 = dry-run\n2 = production")
    val = input("> ").strip()
    if val == "1":
        return True
    if val == "2":
        return False
    fatal("Invalid mode")

# =========================
# FFPROBE
# =========================

def check_ffprobe():
    try:
        subprocess.run(["ffprobe", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except:
        fatal("ffprobe missing from PATH")

def get_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    return float(out.stdout.strip())

# =========================
# FILE META
# =========================

def get_xyz(name):
    m = XYZ_REGEX.match(name)
    return int(m.group(1)) if m else -1

def get_mtime(path):
    return os.path.getmtime(path)

def get_human_time(ts):
    return datetime.fromtimestamp(ts, tz=TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

# =========================
# YOUTUBE
# =========================

def get_youtube_client():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                fatal(f"Missing {CLIENT_SECRETS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    master_log("Successfully connected to YouTube API.")
    return build("youtube", "v3", credentials=creds)

def has_scheduled_tomorrow(youtube):
    master_log("Checking YouTube for tomorrow's schedule...")
    tomorrow = datetime.now(TZ).date() + timedelta(days=1)
    start = datetime.combine(tomorrow, time(0, 0), TZ)
    end = datetime.combine(tomorrow, time(23, 59, 59), TZ)

    stats.api_calls += 1
    res = youtube.search().list(part="snippet", forMine=True, type="video", maxResults=50).execute()

    for i in res.get("items", []):
        vid = i["id"]["videoId"]
        stats.api_calls += 1
        d = youtube.videos().list(part="status", id=vid).execute()
        st = d["items"][0]["status"]

        if st.get("privacyStatus") == "private" and "publishAt" in st:
            pub = datetime.fromisoformat(st["publishAt"].replace("Z", "+00:00")).astimezone(TZ)
            if start <= pub <= end:
                return True
    return False

# =========================
# GAME DISCOVERY
# =========================

def find_active_game(root_path):
    games = []
    if not os.path.isdir(root_path):
        fatal(f"Root path does not exist: {root_path}")

    for item in os.listdir(root_path):
        if not item.startswith("Minitage - "):
            continue
        
        game_path = os.path.join(root_path, item)
        exports_path = os.path.join(game_path, "Exports")
        
        if not os.path.isdir(exports_path):
            continue
            
        # Get all mp4s to determine game age
        vids = [f for f in os.listdir(exports_path) if f.lower().endswith(".mp4")]
        if not vids:
            continue
            
        earliest_mtime = min(os.path.getmtime(os.path.join(exports_path, f)) for f in vids)
        
        # Check completion status
        current_file = os.path.join(exports_path, CURRENT_FILE_NAME)
        status = ""
        if os.path.exists(current_file):
            with open(current_file, "r") as f:
                status = f.read().strip()
        
        if "Complete!" in status:
            continue
            
        games.append({
            "name": item,
            "exports_path": exports_path,
            "age": earliest_mtime
        })
        
    if not games:
        return None
        
    # Sort by age (oldest game first)
    games.sort(key=lambda x: x["age"])
    return games[0]

# =========================
# MAIN
# =========================

def main():
    try:
        dry = select_mode()
        
        check_ffprobe()
        
        active_game = find_active_game(BASE_DIRECTORY)
        if not active_game:
            master_log("No active games found with pending uploads.")
            return

        master_log(f"Active Game: {active_game['name']}")
        exports_path = active_game["exports_path"]
        
        # Ensure local files exist
        ensure_file(os.path.join(exports_path, LOG_FILE_NAME))
        ensure_file(os.path.join(exports_path, DRY_RUN_LOG_FILE_NAME))
        current_file_path = os.path.join(exports_path, CURRENT_FILE_NAME)
        ensure_file(current_file_path)

        youtube = None
        if not dry:
            youtube = get_youtube_client()
            if has_scheduled_tomorrow(youtube):
                msg = "Tomorrow already has scheduled uploads; exiting."
                master_log(msg)
                local_log(msg, dry, exports_path)
                return

        # Get eligible videos in this game
        vids = []
        for f in os.listdir(exports_path):
            if f.lower().endswith(".mp4"):
                f_path = os.path.join(exports_path, f)
                try:
                    if get_duration(f_path) <= MAX_DURATION:
                        vids.append(f)
                except Exception as e:
                    master_log(f"Error checking duration for {f}: {e}")
                    continue

        if not vids:
            master_log(f"No eligible videos found in {active_game['name']}.")
            return

        # Sort videos deterministically
        entries = [(get_xyz(f), get_mtime(os.path.join(exports_path, f)), f) for f in vids]
        entries.sort(key=lambda x: (x[0], x[1], x[2]))

        formatted_entries = [f"{e[2]}_{int(e[1])}_{get_human_time(e[1])}" for e in entries]

        with open(current_file_path, "r") as f:
            current_state = f.read().strip()

        if current_state:
            if current_state not in formatted_entries:
                fatal(f"Current pointer '{current_state}' not found in file list for {active_game['name']}")
            idx = formatted_entries.index(current_state) + 1
        else:
            idx = 0

        batch = entries[idx:idx+MAX_UPLOADS]

        if not batch:
            master_log(f"All eligible videos in '{active_game['name']}' have been processed.")
            with open(current_file_path, "a") as f:
                f.write("\nComplete!")
            return

        tomorrow = datetime.now(TZ).date() + timedelta(days=1)
        master_log(f"Target date for scheduling: {tomorrow}")
        local_log(f"\n{tomorrow} | Batch start", dry, exports_path)

        last_entry = None

        for i, (x, mt, name) in enumerate(batch):
            pub_time = datetime.combine(tomorrow, UPLOAD_TIMES[i], TZ)
            video_path = os.path.join(exports_path, name)

            if dry:
                msg = f"DRY-RUN SIMULATION: {name} (Slot: {UPLOAD_TIMES[i]})"
                master_log(msg)
                local_log(f"{datetime.now(TZ)} | {msg}", dry, exports_path)
                last_entry = formatted_entries[idx + i]
                master_log(f"--- [DRY] SUMMARY: Successfully simulated upload of '{name}'. Scheduled for {pub_time} ---")
                print("")
                continue

            try:
                from googleapiclient.http import MediaFileUpload

                body = {
                    "snippet": {
                        "title": name[:100],
                        "description": "#Shorts",
                        "categoryId": "22"
                    },
                    "status": {
                        "privacyStatus": "private",
                        "publishAt": pub_time.isoformat()
                    }
                }

                media = MediaFileUpload(video_path, resumable=True)

                master_log(f"Commencing upload: {name} (Slot: {UPLOAD_TIMES[i]})")
                stats.api_calls += 1
                youtube.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media
                ).execute()

                master_log(f"--- SUMMARY: Successfully uploaded '{name}'. Scheduled for {pub_time} ---")
                print("")
                local_log(f"{datetime.now(TZ)} | LIVE | {name} | {pub_time}", dry, exports_path)
                last_entry = formatted_entries[idx + i]

            except Exception as e:
                master_log(f"--- SUMMARY: FAILED to upload '{name}'. Error: {e} ---", verbose=True)
                print("")
                local_log(f"FAIL {name}: {e}", dry, exports_path)

                if last_entry:
                    with open(current_file_path, "w") as f:
                        f.write(last_entry)
                sys.exit(1)

        if last_entry:
            # Check if this was the last video in the game
            is_complete = (idx + len(batch)) >= len(formatted_entries)
            with open(current_file_path, "w") as f:
                f.write(last_entry)
                if is_complete:
                    f.write("\nComplete!")
                    master_log(f"Game '{active_game['name']}' is now marked as Complete!")

        master_log(f"Batch complete. Total API calls this run: {stats.api_calls}")

    except Exception as e:
        master_log(f"An unexpected error occurred: {e}", verbose=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
