# Hermes Script Documentation

## Overview
Hermes is a deterministic YouTube Shorts uploader and scheduler designed for safe, low-volume automation.

It:
- Selects up to 4 eligible videos per run
- Uploads them as private
- Schedules them for tomorrow (Seattle timezone)
- Tracks progress via a state file
- Prevents duplicate scheduling
- Supports a full dry-run mode

---

## Directory Structure

```
<base_path>/
  Exports/
    001_clip.mp4
    002_clip.mp4
  hermes.py
  hermes_log.txt
  hermes_dry_run_log.txt
  hermes_current_video.txt
```

---

## How It Works

Each run:
1. Select mode (dry-run or production)
2. Validate base path and Exports folder
3. Validate ffprobe availability
4. Read current pointer
5. Identify next 0–4 eligible videos
6. Check if tomorrow already has scheduled uploads
7. Upload + schedule OR simulate
8. Update pointer
9. Exit

---

## Video Selection Rules

### Eligibility
- Must be `.mp4`
- Duration ≤ 180 seconds (via ffprobe)

### Ordering Priority
1. XYZ integer prefix (before first underscore)
2. Last modified timestamp
3. Filename lexical order

---

## Scheduling

Videos are scheduled for **tomorrow (Seattle timezone)** at:
- 08:30
- 11:30
- 17:30
- 20:30

---

## State Tracking

File: `hermes_current_video.txt`

Format:
```
filename_epoch_human-readable-time
```

Purpose:
- Tracks last successfully scheduled video
- Ensures no duplicates or skips
- Enables safe resumption

---

## Logging

### Production
- hermes_log.txt

### Dry-run
- hermes_dry_run_log.txt

Logs are:
- Append-only
- One-line per action
- Separated by blank lines per run

---

## Dry-Run Mode

Dry-run:
- Executes full logic
- Does NOT upload videos
- Does NOT use OAuth
- Writes to dry-run log only
- Advances pointer

Use it to validate behavior before production.

---

## Failure Handling

If a failure occurs:
1. Error is logged
2. Pointer is reset to last successful video
3. Script exits immediately

---

## Dependencies

### Required
- Python 3.10+
- ffprobe (must be on PATH)

### Python packages
```
pip install google-api-python-client google-auth google-auth-oauthlib
```

### OAuth files
- client_secrets.json
- token.json (auto-generated)

---

## How to Run

```
python hermes.py /path/to/base_folder
```

Then select:
```
1 = dry-run
2 = production
```

---

## Recommended Workflow

1. Run dry-run
2. Review hermes_dry_run_log.txt
3. Run production
4. Repeat every few days

---

## Rules / Best Practices

- Run once per day max
- Do not rename files mid-process
- Do not manually upload overlapping content
- Do not edit hermes_current_video.txt unless necessary
- Always verify with dry-run before production changes
- Ensure ffprobe is available before running

---

## Limitations

- Manual execution only
- Max 4 uploads per run
- No retry mechanism within run
- Single channel support
- No background scheduling

---

## Design Philosophy

Hermes prioritizes:
1. Determinism
2. Safety over speed
3. Idempotent execution
4. Low risk of triggering YouTube abuse systems

---

## Future Improvements (Optional)

- CLI flags for mode selection
- CSV-based scheduling
- Multi-channel support
- Cloud storage integration
- JSON summary output
