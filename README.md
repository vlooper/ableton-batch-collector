# 📦 Ableton Batch Collector

**Batch "Collect All and Save" for Ableton Live — without opening Ableton.**

Collect all external samples across hundreds of projects in one click. No more opening each project one by one.

![Version](https://img.shields.io/badge/version-1.2.0-ff6b4a)
![Python](https://img.shields.io/badge/python-3.8+-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)
![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)

---

## The Problem

Every Ableton producer knows this pain:

- You're migrating to a new computer and need to collect samples for **all** your projects
- You have hundreds of .als files with external sample references scattered across drives
- Ableton's built-in "Collect All and Save" only works **one project at a time** — and requires Ableton to be open
- Missing samples = broken projects = lost work

Forum posts going back over a decade show producers struggling with this exact problem:

> *"I have like a thousand live sets which this needs to be done for, and it would take me a week just to open all of them."*
> — [Ableton Forum](https://forum.ableton.com/viewtopic.php?t=121089&start=30)

> *"It would be handy to be able to collect and save all the projects in one click!"*
> — [Gearspace](https://gearspace.com/board/music-computers/683928-i-want-backup-my-ableton-projects-how.html)

> *"Almost all samples are offline in every single old project I open... I can drag these in manually, but can't figure out a way to do it that isn't tedious as hell."*
> — [Ableton Forum](https://forum.ableton.com/viewtopic.php?t=244316)

> *"The solution to that problem is heavy drinking and crying."*
> — [Ableton Forum](https://forum.ableton.com/viewtopic.php?t=178276) (on migrating projects to a new computer)

## The Solution

Ableton Batch Collector parses your .als files directly (they're gzipped XML), finds all external sample references, copies the files into each project's `Samples/Collected` folder, and updates the references — exactly like Ableton's built-in feature, but for **every project in a folder at once**.

No dependencies. No Ableton required. Just run it.

---

## Features

- **Batch processing** — Point it at a folder and collect samples for every .als file inside, recursively
- **Dry run mode** — Preview what would happen before copying anything
- **Zero dependencies** — Uses only Python 3 (pre-installed on macOS). No pip, no packages, nothing to install
- **Doesn't require Ableton** — Parses .als XML directly, works completely standalone
- **Safe** — Creates .als.bak backups before modifying any project file
- **Native GUI** — Browser-based interface with macOS native folder picker
- **Smart scanning** — Auto-detects Ableton project folders, skips Backup/Trash directories
- **Live progress** — Real-time stats, activity log, and progress tracking
- **Detailed reporting** — See exactly which files were collected, which were already local, and which are missing

---

## Installation

### Option A: Download the .dmg (recommended)

1. Download `Ableton Batch Collector.dmg` from [Releases](../../releases)
2. Open the DMG and drag the app to your Applications folder
3. **First launch:** Right-click (two-finger tap) the app → click **Open**
   - macOS will warn about an unverified developer — click **Open** to proceed
   - You only need to do this once

> **Tip:** If macOS still blocks the app, open Terminal and run:
> ```bash
> xattr -cr "/Applications/Ableton Batch Collector.app"
> ```

### Option B: Run the Python script directly

```bash
python3 ableton_batch_collector.py
```

That's it. Opens in your browser at `http://127.0.0.1:7865`.

---

## Usage

1. **Launch the app** — A browser window opens automatically
2. **Click Browse** — The native macOS folder picker opens. Select the folder containing your Ableton projects
3. **Scan first** (optional) — Click 🔍 Scan to preview how many sessions and media references were found
4. **Toggle Dry Run** — Leave it ON to preview, turn it OFF to actually collect
5. **Click ✨ Collect All** — Sit back and watch it process every project

### What it does

For each `.als` file found:

1. Decompresses the gzipped XML
2. Finds all `<FileRef>` elements pointing to media files (wav, aif, mp3, flac, etc.)
3. Skips samples that are already inside the project folder
4. Skips Ableton factory content and Live Packs
5. Copies external samples into `Samples/Collected/` within the project
6. Updates the file references in the .als to point to the new local paths
7. Saves a `.als.bak` backup of the original before writing changes

### Example output

```
MyTrack Project
  MyTrack.als: 12 collected
  MyTrack_v2.als: 3 collected

Remix Project
  Remix_Final.als: 8 collected, 2 missing

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMPLETE
Sessions: 47 | Collected: 234 | Missing: 5
Data copied: 1.8 GB
Time: 0:02:14
```

---

## Building the .dmg yourself

Both files (`ableton_batch_collector.py` and `build_dmg.sh`) should be in the same folder:

```bash
bash build_dmg.sh
```

This creates:
- `dist/Ableton Batch Collector.app` — The macOS application
- `dist/Ableton Batch Collector.dmg` — Distributable disk image with drag-to-Applications

No Xcode, no developer tools required — uses only built-in macOS utilities.

---

## How it works

Ableton Live project files (`.als`) are gzipped XML. Each sample reference is stored as a `<FileRef>` element containing both an absolute path and a relative path. The collector:

1. **Walks** the target directory recursively for `.als` files
2. **Groups** them by project folder (detected via `Ableton Project Info/` directory)
3. **Parses** the XML and extracts all `<FileRef>` elements
4. **Filters** to only media files (audio/video extensions)
5. **Skips** factory content, Live Packs, and already-local files
6. **Copies** external files to `Samples/Collected/` with collision-safe naming
7. **Updates** `Path`, `RelativePath`, and `RelativePathType` in the XML
8. **Re-compresses** and writes the modified .als

This is the same operation Ableton performs internally with "Collect All and Save" — but done externally, in batch, without needing Ableton to be running.

---

## Supported formats

**Audio:** `.wav` `.aif` `.aiff` `.mp3` `.flac` `.ogg` `.m4a` `.wma` `.rex` `.rx2` `.sd2`

**Video:** `.mp4` `.mov` `.avi` `.m4v`

Works with Ableton Live 8, 9, 10, 11, and 12 project files.

---

## Safety

- **Backups first** — Every modified .als gets a `.als.bak` copy before any changes
- **Dry run** — Preview everything before committing
- **Non-destructive** — Original samples are copied, never moved
- **No Ableton modification** — Doesn't touch Ableton's preferences, library, or database
- **Skips system content** — Ignores factory packs, app resources, and built-in content

---

## FAQ

**Does this replace Ableton's Collect All and Save?**
For batch operations, yes. For single projects you're actively working on, Ableton's built-in feature is still convenient.

**Will this break my projects?**
No. It creates backups (.als.bak) before any modification, and the XML changes it makes are identical to what Ableton does internally. If anything goes wrong, rename the .bak file back.

**Does it handle Max for Live devices?**
Currently it collects audio/video media references only, not M4L devices. This matches the most common use case (sample collection for migration).

**Does it work on Windows?**
The collection engine works cross-platform, but the GUI currently uses `osascript` for the native folder picker (macOS only). Windows support could be added with `tkinter` — PRs welcome.

**Why a browser GUI?**
Zero dependencies. Python's `http.server` is built-in, so the app needs nothing installed. No Electron, no Qt, no tkinter import issues — just open a browser tab.

---

## Requirements

- macOS 10.15+ (Catalina or later)
- Python 3.8+ (pre-installed on macOS)
- No other dependencies

---

## Credits

Built by Vlooper

---

## License

MIT License — use it, modify it, share it.
