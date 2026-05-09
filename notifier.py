#!/usr/bin/env python3
"""
Magazine release date notifier.

Reads magazines.yaml, queries the Rakuten Books Magazine Search API,
and writes calendar.ics covering releases from 14 days ago to 60 days ahead.
Each event includes two VALARM blocks:
  - Day-before 21:00 JST  (TRIGGER:-PT3H from all-day DATE midnight)
  - Release-day 08:00 JST (TRIGGER:PT8H from all-day DATE midnight)
"""

import hashlib
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAKUTEN_API_URL = (
    "https://openapi.rakuten.co.jp/services/api/BooksMagazine/Search/20170404"
)
CALENDAR_FILE = Path("calendar.ics")
PAST_DAYS = 14
FUTURE_DAYS = 60
RETRY_COUNT = 3
RETRY_DELAY = 2      # seconds between retries
REQUEST_INTERVAL = 1  # seconds between magazines (rate-limit courtesy)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Magazine list
# ---------------------------------------------------------------------------


def load_magazines(path: str = "magazines.yaml") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("magazines", [])


# ---------------------------------------------------------------------------
# Rakuten Books API
# ---------------------------------------------------------------------------


def search_magazine(app_id: str, access_key: str, mag: dict) -> list[dict]:
    """Query Rakuten Books Magazine API; returns raw item list (formatVersion=2)."""
    params: dict[str, str] = {
        "applicationId": app_id,
        "accessKey": access_key,
        "formatVersion": "2",
        "sort": "-releaseDate",  # newest/upcoming first
        "hits": "30",
    }
    if mag.get("jan"):
        params["jan"] = str(mag["jan"])
    elif mag.get("isbn"):
        params["isbn"] = str(mag["isbn"])
    else:
        params["title"] = mag["title"]

    headers = {
        "Referer": "https://example.com/",
        "Origin": "https://example.com",
    }

    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(RAKUTEN_API_URL, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                log.warning(
                    "API error for '%s': %s — %s",
                    mag["title"],
                    data.get("error"),
                    data.get("error_description", ""),
                )
                return []
            return data.get("Items", [])
        except requests.RequestException as exc:
            log.warning(
                "Request failed for '%s' (attempt %d/%d): %s",
                mag["title"],
                attempt + 1,
                RETRY_COUNT,
                exc,
            )
            if attempt < RETRY_COUNT - 1:
                time.sleep(RETRY_DELAY)

    log.error("All %d retries exhausted for '%s'", RETRY_COUNT, mag["title"])
    return []


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def parse_sales_date(s: str) -> Optional[date]:
    """Parse the Japanese date strings returned by the Rakuten API."""
    if not s:
        return None
    # Full date: "2024年06月03日" or "2024年6月3日"
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # Month only: "2024年06月" — treat as 1st of month
    m = re.match(r"(\d{4})年(\d{1,2})月", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# iCalendar helpers
# ---------------------------------------------------------------------------


def ical_escape(text: str) -> str:
    """Escape special characters per RFC 5545 §3.3.11."""
    return (
        text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
    )


def ical_fold(line: str) -> str:
    """Fold a logical iCalendar line to ≤75 UTF-8 octets per RFC 5545 §3.1."""
    result: list[str] = []
    while len(line.encode("utf-8")) > 75:
        # Binary-search for the largest prefix that fits in 75 bytes
        lo, hi = 1, min(75, len(line))
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(line[:mid].encode("utf-8")) <= 75:
                lo = mid
            else:
                hi = mid - 1
        result.append(line[:lo])
        line = " " + line[lo:]  # continuation line must start with a space
    result.append(line)
    return "\r\n".join(result)


def make_uid(title: str, release_date: date) -> str:
    digest = hashlib.md5(f"{title}:{release_date.isoformat()}".encode()).hexdigest()
    return f"{digest}@magazine-notifier"


# ---------------------------------------------------------------------------
# iCalendar builder
# ---------------------------------------------------------------------------


def build_ics(events: list[dict]) -> bytes:
    """Return a valid iCalendar file as UTF-8 bytes with CRLF line endings."""
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//magazine-notifier//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        ical_fold("X-WR-CALNAME:📚 雑誌発売日"),
        "X-WR-TIMEZONE:Asia/Tokyo",
        ical_fold("X-WR-CALDESC:楽天ブックスAPIで取得した雑誌の発売日カレンダー"),
        # VTIMEZONE block for Apple Calendar compatibility
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Tokyo",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0900",
        "TZOFFSETTO:+0900",
        "TZNAME:JST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for ev in events:
        d: date = ev["date"]
        title: str = ev["title"]
        url: str = ev.get("url", "")

        date_str = d.strftime("%Y%m%d")
        next_str = (d + timedelta(days=1)).strftime("%Y%m%d")
        uid = make_uid(title, d)

        summary = ical_escape(f"📚 {title} 発売日(明日)")
        alarm1_msg = ical_escape(f"📚 {title} 発売日(明日)")
        if url:
            alarm2_msg = ical_escape(f"📚 {title} 本日発売 - 楽天で購入\n{url}")
        else:
            alarm2_msg = ical_escape(f"📚 {title} 本日発売")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{date_str}",
            f"DTEND;VALUE=DATE:{next_str}",
            ical_fold(f"SUMMARY:{summary}"),
        ]
        if url:
            lines += [
                ical_fold(f"DESCRIPTION:{ical_escape('楽天で購入: ' + url)}"),
                ical_fold(f"URL:{url}"),
            ]

        # ── VALARM 1: 前日 21:00 JST ──────────────────────────────────────
        # All-day DATE event の DTSTART = 当日 00:00 JST
        # TRIGGER:-PT3H → 00:00 の 3 時間前 = 前日 21:00 JST
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "TRIGGER;RELATED=START:-PT3H",
            ical_fold(f"DESCRIPTION:{alarm1_msg}"),
            "END:VALARM",
        ]

        # ── VALARM 2: 当日 08:00 JST ──────────────────────────────────────
        # TRIGGER:PT8H → 00:00 の 8 時間後 = 当日 08:00 JST
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "TRIGGER;RELATED=START:PT8H",
            ical_fold(f"DESCRIPTION:{alarm2_msg}"),
            "END:VALARM",
        ]

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    # RFC 5545 requires CRLF; write as bytes to prevent platform conversion
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    app_id = os.environ.get("RAKUTEN_APP_ID")
    if not app_id:
        log.error("環境変数 RAKUTEN_APP_ID が設定されていません。")
        raise SystemExit(1)

    access_key = os.environ.get("RAKUTEN_ACCESS_KEY")
    if not access_key:
        log.error("環境変数 RAKUTEN_ACCESS_KEY が設定されていません。")
        raise SystemExit(1)

    today = date.today()
    start_date = today - timedelta(days=PAST_DAYS)
    end_date = today + timedelta(days=FUTURE_DAYS)
    log.info("対象期間: %s ～ %s", start_date, end_date)

    magazines = load_magazines()
    log.info("magazines.yaml から %d 件の雑誌を読み込みました", len(magazines))

    events: list[dict] = []

    for mag in magazines:
        time.sleep(REQUEST_INTERVAL)
        title = mag["title"]
        log.info("検索中: %s", title)

        items = search_magazine(app_id, access_key, mag)
        if not items:
            log.warning("結果なし: %s — スキップします", title)
            continue

        seen: set[date] = set()
        for item in items:
            d = parse_sales_date(item.get("salesDate", ""))
            if d is None:
                continue
            if not (start_date <= d <= end_date):
                continue
            if d in seen:
                continue  # 同一日の重複（通常版・限定版など）を除外
            seen.add(d)
            url = item.get("itemUrl", "")
            events.append({"date": d, "title": title, "url": url})
            log.info("  発売日: %s  %s", d, title)

        if not seen:
            log.info("  対象期間内に発売日なし: %s", title)

    events.sort(key=lambda e: (e["date"], e["title"]))
    ics_bytes = build_ics(events)
    CALENDAR_FILE.write_bytes(ics_bytes)
    log.info("%d 件のイベントを %s に書き出しました", len(events), CALENDAR_FILE)


if __name__ == "__main__":
    main()
