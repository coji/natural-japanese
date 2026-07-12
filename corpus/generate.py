# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""corpus/generate.py — AI コーパス生成。

corpus/human/ と同じジャンル(essay / tech / blog)のトピックリストを内蔵し、
claude CLI または codex CLI に「素の状態」(AI臭除去の指示なし)でブログ記事
を書かせ、corpus/ai/{model}/{topic-id}.md に保存する。

設計方針:
    - プロンプトは意図的に素っ気なくする。「〜についてブログ記事を書いて」
      程度に統一し、文体指示や「自然に書いて」等のメタ指示は入れない。
      これは AI の「地の文体癖」を素のまま観測し、lint の検出器を校正する
      ためのコーパスだから。
    - 生成メタデータ(モデル・エンジン・日時・プロンプト)を各ファイルの
      frontmatter に記録する。再現性と検証可能性のため。
    - --engine claude では `claude -p "<prompt>" --model <model>` を、
      --engine codex では `codex exec "<prompt>"` を呼ぶ。
    - このスクリプトは Phase 2 の後半で本格実行する想定。今回は動作確認
      として --limit 1 で1本だけ生成して確認するにとどめる(本格生成は
      次フェーズ)。

使い方:
    uv run corpus/generate.py --engine claude --model claude-sonnet-4-5 --limit 1
    uv run corpus/generate.py --engine codex --limit 1
    uv run corpus/generate.py --engine claude --model claude-sonnet-4-5  # 全トピック生成(本格実行)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).parent
AI_DIR = CORPUS_DIR / "ai"
NEUTRAL_CWD = "/tmp"

# ---------------------------------------------------------------------------
# トピックリスト(人間コーパスと同ジャンル)。各ジャンル 10本以上、合計 30本以上。
# ---------------------------------------------------------------------------
TOPICS: list[dict] = [
    # essay(随筆・エッセイ)
    {"id": "essay-kisetsu-no-utsuroi", "genre": "essay", "topic": "季節の移ろいを感じた瞬間"},
    {"id": "essay-machi-no-oto", "genre": "essay", "topic": "住んでいる街の音について"},
    {"id": "essay-furui-hon", "genre": "essay", "topic": "古い本を読み返すこと"},
    {"id": "essay-asa-no-shukan", "genre": "essay", "topic": "朝の習慣"},
    {"id": "essay-tabi-no-omoide", "genre": "essay", "topic": "旅先で印象に残った出来事"},
    {"id": "essay-shokuji-no-jikan", "genre": "essay", "topic": "一人で食事をする時間"},
    {"id": "essay-tenki-to-kibun", "genre": "essay", "topic": "天気と気分の関係"},
    {"id": "essay-toshi-o-toru-koto", "genre": "essay", "topic": "年を取るということ"},
    {"id": "essay-inaka-to-tokai", "genre": "essay", "topic": "田舎と都会、それぞれの暮らし"},
    {"id": "essay-kotoba-no-chikara", "genre": "essay", "topic": "言葉の力について"},
    {"id": "essay-shumi-no-hajimari", "genre": "essay", "topic": "ある趣味を始めたきっかけ"},
    {"id": "essay-chiisana-shippai", "genre": "essay", "topic": "小さな失敗の思い出"},

    # tech(技術記事)
    {"id": "tech-typescript-nyumon", "genre": "tech", "topic": "TypeScriptの型システムの基本"},
    {"id": "tech-react-jotai-hikaku", "genre": "tech", "topic": "Reactの状態管理ライブラリの比較"},
    {"id": "tech-git-rebase", "genre": "tech", "topic": "git rebaseの使い方"},
    {"id": "tech-docker-nyumon", "genre": "tech", "topic": "Dockerの基本的な使い方"},
    {"id": "tech-code-review-tips", "genre": "tech", "topic": "コードレビューで気をつけていること"},
    {"id": "tech-db-index", "genre": "tech", "topic": "データベースのインデックス設計"},
    {"id": "tech-ci-cd-kouchiku", "genre": "tech", "topic": "CI/CDパイプラインの構築"},
    {"id": "tech-api-design", "genre": "tech", "topic": "REST APIの設計指針"},
    {"id": "tech-test-senryaku", "genre": "tech", "topic": "テスト戦略の立て方"},
    {"id": "tech-performance-tuning", "genre": "tech", "topic": "Webアプリのパフォーマンスチューニング"},
    {"id": "tech-security-kihon", "genre": "tech", "topic": "Webアプリケーションのセキュリティ対策の基本"},
    {"id": "tech-monorepo-unyou", "genre": "tech", "topic": "モノレポ運用のコツ"},

    # blog(ブログ・個人開発系)
    {"id": "blog-kojin-kaihatsu-keiken", "genre": "blog", "topic": "個人開発アプリをリリースした経験"},
    {"id": "blog-tenshoku-taiken", "genre": "blog", "topic": "転職活動の体験談"},
    {"id": "blog-work-life-balance", "genre": "blog", "topic": "仕事と生活のバランスの取り方"},
    {"id": "blog-freelance-1nen", "genre": "blog", "topic": "フリーランス1年目の振り返り"},
    {"id": "blog-chiimu-kaihatsu", "genre": "blog", "topic": "チーム開発で意識していること"},
    {"id": "blog-shin-tool-donyu", "genre": "blog", "topic": "新しいツールを導入したときの話"},
    {"id": "blog-mokuhyo-settei", "genre": "blog", "topic": "年間目標の立て方"},
    {"id": "blog-saido-nyumon", "genre": "blog", "topic": "副業を始めた理由"},
    {"id": "blog-benkyokai-shusai", "genre": "blog", "topic": "勉強会を主催してみた感想"},
    {"id": "blog-shoseki-shokai", "genre": "blog", "topic": "最近読んで良かった本の紹介"},
]

