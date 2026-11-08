---
name: remotion-narration
description: Turn a video script into per-scene voiceover for Remotion in one command - one MP3 per scene in a saved or cloned voice, measured durations converted to durationInFrames, word-level captions in Remotion's Caption format, and an SRT. Use when building a narrated video with Remotion (or any React/code video tool), when the user asks to "add voiceover", "narrate these scenes", "sync scenes to the narration" or "add captions that follow the voice". Voice and timing by Miragea, no GPU or ElevenLabs account needed.
license: MIT
compatibility: Python 3.9+ (standard library only) and ffmpeg/ffprobe on PATH. Needs MIRAGEA_API_KEY.
metadata:
  version: "1.0.0"
  engine: "Miragea TTS + speech recognition (https://miragea.ai/v1)"
---

# Remotion narration

Writes everything a Remotion composition needs to be driven by its voiceover: audio per scene, exact
durations, start frames and captions. Scene lengths come from the real audio, so nothing drifts.

## When to use

- The user has a script (Markdown, text or JSON) and a Remotion project and wants narration.
- Scenes should last exactly as long as their voiceover; captions should follow the voice word by word.

## Steps

1. Make sure `MIRAGEA_API_KEY` is set (never print it). Pick the voice:
   - `--voice VOICE_ID` - a voice saved in the user's Miragea account, or
   - `--ref-url https://...` - a public clip of the voice to clone (with the user's consent), plus
     `--ref-text "exact words in the clip"` for the cheaper 1x rate.
2. Write the script. Each `## Heading` (or blank-line paragraph) becomes one scene:

   ```markdown
   ## intro
   Meet Retake, the fastest way to fix a voiceover mistake.
   ## demo
   Type the right word. Retake re-voices the sentence and splices it in.
   ```

3. Generate into the Remotion `public/` folder:

   ```bash
   python3 scripts/narrate.py script.md --voice VOICE_ID --out public/narration --fps 30
   ```

4. Use `public/narration/narration.json` in the composition (see `examples/Narrated.tsx`):
   `totalFrames` for `durationInFrames`, each scene's `startFrame` / `durationInFrames` for a
   `<Sequence>`, `staticFile('narration/' + scene.file)` for `<Audio>`, and `scene.captions`
   (Remotion `Caption[]`: `text`, `startMs`, `endMs`, `timestampMs`, `confidence`) with
   `@remotion/captions` `createTikTokStyleCaptions()` for animated captions.
5. Edit the script and re-run freely: unchanged scenes are reused from the manifest at no cost; if a
   run stops midway, finished scenes are kept and the next run resumes.

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--fps` | 30 | Frame rate for frame maths |
| `--pad` | 0.4 | Seconds of breathing room after each scene |
| `--captions miragea` | yes | Times captions from the generated audio (accurate; +3 points/s) |
| `--captions estimate` | | Free: spreads words by length |
| `--model` | expressive | `standard` follows the reference voice more closely |
| `--speed` | 1.0 | 0.25-4 |

Scenes longer than 2,000 characters are split at sentence ends and joined automatically.

## Troubleshooting

- `choose a voice` -> pass `--voice` or `--ref-url`. Reference URLs must be public, under 1,024 chars and
  served directly (GitHub raw, S3/R2 public objects work; signed redirects may not).
- `401/402/429` -> key, balance, rate limit. Re-running is always safe.
