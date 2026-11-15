# Miragea Skills: AI voiceover, captions and video-editing Agent Skills for Claude Code, Codex and Cursor

Open-source [Agent Skills](https://agentskills.io) that give coding agents real voice and caption
abilities: narrate a Remotion video in a saved or cloned voice, caption any video into clean SRT/VTT,
burn TikTok-style captions, clip a long video into YouTube Shorts (an open-source Opus Clip
alternative), and more. Every skill is a folder with a `SKILL.md` and small,
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
| [screen-recording-voiceover](screen-recording-voiceover/) | Silent screen recording -> narrated MP4: finds the steps, voices one line per step, starts each line on its step, auto speed-up / freeze-frame when a line runs long, ducked music, captions | `python3 scripts/voiceover.py demo.mp4 demo.script.txt` | 2026-11-10 |
| [shorts-voiceover](shorts-voiceover/) | Text script -> finished 1080x1920 Short/Reel/TikTok: voiceover, captions timed from the real speech, Ken Burns images / B-roll / gradients, ducked music, -14 LUFS | `python3 scripts/short.py tips.txt` | 2026-11-10 |
| [hook-variants](hook-variants/) | A/B test the first 3 seconds: voice 4-6 opening hooks for a Short, TikTok, Reel or ad in the same AI voice, edge silence trimmed, all loudness-matched to -14 LUFS, real spoken length measured with a budget flag | `python3 scripts/hooks.py hooks.txt --budget 3` | 2026-11-15 |
| [video-to-shorts](video-to-shorts/) | AI clip maker / open-source Opus Clip alternative: long podcast, webinar or stream VOD -> captioned 1080x1920 Shorts, TikToks and Reels. Agent picks the moments from a timestamped transcript (no extra LLM key), cuts snap to whole sentences, centre crop or blurred fill, 1-3 word captions, -14 LUFS, optional spoken hook in your cloned voice | `python3 scripts/clips.py render talk.mp4 talk.clips.json` | 2026-11-15 |

Live demos (captioned videos, a narrated screen recording and a Short): https://huggingface.co/spaces/headvox/miragea-skills

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

### Screen recording voiceover vs. the alternatives

| | **screen-recording-voiceover** | Vorec / Clueso / DemoPolish / ScreenStory | Descript / Camtasia | Screen Studio | By hand (TTS + editor) |
|---|---|---|---|---|---|
| Price | Free, MIT; pay-as-you-go voice | $9-19+/month subscriptions | Subscription / license | No TTS (request closed) | TTS plan + your time |
| Your own cloned voice | Yes | Mostly stock voices | Descript: yes, in-app | - | Depends |
| Each line starts on its step | Automatic, from timestamps | Automatic | Manual on timeline | - | Manual, frame by frame |
| Line longer than the action | Auto speed-up (max 1.15x), then freeze-frame | Some (freeze-sync) | Manual | - | Manual |
| Runs locally on your file, any recorder | Yes (OBS, QuickTime, Loom, Screen Studio exports) | Upload to their cloud | In-app | - | Yes |
| Used by AI agents | Yes (Agent Skill; agent reads the frames and writes the lines) | No | No | No | No |

### Shorts voiceover vs. the alternatives

| | **shorts-voiceover** | MoneyPrinterTurbo / short-video-maker | CapCut text-to-speech | Paid faceless-video SaaS |
|---|---|---|---|---|
| Setup | Python stdlib + ffmpeg | Docker or large Python env, stock-footage API key | App, per project | Account + subscription |
| Voice | Your saved/cloned Miragea voice | Free TTS voices (Edge, Kokoro) | Fixed voice list, char caps | Stock voices |
| Caption timing | Transcribed from the finished voice | Estimated or extra Whisper model | Auto, in-app | Varies |
| Your own images/clips, per scene | `@file` or a folder | Stock search terms | Manual | Upload |
| Loudness for Shorts | -14 LUFS automatic | Not normalized | Not normalized | Varies |
| Re-run after one edit | Only changed scenes re-voiced | Full re-render and re-voice | Manual | Re-generate |

### Video to Shorts vs. the alternatives

| | **video-to-shorts** | Opus Clip / Klap / Vizard | AI-Youtube-Shorts-Generator / OpenShorts / ClipMint | video-use |
|---|---|---|---|---|
| Price | Free, MIT; pay-as-you-go transcription | $15-29+/month, minute credits, watermark on free tier | Free; you pay your LLM / GPU | Free; you pay your LLM |
| Who picks the moments | Your coding agent reads the timestamped transcript (no extra LLM key); offline keyword draft included | Their model (virality score) | GPT / Gemini / local LLM key | Claude Code |
| Cuts mid-sentence | Never: cuts snap to sentence edges | Sometimes | Sometimes | Word-level cuts |
| Setup | Python stdlib + ffmpeg, no GPU, no model download | Upload to their cloud | Docker / Whisper model, GPU recommended | Python + ElevenLabs Scribe key |
| Spoken hook in your own voice | Yes (Miragea cloned voice), frame held while it plays | Text hook only | No | No |
| Loudness for Shorts | -14 LUFS on every clip | Varies | Usually not normalised | Varies |
| Framing | Centre crop or blurred fill (no face tracking yet) | Face tracking | Face tracking (most) | Agent-defined |

Honest limits: speech recognition is cloud-based (needs a key and internet); reference clips for cloning
must currently be public URLs (an upload endpoint is planned by Miragea); English is the focus.

## FAQ

### How do I A/B test video hooks with AI voiceover?
Put one hook per line in `hooks.txt` and run `python3 hook-variants/scripts/hooks.py hooks.txt --budget 3 --voice VOICE_ID`. Every variant is voiced in the same voice, trimmed and loudness-matched, so you compare hooks fairly. `--dry-run` estimates lengths for free.


**Do I need a GPU?** No. All heavy lifting is done by the Miragea API; scripts are standard-library Python.

**Is my API key safe?** Scripts read `MIRAGEA_API_KEY` from the environment and never print, log or store it.

**What does it cost?** Miragea bills captions at 3 points per audio second and speech per character (live
rates: `GET https://miragea.ai/v1/capabilities`). Cached re-runs cost nothing.

**Can I clone someone else's voice?** Only with their permission. Use your own voice or a voice you are
licensed to use.

**Which agents work?** Any agent that reads `SKILL.md` skills: Claude Code, Codex CLI, Cursor, Gemini CLI,
OpenCode and others. The scripts also run fine by hand.

### How do I turn a long video into YouTube Shorts with AI (free Opus Clip alternative)?
Run `python3 video-to-shorts/scripts/clips.py moments talk.mp4 --suggest 5`, let your agent read `talk.moments.md` and write `talk.clips.json`, then `python3 video-to-shorts/scripts/clips.py render talk.mp4 talk.clips.json`. You get captioned 1080x1920 clips plus titles; `--dry-run` previews the cuts for free, and a `hook` line per clip is voiced in your own cloned voice.

## Credits

video-to-shorts is an original rewrite inspired by these MIT-licensed projects (no code copied):
[SamurAIGPT/AI-Youtube-Shorts-Generator](https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator),
[mutonby/openshorts](https://github.com/mutonby/openshorts) and
[browser-use/video-use](https://github.com/browser-use/video-use). Thank you to their authors.

## Related projects

- [Retake](https://github.com/yyert123/retake) - fix a flubbed voiceover line in your own voice (CLI + MCP).
- [HeadVox](https://github.com/yyert123/headvox) - script to voiceover with word-aligned captions.

## License

MIT. Skills follow the open [Agent Skills specification](https://agentskills.io/specification).
