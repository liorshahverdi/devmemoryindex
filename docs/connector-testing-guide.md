# Connector Testing Guide

Step-by-step manual testing instructions for each of the four new connectors.
Each section covers prerequisites, configuration, triggering ingestion, and
verifying results with `devmemory search`.

---

## 1. FilesystemConnector

Indexes source code files from configured directories, splitting them into
80-line chunks with 10-line overlap. Memories have type `file_content`.

### Prerequisites

No extra dependencies required. Works with the base install.

### Step 1 — Add a code directory

```bash
devmemory config add-code ~/projects/myapp
```

Verify it was saved:

```bash
devmemory config list
# Expected: "Code Scan Dirs" table showing ~/projects/myapp
```

### Step 2 — Run ingestion

```bash
devmemory ingest --source filesystem
```

Expected output:

```
filesystem  indexed N memories
```

If `N = 0`, check that the directory contains files with supported extensions
(`.py`, `.ts`, `.js`, `.go`, `.rs`, `.rb`, `.java`, `.swift`, `.sh`, etc.) and
that files are at least 10 lines long.

### Step 3 — Search for indexed code

```bash
devmemory search "authentication handler"
devmemory search "database connection" --type file_content
```

Each result shows the relative file path and line range in the summary:

```
utils/auth.py (lines 1–80)
```

### Step 4 — Verify deduplication

Run ingestion a second time on the same directory:

```bash
devmemory ingest --source filesystem
# Expected: filesystem  indexed 0 memories
```

Unchanged files produce no new memories. If a file is edited and ingested
again, only the modified chunks get a new ID and are re-indexed.

### Step 5 — Remove a directory

```bash
devmemory config remove-code ~/projects/myapp
devmemory config list
# Expected: "Code Scan Dirs" table is gone
```

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `indexed 0 memories` on first run | Files are < 10 lines or unsupported extension | Use `.py`/`.ts` files with at least 10 lines |
| `indexed 0 memories` on first run | Directory is inside `node_modules`, `.venv`, etc. | Move code outside skip dirs |
| Large repo indexes slowly | All files are read and chunked on first run | Normal — subsequent runs are instant |

---

## 2. CopilotConnector

Indexes GitHub Copilot Chat assistant responses from VS Code's extension
storage. No configuration required — the connector auto-detects VS Code and
VS Code Insiders storage paths. Memories have type `copilot_chat`.

### Prerequisites

- VS Code (or VS Code Insiders) installed with the GitHub Copilot Chat extension
- At least one Copilot Chat session that produced responses ≥ 100 characters

Storage location (macOS, detected automatically):

```
~/Library/Application Support/Code/User/globalStorage/github.copilot-chat/
```

### Step 1 — Confirm the storage directory exists

```bash
ls ~/Library/Application\ Support/Code/User/globalStorage/github.copilot-chat/
```

If the directory is missing, open VS Code, install Copilot Chat, and have a
conversation before proceeding.

### Step 2 — Run ingestion

```bash
devmemory ingest --source copilot
```

Expected output:

```
copilot  indexed N memories
```

If `N = 0` and the directory exists, the session JSON files may use an
unrecognised format or all responses were shorter than 100 characters.

### Step 3 — Search for indexed responses

```bash
devmemory search "how to implement rate limiting" --type copilot_chat
devmemory search "refactor this function"
```

Results show the first 200 characters of the assistant response as the summary.

### Step 4 — Verify deduplication

```bash
devmemory ingest --source copilot
# Expected: copilot  indexed 0 memories
```

Message content is hashed — the same response is never indexed twice
regardless of how many times the session file is scanned.

### Step 5 — Inspect a result

```bash
devmemory search "error handling" --type copilot_chat
# Pick a result ID from the output, then:
devmemory get <memory-id>
```

The `raw_text` field contains the full assistant response (redacted of any
secrets, up to 3000 characters). The `source` field shows the path to the
session JSON file.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `indexed 0 memories` | No Copilot Chat sessions | Have a conversation in VS Code first |
| `indexed 0 memories` | Session JSON format changed | Open an issue with a sanitised sample of the JSON structure |
| Results from old sessions only | New sessions use a different file path | Re-run `devmemory ingest --source copilot` |

---

## 3. BrowserConnector

Indexes bookmarks from Chrome, Brave, Edge, Arc, Chromium, and Firefox.
No configuration required — browser profile paths are detected automatically.
Memories have type `browser_bookmark`.

### Prerequisites

At least one of the following must be installed on macOS:

- **Chrome-family**: Google Chrome, Brave, Microsoft Edge, Arc, or Chromium
- **Firefox**

The same URL bookmarked in multiple browsers is indexed only once.

### Step 1 — Run ingestion

```bash
devmemory ingest --source browser
```

Expected output:

```
browser  indexed N memories
```

A fresh run on a browser with hundreds of bookmarks will index all of them.
Subsequent runs index only newly added bookmarks.

### Step 2 — Search bookmarks

```bash
devmemory search "python documentation" --type browser_bookmark
devmemory search "github" --type browser_bookmark
```

Each result summary has the format `Page Title: https://example.com`.

### Step 3 — Filter by browser

Memories are tagged with the source browser name. To find only Brave bookmarks:

```bash
devmemory search "blog" --type browser_bookmark
# Check the tags field in results for "brave", "chrome", "firefox", etc.
```

### Step 4 — Verify deduplication

```bash
devmemory ingest --source browser
# Expected: browser  indexed 0 memories
```

