---
name: hyperframes-narration
description: Add voiceover to HyperFrames videos in your own cloned voice. Turns a script into one narration file per scene, measures the real duration, and writes a HyperFrames composition (index.html) with scene clips, word-timed captions and audio tracks that already line up, plus an SRT. HTML to video with AI voiceover, HeyGen HyperFrames narration, explainer video with captions, product launch video voiceover, PR walkthrough narration, faceless video from a script, text to speech for coding-agent videos. Use when the user says narrate this HyperFrames video, add voiceover to my HTML video, sync scenes to the voice, add captions that follow the voice, or make an explainer with my voice. Claude Code, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ (standard library only), ffmpeg/ffprobe on PATH, Node 22+ for HyperFrames. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech + speech recognition (https://miragea.ai/v1)"
---

# HyperFrames narration (voiceover that drives the timeline)

HyperFrames compositions are HTML with `data-start` / `data-duration` in seconds. This skill makes the
voice first and the timeline second: every scene lasts exactly as long as its narration, so nothing drifts
and nobody counts frames by hand.

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it; free key at https://miragea.ai). Set `MIRAGEA_ACTOR_ID` to your saved
   voice, or pass `--voice ACTOR_ID`. No saved voice yet? The error explains how to create one.
2. Create a project if needed: `npx hyperframes init my-video --example blank --non-interactive`.
3. Write `script.md`, one `## Scene title` block per scene (plain spoken English, numbers written as spoken). See `examples/script.md`.
4. Free preview of the timeline, no API calls: `python3 scripts/hf_narrate.py script.md --project my-video --dry-run`.
5. Real run: `python3 scripts/hf_narrate.py script.md --project my-video` (`--format portrait` for 9:16, `square` for 1:1).
6. Make it pretty: keep the generated clips and tracks, restyle the CSS, add GSAP animation, B-roll or blocks from the
   HyperFrames registry. Keep each scene's `data-start` / `data-duration` untouched; the voice owns the timing.
7. Check and render: `npx hyperframes lint`, `npx hyperframes check`, `npx hyperframes render`.
8. Edit the script and re-run freely: unchanged scenes are reused at no cost; an existing hand-edited `index.html` is
   never overwritten (the new one lands in `narration.snippet.html`).

## What it writes
`assets/narration/scene-NN.mp3`, `narration.json` (start, duration, word timing per scene), `narration.srt`, `index.html`
(scene `<h2>` clips on track 1, caption lines on track 2, `<audio>` on track 3, a paused GSAP timeline that lights each
caption word as it is spoken).

## Options
| Flag | Default | Meaning |
|---|---|---|
| `--voice` | `$MIRAGEA_ACTOR_ID` | Saved Miragea voice |
| `--format` | landscape | `portrait` 1080x1920, `square` 1080x1080 |
| `--pad` | 0.5 | Seconds of air after each scene |
| `--captions` | miragea | `estimate` is free but approximate |
| `--model` | expressive | `standard` follows the reference voice more closely |
| `--dry-run` | off | Silent placeholder audio, estimated timing |

## How it compares
| | Built-in HyperFrames `/media-use` voiceover | Generic TTS scripts | This skill |
|---|---|---|---|
| Your own cloned voice | not the default | rarely | yes (Miragea actor) |
| Scene length from the real audio | manual | manual | automatic |
| Word-timed captions from the generated audio | separate step | no | built in |
| Free reruns of unchanged scenes | no | no | yes |
| Overwrites your edited composition | n/a | n/a | never |

## FAQ
- Does it render the video? No. HyperFrames renders (`npx hyperframes render`); on Linux ARM64 set `HYPERFRAMES_BROWSER_PATH` to a Chromium.
- Remotion instead? Use `remotion-narration` in the same collection.
- Free TTS? Never; every line goes through Miragea, so voice and captions come from one engine.
- Whose voice? Only voices you own or have consent for.

Credit: HyperFrames by HeyGen (Apache-2.0) for the composition format; concept from its voiceover and captions guides. Code written from scratch.
