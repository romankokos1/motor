#!/usr/bin/env python3
"""
Stahne .ics rozpisy tri mladeznickych tymu HC Motor Ceske Budejovice
z hcmotor.cz, spoji je do jednoho data/matches.json (pro webovou stranku)
a jednoho data/motor-mladez.ics (pro re-export / debug).
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar

PRAGUE = ZoneInfo("Europe/Prague")

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "data" / "matches.json"
OUT_ICS = ROOT / "data" / "motor-mladez.ics"

SOURCES = {
    "mdo": {"label": "Mladší dorost", "url": "https://www.hcmotor.cz/zapas_ics.asp?sezona=2027MDO"},
    "sdo": {"label": "Starší dorost", "url": "https://www.hcmotor.cz/zapas_ics.asp?sezona=2027SDO"},
    "u20": {"label": "Junioři", "url": "https://www.hcmotor.cz/zapas_ics.asp?sezona=2027U20"},
}

HOME_TEAM_NAMES = [
    "české budějovice", "č. budějovice", "motor české budějovice",
    "hc motor", "banes motor", "madeta motor",
]
HOME_LOCATION_HINTS = ["české budějovice", "budvar aréna"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/calendar,*/*",
}


def is_home_team_name(name: str) -> bool:
    n = name.strip().lower()
    return any(hint in n for hint in HOME_TEAM_NAMES)


def is_home_location(location: str) -> bool:
    loc = (location or "").strip().lower()
    return any(hint in loc for hint in HOME_LOCATION_HINTS)


def split_summary(summary: str):
    parts = [p.strip() for p in summary.split(" - ")]
    if len(parts) != 2:
        return None, summary.strip()
    a, b = parts
    a_is_us = is_home_team_name(a)
    b_is_us = is_home_team_name(b)
    if a_is_us and not b_is_us:
        return a, b
    if b_is_us and not a_is_us:
        return b, a
    return a, b


def fetch_team(team_code: str, meta: dict) -> list:
    resp = requests.get(meta["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    cal = Calendar.from_ical(resp.content)

    matches = []
    for component in cal.walk("VEVENT"):
        summary = str(component.get("summary", "")).strip()
        if not summary or " - " not in summary:
            continue
        dtstart = component.get("dtstart").dt
        if isinstance(dtstart, datetime):
            # ics ze hcmotor.cz dává čas v UTC — převedeme na pražský čas
            local_dt = dtstart.astimezone(PRAGUE) if dtstart.tzinfo else dtstart
            date_str = local_dt.strftime("%Y-%m-%d")
            time_str = local_dt.strftime("%H:%M")
        else:
            date_str = dtstart.strftime("%Y-%m-%d")
            time_str = None

        location = str(component.get("location", "")).strip()
        home = is_home_location(location)
        _, opponent = split_summary(summary)

        desc = str(component.get("description", ""))
        round_match = re.search(r"(\d+)\.?\s*kolo", desc, re.IGNORECASE)
        round_no = int(round_match.group(1)) if round_match else None

        matches.append({
            "team": team_code, "date": date_str, "time": time_str,
            "home": home, "opponent": opponent,
            "location": location or None, "round": round_no,
        })

    matches.sort(key=lambda m: (m["date"], m["time"] or ""))
    return matches


def build_ics(all_matches: list) -> str:
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//HC Motor Ceske Budejovice//Mladez rozpis//CS",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:HC Motor ČB — mládež", "X-WR-TIMEZONE:Europe/Prague",
    ]
    for m in all_matches:
        if not m["time"]:
            continue
        y, mo, d = m["date"].split("-")
        h, mi = m["time"].split(":")
        start = f"{y}{mo}{d}T{h}{mi}00"
        end_dt = datetime.strptime(f"{m['date']} {m['time']}", "%Y-%m-%d %H:%M") + timedelta(hours=2)
        end = end_dt.strftime("%Y%m%dT%H%M00")
        label = SOURCES[m["team"]]["label"]
        side = "Motor" if m["home"] else m["opponent"]
        other = m["opponent"] if m["home"] else "Motor"
        uid_src = f"{m['team']}-{m['date']}-{m['time']}-{m['opponent']}"
        uid = str(abs(hash(uid_src))) + "@hcmotor-mladez"
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{start}Z",
            f"DTSTART;TZID=Europe/Prague:{start}", f"DTEND;TZID=Europe/Prague:{end}",
            f"SUMMARY:{label}: {side} - {other}", f"LOCATION:{m['location'] or ''}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    all_matches = []
    for team_code, meta in SOURCES.items():
        try:
            matches = fetch_team(team_code, meta)
            print(f"{team_code}: {len(matches)} zápasů", file=sys.stderr)
            all_matches.extend(matches)
        except Exception as exc:
            print(f"CHYBA při stahování {team_code}: {exc}", file=sys.stderr)
            raise

    all_matches.sort(key=lambda m: (m["date"], m["time"] or ""))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({
            "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "teams": {code: meta["label"] for code, meta in SOURCES.items()},
            "matches": all_matches,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUT_ICS.write_text(build_ics(all_matches), encoding="utf-8")
    print(f"Hotovo: {len(all_matches)} zápasů celkem", file=sys.stderr)


if __name__ == "__main__":
    main()
