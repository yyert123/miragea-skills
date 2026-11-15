---
name: ugc-video-ads
description: UGC-style video ads for TikTok, Instagram Reels, YouTube Shorts and Meta ads, made by Claude Code, Codex or Cursor without a video model. The agent writes 3-5 hooks and a direct-response body (problem, demo, proof, CTA) from a product page; the script voices every line in the creator's or founder's own cloned voice, renders every hook x body combination as a captioned 1080x1920 MP4 (plus 4:5, 1:1 or 16:9), keeps captions, price overlays and the end card inside the platform safe zones, trims dead air, hits -14 LUFS, measures each hook against a 3-second budget, lints risky ad claims (guarantees, health, income, personal attributes, "free"), and writes a manifest for Ads Manager naming. Lines are cached, so a new hook re-bills only that hook. Use when the user asks for a UGC ad, a TikTok/Reels/Meta video ad, product video ad, ad creative variations, creative testing, a faceless or founder-voice product ad, or "make ads from my product photos". Voice and speech recognition by Miragea; stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY and a voice (MIRAGEA_VOICE_ID, or MIRAGEA_REF_URL + MIRAGEA_REF_TEXT).
metadata:
  version: "1.0.0"
  engine: "Miragea text-to-speech + speech recognition (https://miragea.ai/v1)"
---

# UGC video ads (voice-first, no video model)

Product photos, clips or screen recordings in; a matrix of ready-to-upload ad videos out. You (the agent)
are the copywriter and creative strategist; the script is the editor: voice, timing, captions, safe zones,
loudness, export and naming.

## When to use
- "Make a TikTok / Reels / Meta ad for my product" or "UGC-style ad from these photos".
- "Give me 3 hook variations of this ad to test."
- "Turn this product page into a 20-second video ad in my voice."
- "Export the ad in 9:16 and 4:5 for Instagram feed."

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it), `ffmpeg -version` works, and a voice is chosen:
   `MIRAGEA_VOICE_ID`, or `MIRAGEA_REF_URL` + `MIRAGEA_REF_TEXT`. Only a voice the user owns or may use;
   founder-voice ads are the honest default.
2. Gather the facts: product name, price, offer, who it is for, the one problem it solves, real proof
   (reviews, numbers the user can back up). Never invent a testimonial, statistic or result.
3. Write `ad.json` next to the media (see `examples/brewly.ad.json`):
   - `hooks`: 3-5, each under ~3 s spoken (7-8 words). Mix angles: price shock, POV, call-out
     ("Stop paying..."), demo-first, curiosity. Optional `overlay` (on-screen text, <= 28 chars) and `media`.
   - `bodies`: one or more `{id, lines}`; 2-4 lines: problem or setup -> demo -> proof/benefit.
     Short spoken sentences; write numbers the way they should be heard if it matters.
   - `cta`: one spoken line (what to tap + why now). `end_card`: `title`, up to 3 `lines`, `button`, `seconds`, `media`.
   - `platform`: tiktok | reels | shorts | meta | any (length advice). `label`: e.g. "AI voice" when the
     voice is synthetic or first-person lines are not the speaker's own words.
   - `media`: image (slow push-in) or clip (cover-cropped, looped/trimmed). Omit it for a gradient.
4. `python scripts/ads.py check ad.json` (free). `!` must be fixed (missing media, over the platform's
   max length). `~` is advice: long hooks, length outside the usual sweet spot, risky claims, missing
   CTA/end card, testimonial disclosure. Rewrite and re-check until clean or each `~` is a conscious choice.
5. `python scripts/ads.py render ad.json --dry-run` (free) shows the variant matrix, estimated lengths and
   how many unique lines will be voiced.
6. Render: `python scripts/ads.py render ad.json -o ads_out --ratios 9:16,4:5`
   Options: `--only price-demo` (or a hook/body id), `--max N`, `--music bed.mp3` (ducked), `--gap 0.12`
   (pace), `--hook-budget 3`, `--lowercase`, `--no-captions`.
7. Report: the files, their lengths, any hook over budget (`hooks_over_budget`), and the advice you kept.
   Suggest testing all hooks with the same body first, then the winning hook with new bodies.

## Output (in `ads_out/`)
- `<brand>_<hook>-<body>_<9x16|4x5|1x1|16x9>.mp4`: H.264/AAC, 30 fps, -14 LUFS, captions burned in.
- `<brand>_<hook>-<body>.srt`: the captions (upload as a separate track where supported).
- `manifest.csv` / `manifest.json`: file, variant, hook, body, ratio, seconds, measured hook seconds,
  over-budget flag, plus the `check` advice.

## How it works
- Each line is voiced once with Miragea and cached by text + voice; edge silence is trimmed; lines are
  joined with a short UGC-pace gap, so every scene change lands on a line change.
- Captions use your script's exact spelling (brand names stay right) placed on Miragea speech-recognition
  timing, 1-3 words per caption, breaking at commas and sentence ends.
- Safe zones (9:16): captions centred at ~60% height and shifted left of the like/share rail; overlays
  below the top bar; end card text inside the middle band.

## Honest limits
- No AI actor or lip-sync: this is a voice-first ad over your product footage. Pair it with real creator
  clips when you have them (put them in `media`).
- The claim lint is a checklist, not legal review. Platform policies change; read the current ad policy.
- Speech recognition and voice are cloud-based (Miragea); only the generated voice lines are uploaded.