PROMPT_TEMPLATE = "{topic}についてブログ記事を書いて。"

# generate.py は claude -p を1往復のみの非対話呼び出しとして使う。
# ユーザー向けプロンプト自体は「素の状態」(文体・自然さの指示なし)に保つが、
# それとは別に「確認質問をせず本文を直接出力する」という運用上の指示だけは
# システムプロンプトとして与える。そうしないと、素っ気ないプロンプトに対して
# Claude が対話的な確認質問を返すだけで記事本文が得られず、コーパスとして
# 機能しないため。
NONINTERACTIVE_SYSTEM_PROMPT = (
    "これは1往復のみの非対話バッチ呼び出しです。フォローアップの質問はできません。"
    "確認や許可を求めず、指示に対して適切と思う内容を自分で判断し、"
    "記事本文だけをそのまま出力してください。"
)


def run_claude(prompt: str, model: str) -> str:
    # cwd をリポジトリ外(素の状態)にする: このリポジトリの CLAUDE.md や
    # スキルのメモリが自動読み込みされると、Claude が「素っ気ないプロンプト」を
    # 対話的な確認質問として扱ってしまい、記事本文が生成されないため。
    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--model",
            model,
            # ツール(Write/Bash等)を一切使わせず、応答テキストだけを本文として
            # 得る。ツールがあると「ファイルに保存しました」等の要約だけを
            # 返したり、確認や許可を求めたりして本文が得られないことがある。
            "--disallowed-tools",
            "*",
            "--append-system-prompt",
            NONINTERACTIVE_SYSTEM_PROMPT,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
        cwd=NEUTRAL_CWD,
    )
    return result.stdout.strip()


def run_codex(prompt: str) -> str:
    result = subprocess.run(
        ["codex", "exec", "--skip-git-repo-check", prompt],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
        cwd=NEUTRAL_CWD,
    )
    return result.stdout.strip()


def generate_one(
    topic: dict, engine: str, model: str, *, retries: int = 1, force: bool = False
) -> dict | None:
    """1トピックを生成する。スキップ時は None、生成時はメタ情報 dict を返す。"""
    prompt = PROMPT_TEMPLATE.format(topic=topic["topic"])
    out_model = "codex-cli" if engine == "codex" else model
    out_dir = AI_DIR / out_model
    out_path = out_dir / f"{topic['id']}.md"

    if out_path.exists() and not force:
        print(f"skip (exists): {topic['id']} (engine={engine}, model={out_model})", file=sys.stderr)
        return None

    print(f"generate: {topic['id']} (engine={engine}, model={out_model})", file=sys.stderr)

    last_error: Exception | None = None
    body: str | None = None
    for attempt in range(retries + 1):
        try:
            if engine == "claude":
                body = run_claude(prompt, model)
            elif engine == "codex":
                body = run_codex(prompt)
            else:
                raise ValueError(f"unknown engine: {engine}")
            last_error = None
            break
        except Exception as e:  # noqa: BLE001
            last_error = e
            if attempt < retries:
                print(f"  retry ({attempt + 1}/{retries}): {topic['id']}: {e}", file=sys.stderr)
            continue

    if last_error is not None or body is None:
        raise last_error or RuntimeError("empty response")

    out_dir.mkdir(parents=True, exist_ok=True)

    generated_at = dt.datetime.now().isoformat(timespec="seconds")
    frontmatter = (
        "---\n"
        f"id: {topic['id']}\n"
        f"genre: {topic['genre']}\n"
        f"engine: {engine}\n"
        f"model: {out_model}\n"
        f"generated_at: {generated_at}\n"
        f"prompt: {json.dumps(prompt, ensure_ascii=False)}\n"
        "---\n\n"
    )
    out_path.write_text(frontmatter + body + "\n", encoding="utf-8")
    print(f"  -> {out_path} ({len(body)} chars)", file=sys.stderr)

    return {
        "id": topic["id"],
        "genre": topic["genre"],
        "engine": engine,
        "model": out_model,
        "chars": len(body),
        "generated_at": generated_at,
        "path": str(out_path.relative_to(CORPUS_DIR)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AI コーパス生成(claude/codex CLI 経由)")
    parser.add_argument("--engine", choices=["claude", "codex"], default="claude")
    parser.add_argument("--model", default="claude-sonnet-4-5", help="claude -p --model に渡すモデル名")
    parser.add_argument("--limit", type=int, help="先頭 N トピックだけ生成する(動作確認用)")
    parser.add_argument("--genre", choices=["essay", "tech", "blog"], help="このジャンルだけ生成する")
    parser.add_argument("--retries", type=int, default=1, help="失敗時のリトライ回数(既定 1)")
    parser.add_argument("--force", action="store_true", help="既存ファイルがあっても再生成する")
    args = parser.parse_args()

    topics = TOPICS
    if args.genre:
        topics = [t for t in topics if t["genre"] == args.genre]
    if args.limit:
        topics = topics[: args.limit]

    for topic in topics:
        try:
            generate_one(topic, args.engine, args.model, retries=args.retries, force=args.force)
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: {topic['id']}: {e.stderr}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR: {topic['id']}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
