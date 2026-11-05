"""critical-thinking のリリースノートに載せる数字を、dev/ct-eval/runs/*/summary.md から集計して表示する。
  python3 dev/release-eval/ct_numbers.py --detect r12:logic r19:logic r19d:somosomo --rewrite r21a r21b --redesign r21a r21b
run の指定は「run-label[:mode]」。detect は仕込んだ欠陥の表(found/partial/missed)、rewrite/redesign は run ごとの fixed/deferred/remains を足す。
"""
import argparse, re, sys
from pathlib import Path
RUNS = Path(__file__).resolve().parents[1] / "ct-eval" / "runs"

def detect(spec):
    label, _, mode = spec.partition(":")
    md = (RUNS / label / "summary.md").read_text()
    f = p = m = rows = 0; sec = ""
    for line in md.splitlines():
        if line.startswith("## "): sec = line
        if mode and f"/ {mode}" not in sec: continue
        mm = re.match(r"\|\s*([A-Z]+\d+)\s*\|[^|]*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", line)
        if mm and "仕込んだ欠陥" in sec:
            rows += 1; f += int(mm.group(2)); p += int(mm.group(3)); m += int(mm.group(4))
    return rows, f, p, m

def fixes(label, mode):
    md = (RUNS / label / "summary.md").read_text()
    sec = ""; fx = df = rm = runs = 0; ratios = []; kept_fail = 0; restructured = 0
    for line in md.splitlines():
        if line.startswith("## "): sec = line
        if f"/ {mode}" not in sec: continue
        mm = re.match(r"\|\s*(\d)\s*\|\s*(\d+)→(\d+)/(\d+)\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*\d+\s*\|\s*(\d+)\s*\|(.*)", line)
        if mm:
            runs += 1; fx += int(mm.group(5)); df += int(mm.group(6)); rm += int(mm.group(7))
            ratios.append(int(mm.group(4)) / int(mm.group(2)))
            rest = mm.group(9)
            if mode == "redesign":
                cells = [c.strip() for c in rest.split("|") if c.strip()]
                if len(cells) >= 3:
                    if cells[0] != "○" or cells[1] != "○": kept_fail += 1
                    if cells[2] == "○": restructured += 1
    return runs, fx, df, rm, (min(ratios), max(ratios)) if ratios else None, kept_fail, restructured

ap = argparse.ArgumentParser()
ap.add_argument("--detect", nargs="*", default=[]); ap.add_argument("--rewrite", nargs="*", default=[]); ap.add_argument("--redesign", nargs="*", default=[])
a = ap.parse_args()
R = F = P = M = 0
for spec in a.detect:
    r, f, p, m = detect(spec); R += r; F += f; P += p; M += m; print(f"detect {spec}: rows {r} found {f} partial {p} missed {m}")
if a.detect: print(f"検査: 欠陥 {R} か所 × 3 回 = {R*3} 回のうち found {F}, partial {P}, missed {M}")
for mode, labels in (("rewrite", a.rewrite), ("redesign", a.redesign)):
    tr = tf = td = trm = 0; lo, hi = 9, 0; kf = rs = 0
    for lb in labels:
        runs, fx, df, rm, ratio, kept_fail, restructured = fixes(lb, mode)
        tr += runs; tf += fx; td += df; trm += rm; kf += kept_fail; rs += restructured
        if ratio: lo, hi = min(lo, ratio[0]), max(hi, ratio[1])
        print(f"{mode} {lb}: runs {runs} fixed {fx} deferred {df} remains {rm} ratio {ratio} kept_fail {kept_fail} restructured {restructured}")
    if labels:
        tot = tf + td + trm
        print(f"{mode}: {tot} 回のうち fixed+deferred {tf+td}, remains {trm}。全体/本編の比 {lo:.1f}〜{hi:.1f}" + (f"。主結論・決裁事項を保てなかった run {kf}、背骨が替わった run {rs}/{tr}" if mode == "redesign" else ""))
