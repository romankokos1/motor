"""Gratulační příspěvky z facebookové stránky HC Motor (přes Apify) → gratulace/.

Stáhne příspěvky za zadané období, nechá jen ty, kde se gratuluje (narozeniny apod.),
a uloží text, datum, odkaz a obrázky. Platí se za každý stažený příspěvek (~0,002 $),
i za ty, které se pak vyhodí – proto se stahuje po obdobích.

    python gratulace.py 2026-10-01 2026-11-13
"""
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

STRANKA = "https://www.facebook.com/hcmotor"
ACTOR = "alfalfa~facebook-posts-scraper"
TZ = ZoneInfo("Europe/Prague")
OUT = Path(__file__).parent / "gratulace"
# hledá se v textu příspěvku i v textu rozpoznaném na obrázku (bez diakritiky, malými písmeny)
SLOVA = ["narozenin", "gratul", "blahoprej", "vse nejlepsi", "vsechno nejlepsi", "happy birthday", "jubile"]


def bez_diakritiky(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def obrazky(it: dict) -> list[str]:
    out = []
    for x in it.get("images") or []:
        u = x if isinstance(x, str) else (x.get("url") or x.get("uri") or "")
        if u:
            out.append(u)
    if not out:                                       # záloha: náhledy v media
        for m in it.get("media") or []:
            u = (m.get("thumbnail") or "") if isinstance(m, dict) else ""
            if u:
                out.append(u)
    return out


def main(od: str, do: str) -> int:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("Chybí APIFY_TOKEN.")
        return 1
    r = requests.post(f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items",
                      params={"token": token}, timeout=900,
                      json={"startUrls": [{"url": STRANKA}], "onlyPostsNewerThan": od, "onlyPostsOlderThan": do})
    r.raise_for_status()
    posts = r.json()
    print(f"Staženo {len(posts)} příspěvků za {od} – {do}.")

    OUT.mkdir(exist_ok=True)
    (OUT / "obrazky").mkdir(exist_ok=True)
    db_f = OUT / "gratulace.json"
    db = {e["url"]: e for e in json.loads(db_f.read_text(encoding="utf-8"))} if db_f.exists() else {}

    nove = 0
    for it in posts:
        text = it.get("text") or ""
        ocr = " ".join((m.get("ocrText") or "") for m in it.get("media") or [] if isinstance(m, dict))
        if not any(w in bez_diakritiky(text + " " + ocr) for w in SLOVA):
            continue
        url = it.get("url") or it.get("topLevelUrl") or ""
        if not url or url in db:
            continue
        try:
            when = datetime.fromisoformat((it.get("time") or "").replace("Z", "+00:00")).astimezone(TZ)
        except ValueError:
            continue
        soubory = []
        for i, u in enumerate(obrazky(it)):
            name = f"{when:%Y-%m-%d_%H%M}_{re.sub(r'\W', '', str(it.get('postId', '')))[-8:]}_{i + 1}.jpg"
            try:
                img = requests.get(u, timeout=60)
                img.raise_for_status()
                (OUT / "obrazky" / name).write_bytes(img.content)
                soubory.append(f"obrazky/{name}")
            except requests.RequestException as e:
                print(f"  obrázek se nestáhl ({e})")
        db[url] = {"datum": f"{when:%Y-%m-%d %H:%M}", "text": text, "url": url, "obrazky": soubory}
        nove += 1

    rows = sorted(db.values(), key=lambda e: e["datum"])
    db_f.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gratulací nově {nove}, celkem {len(rows)}.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2]))
