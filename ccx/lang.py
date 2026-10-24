"""The language of the lines ccx writes into a conversation (session start, per-turn hints) and of `ccx ui`.

One setting: `ccx config set ui.lang zh|en`. Unset, the page follows the browser and these lines stay English.
The words live in one table with the page's: ccx/ui_static/strings.json (keys hint_*)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LANGS = ("zh", "en")
STRINGS = Path(__file__).resolve().parent / "ui_static" / "strings.json"


@lru_cache(maxsize=1)
def table() -> dict:
    return json.loads(STRINGS.read_text(encoding="utf-8"))


def current(p=None) -> str:
    """The configured language, 'en' when unset or unreadable."""
    try:
        from .config import load_config, paths
        v = (load_config(p or paths()).get("ui") or {}).get("lang")
    except Exception:  # noqa: BLE001 — a hint must never fail for want of a setting
        v = None
    return v if v in LANGS else "en"


def say(key: str, p=None, lang: str | None = None, **params) -> str:
    """One line from the table in the configured language; {name} placeholders filled from params."""
    t = table()
    s = t.get(lang or current(p), {}).get(key) or t["en"][key]
    for k, v in params.items():
        s = s.replace("{" + k + "}", str(v))
    return s
