---
name: article-to-video
description: Turn a blog post, newsletter or markdown article into a narrated explainer video with text cards, an SRT caption file and your own cloned AI voice. Blog to video, article to video, text to video without a video model, faceless YouTube explainer and Shorts from a script. Use when the user asks to repurpose a blog post as a video, make a faceless video from text, add voiceover to an article, or create a YouTube or TikTok video from a script. Stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice id (actor id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech (https://miragea.ai/v1)"
---

# Article to video (blog to video, faceless explainer)

One post, many formats: each heading becomes a scene with a title card, each sentence is voiced in the creator's cloned voice, and an SRT is written with matching timing.

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai.
2. Trim the article first: spoken length is about 15 characters per second, so aim for 400-1200 words (3-8 min). Cut link lists, tables and code.
3. Preview free: `python scripts/article2video.py post.md --dry-run`
4. Render: `python scripts/article2video.py post.md --voice YOUR_ACTOR_ID --format 16:9 -o post.mp4` (`9:16` for Shorts; or set `MIRAGEA_ACTOR_ID`). Get the id from the voices list in your Miragea account after saving a clip of your own voice.
5. Check the duration with ffprobe and a frame before delivering. Burn the `.srt` with `video-captions` and add B-roll with `auto-broll` for a richer cut.

Only clone a voice the user owns or has permission to use.

## FAQ
- **How is it different from text-to-video apps?** No video model: clean text cards plus a real cloned voice, so it is free of stock-footage licensing and renders in seconds.
- **Which languages?** Whatever Miragea speaks; an English reference voice also speaks other languages.
- **Credits:** idea from open blog-to-video tools (e.g. Remotion blog-to-video templates); code is an original rewrite.
