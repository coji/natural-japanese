"""表から開く相談文のデータを release-notes/data/docs.json にまとめる。

スキルなしで書いた相談文(直す前)と、それを v1.6.0・v1.6.1 で直した文書、
直す前の文書で挙がった言葉と、その言葉がそれぞれで直ったかどうかの判定を1つにする。
実験の文書と判定は、リポジトリの外(.claude/work/scratch/calque-eval/score/)にある。
  python3 release-notes/build-docs.py .claude/work/scratch/calque-eval/score
"""
import json
import sys
from pathlib import Path

SCORE = Path(sys.argv[1])
TOPICS = [("finance", "経理"), ("infra", "インフラ"), ("design", "デザイナー")]
# ページで見せる1本。冒頭の比較に使った文を含む文書を選んでいる
REP = {"finance": 1, "infra": 2, "design": 1}
keymap = json.loads((SCORE / "keymap.json").read_text())

data = []
for key, reader in TOPICS:
    result = json.loads((SCORE / key / "result.json").read_text())
    topic = {"key": key, "reader": reader, "rep": REP[key] - 1, "docs": []}
    for n in (1, 2, 3):
        d = SCORE / key / f"doc_{n}"
        label = keymap[f"{key}/doc_{n}"]
        doc = {
            "original": (d / "original.md").read_text(),
            "out": {label[x]: (d / f"{x}.md").read_text() for x in "AB"},
            "flags": [],
        }
        verdict = {it["id"]: it for it in result[f"doc_{n}"]}
        for f in json.loads((d / "flags.json").read_text()):
            v = verdict[f["id"]]
            doc["flags"].append({
                "line": f["line"],
                "word": f["word"],
                "status": {label[x]: v[x]["status"] for x in "AB"},
                "text": {label[x]: v[x]["text"] for x in "AB"},
            })
        topic["docs"].append(doc)
    data.append(topic)

out = Path(__file__).parent / "data" / "docs.json"
out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
for t in data:
    flags = [f for d in t["docs"] for f in d["flags"]]
    fixed = {v: sum(f["status"][v] == "fixed" for f in flags) for v in ("v1.6.0", "v1.6.1")}
    print(t["reader"], len(flags), "件", fixed)
