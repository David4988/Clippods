"""
Render results.json from asr_model_compare as a markdown report.

    python -m evaluation.experiments.asr_model_compare_report <results.json>
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def _fmt(value, digits=3):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render(results: dict) -> str:
    lines = ["# ASR model comparison", ""]
    env = results["environment"]
    lines += [f"Environment: Python {env['python']}, {env['platform']}, {env['logical_cpus']} logical CPUs, "
              f"{env['ram_gb']} GB RAM; packages {env['packages']}", ""]
    lines += ["## Models on disk", "", "| repo | revision | size | path |", "|---|---|---|---|"]
    for repo, info in results["models"].items():
        lines.append(f"| {repo} | `{(info['revision'] or '')[:12]}` | {info['size_bytes'] / 2**30:.2f} GiB | `{info['path']}` |")
    lines.append("")

    lines += ["## Resources per group", "",
              "| model | variant | load s | RSS after load MB | peak RSS MB | group wall s |", "|---|---|---|---|---|---|"]
    for g in results["groups"]:
        lines.append(f"| {g['model']} | {g['variant']} | {g['model_load_s']} | {g['rss_mb_after_load']} | "
                     f"{g['peak_rss_mb']} | {g.get('wall_s')} |")
    lines.append("")

    # Aggregate runs by (item, mode) → per group
    table = defaultdict(dict)
    for g in results["groups"]:
        key = f"{g['model']} / {g['variant']}"
        for run in g["runs"]:
            table[(run["item"], run["mode"])].setdefault(key, []).append(run)

    for (item, mode), groups in table.items():
        lines += [f"## {item} (language mode: {mode})", ""]
        if item == "mixed":
            lines += ["| model / variant | run | decoded lang (p) | uncertain | hi CER / Devanagari | en Latin | ta CER / Tamil script | suspects | coverage | total s |",
                      "|---|---|---|---|---|---|---|---|---|---|"]
            for key, runs in groups.items():
                for r in runs:
                    p = r["portions"]
                    lines.append(
                        f"| {key} | {r['repeat']} | {r['language']} ({_fmt(r['language_probability'], 2)}) | {r['language_uncertain']} | "
                        f"{_fmt(p['hi']['cer'])} / {_fmt(p['hi']['expected_script_share'], 2)} | {_fmt(p['en']['expected_script_share'], 2)} | "
                        f"{_fmt(p['ta']['cer'])} / {_fmt(p['ta']['expected_script_share'], 2)} | {r['hallucination_suspects']} | "
                        f"{_fmt(r['speech_coverage'], 2)} | {r['timings']['total_s']} |")
        else:
            lines += ["| model / variant | run | CER | expected script | decoded lang (p) | temps | suspects (flags) | intro-music text | words in speech | coverage | decode s | total s | RTF |",
                      "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for key, runs in groups.items():
                for r in runs:
                    w = r["words"]
                    flags = ", ".join(f"{k}:{v}" for k, v in r["flag_counts"].items()) or "none"
                    lines.append(
                        f"| {key} | {r['repeat']} | {_fmt(r['cer'])} | {_fmt(r['expected_script_share'], 2)} | "
                        f"{r['language']} ({_fmt(r['language_probability'], 2)}) | {r['temperatures']} | "
                        f"{r['hallucination_suspects']} ({flags}) | {repr(r['text_in_music_intro'][:30]) if r['text_in_music_intro'] else '—'} | "
                        f"{_fmt(w['in_speech_fraction'], 2) if w else '—'} | {_fmt(r['speech_coverage'], 2)} | "
                        f"{r['timings'].get('decode_s')} | {r['timings']['total_s']} | {r['rtf']} |")
        # stability
        stable = []
        for key, runs in groups.items():
            if len(runs) > 1:
                stable.append(f"{key}: {'identical' if len({r['text'] for r in runs}) == 1 else 'DIFFERENT'}")
        if stable:
            lines += ["", "Repeat stability: " + "; ".join(stable)]
        lines.append("")

    lines += ["## Word timestamps (first repeat, words-enabled groups)", "",
              "| item/mode | model / variant | words | in speech | non-monotonic | ≤0 s | median dur s | max dur s | mean prob |",
              "|---|---|---|---|---|---|---|---|---|"]
    for (item, mode), groups in table.items():
        for key, runs in groups.items():
            w = runs[0]["words"]
            if w:
                lines.append(f"| {item}/{mode} | {key} | {w['count']} | {w['in_speech_fraction']} | {w['non_monotonic']} | "
                             f"{w['zero_or_negative']} | {w['median_duration_s']} | {w['max_duration_s']} | {w['mean_probability']} |")
    lines.append("")

    lines += ["## Sample output (first repeat, first 160 chars)", ""]
    for (item, mode), groups in table.items():
        if item == "mixed":
            continue
        lines.append(f"**{item} / {mode}**")
        lines.append("")
        for key, runs in groups.items():
            lines.append(f"- {key}: {runs[0]['text'][:160]}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = Path((argv or sys.argv[1:])[0])
    report = render(json.loads(path.read_text(encoding="utf-8")))
    out = path.with_name("report.md")
    out.write_text(report, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
