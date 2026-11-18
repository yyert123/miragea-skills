# Miragea Skills: AI voiceover, captions and video-editing Agent Skills for Claude Code, Codex and Cursor

Open-source [Agent Skills](https://agentskills.io) that give coding agents real voice and caption
abilities: narrate a Remotion video in a saved or cloned voice, caption any video into clean SRT/VTT,
burn TikTok-style captions, clip a long video into YouTube Shorts (an open-source Opus Clip
alternative), dub a video into another language in your own voice, auto-insert B-roll on the spoken word, make UGC-style video ads with hook variations, and more. Every skill is a folder with a `SKILL.md` and small,
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
| [video-dubbing](video-dubbing/) | AI dubbing / video translator in your own cloned voice (own-voice dubbing): the agent translates each line within its time budget (no extra LLM key), every line starts on the original, gentle 1.2x max speed-up, music kept in the pauses, translated SRT, -14 LUFS, plus a full-length audio track for YouTube multi-language audio | `python3 scripts/dub.py render talk.mp4 talk.es.dub.json` | 2026-11-15 |
| [auto-broll](auto-broll/) | Automatic B-roll on the exact spoken word: your agent picks a cutaway for each concrete moment of a talking-head video, podcast or tutorial; cuts land on the word, speaker audio untouched, cover-crop to 16:9 or 9:16, Ken Burns on stills, flash-cut / covered-hook / too-much-B-roll checks, MP4 + CMX 3600 EDL for Premiere and Resolve. Your clips or free Pexels stock. Faceless mode voices a script in your cloned voice first | `python3 scripts/broll.py render talk.mp4 talk.broll.json` | 2026-11-15 |
| [ugc-video-ads](ugc-video-ads/) | UGC-style video ads without a video model: your agent writes 3-5 hooks and a direct-response body from a product page; every hook x body is voiced in your own cloned voice and rendered as a captioned TikTok / Reels / Shorts / Meta ad (9:16, 4:5, 1:1), captions and price overlays in the safe zones, end card + CTA, 3-second hook budget, ad-claim lint, -14 LUFS, Ads Manager manifest | `python3 scripts/ads.py render ad.json --ratios 9:16,4:5` | 2026-11-15 |
| [audiogram-clips](audiogram-clips/) | Podcast to video: turn any audio clip into a captioned waveform video (audiogram) for TikTok, Shorts, Reels, LinkedIn and X; auto captions from Miragea ASR, cover art, title, 9:16 / 1:1 / 4:5 / 16:9, free `--dry-run` | `python3 scripts/audiogram.py clip.mp3 --title "..." -o clip.mp4` | 2026-11-15 |

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

### Video dubbing vs. the alternatives

| | **video-dubbing** | ElevenLabs Dubbing / HeyGen / Rask | VideoLingo / pyVideoTrans / KrillinAI | YouTube auto-dubbing |
|---|---|---|---|---|
| Price | Free, MIT; pay-as-you-go voice + transcription | Per-minute plans, credits expire | Free; you bring LLM + TTS keys (or a GPU) | Free |
| Voice | Your own cloned Miragea voice, any target language tested (es, ja, zh...) | Clone on paid tiers | Free TTS by default; cloning needs local models + GPU | Generic or limited "expressive" voices |
| Who translates | Your coding agent, line by line with a per-line character budget (no extra key) | Their model, fixed | Your LLM key | Google, no edits |
| Fits the timing | Budget before voicing, free `check`, then max 1.2x speed-up and reported drift | Automatic, opaque | Speed-up / re-gen loops | Automatic |
| Fix one line | Edit one line, re-render: others cached, not billed | Re-dub segment in editor | Re-run pipeline | Not possible |
| Output | MP4 (picture untouched), SRT, full-length track for YouTube multi-language audio | MP4 / track | MP4 / SRT | Only on YouTube |
| Setup | Python stdlib + ffmpeg, no GPU, no model download | Upload to their cloud | Conda/Docker, model downloads, GPU recommended | None |

Honest limits: speech recognition is cloud-based (needs a key and internet); reference clips for cloning
must currently be public URLs (an upload endpoint is planned by Miragea); English is the focus.

### Auto B-roll vs. the alternatives

| | **auto-broll** | Submagic / Captions / Descript AI B-roll | Manual B-roll in Premiere / CapCut | Other B-roll agent skills |
|---|---|---|---|---|
| Price | Free, MIT; pay-as-you-go transcription (voice only in faceless mode) | Monthly plans, B-roll often on higher tiers | Your time | Free; most need extra LLM / video-gen keys |
| Cut timing | On the exact spoken word (word times from the transcript, 0.1 s lead) | Automatic, coarse | Frame-accurate but by hand | Varies (SRT-line level is common) |
| Footage | Your own clips and stills, or free Pexels stock | Their stock library | Anything you import | Generated video (paid) or stock |
| Editorial rules | Built-in checks: hook never covered, no flash cuts, speaker breaks, 20-40% coverage | Opaque | Your judgement | Mostly none |
| Hand-off to an editor | MP4 + CMX 3600 EDL (Premiere, Resolve, Avid) | Export MP4 only | Native | MP4 only (mostly) |
| Faceless video | Voices your script in your own cloned voice, then covers it with B-roll | Stock voices | Separate TTS | Free TTS voices |
| Setup | Python stdlib + ffmpeg | Upload to their cloud | Desktop app | Node/Remotion or model keys |


### UGC video ads vs. the alternatives

| | **ugc-video-ads** | Arcads / Creatify / MakeUGC | Video-model ad skills (Seedance, Veo, Kling) | CapCut / Canva by hand |
|---|---|---|---|---|
| Price | Free, MIT; pay-as-you-go voice | Monthly plans, per-video credits | Free skill; you pay per generated clip | Your time |
| Voice | Your own (or founder's) cloned voice, same in every variant | Stock AI actors and voices | Model voice or a separate TTS | Stock TTS or record yourself |
| Footage | Your real product photos, clips, screen recordings | AI avatars | Generated video (can drift between shots, garbles on-screen text) | Anything |
| Hook testing | Every hook x every body in one run; lines cached, a new hook re-bills only itself | Re-generate per variant | Re-generate per variant | Duplicate the project |
| Platform safe zones, -14 LUFS, 3 s hook check | Built in, measured | Varies | Rarely | Manual |
| Claim lint (guarantees, health, income, "free", personal attributes) | Free `check` before any spend | No | Some | No |
| Hand-off | MP4 per ratio + SRT + manifest.csv for Ads Manager naming | MP4 | MP4 | MP4 |

The coined term we use: a **voice-first UGC ad**, real product footage carried by a real (cloned) voice, so
every variant sounds like the same creator.

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

### How do I dub a YouTube video into Spanish (or any language) in my own voice?
Run `python3 video-dubbing/scripts/dub.py prep talk.mp4 --to es`, let your agent fill the `text` of each line in `talk.es.dub.json` (it sees a character budget per line), check for free with `dub.py check`, then `dub.py render talk.mp4 talk.es.dub.json`. You get the dubbed MP4 in your cloned voice, Spanish SRT captions, and `talk.es.dub.wav` to upload as an extra YouTube audio track.

### Is there an open-source alternative to ElevenLabs Dubbing or HeyGen video translation?
Yes: the video-dubbing skill. It runs locally with Python and ffmpeg, uses your own cloned voice through the Miragea API, lets your coding agent do the translation, and costs only pay-as-you-go voice and transcription. It does not do lip-sync.

### How do I add B-roll to a talking-head video automatically?
Run `python3 auto-broll/scripts/broll.py prep talk.mp4 --library broll/`, let your agent add `cutaways` to `talk.broll.json` (each one names the clip and the spoken word it lands on), check for free with `broll.py check`, then `broll.py render talk.mp4 talk.broll.json`. You get the edited MP4 plus an EDL for Premiere Pro or DaVinci Resolve; `pexels:<query>` clips are downloaded with `broll.py fetch`.

### How do I make a faceless YouTube video with B-roll and my own voice?
Write the script, run `broll.py prep --script script.txt --library broll/ --vertical` (it voices the script in your cloned Miragea voice and times every word), let your agent pick a shot every 2-4 seconds, then render. Each shot runs until the next, so the screen is never empty, and the audio is normalised to -14 LUFS.

### How do I make a UGC-style TikTok ad without filming myself?
Put a few product photos or clips in a folder, let your agent write `ad.json` (3-5 hooks, a short body, a CTA, an end card), run `python3 ugc-video-ads/scripts/ads.py check ad.json` for free, then `ads.py render ad.json --ratios 9:16,4:5`. Every line is voiced in your own cloned voice, captioned and kept inside the TikTok/Reels safe zones.

### How do I create ad creative variations for testing on Meta or TikTok?
The ugc-video-ads skill renders every hook with every body (for example 4 hooks x 2 bodies = 8 ads) and names the files `brand_hook-body_9x16.mp4`, with a `manifest.csv` for Ads Manager. Body lines are voiced once and cached, so adding a new hook only pays for that one line.

## Credits

video-to-shorts is an original rewrite inspired by these MIT-licensed projects (no code copied):
[SamurAIGPT/AI-Youtube-Shorts-Generator](https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator),
[mutonby/openshorts](https://github.com/mutonby/openshorts) and
[browser-use/video-use](https://github.com/browser-use/video-use). Thank you to their authors.

video-dubbing is an original rewrite inspired by
[Huanshere/VideoLingo](https://github.com/Huanshere/VideoLingo) (Apache-2.0),
[jianchang512/pyvideotrans](https://github.com/jianchang512/pyvideotrans) (GPL-3.0) and
[krillinai/OpenCreator (KrillinAI)](https://github.com/krillinai/OpenCreator) (Apache-2.0); no code was copied.
Thank you to their authors for showing what creators need from video translation.

auto-broll is an original rewrite (no code copied) informed by the B-roll agent skills creators shared in 2026:
[Barty-Bart/motion-graphics](https://github.com/Barty-Bart/motion-graphics) (motion-broll),
[Samin12/b-roll-finder](https://github.com/Samin12/b-roll-finder),
[WhiteTowerAI/cut-as-code](https://github.com/WhiteTowerAI/cut-as-code) (MIT) and
[erduo1998-cell/erduo-broll-loop-engineering](https://github.com/erduo1998-cell/erduo-broll-loop-engineering) (MIT).
Thank you to their authors for showing that B-roll should land on the word, with the editor keeping the final say.

ugc-video-ads is an original rewrite (no code copied) informed by the UGC ad agent skills of 2026:
[charlesdove977/UGC-Factory](https://github.com/charlesdove977/UGC-Factory) (MIT),
[iart-ai/ad-video-skills](https://github.com/iart-ai/ad-video-skills) (MIT) and Ahmad Dogar's
[reel-studio write-up](https://dev.to/ahmad_dogar_7d098f5e48f72/i-built-a-claude-code-skill-that-makes-video-ads-without-a-video-model-51op)
on making ads without a video model. Thank you to their authors.

## Related projects

- [Retake](https://github.com/yyert123/retake) - fix a flubbed voiceover line in your own voice (CLI + MCP).
- [HeadVox](https://github.com/yyert123/headvox) - script to voiceover with word-aligned captions.

## License

MIT. Skills follow the open [Agent Skills specification](https://agentskills.io/specification).
| `jump-cut-editor` | Remove silences, ums and stutters from talking-head videos (AI jump cut editor) |
| `voice-patch` | Fix a wrong word or number in a finished video by re-speaking it in your cloned voice (AI overdub) |
| `slides-to-video` | Turn slides plus speaker notes into a narrated MP4 + SRT in your cloned voice (PowerPoint/PDF to video) |
| `dub-batch` | One video into many languages (Spanish, Portuguese, Hindi...) in your cloned voice, one command |
