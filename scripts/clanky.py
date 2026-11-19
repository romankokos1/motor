#!/usr/bin/env python3
"""Hlídač článků o HC Motor.

  python scripts/clanky.py               projde zdroje (RSS + výpisy) a doplní nové články
  python scripts/clanky.py --add URL     ručně přidá článek
  python scripts/clanky.py --remove URL  odebere článek
"""
import argparse
import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scripts" / "clanky_zdroje.json"
DATA = ROOT / "docs" / "clanky.json"
BASELINE = ROOT / "scripts" / "players_baseline.json"
TZ = ZoneInfo("Europe/Prague")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
PEREX_MAX = 320

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "cs,en;q=0.8"})


# ---------- pomocné ----------

def now_iso():
    return datetime.now(TZ).isoformat(timespec="minutes")


def to_iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).isoformat(timespec="minutes")


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def canon(url):
    p = urlsplit(url.strip())
    host = p.netloc.lower()
    path = p.path
    if host == "hokej.cz":
        host = "www.hokej.cz"
    return urlunsplit(("https", host, path, "", ""))


def clean_text(s):
    if not s:
        return ""
    s = BeautifulSoup(html.unescape(s), "html.parser").get_text(" ")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > PEREX_MAX:
        s = s[:PEREX_MAX].rsplit(" ", 1)[0] + "…"
    return s


