---
name: manim-narration
description: Voiceover for Manim (3Blue1Brown-style) explainer videos in your own cloned voice. Turns a script into one narration clip per scene, reads math aloud naturally (x^2 becomes "x squared"), measures real duration and word times, and gives you a Narrated mixin so animations land on the exact spoken word, plus an SRT and a one-command mux for silent renders. Manim voiceover, 3Blue1Brown style video with AI voice, math explainer video, animated explainer from a paper, algorithm visualization narration, ManimCE and ManimGL, text to speech for Manim, add voiceover to Manim video, sync animation to narration. Use when the user says narrate my Manim scene, add my voice to this math animation, make a 3b1b style explainer, or sync animations to the voiceover. Claude Code, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ (standard library only), ffmpeg/ffprobe on PATH; Manim Community (or ManimGL) only to render your own scenes. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech + speech recognition (https://miragea.ai/v1)"
---

# Manim narration (the voice sets the pace, the animation follows)

Manim animations have run times, not timestamps. The reliable way to sync them is voice first: generate each
scene's narration, read the word times, then set every `run_time` from them. This skill does that in your own
cloned voice, with no local TTS model to install and no free-TTS robot voice.

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it; free key at https://miragea.ai). `export MIRAGEA_ACTOR_ID=...` (your saved voice) or pass `--voice`.
   No saved voice yet? The error explains how to create one.
2. Write `script.md`: `## key` per scene, plain English, math written naturally (`x^2`, `3/4`, `∫`, `\pi`, `$...$` all read aloud correctly). See `examples/script.md`.
3. Free preview, no API calls: `python3 scripts/manim_narrate.py plan script.md --out narration --dry-run`.
4. Real run: `python3 scripts/manim_narrate.py plan script.md --out narration`. Unchanged scenes are reused at no cost.
5. In your scene file use the helper copied into `narration/` (`from narration_manim import Narrated`):
   ```python
   class Explainer(Narrated, Scene):
       def construct(self):
           with self.narrate("intro") as n:
               self.play(Write(title), run_time=n.until("derivative"))   # next beat starts on the word "derivative"
               self.play(Create(curve), run_time=n.until_end(0.5))
   ```
   The voice is added with `add_sound`, the clip is never cut off, and the scene waits for it to end.
6. Render: `manim -qh scene.py Explainer`. Captions: `narration/narration.srt` (sentence cues).
7. Silent render or ManimGL? `NARRATION_MUTE=1 manim ...` then `python3 scripts/manim_narrate.py mux media/.../Explainer.mp4 --narration narration -o final.mp4` (uses the recorded start times, video stream copied).
8. Check a few frames and listen once; if a line is too long for its visual, shorten the script line and re-run.

## Options (`plan`)
| Flag | Default | Meaning |
|---|---|---|
| `--voice` | `$MIRAGEA_ACTOR_ID` | Saved Miragea voice |
| `--out` | `narration` | Output folder |
| `--pad` | 0.6 | Seconds of air between scenes in the planned timeline |
| `--model` | expressive | `standard` follows the reference voice more closely |
| `--dry-run` | off | Silent placeholder clips, estimated timing |

## How it compares
| | Yusuke710/manim-skill | manim-voiceover plugin | This skill |
|---|---|---|---|
| Your own cloned voice | no (local Kokoro) | service-dependent | yes (Miragea actor) |
| Setup | clone repo, uv sync, Cairo, LaTeX | pip plugin per TTS service | stdlib + ffmpeg |
| Word-level sync from the real audio | scene-level | service timestamps | Miragea ASR word times (`n.until("word")`) |
| Reads math aloud | manual | manual | built in (squared, over, integral, pi, ...) |
| Silent render fix | n/a | n/a | `mux` with recorded start times |

## FAQ
- Does it write the Manim code? No: your agent does; this skill owns voice, timing and captions.
- Not 3Blue1Brown style, just a screen demo? Use `screen-recording-voiceover` or `hyperframes-narration` in the same collection.
- Free TTS? Never; every line goes through Miragea, so voice and word timing come from one engine.
- Whose voice? Only voices you own or have consent for.

Credit: Manim (3Blue1Brown, Manim Community; MIT) for the animation engine; concept from Yusuke710/manim-skill (MIT), manim-voiceover (MIT) and devamsheth21/3b1b-video-skill. Code written from scratch.
