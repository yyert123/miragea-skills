---
name: video-to-shorts
description: Turn a long video (podcast, interview, webinar, tutorial, livestream VOD) into captioned 9:16 YouTube Shorts, TikToks and Reels, an open-source Opus Clip alternative for Claude Code, Codex and Cursor. Transcribes once, lists every sentence with timestamps so the agent picks the best moments (no extra LLM key), snaps cuts to whole sentences, reframes to 1080x1920 (centre crop or blurred fill), burns 1-3 word captions, normalises to -14 LUFS, and can open each clip with a spoken hook in the creator's own cloned voice. Use when the user asks to clip a long video, make shorts from a podcast or stream, repurpose a video, find viral moments, or wants an AI clip maker. Speech recognition and voice by Miragea; stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY. Spoken hooks need a voice (MIRAGEA_VOICE_ID, or MIRAGEA_REF_URL + MIRAGEA_REF_TEXT).
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition + text-to-speech (https://miragea.ai/v1)"
---

# Video to Shorts (AI clip maker)

Long video in, a folder of ready-to-post vertical clips out. You (the agent) are the "virality
model": read the timestamped sentences and choose moments a viewer would understand with no
context. The script does the precise work: sentence-safe cuts, 9:16 framing, captions, loudness,
and an optional voiced hook in the creator's own voice.

## When to use
- "Make 5 Shorts from this podcast episode."
- "Clip the best moments of my webinar / stream VOD for TikTok and Reels."
- "Find the viral parts of this interview and caption them."

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Check `ffmpeg -version`.
2. Transcribe and list moments (billed once, then cached in `<video>.transcript.json`, shared with
   the video-captions skill):
   `python scripts/clips.py moments talk.mp4 --suggest 5`
   This writes `talk.moments.md` (one sentence per line, `[start-end]` seconds) and a keyword-scored
   draft `talk.clips.json`.
3. Read `talk.moments.md` and write the final `talk.clips.json` yourself. Good clips:
   - 20-60 s, start on a claim, question or number, never on "and / so / but";
   - one complete idea with its payoff; no inside references ("like I said earlier");
   - a `title` (under 60 chars, for the upload) and, if the opening is slow, a `hook`: 5-9 words,
     under ~3 s spoken, that states the payoff ("This one rule doubled our retention.").
   `[{"start": 12.3, "end": 48.0, "title": "...", "hook": "..."}]`
4. Preview for free: `python scripts/clips.py render talk.mp4 talk.clips.json --dry-run`
   Fix any warnings (too short, too long, long hook).
5. Render: `python scripts/clips.py render talk.mp4 talk.clips.json -o shorts_out`
   - `--frame crop` (default) for one person on camera; `--frame fit` for slides, screen
     recordings or two people side by side (whole frame over a blurred fill).
   - Hooks are voiced only if a voice is set; only clone a voice the user owns or may use.
     `--no-hook` skips them.
6. Report each clip: file, length, title, and the hook. Offer to re-cut any clip by editing its
   times in clips.json and re-running (the transcript is cached, so only hooks are billed).

## Output
`shorts_out/clip_01.mp4` (1080x1920, H.264/AAC, 30 fps, -14 LUFS), `clip_01.srt`, and
`manifest.json`: `{"id","title","start","end","hook","seconds","hook_seconds","warnings","file","srt"}`.

## Honest limits
- Framing is a centre crop or blurred fill, not face tracking. For a speaker off-centre, use `fit`.
- Speech recognition is cloud-based (Miragea); the video itself is never uploaded, only a 16 kHz
  mono audio track.
- English is the focus.
