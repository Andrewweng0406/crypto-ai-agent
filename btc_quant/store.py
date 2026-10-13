"""BTC 量化狀態/事件的儲存：production 用 Postgres，本機沒有 DATABASE_URL 時用 logs/ 下的檔案。"""

from __future__ import annotations

import json
import os
from typing import Optional

import database

STATE_ID = "default"
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


class FileStore:
    def __init__(self, state_path: str, events_path: str):
        self.state_path = state_path
        self.events_path = events_path

    def load(self) -> Optional[dict]:
        if not os.path.exists(self.state_path):
            return None
        with open(self.state_path, encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, state: dict) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
        os.replace(tmp, self.state_path)

    def append(self, event: dict) -> None:
        os.makedirs(os.path.dirname(self.events_path), exist_ok=True)
        with open(self.events_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 50) -> list[dict]:
        if not os.path.exists(self.events_path):
            return []
        with open(self.events_path, encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
        return [json.loads(line) for line in reversed(lines)]


class DbStore:
    def load(self) -> Optional[dict]:
        return database.load_btc_quant_state(STATE_ID)

    def save(self, state: dict) -> None:
        database.save_btc_quant_state(STATE_ID, state)

    def append(self, event: dict) -> None:
        database.insert_btc_quant_event(event.get("kind", "unknown"), event)

    def recent(self, limit: int = 50) -> list[dict]:
        return database.list_btc_quant_events(limit) or []


def make_store():
    if database.is_database_enabled():
        return DbStore()
    return FileStore(os.path.join(_LOG_DIR, "btc_quant_state.json"), os.path.join(_LOG_DIR, "btc_quant_events.jsonl"))
