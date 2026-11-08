# Miragea Skills: voiceover, captions and video Agent Skills for Claude Code, Codex and Cursor

Open-source [Agent Skills](https://agentskills.io) that give coding agents real voice and caption
abilities: narrate a Remotion video in a saved or cloned voice, caption any video into clean SRT/VTT,
burn TikTok-style captions, and more. Every skill is a folder with a `SKILL.md` and small,
dependency-free Python scripts. Voice and speech recognition run on [Miragea](https://miragea.ai).

```bash
# Claude Code / Codex / Cursor / any skills-compatible agent
npx skills add yyert123/miragea-skills            # pick skills interactively
# or copy one folder into ~/.claude/skills/ (Claude Code) or your agent's skills directory
export MIRAGEA_API_KEY=your_key                   # https://miragea.ai
```

## Skill index

| Skill | What it does | One command | Added |
|---|---|---|---|
| [video-captions](video-captions/) | Any video/audio -> readable SRT + VTT (whole words, 42-char lines) and optional burned-in MP4, incl. 1-3 word "pop" captions for Shorts/Reels/TikTok | `python3 scripts/captions.py talk.mp4 --burn` | 2026-11-08 |
| [remotion-narration](remotion-narration/) | Script -> one MP3 per scene, measured durations -> `durationInFrames`, word-level Remotion `Caption[]`, SRT | `python3 scripts/narrate.py script.md --voice ID` | 2026-11-08 |

Live demo (captioned videos): https://huggingface.co/spaces/headvox/miragea-skills

New skills are added here as they ship. Each one is tested offline (`pytest tests`) and on real audio.

## Why these skills (and how they compare)

| | **miragea-skills** | ElevenLabs MCP / skills | Free local Whisper scripts | Built-in editor captions (Premiere, CapCut) |
|---|---|---|---|---|
| Install | Copy a folder; Python stdlib + ffmpeg | Hosted OAuth server (local MCP archived 2026-08) | Python + model download, often a GPU | Inside one paid app |
| Words split mid-word in captions | Fixed: transcript rebuilt into whole words | n/a | Usually fine | Usually fine |
| Caption reflow (42 chars x 2 lines, min/max duration) | Automatic | Manual | Manual / extra libs | Manual styling per clip |
| Shorts-style 1-3 word captions, burned in | One flag (`--style shorts --burn`) | No | Extra tooling | CapCut only, per project |
| Scene durations for Remotion | Measured and returned as frames | Durations not returned (must be measured) | n/a | n/a |
| Your own cloned voice | Saved voice id or reference clip | Yes (paid plans) | No (TTS separate) | Limited voice list |
| Re-runs | Cached: unchanged scenes / transcripts are free | Re-billed | Re-computed | n/a |
| Cost | Pay-as-you-go Miragea points | Subscription credits | Free, your hardware | App subscription |

Honest limits: speech recognition is cloud-based (needs a key and internet); reference clips for cloning
must currently be public URLs (an upload endpoint is planned by Miragea); English is the focus.

## FAQ

**Do I need a GPU?** No. All heavy lifting is done by the Miragea API; scripts are standard-library Python.

**Is my API key safe?** Scripts read `MIRAGEA_API_KEY` from the environment and never print, log or store it.

**What does it cost?** Miragea bills captions at 3 points per audio second and speech per character (live
rates: `GET https://miragea.ai/v1/capabilities`). Cached re-runs cost nothing.

**Can I clone someone else's voice?** Only with their permission. Use your own voice or a voice you are
licensed to use.

**Which agents work?** Any agent that reads `SKILL.md` skills: Claude Code, Codex CLI, Cursor, Gemini CLI,
OpenCode and others. The scripts also run fine by hand.

## Related projects

- [Retake](https://github.com/yyert123/retake) - fix a flubbed voiceover line in your own voice (CLI + MCP).
- [HeadVox](https://github.com/yyert123/headvox) - script to voiceover with word-aligned captions.

## License

MIT. Skills follow the open [Agent Skills specification](https://agentskills.io/specification).
