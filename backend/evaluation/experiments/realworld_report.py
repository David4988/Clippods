"""
Summarise real-world ASR validation results as markdown.

    python -m evaluation.experiments.realworld_report

Reads <eval_dir>/realworld/windows.json and asr/<model>/<key>.json, writes
<eval_dir>/realworld/report.md. Podcast-body and difficult windows are reported
in separate tables and never aggregated together.
"""
from __future__ import annotations

import json
import sys

from evaluation.storage import eval_dir


def _clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def row(model: str, key: str, plan: dict, w: dict, peak_mb: int) -> str:
    words = w["words"]
    shares = {k: v for k, v in (w["script_shares"] or {}).items() if v >= 0.02}
    probes = "".join(p[1][0] for p in w["language_probes"])  # e.g. "eheeh"
    flags = ", ".join(f"{k}:{v}" for k, v in sorted(w["flag_counts"].items(), key=lambda kv: -kv[1])[:4]) or "none"
    temps = {k: v for k, v in w["temperatures"].items() if k not in ("0.0", 0.0)}
    return (f"| {key} | {plan['lang']} | {_clock(plan['body_start'])} | {model} | {w['label']} @{_clock(w['start'])} | "
            f"{w['language']} ({w['language_probability']}) probes `{probes}` | {shares} | "
            f"{w['hallucination_suspects']}/{w['segments']} ({flags}){' fallback ' + str(temps) if temps else ''} | "
            f"speech {w['speech_seconds']}s | {words['count']} w, {words['in_speech_fraction']} in speech, "
            f"{words['zero_or_negative']} zero-len, {words['longer_than_2s']} >2s | {w['timing_suspects']} | "
            f"{w['transcript_coverage']} (missing {w['untranscribed_speech']['seconds']}s) | {w['rtf']}× | {peak_mb} MB |")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = eval_dir() / "realworld"
    plan = json.loads((root / "windows.json").read_text(encoding="utf-8"))
    header = ("| Video | Lang | Body starts | Model | Window | Detection | Script mix | Hallucination suspects (top flags) | "
              "VAD | Word timestamps | Timing suspects | Coverage | RTF | Peak RAM |\n|" + "---|" * 14)
    body, difficult = [header], [header]
    for model in ("base", "large-v3"):
        for key in plan:
            path = root / "asr" / model / f"{key}.json"
            if not path.exists():
                continue
            result = json.loads(path.read_text(encoding="utf-8"))
            kinds = {w["label"]: w["kind"] for w in plan[key]["windows"]}
            for w in result["windows"]:
                target = body if kinds[w["label"]] == "podcast_body" else difficult
                target.append(row(model, key, plan[key], w, result["peak_rss_mb"]))
    starts = ["| Video | Duration | podcast_body_start | Confidence | Evidence |", "|---|---|---|---|---|"]
    for key, p in plan.items():
        starts.append(f"| {key} | {_clock(p['duration'])} | {_clock(p['body_start'])} ({p['body_start']} s) | "
                      f"{p['body_start_confidence']} | {p['body_start_evidence']} |")
    report = "\n".join(["# Real-world ASR validation", "", "## Podcast body starts", "", *starts, "",
                        "## Podcast body windows", "", *body, "",
                        "## Difficult regions (reported separately)", "", *difficult, ""])
    (root / "report.md").write_text(report, encoding="utf-8")
    print(root / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
