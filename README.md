<div align="center">
<h1>Local to OneDrive Sync</h1>

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows&logoColor=white)
![OneDrive](https://img.shields.io/badge/OneDrive-Ready-0364B8?logo=microsoftonedrive&logoColor=white)
![Robocopy](https://img.shields.io/badge/Engine-robocopy%20%2FMIR-informational)
![License](https://img.shields.io/badge/License-MIT-green)
</div>

A small Python wrapper around Windows' native `robocopy /MIR` that mirrors any local folder into your OneDrive folder, runs as a scheduled task, and keeps things fast even with thousands of files.

## Why would you use this?

The OneDrive client only syncs what lives inside `C:\Users\<you>\OneDrive`. If your data sits on another drive (`D:\`, an external disk, a NAS, a RAID array, etc.), OneDrive simply ignores it.

The usual workaround is to create a symlink so OneDrive "thinks" the external folder is inside its own. It works until it doesn't: OneDrive is known to break on symlinks, skip files, get into sync loops, or stop uploading altogether.

This script takes a different route:

```
D:\YOUR_FOLDER  --(robocopy /MIR)-->  C:\Users\You\OneDrive\YOUR_FOLDER  --(OneDrive)-->  Cloud
```

It copies only what actually changed, on a schedule you control, and leaves a clean log behind.

### Good fits

- Data on a secondary disk (`D:\`, `E:\`, etc.) you want backed up to OneDrive
- A RAID volume or external drive you want mirrored to the cloud
- Network shares / NAS paths (`\\server\share`) that OneDrive can't sync natively
- Any case where you want filtering, logging, or control that the OneDrive client doesn't offer

### Why not just a symlink

| | Symlink trick | This script |
|---|---|---|
| Reliable with OneDrive | Flaky | Yes |
| Exclude files / folders | No | Yes |
| Audit log of what changed | No | Yes |
| Control sync frequency | No | Yes |
| Works with network paths | Limited | Yes |

## Requirements

- Windows 10 / 11
- Python 3.10+
- `robocopy` (ships with Windows)

No external Python packages needed, it only uses the standard library.

## Configuration

Edit `config.json` before running:

| Field | Description | Example |
|---|---|---|
| `source` | Local folder to sync from | `D:\\ARCHIVOS_PR` |
| `destination` | Target folder inside OneDrive | `C:\\Users\\Oscar\\OneDrive\\ARCHIVOS_PR` |
| `log_file` | Log file path | `D:\\Python\\Script_sincro\\sync.log` |
| `log_max_mb` | Max log size before rotating (MB) | `5` |
| `exclude_dirs` | Directories to skip | `[".git", "node_modules"]` |
| `exclude_files` | Files to skip (wildcards allowed) | `["*.tmp", "~*"]` |
| `robocopy_threads` | Parallel copy threads | `8` |
| `retry_count` | Retries on locked files | `2` |
| `retry_wait_seconds` | Wait between retries | `3` |
| `schedule_interval_minutes` | Interval for the scheduled task | `5` |

## Usage

```bash
# Run a sync right now
python sync.py

# Preview what would happen without changing anything
python sync.py --dry-run

# Register the scheduled task in Windows (run as Administrator)
python sync.py --install-task

# Remove the scheduled task
python sync.py --uninstall-task
```

## Logs

Everything the script does is written to the path set in `config.json` (defaults to `sync.log`). The file rotates automatically once it hits the size limit and keeps up to 3 backups, so it never grows out of control.

## How it stays fast

`robocopy /MIR` doesn't read file contents, it compares names, sizes and timestamps. On runs where nothing changed, it finishes in well under a second even across thousands of files. With `/MT:8` it also copies in parallel, which is why this holds up well on large datasets, RAID volumes or NAS shares.
