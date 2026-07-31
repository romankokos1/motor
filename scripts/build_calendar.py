#!/usr/bin/env python3
"""
Stáhne .ics rozpisy tří mládežnických týmů HC Motor České Budějovice
z hcmotor.cz, spojí je do jednoho data/matches.json (pro webovou stránku)
a jednoho data/motor-mladez.ics (pro re-export / debug).

Zdrojové feedy (hcmotor.cz je vydává jako webcal:, my čteme https: ekvivalent):
  mladší dorost  -> sezona=2027MDO
  starší dorost  -> sezona=2027SDO
  junioři        -> sezona=2027U20

Pozn.: pokud si Motor v budoucnu změní URL schéma, stačí upravit SOURCES níže.
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from icalendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "data" / "matches.json"
OUT_ICS = ROOT / "data" / "motor-mladez.ics"

SOURCES = {
    "mdo": {
        "label": "Mladší dorost",
        "url": "https://www.hcmotor.cz/zapas_ics.asp?sezona=2027MDO",
    },
    "sdo": {
        "label": "Starší dorost",
        "url": "https://www.hcmotor.cz/zapas_ics.asp?sezona=2027SDO",
    },
    "u20": {
        "label": "Junioři",
        "url": "https://www.hcmotor.cz/zapas_ics.asp?sezona=2027U20",
    },
}

HOME_NAMES = ["české budějovice", "č. budějovice", "motor české budějovice", "hc motor"]

HEADERS = {
    # hcmotor.cz's ics endpoint appears to check for a browser-like UA
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/calendar,*/*",
}


def is_home(summary: str) -> bool:
    first_team = summary.split(" - ")[0].strip().lower()
    return any(name in first_team for name in HOME_NAMES)


def opponent_from_summary(summary: str, home: bool) -> str:
    parts = [p.strip() for p in summary.split(" - ")]
    if len(parts) < 2:
        return summary.strip()
    return parts[1] if home else parts[0]


def fetch_team(team_code: str, meta: dict) -> list[dict]:
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
            date_str = dtstart.strftime("%Y-%m-%d")
            time_str = dtstart.strftime("%H:%M")
        else:
            # all-day / date-only event, no kickoff time known
            date_str = dtstart.strftime("%Y-%m-%d")
            time_str = None

        location = str(component.get("location", "")).strip()
        home = is_home(summary)
        opponent = opponent_from_summary(summary, home)

        # try to pull a round number out of the description, if present
        desc = str(component.get("description", ""))
        round_match = re.search(r"(\d+)\.?\s*kolo", desc, re.IGNORECASE)
        round_no = int(round_match.group(1)) if round_match else None

        matches.append(
            {
                "team": team_code,
                "date": date_str,
                "time": time_str,
                "home": home,
                "opponent": opponent,
                "location": location or None,
                "round": round_no,
            }
        )

    matches.sort(key=lambda m: (m["date"], m["time"] or ""))
    return matches


def build_ics(all_matches: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//HC Motor Ceske Budejovice//Mladez rozpis//CS",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:HC Motor ČB — mládež",
        "X-WR-TIMEZONE:Europe/Prague",
    ]
    for m in all_matches:
        if not m["time"]:
            continue
        y, mo, d = m["date"].split("-")
        h, mi = m["time"].split(":")
        start = f"{y}{mo}{d}T{h}{mi}00"
        end_dt = datetime.strptime(f"{m['date']} {m['time']}", "%Y-%m-%d %H:%M") + timedelta(
            hours=2
        )
        end = end_dt.strftime("%Y%m%dT%H%M00")
        label = SOURCES[m["team"]]["label"]
        side = "ČB" if m["home"] else m["opponent"]
        other = m["opponent"] if m["home"] else "ČB"
        uid_src = f"{m['team']}-{m['date']}-{m['time']}-{m['opponent']}"
        uid = str(abs(hash(uid_src))) + "@hcmotor-mladez"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{start}Z",
            f"DTSTART;TZID=Europe/Prague:{start}",
            f"DTEND;TZID=Europe/Prague:{end}",
            f"SUMMARY:{label}: {side} - {other}",
            f"LOCATION:{m['location'] or ''}",
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
        except Exception as exc:  # noqa: BLE001
            print(f"CHYBA při stahování {team_code}: {exc}", file=sys.stderr)
            raise

    all_matches.sort(key=lambda m: (m["date"], m["time"] or ""))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "teams": {code: meta["label"] for code, meta in SOURCES.items()},
                "matches": all_matches,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    OUT_ICS.write_text(build_ics(all_matches), encoding="utf-8")
    print(f"Hotovo: {len(all_matches)} zápasů celkem", file=sys.stderr)


if __name__ == "__main__":
    main()
