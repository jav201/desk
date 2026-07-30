# Quick Spec — desk: transcribe the audio of a web video (YouTube + others)

## 1. Objective
Turn a video URL into a local transcript, so tutorials, talks and interviews can
be read/searched instead of watched. Pull ONLY the audio track with yt-dlp and
feed it to the existing GPU-or-CPU `transcribe_file()`. No re-encoding is needed
(faster-whisper decodes the native m4a/webm/opus via PyAV), so ffmpeg is not a
requirement.

## 2. User stories
- As a user, I paste a YouTube URL into desk and get a transcript `.md` without
  leaving the app or opening a browser.
- As a user, I can do the same from the terminal: `desk-transcribe <url>`.
- As a user on a locked-down work machine, desk stays fully offline unless I
  explicitly install the network extra.

## 3. Acceptance criteria (observable)
- [x] AC-1: given an http(s) video URL, `fetch_audio()` writes ONE audio file
      under `~/.desk/transcripts/<stamp>-<safe-title>/` and returns its path +
      metadata (title, duration, extractor).
- [x] AC-2: given a playlist/channel URL, exactly ONE video is downloaded
      (`noplaylist`), never the whole list.
- [x] AC-3: given a video longer than the cap (default 2 h), the download is
      REFUSED before any bytes are fetched, with a message naming the duration.
- [x] AC-4: given a non-http(s) URL (e.g. `file://`, `ftp://`), the request is
      refused — the downloader is never handed a local-file scheme.
- [x] AC-5: given a title with filesystem-hostile characters (`/ \ : * ? " < > |`),
      the created folder name contains none of them and is never empty.
- [x] AC-6: `desk-transcribe <url>` transcribes the video and writes a `.md`
      whose header names the source URL and title; `desk-transcribe <file>`
      keeps working exactly as before.
- [x] AC-7: in-app, pasting a URL into the `i` picker input transcribes that
      video; pressing `u` opens a URL prompt that does the same.
- [x] AC-8: while fetching, the Record panel shows a distinct "fetching" state
      with progress; on failure the panel returns to idle and reports the error.
- [x] AC-9: without the `[web]` extra installed, the URL paths report a clear
      "pip install desk[web]" message and NOTHING else in desk changes.
- [x] AC-10: the live recording flow (space -> record -> auto-transcribe) is
      unchanged; the existing suite stays green.

## 4. Validation strategy
Unit tests for the pure/guarded logic with yt-dlp mocked (URL detection, scheme
refusal, playlist flag, duration cap, name sanitising, extra-missing guard) — no
test performs a real download. One manual smoke against a real short video, run
by hand and reported honestly. Deck-level tests for the `u` prompt / picker URL
branch with `fetch_audio` monkeypatched.

## 5. Non-goals
- No video download, no ffmpeg post-processing, no format conversion.
- No batch/playlist mode, no subtitle scraping, no browser cookies/login for
  private or paywalled content.
- No change to the recording, board, focus or capture panels.

## 6. Detected security flags
- [x] **External integration / third-party SDK** — yt-dlp, hitting external sites.
- [x] **User input -> fetcher (SSRF-adjacent)** — an arbitrary URL is handed to a
      downloader running on the user's machine.
- [x] **Network exposure (egress)** — desk's FIRST outbound network access; it
      was a fully offline tool until now.
- [x] **Filesystem write from untrusted metadata** — the remote title becomes a
      folder name.
**security_required:** true

### Mitigations required by this spec
1. Drive yt-dlp through its **Python API**; never interpolate a URL into a shell.
2. Force `noplaylist=True` (AC-2).
3. **Allow only `http`/`https`** schemes — reject `file://` and friends (AC-4).
4. Fixed `outtmpl` inside a per-video directory under `~/.desk/transcripts/`.
5. Sanitise the remote title before using it as a path segment (AC-5).
6. Check duration BEFORE downloading; refuse past the cap (AC-3).
7. Ship as an **opt-in extra** so an offline install stays offline (AC-9).
8. State the ToS/copyright expectation in the README and in-app, alongside the
   existing recording-consent note.

## 7. Batch status
| Field | Value |
|-------|-------|
| Current phase | C — CLOSED 2026-07-25 |
| Started | 2026-07-24 |
| Notes | 2 increments: (1) fetch.py + extra + CLI; (2) in-app `i`/`u` + progress. |
