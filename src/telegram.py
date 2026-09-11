"""ONE messaging module: the phone-side inbox AND delivery, both over the Telegram Bot API
(complexity review, hosted wrapper, Reduction 4 — one integration, one secret pair).

- ``pull_links()`` — every URL in messages the bot has not yet confirmed, from the configured
  chat. STATELESS on our side (Reduction 3): Telegram keeps the unconfirmed queue; we append
  to ``links.txt`` FIRST, then confirm (``offset``) — a crash between the two just re-delivers
  the same links next run, and ``_parse_links`` dedupes. "Done" is the output folder, never a
  seen-file. Only ``TELEGRAM_CHAT_ID``'s messages count (anyone can message a bot).
- ``send_bundle(dir)`` — notes.md (+ coverage_report.md, slides.pdf when present) as documents.
- ``send_text(msg)`` — the batch tally.

Gated on ``configured()``: no token ⇒ every call is a no-op and the loop is byte-identical.
HTTP goes through an injectable ``http`` (``(method, url, data|None, files|None) -> dict``)
so tests never touch the network. stdlib only — no ``requests`` dependency.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Optional

API = "https://api.telegram.org/bot{token}/{method}"
_URL_RE = re.compile(r"https?://[^\s<>\"'()]+")
MAX_DOC_BYTES = 50 * 1024 * 1024      # Bot API sendDocument cap
BUNDLE_FILES = ("notes.md", "coverage_report.md", "references.md", "slides.pdf")


def configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN")) and bool(os.getenv("TELEGRAM_CHAT_ID"))


def _api(method: str) -> str:
    return API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)


def _http(method: str, url: str, data: Optional[dict] = None,
          files: Optional[dict[str, tuple[str, bytes]]] = None) -> dict:
    """Minimal urllib client: JSON body, or multipart when ``files`` is given."""
    if files:
        boundary = uuid.uuid4().hex
        body = b""
        for k, v in (data or {}).items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                     f"{v}\r\n").encode()
        for k, (name, blob) in files.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                     f"filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                     ).encode() + blob + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(data or {}).encode(), method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _links_in(update: dict, chat_id: str) -> list[str]:
    msg = update.get("message") or update.get("channel_post") or {}
    if str((msg.get("chat") or {}).get("id")) != str(chat_id):
        return []
    return _URL_RE.findall(msg.get("text") or msg.get("caption") or "")


def pull_links(http: Callable = _http, confirm: bool = True) -> list[str]:
    """URLs from all unconfirmed updates (paged), then confirm them — if ``confirm``. The
    caller appends to links.txt BEFORE confirming (see module doc)."""
    if not configured():
        return []
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    links: list[str] = []
    last_id: Optional[int] = None
    offset: Optional[int] = None
    while True:
        params = {"timeout": 0, "limit": 100}
        if offset is not None:
            params["offset"] = offset
        updates = (http("POST", _api("getUpdates"), params) or {}).get("result") or []
        for u in updates:
            last_id = u["update_id"]
            for l in _links_in(u, chat_id):
                if l not in links:
                    links.append(l)
        if len(updates) < 100:
            break
        offset = last_id + 1
    if confirm and last_id is not None:
        http("POST", _api("getUpdates"), {"offset": last_id + 1, "limit": 1, "timeout": 0})
    return links


def send_text(text: str, http: Callable = _http) -> None:
    if not configured():
        return
    http("POST", _api("sendMessage"),
         {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000],
          "disable_web_page_preview": True})


def send_bundle(bundle_dir: Path, caption: str = "", http: Callable = _http) -> list[str]:
    """Push the reader-facing files of one bundle; returns the names sent. Never raises for a
    missing/oversized file — it is skipped and named in the return so the tally can say so."""
    if not configured():
        return []
    sent: list[str] = []
    for name in BUNDLE_FILES:
        p = Path(bundle_dir) / name
        if not p.is_file() or p.stat().st_size == 0 or p.stat().st_size > MAX_DOC_BYTES:
            continue
        http("POST", _api("sendDocument"),
             {"chat_id": os.environ["TELEGRAM_CHAT_ID"],
              "caption": (f"{caption} — {name}" if caption else name)[:1000]},
             files={"document": (f"{Path(bundle_dir).name[:60]}__{name}", p.read_bytes())})
        sent.append(name)
    return sent


def merge_into_links_file(list_file: Path, new_links: list[str]) -> int:
    """Append unseen links to the links file (creating it); returns how many were added."""
    from src.adhoc import _parse_links
    list_file = Path(list_file)
    existing = _parse_links(list_file.read_text()) if list_file.exists() else []
    added = [l for l in new_links if l not in existing]
    if added:
        with list_file.open("a") as f:
            if existing and not list_file.read_text().endswith("\n"):
                f.write("\n")
            f.write("".join(f"{l}\n" for l in added))
    return len(added)
