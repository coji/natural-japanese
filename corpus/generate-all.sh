#!/usr/bin/env bash
# corpus/generate-all.sh — 全モデル × 全ジャンルの AI コーパスを一括生成する。
#
# corpus/generate.py は「モデル1つ × ジャンル1つ(省略時は全ジャンル)」を
# 1回の起動で処理する設計なので、このスクリプトはモデル×ジャンルの
# 全組み合わせをループで回すランナー。
#
# 安全に再実行できる設計:
#   generate.py は出力先ファイル(corpus/ai/{model}/{topic-id}.md)が既に
#   存在する場合はスキップする(--force を渡さない限り上書きしない)。
#   そのため本スクリプトを何度実行しても、未生成分だけが追加生成される。
#
# 並列度:
#   API レートリミットへの配慮から、同時実行は最大2ストリームまでに抑える。
#   `set -e` は使わない(バックグラウンドジョブの一部が失敗しても他のジョブを
#   継続させたいため)。個々の generate.py 呼び出しの失敗は generate.py 内部で
#   トピック単位に捕捉・ログ出力される。

set -uo pipefail

cd "$(dirname "$0")"

CLAUDE_MODELS="claude-haiku-4-5 claude-sonnet-5 claude-opus-4-8 claude-fable-5"
CODEX_MODELS="gpt-5.6-sol gpt-5.6-terra gpt-5.6-luna"
GENRES="blog essay tech business slide"

MAX_PARALLEL=2

run_jobs() {
    local engine="$1"
    local models="$2"

    for model in $models; do
        for genre in $GENRES; do
            # 実行中ジョブ数が MAX_PARALLEL 未満になるまで待つ。
            # macOS 標準の bash (3.2) は `wait -n` を持たないため、
            # ジョブ数をポーリングして間引く。
            while [ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$MAX_PARALLEL" ]; do
                sleep 1
            done
            echo "=== ${engine} / ${model} / ${genre} ===" >&2
            uv run generate.py --engine "$engine" --model "$model" --genre "$genre" &
        done
    done
}

run_jobs claude "$CLAUDE_MODELS"
run_jobs codex "$CODEX_MODELS"

wait

echo "generate-all.sh: 完了" >&2
