"""Drop-in helper for Manim scenes: voice first, animation second.

    from narration_manim import Narrated          # file is copied next to narration.json by `manim_narrate.py plan`
    class Explainer(Narrated, Scene):
        narration_dir = "narration"
        def construct(self):
            with self.narrate("intro") as n:                      # plays the clip, then waits for it to finish
                self.play(Write(title), run_time=n.until("derivative"))   # land exactly on the word "derivative"
                self.play(FadeIn(graph), run_time=n.until_end(0.5))

Works with Manim Community (ManimCE) and ManimGL-style scenes that have play/wait/add_sound.
Set NARRATION_MUTE=1 to skip embedding the audio (then use `manim_narrate.py mux`).
Real start times are written to narration.timeline.json so `mux` stays exact.
"""
from __future__ import annotations

import json, os, re
from pathlib import Path


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def word_time(words: list, target: str, occurrence: int = 1) -> float:
    """Start second (inside the clip) of the Nth occurrence of a word; matches ignore case/punctuation."""
    want, seen = _norm(target), 0
    for w in words:
        if _norm(w["text"]) == want:
            seen += 1
            if seen == occurrence:
                return float(w["start"])
    raise KeyError(f"word {target!r} (occurrence {occurrence}) not in this scene's narration")


class Beat:
    """Tracks where the animation is inside one narration clip."""

    def __init__(self, scene, info: dict):
        self.scene, self.info = scene, info
        self.t0 = scene._now()

    @property
    def elapsed(self) -> float:
        return self.scene._now() - self.t0

    def until(self, word: str, occurrence: int = 1, lead: float = 0.0, minimum: float = 0.05) -> float:
        """Seconds to spend so the NEXT thing starts on `word` (use as run_time or wait time)."""
        return max(minimum, word_time(self.info["words"], word, occurrence) - lead - self.elapsed)

    def until_end(self, tail: float = 0.0, minimum: float = 0.05) -> float:
        return max(minimum, self.info["durationSec"] - tail - self.elapsed)


class Narrated:
    narration_dir = "narration"
    narration_gap = 0.0  # extra seconds of air after each clip

    def _now(self) -> float:
        r = getattr(self, "renderer", None)
        return float(getattr(r, "time", None) if r is not None and getattr(r, "time", None) is not None else getattr(self, "time", 0.0))

    def _narration(self) -> dict:
        if not hasattr(self, "_narr"):
            d = Path(self.narration_dir)
            self._narr = {s["key"]: s for s in json.loads((d / "narration.json").read_text())["scenes"]}
        return self._narr

    def narrate(self, key: str):
        info = self._narration().get(key)
        if info is None:
            raise KeyError(f"no narration scene {key!r}; known: {', '.join(self._narration())}")
        return _Ctx(self, info)


class _Ctx:
    def __init__(self, scene, info):
        self.scene, self.info = scene, info

    def __enter__(self) -> Beat:
        s = self.scene
        self.beat = Beat(s, self.info)
        clip = Path(s.narration_dir) / self.info["file"]
        if os.environ.get("NARRATION_MUTE") != "1" and hasattr(s, "add_sound"):
            s.add_sound(str(clip))
        tl = Path(s.narration_dir) / "narration.timeline.json"
        data = json.loads(tl.read_text()) if tl.exists() else {}
        data[self.info["key"]] = round(self.beat.t0, 3)
        tl.write_text(json.dumps(data, indent=2))
        return self.beat

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            rest = self.info["durationSec"] + self.scene.narration_gap - self.beat.elapsed
            if rest > 0.01:
                self.scene.wait(rest)  # never cut the voice off
        return False