IDs are derived from the URL — the same URL is never stored twice, even across
browser profiles.

### Step 5 — Add a new bookmark and re-index

1. Add a new bookmark in Chrome or Firefox.
2. Run `devmemory ingest --source browser`.
3. Expected: `browser  indexed 1 memories`.
4. Search for it: `devmemory search "<bookmark title>"`.

### Notes on Firefox

Firefox locks `places.sqlite` while the browser is open. The connector
automatically copies the database to a temp file before reading, so ingestion
works regardless of whether Firefox is running.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `indexed 0 memories` | No bookmarks in detected profiles | Confirm `~/Library/Application Support/Google/Chrome/Default/Bookmarks` exists |
| `indexed 0 memories` | All bookmark URLs start with `chrome-extension://` or `file://` | Only `http`/`https` URLs are indexed |
| Firefox bookmarks missing | Non-default Firefox profile path | Check `~/Library/Application Support/Firefox/Profiles/` for `.sqlite` files |

---

## 4. MeetingConnector

Indexes audio recordings by transcribing them locally with
[Whisper](https://github.com/openai/whisper). Optionally labels each
speech segment with a speaker identifier using
[pyannote.audio](https://github.com/pyannote/pyannote-audio).
Memories have type `meeting_transcript`.

### Prerequisites

Install the `voice` extras:

```bash
uv pip install "devmemoryindex[voice]"
# Installs: openai-whisper, sounddevice, scipy, pyannote.audio
```

Whisper downloads a model on first use (~140 MB for `base`). Ensure you have
an internet connection on the first run.

Supported audio formats: `.mp3`, `.wav`, `.m4a`, `.mp4`, `.ogg`, `.flac`,
`.webm`, `.aac`. Maximum file size: 500 MB.

### Step 1 — Add a recordings directory

```bash
devmemory config add-meetings ~/Recordings
```

Verify:

```bash
devmemory config list
# Expected: "Meeting Recording Dirs" table showing ~/Recordings
```

### Step 2 — Place a test audio file

Copy a short meeting recording (30 seconds to a few minutes works well for
testing) into the configured directory:

```bash
cp ~/Downloads/standup-2025-01-10.m4a ~/Recordings/
```

### Step 3 — Run ingestion

```bash
devmemory ingest --source meeting
```

Whisper loads and transcribes the file. This takes longer than other
connectors — roughly 1–5× real-time depending on hardware.

Expected output:

```
meeting  indexed 1 memories
```

If the transcript is fewer than 50 characters (silence, noise, or a very
short clip), the memory is skipped with `indexed 0 memories`.

### Step 4 — Search the transcript

```bash
devmemory search "sprint planning" --type meeting_transcript
devmemory search "action items"
```

Results show the first 200 characters of the transcript as the summary.

### Step 5 — Inspect speaker labels (if pyannote is installed)

When `pyannote.audio` is available and a HuggingFace token is configured,
transcripts include speaker prefixes:

```
SPEAKER_00: Let's start with blockers from yesterday.
SPEAKER_01: I was waiting on the API review.
SPEAKER_00: That should be merged by end of day.
```

To enable diarization, set your HuggingFace token:

```bash
export HF_TOKEN=hf_...
devmemory ingest --source meeting
```

Without a token, the connector falls back to a plain transcript without speaker
labels (still fully functional).

### Step 6 — Verify change detection

Edit the audio file (e.g. replace it with a different recording at the same
path) and re-run ingestion:

```bash
cp ~/Downloads/different-meeting.m4a ~/Recordings/standup-2025-01-10.m4a
devmemory ingest --source meeting
# Expected: meeting  indexed 1 memories  (new mtime → new ID)
```

Unchanged files (same mtime) are skipped automatically.

### Step 7 — Remove a recordings directory

```bash
devmemory config remove-meetings ~/Recordings
```

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `indexed 0 memories` | Whisper not installed | `uv pip install "devmemoryindex[voice]"` |
| `indexed 0 memories` | Transcript < 50 chars | Use a longer recording with audible speech |
| `indexed 0 memories` | File > 500 MB | Split into smaller files |
| Very slow transcription | CPU-only Whisper on long files | Use a shorter clip for testing; GPU speeds this up significantly |
| No speaker labels | pyannote not installed or no HF_TOKEN | Set `HF_TOKEN` env var; falls back to plain transcript if unavailable |
| pyannote download error | Model requires HuggingFace agreement | Accept the pyannote model license at huggingface.co |

---

## Running All Connectors at Once

To ingest from all configured sources in a single command:

```bash
devmemory ingest
```

To run selectively:

```bash
devmemory ingest --source filesystem --source copilot
devmemory ingest --source browser
devmemory ingest --source meeting
```

## Checking What Was Indexed

```bash
# Count memories by type
devmemory search "" --type file_content   | head -5
devmemory search "" --type copilot_chat   | head -5
devmemory search "" --type browser_bookmark | head -5
devmemory search "" --type meeting_transcript | head -5
```

## Adjusting Ingest Frequency (Daemon)

The daemon ingests each connector on its own schedule. Defaults:

| Connector  | Default interval |
|---|---|
| filesystem | 30 minutes |
| copilot    | 10 minutes |
| browser    | 2 hours    |
| meeting    | 1 hour     |

To change an interval:

```bash
devmemory config set-schedule filesystem 900   # every 15 minutes
devmemory config set-schedule browser 3600     # every hour
```
