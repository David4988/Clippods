"""
Phase 5 measurement: sentences, thought units and safe cut points on real podcasts.

    python -m evaluation.experiments.phase5_structure_report

Offline — no ASR, no models. Reads transcripts already saved under
<eval_dir>/realworld/ at the current V1 ASR configurations and reports, per
language and per window, the distributions CP4 needs (D6 padding, D7 durations,
D8 open loops), plus the master-plan diagnostic: where legacy_v2@5 clip
boundaries land relative to speech and to the nearest safe cut.

Output: <eval_dir>/realworld/phase5/report.json and report.md
"""
from __future__ import annotations

import json
import sys
import time
from bisect import bisect_left
from pathlib import Path

from evaluation.storage import eval_dir, write_json

# (group, window label, path relative to <eval_dir>/realworld, note)
SOURCES = [
    *[("en", f"en{i}.{w}", f"asr/base/en{i}.body_{w}.transcript.json", "en_v1 (rich_v1 + base)")
      for i in (1, 2, 3) for w in ("early", "middle", "late")],
    ("hi", "hi1.middle", "adaptive_v1/hi1.body_middle.hi.transcript.json", "hi_v1 OFF, adaptive"),
    ("hi", "hi2.middle", "adaptive_v1/hi2.body_middle.hi.transcript.json", "hi_v1 OFF, adaptive"),
    ("hi", "hi2.early", "ev51/hi2.body_early.B_off.transcript.json", "hi_v1 OFF, first pass"),
    ("hi", "hi2.late", "ev51/hi2.body_late.B_off.transcript.json", "hi_v1 OFF, first pass"),
    ("hi", "hi3.early", "ev51/hi3.body_early.B_off.transcript.json", "hi_v1 OFF, first pass"),
    # EV-5.1: hi3 middle/late are English speech decoded under forced `hi`.
    ("hi_english_speech", "hi3.middle", "ev51/hi3.body_middle.B_off.transcript.json", "English speech, forced hi"),
    ("hi_english_speech", "hi3.late", "ev51/hi3.body_late.B_off.transcript.json", "English speech, forced hi"),
    ("ta", "ta1.middle", "adaptive_v1/ta1.body_middle.ta.transcript.json", "ta_v1 OFF, adaptive"),
    ("ta", "ta2.middle", "adaptive_v1/ta2.body_middle.ta.transcript.json", "ta_v1 OFF, adaptive"),
]
SCALE = ("ta2.full (74 min)", "adaptive_v1/ta2.full.ta.transcript.json", "older config: ta previous-text ON")
GROUPS = ["en", "hi", "ta", "hi_english_speech"]


