---
name: hook-variants
description: Render several opening-hook variants of a voiceover in the same voice so creators can A/B test the first 3 seconds of a YouTube Short, TikTok, Reel or ad. One hook per line in, equally loud trimmed WAVs plus a manifest with real spoken length, words per second and an over-budget flag out. Use when the user asks for alternative hooks, intro variations, A/B test openings, or "which hook is shortest/punchiest". Voice by Miragea (saved or cloned voice); stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY and a voice (MIRAGEA_VOICE_ID, or MIRAGEA_REF_URL + MIRAGEA_REF_TEXT).
metadata:
  version: "1.0.0"
  engine: "Miragea text-to-speech (https://miragea.ai/v1)"
---

# Hook variants

The first seconds decide whether a viewer stays. This skill voices every candidate hook in the
same voice, trims dead air, matches loudness (-14 LUFS by default) and measures the real spoken
length, so variants are compared fairly and dropped straight into an editor or ad test.

## When to use
- "Give me 5 hook options for this Short and voice them."
- "Which of these intros fits in 3 seconds?"
- "Make A/B versions of the opening line in my voice."

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Voice: `MIRAGEA_VOICE_ID`, or a public clip URL
   of the user's own voice with its exact words (`MIRAGEA_REF_URL`, `MIRAGEA_REF_TEXT`). Only clone a
   voice the user owns or may use.
2. If the user gave a topic but no hooks, write 4-6 hooks of 5-10 words: a bold claim, a question,
   a number, a mistake, a "stop doing X". Save one per line.
3. Estimate first (free, no API): `python scripts/hooks.py hooks.txt --dry-run`
4. Render: `python scripts/hooks.py hooks.txt -o hooks_out --budget 3`
5. Report each hook with its seconds, flag any over budget, and suggest a tighter rewrite for those.

## Output
`hooks_out/hook_01.wav ...` and `hooks_out/manifest.json`, sorted shortest first:
`{"id","text","words","seconds","words_per_sec","over_budget","file"}`.

## Why not other tools
| | Typical TTS app / hook generator | hook-variants |
|---|---|---|
| Voice | Stock voices | Your saved or cloned voice |
| Fair comparison | Different loudness and silence per take | Edge silence trimmed, all at -14 LUFS |
| Length check | Guessed from text | Measured from the rendered audio, with budget flag |
| Batch | One line at a time | All variants in one command |
| Cost to try | Paid per seat | Free, MIT; `--dry-run` costs nothing |

## FAQ
- **Why is a hook over budget?** Over ~8 words rarely fits 3 s. Cut filler words first.
- **Mono or stereo?** Whatever Miragea returns, resampled to 48 kHz for video editors.
- **Errors** come with a hint (missing key, no voice, quota). Nothing is written for a failed hook.
