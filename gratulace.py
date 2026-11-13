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


VELKE = "A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽÖÜÄ"


def jmeno(text: str) -> str:
    """„65. narozeniny dnes slaví bývalý brankář Motoru Marcel Kurfürst. …“ → „Marcel Kurfürst“:
    poslední dvě slova s velkým písmenem ve větě o narozeninách. Nenajde-li, vrátí ''."""
    for veta in re.split(r"(?<=[^\d\s])[.!?]\s", text):
        if not any(w in bez_diakritiky(veta) for w in ("narozenin", "nejlepsi", "birthday", "jubile")):
            continue
        slova = re.findall(rf"\b[{VELKE}][^\W\d_]+(?:-[{VELKE}][^\W\d_]+)?", veta)
        if len(slova) >= 2:
            return " ".join(slova[-2:])
    return ""


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", bez_diakritiky(s)).strip("-")


def rok_narozeni(text: str, datum: str) -> int | None:
    """„60. narozeniny“ v příspěvku z roku 2026 → 1966."""
    m = re.search(r"(\d{1,3})\.\s*narozenin", bez_diakritiky(text))
    return int(datum[:4]) - int(m.group(1)) if m else None


def nazev(e: dict) -> str:
    """Základ názvu fotek: prijmeni_jmeno_rok (kořínek → korinek), jinak datum + číslo příspěvku."""
    if not e.get("jmeno"):
        return e["datum"][:10] + "_" + re.sub(r"\W", "", e["url"])[-8:]
    krestni, prijmeni = e["jmeno"].split(" ", 1)
    rok = f"_{e['rok_narozeni']}" if e.get("rok_narozeni") else ""
    return f"{slug(prijmeni)}_{slug(krestni)}{rok}"


def pojmenovat(e: dict) -> None:
    """Doplnit jméno a rok narození a podle nich (pře)jmenovat fotky záznamu."""
    e["jmeno"] = jmeno(e["text"])
    e["rok_narozeni"] = rok_narozeni(e["text"], e["datum"])
    stem, nove = nazev(e), []
    for i, f in enumerate(e["obrazky"]):
        dst = f"obrazky/{stem}{'' if i == 0 else f'_{i + 1}'}.jpg"
        n = 2
        while (OUT / dst).exists() and dst != f:           # stejný hráč v jiném příspěvku
            dst = f"obrazky/{stem}_{chr(96 + n)}.jpg"; n += 1
        if dst != f and (OUT / f).exists():
            (OUT / f).rename(OUT / dst)
        nove.append(dst)
    e["obrazky"] = nove


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
    for e in db.values():
        pojmenovat(e)

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
            name = f"obrazky/_novy_{i + 1}.jpg"
            try:
                img = requests.get(u, timeout=60)
                img.raise_for_status()
                (OUT / name).write_bytes(img.content)
                soubory.append(name)
            except requests.RequestException as e:
                print(f"  obrázek se nestáhl ({e})")
        e = {"datum": f"{when:%Y-%m-%d %H:%M}", "text": text, "url": url, "obrazky": soubory}
        pojmenovat(e)
        db[url] = {"datum": e["datum"], "jmeno": e["jmeno"], "rok_narozeni": e["rok_narozeni"],
                   "text": text, "url": url, "obrazky": e["obrazky"]}
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