def pct(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    xs = sorted(values)

    def q(f: float) -> float:
        return round(xs[min(len(xs) - 1, int(f * (len(xs) - 1) + 0.5))], 2)
    return {"n": len(xs), "p10": q(0.1), "p25": q(0.25), "p50": q(0.5), "p75": q(0.75), "p90": q(0.9),
            "max": round(xs[-1], 2)}


def in_speech(t: float, regions) -> bool:
    return any(a < t < b for a, b in regions)


def nearest(t: float, sorted_times: list[float]) -> float | None:
    if not sorted_times:
        return None
    i = bisect_left(sorted_times, t)
    return min(abs(t - sorted_times[j]) for j in (i - 1, i) if 0 <= j < len(sorted_times))


def measure(transcript) -> dict:
    """Everything one window contributes (raw lists, pooled later per language)."""
    from services.segment_selection import select_segments
    from services.speech_structure import build_speech_structure
    from services.cut_points import cuts_outside_silence
    from services.speech_regions import silences
    from services.units import terminal_of

    t0 = time.perf_counter()
    s = build_speech_structure(transcript)
    build_ms = round((time.perf_counter() - t0) * 1000, 1)
    regions = transcript.speech_regions.regions
    sil = silences(regions, transcript.speech_regions.audio_duration)
    cut_ins = sorted(c.cut_in for c in s.cut_points if c.cut_in is not None)
    cut_outs = sorted(c.cut_out for c in s.cut_points if c.cut_out is not None)

    # Silence after punctuation-terminated words: how long real sentence ends pause.
    gap_after = {c.after_word: c.gap_ms for c in s.cut_points if c.after_word is not None}
    punct_end_gaps = [gap_after.get(w.index, 0) for w in s.words[:-1]
                      if terminal_of(w.text, s.language) and s.words[w.index + 1].run == w.run]

    # Legacy diagnostic: legacy_v2@5 boundaries vs speech and safe cuts (not shipped).
    legacy = select_segments(transcript.legacy_segments(), transcript.audio_duration, max_clips=5)
    starts = [c["start"] for c in legacy]
    ends = [c["end"] for c in legacy]

    return {
        "build_ms": build_ms,
        "stats": s.stats,
        "cuts_outside_silence": len(cuts_outside_silence(s.cut_points, sil)),
        "sentence_durations": [x.end - x.start for x in s.sentences],
        "sentence_reasons": [x.boundary_reason for x in s.sentences],
        "thought_durations": [x.end - x.start for x in s.thoughts],
        "thought_reasons": [x.boundary_reason for x in s.thoughts],
        "punct_end_gaps_ms": punct_end_gaps,
        "sentence_inner": s.stats["sentences"]["boundaries"],
        "thought_inner": s.stats["thoughts"]["boundaries"],
        "legacy": {
            "starts_inside_speech": sum(in_speech(t, regions) for t in starts),
            "ends_inside_speech": sum(in_speech(t, regions) for t in ends),
            "boundaries": len(starts) + len(ends),
            "start_move_s": [d for d in (nearest(t, cut_ins) for t in starts) if d is not None],
            "end_move_s": [d for d in (nearest(t, cut_outs) for t in ends) if d is not None],
        },
        "excerpt": [{"start": round(x.start, 1), "end": round(x.end, 1), "reason": x.boundary_reason,
                     "start_cut": x.start_cut, "end_cut": x.end_cut, "text": x.text[:160]}
                    for x in s.thoughts[:4]],
    }


def pool(rows: list[dict]) -> dict:
    from collections import Counter

    def total(key, field):
        return sum(r[key][field] for r in rows)

    words = sum(r["stats"]["trusted_words"] for r in rows)
    sec = sum(r["stats"]["sentences"]["count"] for r in rows)
    terminals = sum((r["stats"]["terminals_per_100_words"] or 0) * r["stats"]["trusted_words"] / 100 for r in rows)
    s_inner, s_safe = total("sentence_inner", "inner_boundaries"), total("sentence_inner", "with_safe_cut")
    t_inner, t_safe = total("thought_inner", "inner_boundaries"), total("thought_inner", "with_safe_cut")
    minutes = sum(r["minutes"] for r in rows)
    lb = sum(r["legacy"]["boundaries"] for r in rows)
    lin = sum(r["legacy"]["starts_inside_speech"] + r["legacy"]["ends_inside_speech"] for r in rows)
    pooled_reasons = lambda key: dict(sorted(Counter(x for r in rows for x in r[key]).items()))
    return {
        "windows": len(rows),
        "minutes": round(minutes, 1),
        "trusted_words": words,
        "excluded_seconds": round(sum(r["stats"]["excluded_seconds"] for r in rows), 1),
        "terminals_per_100_words": round(100 * terminals / words, 2) if words else None,
        "sentences": sec,
        "sentence_reasons": pooled_reasons("sentence_reasons"),
        "sentence_duration_s": pct([d for r in rows for d in r["sentence_durations"]]),
        "thoughts": sum(r["stats"]["thoughts"]["count"] for r in rows),
        "thought_reasons": pooled_reasons("thought_reasons"),
        "thought_duration_s": pct([d for r in rows for d in r["thought_durations"]]),
        "sentence_boundary_safe_share": round(s_safe / s_inner, 3) if s_inner else None,
        "thought_boundary_safe_share": round(t_safe / t_inner, 3) if t_inner else None,
        "cut_points_per_minute": round(sum(r["stats"]["cut_points"]["count"] for r in rows) / minutes, 2),
        "silence_after_punct_ms": pct([g for r in rows for g in r["punct_end_gaps_ms"]]),
        "punct_ends_with_no_silence_share": (
            round(sum(g == 0 for r in rows for g in r["punct_end_gaps_ms"])
                  / max(1, sum(len(r["punct_end_gaps_ms"]) for r in rows)), 3)),
        "cuts_outside_silence": sum(r["cuts_outside_silence"] for r in rows),
        "cut_points": sum(r["stats"]["cut_points"]["count"] for r in rows),
        "words_inside_cut_silences": sum(r["stats"]["words_inside_cut_silences"] for r in rows),
        "legacy_boundaries_inside_speech": f"{lin}/{lb}",
        "legacy_start_move_s": pct([d for r in rows for d in r["legacy"]["start_move_s"]]),
        "legacy_end_move_s": pct([d for r in rows for d in r["legacy"]["end_move_s"]]),
    }


def markdown(report: dict) -> str:
    g = report["groups"]
    cols = [k for k in GROUPS if k in g]
    lines = ["# Phase 5 — speech structure on real podcasts", "",
             f"Generated {report['generated']} · structure `{report['structure_version']}` · params "
             f"`{json.dumps(report['params'], ensure_ascii=False)}`", "",
             "| metric | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(str(fn(g[c])) for c in cols) + " |")

    row("windows / minutes", lambda x: f"{x['windows']} / {x['minutes']}")
    row("trusted words", lambda x: x["trusted_words"])
    row("untrusted speech excluded (s)", lambda x: x["excluded_seconds"])
    row("terminals per 100 words", lambda x: x["terminals_per_100_words"])
    row("sentences by reason", lambda x: x["sentence_reasons"])
    row("sentence duration p10/p50/p90 (s)", lambda x: _q(x["sentence_duration_s"]))
    row("thoughts by reason", lambda x: x["thought_reasons"])
    row("thought duration p10/p50/p90 (s)", lambda x: _q(x["thought_duration_s"]))
    row("sentence boundaries with a safe cut", lambda x: x["sentence_boundary_safe_share"])
    row("thought boundaries with a safe cut", lambda x: x["thought_boundary_safe_share"])
    row("silence after punctuation p25/p50/p75 (ms)",
        lambda x: _q(x["silence_after_punct_ms"], ("p25", "p50", "p75")))
    row("punctuation ends with no silence", lambda x: x["punct_ends_with_no_silence_share"])
    row("cut points per minute", lambda x: x["cut_points_per_minute"])
    row("cut times outside VAD silence", lambda x: f"{x['cuts_outside_silence']} of {x['cut_points']}")
    row("words timed inside a cut silence", lambda x: f"{x['words_inside_cut_silences']} of {x['trusted_words']}")
    row("legacy_v2@5 boundaries inside speech", lambda x: x["legacy_boundaries_inside_speech"])
    row("legacy start → nearest safe cut p50/p90 (s)", lambda x: _q(x["legacy_start_move_s"], ("p50", "p90")))
    row("legacy end → nearest safe cut p50/p90 (s)", lambda x: _q(x["legacy_end_move_s"], ("p50", "p90")))
    sc = report["scale_check"]
    lines += ["", f"Scale check — {sc['label']} ({sc['note']}): built in {sc['build_ms']} ms, "
                  f"{sc['words']} words, {sc['cut_points']} cut points, "
                  f"{sc['cuts_outside_silence']} outside silence.", "", "## Per window", "",
              "| window | group | note | sentences | thoughts | safe sentence / thought boundaries | cuts/min |",
              "|---|---|---|---|---|---|---|"]
    for w in report["windows"]:
        st = w["stats"]
        lines.append(f"| {w['label']} | {w['group']} | {w['note']} | {st['sentences']['count']} | "
                     f"{st['thoughts']['count']} | {st['sentences']['boundaries']['safe_share']} / "
                     f"{st['thoughts']['boundaries']['safe_share']} | {st['cut_points']['per_minute']} |")
    lines += ["", "## Example thoughts (first four per window)", ""]
    for w in report["windows"]:
        lines.append(f"**{w['label']}**")
        for e in w["excerpt"]:
            lines.append(f"- [{e['start']}–{e['end']} s, {e['reason']}, cuts {e['start_cut']}→{e['end_cut']}] {e['text']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _q(p: dict, keys=("p10", "p50", "p90")) -> str:
    return "/".join(str(p.get(k, "–")) for k in keys) if p.get("n") else "–"


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    from services.cut_points import CUT_PARAMS
    from services.speech_structure import VERSION
    from services.transcript import Transcript
    from services.units import UNIT_PARAMS

    root = eval_dir() / "realworld"
    out = root / "phase5"
    out.mkdir(parents=True, exist_ok=True)

    def load(rel: str):
        return Transcript.from_dict(json.loads((root / rel).read_text(encoding="utf-8")))

    windows = []
    for group, label, rel, note in SOURCES:
        t = load(rel)
        row = {"group": group, "label": label, "source": rel, "note": note,
               "minutes": t.audio_duration / 60, **measure(t)}
        windows.append(row)
        print(f"  {label:12s} {group:18s} sentences={row['stats']['sentences']['count']:4d} "
              f"thoughts={row['stats']['thoughts']['count']:3d} cuts={row['stats']['cut_points']['count']:4d} "
              f"outside_silence={row['cuts_outside_silence']}", flush=True)

    scale_t = load(SCALE[1])
    scale = measure(scale_t)
    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "structure_version": VERSION,
        "params": {**UNIT_PARAMS, **CUT_PARAMS},
        "groups": {g: pool([w for w in windows if w["group"] == g]) for g in GROUPS
                   if any(w["group"] == g for w in windows)},
        "scale_check": {"label": SCALE[0], "note": SCALE[2], "build_ms": scale["build_ms"],
                        "words": scale["stats"]["trusted_words"],
                        "cut_points": scale["stats"]["cut_points"]["count"],
                        "cuts_outside_silence": scale["cuts_outside_silence"]},
        "windows": [{k: v for k, v in w.items() if k not in (
            "sentence_durations", "thought_durations", "punct_end_gaps_ms", "sentence_reasons",
            "thought_reasons")} for w in windows],
    }
    write_json(out / "report.json", report)
    (out / "report.md").write_text(markdown(report), encoding="utf-8")
    print(f"wrote {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