def deaccent(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def get(url):
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return r


# ---------- hráči ----------

def load_players(cfg):
    names = [n.strip() for n in cfg.get("hraci", []) if n.strip()]
    if names or not BASELINE.exists():
        return names
    # záloha: vytáhni jména ze scripts/players_baseline.json (ať je formát jakýkoli)
    found = set()
    pat = re.compile(r"^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž'-]+(?: [A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž'-]+)+$")

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and pat.match(k):
                    found.add(k)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and pat.match(o):
            found.add(o)

    try:
        walk(json.loads(BASELINE.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        pass
    return sorted(found)


def surname_stem(surname):
    s = deaccent(surname).lower()
    return s[: max(4, len(s) - 2)] if len(s) > 4 else s


def player_matchers(names):
    out = []
    for full in names:
        parts = full.split()
        if len(parts) < 2:
            continue
        first, last = deaccent(parts[0]).lower(), parts[-1]
        stem = surname_stem(last)
        out.append((full, re.compile(r"\b" + re.escape(stem) + r"\w*"), first))
    return out


def tag_players(text, matchers):
    t = deaccent(text).lower()
    return [full for full, rx, _ in matchers if rx.search(t)]


def mentions_full_name(text, matchers):
    t = deaccent(text).lower()
    for full, rx, first in matchers:
        m = rx.search(t)
        if m and first in t[max(0, m.start() - 25): m.start()]:
            return True
    return False


# ---------- filtr ----------

def is_relevant(src, url, text, cfg, matchers):
    marker = src.get("hokej_v_url", "")
    if marker and marker not in url:
        return False
    if any(k in text for k in cfg["klicova_slova"]):
        return True
    slug = urlsplit(url).path.lower()
    if "motor" in slug or "budejovic" in slug:
        return True
    return mentions_full_name(text, matchers)


# ---------- čtení zdrojů ----------

def read_rss(url):
    root = ET.fromstring(get(url).content)
    items = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        d = {}
        for ch in it:
            name = ch.tag.split("}")[-1]
            if name == "link":
                d["link"] = (ch.text or ch.get("href") or "").strip()
            elif name in ("title", "description", "summary", "pubDate", "published", "updated"):
                d.setdefault(name, ch.text or "")
        if d.get("link"):
            items.append({
                "url": d["link"],
                "titulek": clean_text(d.get("title")),
                "perex": clean_text(d.get("description") or d.get("summary")),
                "datum": parse_date(d.get("pubDate") or d.get("published") or d.get("updated")),
            })
    return items


def read_listing(url, pattern):
    soup = BeautifulSoup(get(url).text, "html.parser")
    rx = re.compile(pattern)
    seen = {}
    for a in soup.find_all("a", href=True):
        href = canon(urljoin(url, a["href"]))
        if not rx.match(href):
            continue
        text = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        if len(text) > len(seen.get(href, "")):
            seen[href] = text
    return [{"url": u, "titulek": t, "perex": "", "datum": None} for u, t in seen.items()]


def read_article_meta(url):
    soup = BeautifulSoup(get(url).text, "html.parser")

    def meta(*keys):
        for k in keys:
            m = soup.find("meta", attrs={"property": k}) or soup.find("meta", attrs={"name": k})
            if m and m.get("content"):
                return m["content"]
        return ""

    title = meta("og:title", "twitter:title") or (soup.title.get_text() if soup.title else "")
    title = re.sub(r"\s+[|–-]\s+(iSport|iDNES|Deník|Sport\.cz|Hokej\.cz|hokej\.cz|Českobudějovický)[^|]*$",
                   "", title.strip())
    perex = meta("og:description", "description", "twitter:description")
    date = parse_date(meta("article:published_time", "og:published_time", "date",
                           "publish-date", "article:published"))
    if date is None:
        t = soup.find("time", attrs={"datetime": True})
        date = parse_date(t["datetime"]) if t else None
    if date is None:
        for s in soup.find_all("script", type="application/ld+json"):
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', s.string or "")
            if m:
                date = parse_date(m.group(1))
                break
    return {"titulek": clean_text(title), "perex": clean_text(perex), "datum": date}


# ---------- data ----------

def load_data():
    if DATA.exists():
        return json.loads(DATA.read_text(encoding="utf-8"))
    return {"aktualizace": None, "clanky": []}


def save_data(data):
    data["clanky"].sort(key=lambda c: c.get("datum") or c["pridano"], reverse=True)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def source_for(url, cfg):
    host = urlsplit(url).netloc.lower()
    for s in cfg["zdroje"]:
        if host == s["domena"] or host.endswith("." + s["domena"]):
            return s
    return None


def make_record(item, src_name, matchers, manual=False):
    text = f'{item["titulek"]} {item["perex"]}'
    return {
        "url": item["url"],
        "titulek": item["titulek"],
        "perex": item["perex"],
        "zdroj": src_name,
        "datum": to_iso(item["datum"]),
        "pridano": now_iso(),
        "rucne": manual,
        "hraci": tag_players(text, matchers),
    }


# ---------- režimy ----------

def scan(cfg):
    data = load_data()
    known = {c["url"] for c in data["clanky"]} | set(data.get("odebrane", []))
    matchers = player_matchers(load_players(cfg))
    added, report = 0, []

    for src in cfg["zdroje"]:
        candidates, errors = {}, []
        for u in src.get("rss", []):
            try:
                for it in read_rss(u):
                    it["url"] = canon(it["url"])
                    candidates.setdefault(it["url"], it)
            except Exception as e:  # noqa: BLE001
                errors.append(f"RSS {u}: {e}")
        for u in src.get("vypisy", []):
            try:
                for it in read_listing(u, src["vzor_clanku"]):
                    candidates.setdefault(it["url"], it)
            except Exception as e:  # noqa: BLE001
                errors.append(f"výpis {u}: {e}")

        hits = 0
        for url, it in candidates.items():
            if url in known or source_for(url, cfg) is not src:
                continue
            if not is_relevant(src, url, f'{it["titulek"]} {it["perex"]}', cfg, matchers):
                continue
            if not it["perex"] or not it["datum"] or not it["titulek"]:
                try:
                    m = read_article_meta(url)
                    if m["titulek"]:
                        it["titulek"] = m["titulek"]  # z výpisu bývá titulek slepený s perexem
                    it["perex"] = it["perex"] or m["perex"]
                    it["datum"] = it["datum"] or m["datum"]
                except Exception as e:  # noqa: BLE001
                    errors.append(f"článek {url}: {e}")
            if not it["titulek"]:
                continue
            data["clanky"].append(make_record(it, src["nazev"], matchers))
            known.add(url)
            hits += 1
        added += hits
        report.append(f'{src["nazev"]:10} kandidátů {len(candidates):3}  nových {hits:2}'
                      + (f'  CHYBY: {"; ".join(errors)}' if errors else ""))

    data["aktualizace"] = now_iso()
    save_data(data)
    print("\n".join(report))
    print(f"Přidáno celkem: {added}")


def add(url, cfg):
    url = canon(url)
    data = load_data()
    data["odebrane"] = [u for u in data.get("odebrane", []) if u != url]
    if any(c["url"] == url for c in data["clanky"]):
        print("Článek už v úložišti je.")
        save_data(data)
        return
    matchers = player_matchers(load_players(cfg))
    m = read_article_meta(url)
    if not m["titulek"]:
        sys.exit("Nepodařilo se načíst titulek článku.")
    m["url"] = url
    src = source_for(url, cfg)
    name = src["nazev"] if src else urlsplit(url).netloc.removeprefix("www.")
    rec = make_record(m, name, matchers, manual=True)
    data["clanky"].append(rec)
    save_data(data)
    print(f'Přidáno: {rec["titulek"]} ({name})')


def remove(url):
    url = canon(url)
    data = load_data()
    before = len(data["clanky"])
    data["clanky"] = [c for c in data["clanky"] if c["url"] != url]
    data.setdefault("odebrane", [])
    if url not in data["odebrane"]:
        data["odebrane"].append(url)  # ať ho další běh znovu nepřidá
    save_data(data)
    print("Odebráno." if len(data["clanky"]) < before else "Článek v úložišti nebyl, jen zablokován.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add")
    ap.add_argument("--remove")
    a = ap.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if a.add:
        add(a.add, cfg)
    elif a.remove:
        remove(a.remove)
    else:
        scan(cfg)


if __name__ == "__main__":
    main()
