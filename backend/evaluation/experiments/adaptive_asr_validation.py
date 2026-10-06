"""
Real-podcast validation of the adaptive ASR pipeline (adaptive_v1).

    python -m evaluation.experiments.adaptive_asr_validation windows
    python -m evaluation.experiments.adaptive_asr_validation long <key> <language>

windows: the 5-minute podcast-body windows used in the previous-text ON/OFF
comparison (ta1, ta2, hi1, hi2) plus en1, with manual language selection, and
en1 once more with `auto`.
long:    one whole podcast end to end.

Uses only cached audio and local models. Output: <eval_dir>/realworld/adaptive_v1/
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from evaluation.experiments.realworld_asr import cut
from evaluation.storage import eval_dir, write_json

WINDOWS = [("ta1", "ta"), ("ta2", "ta"), ("hi1", "hi"), ("hi2", "hi"), ("en1", "en"), ("en1", "auto")]


def _norm(text: str) -> list[str]:
    from services.transcript_quality import _normalise
    return _normalise(text).split()


def boundary_checks(t) -> list[dict]:
    """At every accepted region edge: overlap, speech left in the gap, repeated words."""
    from services.speech_regions import overlap_seconds

    speech = t.speech_regions.regions if t.speech_regions else []
    segs = t.segments
    rows = []
    for a in t.attempts:
        if a.scope != "region" or a.outcome != "accepted":
            continue
        idx = [i for i, s in enumerate(segs) if s.attempt == a.attempt]
        if not idx:
            rows.append({"attempt": a.attempt, "region": a.region, "note": "accepted but inserted nothing"})
            continue
        for side, (i, j) in (("start", (idx[0] - 1, idx[0])), ("end", (idx[-1], idx[-1] + 1))):
            if i < 0 or j >= len(segs):
                continue
            left, right = segs[i], segs[j]
            l_end = left.words[-1].end if left.words else left.end
            r_start = right.words[0].start if right.words else right.start
            lw, rw = _norm(left.text)[-8:], _norm(right.text)[:8]
            shared = max((n for n in range(1, min(len(lw), len(rw)) + 1) if lw[-n:] == rw[:n]), default=0)
            tri_l = {tuple(lw[k:k + 3]) for k in range(len(lw) - 2)}
            tri_r = {tuple(rw[k:k + 3]) for k in range(len(rw) - 2)}
            rows.append({
                "attempt": a.attempt, "region": a.region, "side": side,
                "left": f"[{left.attempt}] {left.text[-60:]}", "right": f"[{right.attempt}] {right.text[:60]}",
                "segment_overlap_s": round(max(0.0, left.end - right.start), 3),
                "word_gap_s": round(r_start - l_end, 3),
                "speech_in_word_gap_s": round(overlap_seconds(l_end, r_start, speech), 2) if r_start > l_end else 0.0,
                "repeated_edge_words": shared,
                "shared_trigrams": len(tri_l & tri_r),
            })
    return rows


def global_checks(t) -> dict:
    segs = t.segments
    words = [w for s in segs for w in (s.words or [])]
    return {
        "segments_ordered": all(a.start <= b.start for a, b in zip(segs, segs[1:])),
        "segment_overlaps": sum(1 for a, b in zip(segs, segs[1:]) if a.end > b.start + 1e-6),
        "words_ordered": all(a.start <= b.start + 1e-6 for a, b in zip(words, words[1:])),
        "ids_sequential": [s.id for s in segs] == list(range(len(segs))),
        "zero_length_words": sum(1 for w in words if w.end - w.start <= 0),
        "words_over_2s": sum(1 for w in words if w.end - w.start > 2.0),
        "repeated_text_seconds": round(sum(s.end - s.start for s in segs if "repeated_text" in s.flags), 1),
        "words": len(words),
        "words_per_speech_minute": round(len(words) / (t.speech_regions.speech_seconds / 60), 1)
        if t.speech_regions and t.speech_regions.speech_seconds else None,
        "trusted_words_per_speech_minute": _trusted_wpm(t),
    }


def _trusted_wpm(t):
    from services.transcript_quality import segment_suspicion
    if not t.speech_regions or not t.speech_regions.speech_seconds:
        return None
    n = sum(len(s.words or []) for s in t.segments if not segment_suspicion(s))
    return round(n / (t.speech_regions.speech_seconds / 60), 1)


def readable(t, offset: float = 0.0) -> str:
    def clock(x):
        x = x + offset
        return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"
    lines = [f"# status={t.quality.status} language={t.language.language} mode={t.language.mode} "
             f"profile={t.asr['pipeline']['profile']}"]
    for a in t.attempts:
        region = "" if a.region is None else f" region {clock(a.region[0])}–{clock(a.region[1])}"
        lines.append(f"# attempt {a.attempt}: {a.scope} {a.model} {a.profile} prevtext={a.condition_on_previous_text}"
                     f"{region} reasons={a.retry_reasons} outcome={a.outcome} status={a.quality_status}")
    for s in t.segments:
        flags = f"  {{{', '.join(s.flags)}}}" if s.flags else ""
        lines.append(f"[{clock(s.start)}] a{s.attempt} {s.text}{flags}")
    return "\n".join(lines) + "\n"


class PeakRss:
    def __init__(self):
        import psutil
        self.proc = psutil.Process()
        self.peak = self.proc.memory_info().rss
        self.stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stop.wait(0.2):
            self.peak = max(self.peak, self.proc.memory_info().rss)

    def reset(self):
        self.peak = self.proc.memory_info().rss


def run_case(audio: Path, language: str, out: Path, stem: str, offset: float, rss: PeakRss) -> dict:
    from services.asr_pipeline import transcribe_adaptive

    rss.reset()
    started = time.perf_counter()
    t = transcribe_adaptive(str(audio), language=language)
    wall = round(time.perf_counter() - started, 1)
    regions = [a for a in t.attempts if a.scope == "region"]
    row = {
        "case": stem, "language_selection": language, "wall_s": wall,
        "audio_s": t.audio_duration, "rtf": round(wall / t.audio_duration, 3),
        "peak_rss_mb": round(rss.peak / 2**20),
        "status": t.quality.status, "reasons": t.quality.reasons,
        "language": t.language.language, "language_uncertain": t.language.uncertain,
        "language_reasons": t.language.reasons, "pipeline": t.asr["pipeline"],
        "timings": t.timings,
        "attempt1": {k: getattr(t.attempts[0], k) for k in ("model", "profile", "condition_on_previous_text",
                                                           "quality_status", "decode_s", "metrics")},
        "regions": [{"attempt": a.attempt, "region": a.region, "seconds": round(a.region[1] - a.region[0], 1),
                     "reasons": a.retry_reasons, "notes": a.metrics.get("region_notes"),
                     "outcome": a.outcome, "status": a.quality_status, "decode_s": a.decode_s,
                     "before": a.metrics.get("before"), "after": a.metrics.get("after")} for a in regions],
        "retried_seconds": round(sum(a.region[1] - a.region[0] for a in regions), 1),
        "final_suspicious_spans": len(t.suspicious_spans),
        "checks": global_checks(t),
        "boundaries": boundary_checks(t),
    }
    write_json(out / f"{stem}.json", row)
    write_json(out / f"{stem}.transcript.json", t.to_dict())
    (out / f"{stem}.txt").write_text(readable(t, offset), encoding="utf-8")
    print(f"  {stem}: status={row['status']} wall={wall}s rtf={row['rtf']} regions={len(regions)} "
          f"accepted={sum(1 for a in regions if a.outcome == 'accepted')} retried={row['retried_seconds']}s "
          f"trusted_wpm={row['checks']['trusted_words_per_speech_minute']} "
          f"loops={row['checks']['repeated_text_seconds']}s peak={row['peak_rss_mb']}MB", flush=True)
    return row


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    root = eval_dir() / "realworld"
    out = root / "adaptive_v1"
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads((root / "windows.json").read_text(encoding="utf-8"))
    rss = PeakRss()

    if argv[0] == "windows":
        rows = []
        for key, language in WINDOWS:
            window = next(w for w in plan[key]["windows"] if w["label"] == "body_middle")
            clip = root / "windows" / f"{key}.body_middle.{window['start']}.wav"
            cut(root / "audio" / f"{key}.wav", window["start"], window["duration"], clip)
            rows.append(run_case(clip, language, out, f"{key}.body_middle.{language}", window["start"], rss))
        write_json(out / "windows_summary.json", rows)
    elif argv[0] == "long":
        key, language = argv[1], argv[2]
        run_case(root / "audio" / f"{key}.wav", language, out, f"{key}.full.{language}", 0.0, rss)
    rss.stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
