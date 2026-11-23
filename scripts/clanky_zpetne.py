#!/usr/bin/env python3
"""Jednorázové zpětné doplnění úložiště článků o starší články (od začátku sezóny).

  python scripts/clanky_zpetne.py --od 2026-08-01

Prochází archivy zdrojů stránku po stránce, dokud nenarazí na články starší než --od.
Používá stejná pravidla jako hlídač (filtr Motoru, mládeže, typy, zápasy, slučování).
Články o soupeři se zpětně nedoplňují. Mezi dotazy je pauza, ať weby nezatěžujeme.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import clanky as K

PAUZA = 1.0          # s mezi dotazy
MAX_STRAN = 60       # pojistka na zdroj

# jak se u kterého zdroje listuje do minulosti
ARCHIV = {
    "hcmotor": {"mesice": "https://hcmotor.cz/archiv.asp?kde=clanky&zobraz=datum&mesic={m}&rok={r}&anotace=False&razeni=0"},
    "denik": {"strany": "https://ceskobudejovicky.denik.cz/hokej/?strana={n}"},
    "ctsport": {"strany": "https://sport.ceskatelevize.cz/rubrika/hokej/extraliga-39?page={n}"},
    "sportcz": {"dalsi": "https://www.sport.cz/sekce/hokej-extraliga-47"},
    "isport": {"jedna": "https://isport.blesk.cz/hokej-motor-ceske-budejovice-44"},
    "idnes": {"dalsi": "https://www.idnes.cz/sport/hokej/extraliga"},
}
DALSI = re.compile(r"^\s*(načíst další( články)?|další( stránka| články)?|starší( články)?|další\s*»|»|›)\s*$", re.I)


def aware(d):
    return d.replace(tzinfo=K.TZ) if d and d.tzinfo is None else d


def fetch(url):
    time.sleep(PAUZA)
    return BeautifulSoup(K.get(url).content, "html.parser")


def links(soup, base, src):
    """Odkazy na články na stránce výpisu (jako v hlídači)."""
    rx = re.compile(src["vzor_clanku"])
    dated = src.get("datum_ve_vypisu", False)
    seen = {}
    for a in soup.find_all("a", href=True):
        href = K.canon(urljoin(base, a["href"]))
        if not rx.match(href):
            continue
        text = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        if dated:
            if not K.REL_DATE.match(text) or href in seen:
                continue
            d, has_time = K.parse_rel_date(text)
            seen[href] = {"url": href, "titulek": "", "nahled": text, "perex": "", "datum": d, "bez_casu": not has_time}
            continue
        it = seen.setdefault(href, {"url": href, "titulek": "", "perex": "", "datum": None})
        if len(text) > len(it["titulek"]):
            it["titulek"] = text
    return list(seen.values())


def next_link(soup, base, current):
    a = soup.find("a", rel="next")
    if a and a.get("href"):
        return urljoin(base, a["href"])
    for a in soup.find_all("a", href=True):
        if DALSI.search(a.get_text(" ")) and a["href"] not in ("#", "") and not a["href"].startswith("javascript"):
            u = urljoin(base, a["href"])
            if u != current:
                return u
    return None


def pages(src):
    """Generátor stránek výpisu do minulosti."""
    cfg = ARCHIV[src["id"]]
    if "mesice" in cfg:
        now = datetime.now(K.TZ)
        y, m = now.year, now.month
        for _ in range(MAX_STRAN):
            yield cfg["mesice"].format(m=m, r=y)
            m -= 1
            if m == 0:
                y, m = y - 1, 12
    elif "strany" in cfg:
        for n in range(1, MAX_STRAN + 1):
            yield cfg["strany"].format(n=n)
    elif "jedna" in cfg:
        yield cfg["jedna"]
    elif "dalsi" in cfg:
        url = cfg["dalsi"]
        for _ in range(MAX_STRAN):
            nxt = yield url
            if not nxt:
                return
            url = nxt


def page_date(items, url_errors):
    """Datum nejstaršího článku na stránce – z výpisu, nebo z posledního odkazu."""
    dates = [aware(it["datum"]) for it in items if it.get("datum")]
    if dates:
        return min(dates)
    try:
        time.sleep(PAUZA)
        m = K.read_article_meta(items[-1]["url"])
        return aware(m["datum"])
    except Exception as e:  # noqa: BLE001
        url_errors.append(str(e))
        return None


def backfill(src, cutoff, data, cfg, matchers, index):
    gen = pages(src)
    url, added, n_pages, errors, seen_first = next(gen), 0, 0, [], set()
    while url:
        try:
            soup = fetch(url)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url}: {e}")
            break
        n_pages += 1
        items = links(soup, url, src)
        if not items or items[0]["url"] in seen_first:
            break  # prázdná stránka nebo web vrací pořád tu samou
        seen_first.add(items[0]["url"])
        for it in items:
            if it["url"] in index:
                continue
            text = f'{it["titulek"] or it.get("nahled", "")} {it["perex"]}'
            if not K.is_relevant(src, it["url"], text, cfg, matchers):
                continue
            time.sleep(PAUZA)
            K.fill_meta(it, it["url"], errors)
            if not it["titulek"] or not it.get("datum"):
                continue
            if src.get("vyloucit") and re.search(src["vyloucit"], it["titulek"]):
                continue
            it["datum"] = aware(it["datum"])
            if it["datum"] < cutoff or K.is_youth(it["titulek"], it["perex"]):
                continue
            rec = K.make_record(it, src["nazev"], matchers)
            rec["pridano"] = rec["datum"]   # ať se zpětně doplněné články neukazují jako „NOVÉ“
            rec["zpetne"] = True
            data["clanky"].append(rec)
            index[it["url"]] = rec
            added += 1
        oldest = page_date(items, errors)
        if oldest and oldest < cutoff:
            break
        if "dalsi" in ARCHIV[src["id"]]:
            try:
                url = gen.send(next_link(soup, url, url))
            except StopIteration:
                url = None
        else:
            url = next(gen, None)
    print(f'{src["nazev"]:13} stran {n_pages:3}  doplněno {added:3}' + (f'  CHYBY: {"; ".join(errors[:3])}' if errors else ""))
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--od", default="2026-08-01", help="nejstarší datum článku (RRRR-MM-DD)")
    ap.add_argument("--zdroj", help="jen jeden zdroj (id z konfigurace)")
    a = ap.parse_args()
    cutoff = datetime.fromisoformat(a.od).replace(tzinfo=K.TZ)
    cfg = json.loads(K.CONFIG.read_text(encoding="utf-8"))
    data = K.load_data()
    data["zapasy"] = K.load_matches(data)
    index = {c["url"]: c for c in data["clanky"]}
    for u in data.get("odebrane", []):
        index.setdefault(u, {})
    matchers = K.player_matchers(K.load_players(cfg))
    total = 0
    for src in cfg["zdroje"]:
        if src["id"] not in ARCHIV or (a.zdroj and src["id"] != a.zdroj):
            continue
        total += backfill(src, cutoff, data, cfg, matchers, index)
    print(f"Doplněno celkem: {total}")
    K.recheck(data, cfg)
    K.enrich(data, cfg)
    K.save_data(data)


if __name__ == "__main__":
    sys.exit(main())
