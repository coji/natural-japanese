#!/usr/bin/env python3
"""個人情報を保存しない読者実験用の小さなHTTPサーバー。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import secrets
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
STIMULI = HERE / "stimuli.json"
DATA_DIR = Path(os.environ.get("READER_STUDY_DATA_DIR", HERE / "data"))
RESPONSES = DATA_DIR / "responses.jsonl"
CONDITIONS = ("uniform", "varied", "control")
WRITE_LOCK = threading.Lock()


def load_stimuli() -> list[dict]:
    data = json.loads(STIMULI.read_text(encoding="utf-8"))
    if len(data) != 12:
        raise ValueError(f"刺激は12件必要です: {len(data)}件")
    return data


def assignment(participant_id: str, stimuli: list[dict]) -> list[dict]:
    """参加者IDから再現可能なラテン方格割付と提示順を作る。"""
    digest = hashlib.sha256(participant_id.encode()).digest()
    list_index = digest[0] % 3
    assigned = []
    for index, item in enumerate(stimuli):
        condition = CONDITIONS[(index + list_index) % 3]
        assigned.append({
            "id": item["id"],
            "genre": item["genre"],
            "condition": condition,
            "text": item["variants"][condition],
            "question": {"prompt": item["question"]["prompt"], "choices": item["question"]["choices"]},
        })
    random.Random(int.from_bytes(digest[1:9])).shuffle(assigned)
    return assigned


def validate_submission(payload: dict, stimuli: list[dict]) -> tuple[bool, str]:
    participant_id = payload.get("participant_id")
    if not isinstance(participant_id, str) or not 16 <= len(participant_id) <= 64:
        return False, "participant_idが不正です"
    if payload.get("attention_check") not in range(1, 8):
        return False, "注意確認項目が不正です"
    answers = payload.get("answers")
    if not isinstance(answers, list) or len(answers) != 12:
        return False, "回答は12件必要です"
    expected = {item["id"]: item for item in assignment(participant_id, stimuli)}
    seen = set()
    for answer in answers:
        item_id = answer.get("item_id")
        if item_id in seen or item_id not in expected:
            return False, "刺激IDが重複または不正です"
        seen.add(item_id)
        if answer.get("condition") != expected[item_id]["condition"]:
            return False, "条件割付が不正です"
        for field in ("monotony", "naturalness", "readability"):
            if answer.get(field) not in range(1, 8):
                return False, f"{field}は1〜7で回答してください"
        if answer.get("comprehension") not in {0, 1, 2}:
            return False, "理解問題の回答が不正です"
        elapsed = answer.get("elapsed_ms")
        if not isinstance(elapsed, int) or not 1000 <= elapsed <= 1_800_000:
            return False, "回答時間が不正です"
    return True, ""


def participant_exists(participant_id: str) -> bool:
    if not RESPONSES.exists():
        return False
    with RESPONSES.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                if json.loads(line).get("participant_id") == participant_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def save_submission(payload: dict, remote_address: str | None = None) -> bool:
    """IPアドレスを受け取っても保存しない。"""
    del remote_address
    record = {
        "schema_version": 1,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "participant_id": payload["participant_id"],
        "attention_check": payload["attention_check"],
        "answers": payload["answers"],
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with WRITE_LOCK:
        if participant_exists(payload["participant_id"]):
            return False
        with RESPONSES.open("a", encoding="utf-8") as handle:
            handle.write(line)
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "ReaderStudy/1.0"

    def log_message(self, format: str, *args) -> None:
        # BaseHTTPRequestHandlerの既定ログはIPを出すため無効化する。
        return

    def send_json(self, status: int, data: dict | list) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self.send_json(HTTPStatus.OK, {"ok": True})
            return
        if path == "/":
            body = (HERE / "index.html").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/session":
            participant_id = secrets.token_urlsafe(18)
            self.send_json(HTTPStatus.OK, {"participant_id": participant_id, "items": assignment(participant_id, self.server.stimuli)})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/submit":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 100_000:
                raise ValueError("payload size")
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "JSONが不正です"})
            return
        ok, error = validate_submission(payload, self.server.stimuli)
        if not ok:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": error})
            return
        if not save_submission(payload, self.client_address[0] if self.client_address else None):
            self.send_json(HTTPStatus.CONFLICT, {"ok": False, "error": "この回答は送信済みです"})
            return
        self.send_json(HTTPStatus.CREATED, {"ok": True})


def make_server(host: str, port: int, stimuli: list[dict] | None = None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), Handler)
    server.stimuli = stimuli if stimuli is not None else load_stimuli()
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.host, args.port)
    print(f"http://{args.host}:{args.port} で読者実験を開始します（IPログなし）")
    server.serve_forever()


if __name__ == "__main__":
    main()
