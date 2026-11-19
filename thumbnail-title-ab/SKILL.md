---
name: thumbnail-title-ab
description: YouTube thumbnail and title A/B maker. Transcribes your video with Miragea speech recognition, pulls candidate frames with ffmpeg, has the agent write 3-4 title + thumbnail-text variants from what is actually said, then renders 1280x720 thumbnails and lints title length and text words. Use when the user asks for YouTube thumbnail ideas, title A/B test, thumbnail maker, click-through rate (CTR) improvements, or Test & Compare variants.
license: MIT
compatibility: Python 3.9+ (standard library only); ffmpeg with drawtext. Needs MIRAGEA_API_KEY.
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition (https://miragea.ai/v1)"
---

# Thumbnail + title A/B

1. Set `MIRAGEA_API_KEY` (never print it); keys: https://miragea.ai.
2. `python3 scripts/thumb_ab.py prep video.mp4` -> `video.thumbs/variants.json` with transcript + 6 frames.
3. Fill 3-4 variants: each a different angle (curiosity, result, warning, how-to). Title <= 60 chars, thumb_text <= 4 words that ADD info (not a copy of the title), pick the frame with a clear face/subject; claims must be true to the video.
4. `python3 scripts/thumb_ab.py build video.thumbs/variants.json` -> `thumb_A.jpg`..., `ab_plan.csv`; fix lint warnings and rebuild.
5. Upload to YouTube Test & Compare. Judge by watch time share, not CTR alone.

No clickbait the video does not pay off. Use `hook-variants` for the first spoken line.
