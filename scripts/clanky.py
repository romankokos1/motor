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
from datetime import datetime, timedelta, timezone
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
    if host in ("hcmotor.cz", "www.hcmotor.cz"):
        # clanek.asp?id=Slug-13927 i clanek.asp?id=13927 → jedno id
        m = re.search(r"id=(?:[^&]*?-)?(\d+)(?:&|$)", p.query)
        return f"https://hcmotor.cz{path}?id={m.group(1)}" if m else urlunsplit(("https", "hcmotor.cz", path, p.query, ""))
    return urlunsplit(("https", host, path, "", ""))


REL_DATE = re.compile(r"\b(dnes|včera|před\s+(\d+)\s+dn[yíe]m?|(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}))"
                      r"(?:\s*,?\s*(\d{1,2}):(\d{2}))?", re.I)


def parse_rel_date(text):
    """„dnes“, „včera“, „před 3 dny“, „15.11.2026 18:30“ → (datetime, má_čas)."""
    m = REL_DATE.search(text or "")
    if not m:
        return None, False
    now = datetime.now(TZ)
    w = m.group(1).lower()
    if w == "dnes":
        d = now
    elif w == "včera":
        d = now - timedelta(days=1)
    elif m.group(2):
        d = now - timedelta(days=int(m.group(2)))
    else:
        try:
            d = datetime(int(m.group(5)), int(m.group(4)), int(m.group(3)), tzinfo=TZ)
        except ValueError:
            return None, False
    if m.group(6):
        return d.replace(hour=int(m.group(6)), minute=int(m.group(7)), second=0, microsecond=0), True
    return d.replace(hour=12, minute=0, second=0, microsecond=0), False


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
    # záloha: jména ze scripts/players_baseline.json – tam jsou jako „Příjmení Jméno“
    try:
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        if isinstance(base, dict) and base:
            out = []
            for k in base:
                parts = k.split()
                if len(parts) >= 2:
                    out.append(" ".join(parts[1:] + parts[:1]))  # → „Jméno Příjmení“
            if out:
                return sorted(out)
    except (ValueError, OSError):
        pass
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


def surname_alts(surname):
    """Varianty kmene příjmení pro české skloňování (Klouček → Kloucek|Klouck, Vála → Val)."""
    s = deaccent(surname)
    alts = {s}
    low = s.lower()
    if low.endswith(("ek", "ec")) and len(s) > 4:
        alts.add(s[:-2] + s[-1])
    elif low[-1:] in "aeiouy" and len(s) > 3:
        alts.add(s[:-1])
    return sorted(alts, key=len, reverse=True)


def player_matchers(names):
    out = []
    for full in names:
        parts = full.split()
        if len(parts) < 2:
            continue
        first = deaccent(parts[0]).lower()
        alts = "|".join(re.escape(a) for a in surname_alts(parts[-1]))
        out.append((full, re.compile(r"\b(?:" + alts + r")\w*"), first))  # záměrně case-sensitive
    return out


def tag_players(text, matchers):
    t = deaccent(text)
    return [full for full, rx, _ in matchers if rx.search(t)]


def mentions_full_name(text, matchers):
    t = deaccent(text)
    for full, rx, first in matchers:
        m = rx.search(t)
        if m and first in t[max(0, m.start() - 25): m.start()].lower():
            return True
    return False


# ---------- filtr ----------

def is_relevant(src, url, text, cfg, matchers):
    marker = src.get("hokej_v_url", "")
    if marker and marker not in url:
        return False
    if src.get("vyloucit") and re.search(src["vyloucit"], text):
        return False
    if src.get("vse"):
        return True
    if src.get("povinne"):
        return bool(re.search(src["povinne"], text))
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


def read_listing(url, pattern, with_dates=False):
    soup = BeautifulSoup(get(url).content, "html.parser")
    rx = re.compile(pattern)
    seen = {}
    for a in soup.find_all("a", href=True):
        href = canon(urljoin(url, a["href"]))
        if not rx.match(href):
            continue
        text = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        if with_dates:
            # hcmotor.cz: odkaz obsahuje „datum, autor titulek“ – bereme jen datum,
            # titulek a perex se dotáhnou z článku; odkazy bez data (menu, staré) přeskočíme
            if not REL_DATE.match(text):
                continue
            d, has_time = parse_rel_date(text)
            if href not in seen:
                seen[href] = {"url": href, "titulek": "", "nahled": text, "perex": "",
                              "datum": d, "bez_casu": not has_time}
            continue
        it = seen.setdefault(href, {"url": href, "titulek": "", "perex": "", "datum": None})
        if len(text) > len(it["titulek"]):
            it["titulek"] = text
    return [it for it in seen.values() if it["titulek"] or it.get("nahled")]


GENERIC_TITLE = {"motor české budějovice", "hc motor české budějovice", "banes motor české budějovice"}


def title_from_preview(nahled):
    """hcmotor.cz výpis: „15.11.2026, Martin Vašíček CEB - PCE 2:1 - Motor…“ → titulek."""
    t = REL_DATE.sub("", nahled, count=1).lstrip(" ,")
    m = re.search(r"\b([A-Z]{2,4}\s*[-–]\s*[A-Z]{2,4}\s+\d+:\d+.*)$", t)
    if m:
        return m.group(1).strip()
    if re.match(r"(Tisková zpráva|Redakce|Klub)\b", t):
        t = re.sub(r"^(Tisková zpráva|Redakce|Klub)\s*", "", t)
    else:
        t = re.sub(r"^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][^\s,]+ [A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][^\s,]+(, Foto: [^\s,]+ [^\s,]+)?\s+", "", t)
    return t.strip()


def hcmotor_body(soup, nahled=""):
    """Titulek z nadpisu článku a perex z prvního odstavce pod ním."""
    heads = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        ht = re.sub(r"\s+", " ", h.get_text(" ")).strip()
        if len(ht) >= 12 and ht.lower() not in GENERIC_TITLE:
            heads.append((h, ht))
    if nahled:  # nadpis, který je i ve výpisu, je jistě titulek článku
        heads.sort(key=lambda x: x[1] not in nahled)
    for h, ht in heads:
        perex = ""
        for p_ in h.find_all_next("p", limit=12):
            t_ = re.sub(r"\s+", " ", p_.get_text(" ")).strip()
            if len(t_) > 40 and not REL_DATE.match(t_) and not re.search(r"\|| cm\b|\bkg\b", t_):
                perex = t_
                break
        return ht, perex
    return "", ""


def read_article_meta(url, nahled=""):
    soup = BeautifulSoup(get(url).content, "html.parser")

    def meta(*keys):
        for k in keys:
            m = soup.find("meta", attrs={"property": k}) or soup.find("meta", attrs={"name": k})
            if m and m.get("content"):
                return m["content"]
        return ""

    title = meta("og:title", "twitter:title") or (soup.title.get_text() if soup.title else "")
    title = re.sub(r"\s+[|–-]\s+(iSport|iDNES|Deník|Sport\.cz|Hokej\.cz|hokej\.cz|Českobudějovický)[^|]*$",
                   "", title.strip())
    title = re.sub(r"^Motor České Budějovice\s*[–-]\s*", "", title.strip())
    perex = meta("og:description", "description", "twitter:description")
    if perex.strip() in ("Motor České Budějovice", ""):
        perex = ""
        for p_ in soup.find_all("p"):
            t_ = re.sub(r"\s+", " ", p_.get_text(" ")).strip()
            if len(t_) > 80 and not REL_DATE.match(t_):
                perex = t_
                break
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
    bez_casu = False
    if date is None:
        date, has_time = parse_rel_date(soup.get_text(" ")[:3000])
        bez_casu = bool(date) and not has_time
    if "hcmotor.cz" in url:
        ht, hp = hcmotor_body(soup, nahled)
        if title.strip().lower() in GENERIC_TITLE or not title.strip():
            title = ht or title_from_preview(nahled)
        perex = hp or perex
    return {"titulek": clean_text(title), "perex": clean_text(perex), "datum": date, "bez_casu": bez_casu}


# ---------- obohacení: typ, zápas, skupiny ----------

LINEUPS = ROOT / "docs" / "sestavy-data.json"
DAY_S = 86400

# typ článku – pravidla nad titulkem (u kádru a zranění i nad perexem)
TYP_PRESTUP = re.compile(r"prestup|smlouv|prodlouzil|prodlouzeni|podepsal|posil[ay]|odchazi|konci v |angazm|"
                         r"mir[ií] do|hostovan|vymen[ay]|zmen[ay] v kadru|pojistil|nove[mh]o? (hrace|obrance|utocnika|golmana)")
TYP_ZRANENI = re.compile(r"zranen|zranil|operac|marod|mimo hru|vypadne na|vynecha|otres mozku|nemocensk")
TYP_ONLINE = re.compile(r"\bonline\b")
TYP_REPORT = re.compile(r"\d+\s*:\s*\d+|porazil|pretlac|zvitez|otocil|porazk|zdolal|skolil|vyhral|vyhr[au]|vyhre|prohral|prohr[au]|"
                        r"padl[ia]?\b|obrat|veze tri|tri body|bod[ uy]|remiz|v prodlouzeni|najezd|vyprodan")
TYP_ROZHOVOR_JMENO = re.compile(r"^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž-]+(?: [A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž-]+)?: ")
TYP_ROZHOVOR = re.compile(r"rozhovor|lici\b|rika\b|rekl\b|priznal|vzkazuje|popsal|tvrdi|hlasi\b|"
                          r"predstavuje|[„\"].+[“\"]")
TYPY = {"online": "Online", "zraneni": "Zranění", "prestup": "Smlouva/přestup",
        "reportaz": "Reportáž", "rozhovor": "Rozhovor"}

SOUPERI = {
    "sparta": r"spart|\bceb\W+spa\b|\bspa\W+ceb\b", "kometa": r"komet|\bbrn[eoa]\b|brnensk|\bceb\W+kom\b|\bkom\W+ceb\b", "plzen": r"plzn|plzen|skodovk|\bceb\W+plz\b|\bplz\W+ceb\b",
    "liberec": r"liber|bili tygri|\bceb\W+lib\b|\blib\W+ceb\b", "vitkovice": r"vitkovic|ostrav|\bceb\W+vit\b|\bvit\W+ceb\b", "pardubice": r"pardubic|\bceb\W+pce\b|\bpce\W+ceb\b",
    "litvinov": r"litvinov|verva|\bceb\W+lit\b|\blit\W+ceb\b", "olomouc": r"olomouc|mamut|\bceb\W+olo\b|\bolo\W+ceb\b", "karlovy": r"karlov|\bvar[yech]\b|energie|\bceb\W+kva\b|\bkva\W+ceb\b",
    "boleslav": r"boleslav|\bceb\W+mbl\b|\bmbl\W+ceb\b", "hradec": r"hradec|hradeck|mountfield|\bceb\W+hkr\b|\bhkr\W+ceb\b", "trinec": r"trin|ocelar|\bceb\W+tri\b|\btri\W+ceb\b",
    "kladno": r"kladn|rytir|\bceb\W+kla\b|\bkla\W+ceb\b",
}
STOP = set("""motor motoru motorem banes ceske ceskych budej hokej hokeje extra tipsp sezon sezony klubu tymu
zapas zapasu utkan kolem kole kola hrace hraci hracu kterem ktery ktera ktere ktery jeste ovsem jenze proto
tohle tento tato taky take vsak nebo ktere pouze stale zatim kdyz protoze potom pred poslednim""".split())


def norm(s):
    return deaccent(s or "").lower()


def stems(text):
    return {w[:5] for w in re.findall(r"[a-z]{5,}", norm(text))} - {w[:5] for w in STOP}


def classify(a, has_match_after):
    t, p = norm(a["titulek"]), norm(a["perex"])
    if TYP_PRESTUP.search(t) and not TYP_ONLINE.search(t) or "prestupy" in t:
        return "prestup"
    if TYP_ONLINE.search(t):
        return "online"
    if TYP_ZRANENI.search(t):
        return "zraneni"
    if TYP_PRESTUP.search(t) or TYP_PRESTUP.search(p[:160]):
        return "prestup"
    if re.search(r"zranen|zranil|operac|marod", p[:160]):
        return "zraneni"
    if has_match_after and (TYP_REPORT.search(t) or TYP_REPORT.search(p[:200])):
        return "reportaz"
    if TYP_ROZHOVOR_JMENO.search(a["titulek"]) or TYP_ROZHOVOR.search(a["titulek"]) or TYP_ROZHOVOR.search(t):
        return "rozhovor"
    return None


def season_start(month, year):
    return year if month >= 7 else year - 1


def load_matches(data):
    """Zápasy Motoru: kumulativně v clanky.json, doplňované z docs/sestavy-data.json."""
    store = {z["id"]: z for z in data.get("zapasy", [])}
    if LINEUPS.exists():
        try:
            src = json.loads(LINEUPS.read_text(encoding="utf-8")).get("zapasy", [])
        except ValueError:
            src = []
        today = datetime.now(TZ)
        start = season_start(today.month, today.year)
        for m in src:
            dm = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.", m.get("datum", ""))
            if not dm:
                continue
            d, mo = int(dm.group(1)), int(dm.group(2))
            y = start if mo >= 7 else start + 1
            hm = re.match(r"(\d{1,2}):(\d{2})", m.get("cas") or "")
            dt = datetime(y, mo, d, int(hm.group(1)) if hm else 17, int(hm.group(2)) if hm else 30, tzinfo=TZ)
            zid = f"{start}-{m['kolo']}"
            store[zid] = {"id": zid, "sezona": f"{start}/{str(start + 1)[2:]}", "kolo": m["kolo"],
                          "start": dt.isoformat(timespec="minutes"), "domaci": m["domaci"], "hoste": m["hoste"],
                          "vysledek": m.get("vysledek") or "", "odehrano": bool(m.get("odehrano")),
                          "odlozeno": (m.get("cas") or "").lower().startswith("odlo")}
    return sorted(store.values(), key=lambda z: z["start"])


def opponent_key(m):
    opp = m["hoste"] if "Budějovice" in m["domaci"] else m["domaci"]
    o = norm(opp)
    for k, rx in SOUPERI.items():
        if re.search(rx, o):
            return k
    return None


def assign_match(a, matches):
    if not a.get("datum"):
        return None
    t = datetime.fromisoformat(a["datum"]).timestamp()
    text = norm(f'{a["titulek"]} {a["perex"]}')
    title = norm(a["titulek"])
    best, bd = None, None
    for m in matches:
        if m.get("odlozeno"):
            continue
        ms = datetime.fromisoformat(m["start"]).timestamp()
        diff = t - ms
        if not (-3 * DAY_S <= diff <= 2 * DAY_S):  # preview až 3 dny předem, ohlasy 2 dny po
            continue
        k = opponent_key(m)
        if not k or not re.search(SOUPERI[k], text):
            continue
        # soupeř v titulku má přednost – ale ne u souhrnů kola, kde je v titulku víc týmů
        in_title = re.search(SOUPERI[k], title) and sum(1 for rx in SOUPERI.values() if re.search(rx, title)) == 1
        score = abs(diff) - (10 * DAY_S if in_title else 0)
        if bd is None or score < bd:
            best, bd = m, score
    return best


def group(articles):
    """Stejná zpráva na více webech → společné id skupiny (url nejstaršího článku)."""
    n = len(articles)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    info = []
    for a in articles:
        ts = datetime.fromisoformat(a.get("datum") or a["pridano"]).timestamp()
        info.append((ts, stems(f'{a["titulek"]} {a["perex"]}'), set(a.get("hraci", []))))
    for i in range(n):
        for j in range(i + 1, n):
            ai, aj = articles[i], articles[j]
            if ai["zdroj"] == aj["zdroj"] or ai.get("typ") != aj.get("typ") or ai.get("souper") != aj.get("souper"):
                continue
            if ai.get("zapas") != aj.get("zapas"):
                continue
            (ti, si, pi), (tj, sj, pj) = info[i], info[j]
            if abs(ti - tj) > 36 * 3600:
                continue
            common = len(si & sj) + 2 * len(pi & pj)
            if common >= 4 and common / max(1, min(len(si), len(sj))) >= 0.22:
                parent[find(j)] = find(i)
    roots = {}
    for i in range(n):
        roots.setdefault(find(i), []).append(i)
    for members in roots.values():
        if len(members) < 2:
            articles[members[0]].pop("skupina", None)
            continue
        first = min(members, key=lambda k: info[k][0])
        for k in members:
            articles[k]["skupina"] = articles[first]["url"]


def order_undated(articles):
    """hcmotor.cz neuvádí čas vydání: články bez času seřadí v rámci dne podle čísla článku
    (vyšší id = vydán později). Čas se na stránce nezobrazuje, slouží jen k pořadí."""
    days = {}
    for a in articles:
        m = re.search(r"[?&]id=(\d+)", a["url"])
        if a.get("bez_casu") and a.get("datum") and m:
            days.setdefault(a["datum"][:10], []).append((int(m.group(1)), a))
    for day, items in days.items():
        for rank, (_, a) in enumerate(sorted(items, key=lambda x: x[0])):
            a["datum"] = f"{day}T12:{rank:02d}{a['datum'][16:]}"


MLUVI = re.compile(r"\b(rika|rekl|lici|hodnoti|zhodnotil|prozradil|popsal|predstavuje|odpovida|vzkazuje|priznal|"
                   r"tvrdi|hlasi|uvedl|dodal|vysvetluje|rozhovor|dotaznik|ptejte se|offline|promluvil|mluvi|o sobe)\b")


def speakers(a, matchers):
    """Kdo v článku mluví: lidé z kádru/vedení, kteří jsou v titulku rozhovoru nebo výroku."""
    title = a["titulek"]
    in_title = tag_players(title, matchers)
    if not in_title:
        return []
    t = norm(title)
    # „Nedorost: …“, „… Pardubicemi. Martin Beránek: Chtěli jsme…“ (ne „3:4“)
    for h in re.finditer(r"([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\w-]+(?: [A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\w-]+)?): ", title):
        who = tag_players(h.group(1), matchers)
        if who:
            return who
    if a.get("typ") == "rozhovor" or MLUVI.search(t):
        return in_title
    return []


def enrich(data, cfg):
    order_undated(data["clanky"])
    matchers = player_matchers(load_players(cfg))
    matches = load_matches(data)
    data["zapasy"] = matches
    for a in data["clanky"]:
        a["hraci"] = tag_players(f'{a["titulek"]} {a["perex"]}', matchers)
        if a.get("souper"):
            a["zapas"], a["typ"] = a["souper"], classify(a, False)
            continue
        m = assign_match(a, matches)
        a["zapas"] = m["id"] if m else None
        after = bool(m and a.get("datum") and (a["datum"] >= m["start"] or
                     (a.get("bez_casu") and a["datum"][:10] == m["start"][:10])))
        a["typ"] = classify(a, after)
        if a["typ"] == "prestup":
            a["zapas"] = None  # kádrové zprávy k zápasu nepatří
    group(data["clanky"])
    for a in data["clanky"]:
        sp = [] if a.get("souper") else speakers(a, matchers)
        if sp:
            a["mluvi"] = sp
        else:
            a.pop("mluvi", None)


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
        doms = s["domena"] if isinstance(s["domena"], list) else [s["domena"]]
        if any(host == d or host.endswith("." + d) for d in doms):
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
        **({"bez_casu": True} if item.get("bez_casu") else {}),
        **({"ver": 3} if src_name == "HC Motor" else {}),
        **({"t_rss": item["_rss_t"]} if item.get("_rss") else {}),
        **({"t_vypis": item["_key"]} if item.get("_key") and not item.get("_rss") else {}),
    }


# ---------- režimy ----------

SOUPER_DNI = 4  # kolik dní před zápasem sbírat články o soupeři
MAX_KONTROL = 10  # kolik článků za běh se smí kvůli titulku stáhnout znovu

# přísnější vzory soupeřů pro články, které Motor nezmiňují (bez diakritiky, s velkým písmenem)
SOUPERI_PRESNE = {
    "sparta": r"\bSpart\w*", "kometa": r"\bKomet\w*|\bBrn[oaeu]\b|\bBrnens\w*",
    "plzen": r"\bPlz(en|n)\w*|\bSkodovk\w*", "liberec": r"\bLiber(ec|c)\w*|\bBil\w* Tygr\w*",
    "vitkovice": r"\bVitkovic\w*|\bOstrav\w*", "pardubice": r"\bPardubic\w*",
    "litvinov": r"\bLitvinov\w*|\bVerv[aouy]\b", "olomouc": r"\bOlomou\w*|\bKohout\w*",
    "karlovy": r"\bKarlov\w* Var\w*|\bVar(y|ech|um)\b|\bEnergi\w*", "boleslav": r"\bBoleslav\w*",
    "hradec": r"\bHrad(ec|ci|ce)\b|\bHradeck\w*|\bMountfield\w*", "trinec": r"\bTrin(ec|ce|ci|cem|cu)\b|\bOcelar\w*",
    "kladno": r"\bKladn\w*|\bRytir\w*",
}


def opponent_match(src, url, text, upcoming):
    """Článek o nejbližším soupeři (bez zmínky o Motoru) – jen hokejové rubriky celostátních webů."""
    if not upcoming or src.get("povinne") or src.get("vse"):
        return None
    marker = src.get("hokej_v_url", "")
    if marker and marker not in url:
        return None
    if not marker and src["id"] != "hokejcz":
        return None
    t = deaccent(text)
    for m in upcoming:
        k = opponent_key(m)
        if k and re.search(SOUPERI_PRESNE[k], t):
            return m
    return None


def fill_meta(it, url, errors):
    if it["perex"] and it["datum"] and it["titulek"]:
        return
    try:
        m = read_article_meta(url, it.get("nahled", ""))
        if m["titulek"]:
            it["titulek"] = m["titulek"]  # z výpisu bývá titulek slepený s perexem
        it["perex"] = it["perex"] or m["perex"]
        if not it["datum"] and m["datum"]:
            it["datum"], it["bez_casu"] = m["datum"], m.get("bez_casu", False)
    except Exception as e:  # noqa: BLE001
        errors.append(f"článek {url}: {e}")


def tnorm(t):
    t = re.sub(r"[„“”\"'‚‘’«»]", '"', t or "")
    t = re.sub(r"[–—−]", "-", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def listing_key(it):
    return tnorm(REL_DATE.sub("", it.get("nahled") or it["titulek"] or "", count=1))


def change_title(rec, new):
    if not new or tnorm(new) == tnorm(rec["titulek"]):
        return False
    rec.setdefault("puvodni", []).append({"titulek": rec["titulek"], "zmeneno": now_iso()})
    rec["titulek"] = new
    return True


def watch_title(rec, it, errors, checks):
    """Hlídá přepsané titulky u článků, které jsou pořád ve výpisu/RSS. Vrací počet stažení."""
    if it.get("_rss"):
        seen = clean_text(it["titulek"])
        if "t_rss" not in rec:
            rec["t_rss"] = seen
        elif tnorm(seen) != tnorm(rec["t_rss"]):
            change_title(rec, seen)
            rec["t_rss"] = seen
        return 0
    key = listing_key(it)
    if not key:
        return 0
    if "t_vypis" not in rec:
        rec["t_vypis"] = key
        return 0
    if key == rec["t_vypis"] or checks >= MAX_KONTROL:
        return 0
    rec["t_vypis"] = key
    try:  # výpis se změnil → ověř titulek přímo v článku
        m = read_article_meta(rec["url"], it.get("nahled", ""))
        change_title(rec, m["titulek"])
    except Exception as e:  # noqa: BLE001
        errors.append(f"kontrola {rec['url']}: {e}")
    return 1


def cleanup(data):
    """Odstraní záznamy hcmotor.cz z prvního (vadného) načtení: rozbité kódování, datum v titulku, menu."""
    data["clanky"] = [c for c in data["clanky"] if not (c["zdroj"] == "HC Motor" and c.get("ver") != 3)]


def scan(cfg):
    data = load_data()
    cleanup(data)
    known = {c["url"] for c in data["clanky"]} | set(data.get("odebrane", []))
    index = {c["url"]: c for c in data["clanky"]}
    matchers = player_matchers(load_players(cfg))
    now = datetime.now(TZ).timestamp()
    upcoming = [m for m in load_matches(data) if not m.get("odehrano") and not m.get("odlozeno")
                and 0 <= datetime.fromisoformat(m["start"]).timestamp() - now <= SOUPER_DNI * DAY_S]
    added, report, checks = 0, [], 0

    for src in cfg["zdroje"]:
        candidates, errors = {}, []
        for u in src.get("rss", []):
            try:
                for it in read_rss(u):
                    it["url"] = canon(it["url"])
                    it["_rss"] = True
                    it["_rss_t"] = clean_text(it["titulek"])
                    candidates.setdefault(it["url"], it)
            except Exception as e:  # noqa: BLE001
                errors.append(f"RSS {u}: {e}")
        for u in src.get("vypisy", []):
            try:
                for it in read_listing(u, src["vzor_clanku"], src.get("datum_ve_vypisu", False)):
                    candidates.setdefault(it["url"], it)
            except Exception as e:  # noqa: BLE001
                errors.append(f"výpis {u}: {e}")

        hits = 0
        for url, it in candidates.items():
            if source_for(url, cfg) is not src:
                continue
            if url in index:
                checks += watch_title(index[url], it, errors, checks)
                continue
            if url in known:
                continue
            text = f'{it["titulek"] or it.get("nahled", "")} {it["perex"]}'
            opp = None
            if not is_relevant(src, url, text, cfg, matchers):
                opp = opponent_match(src, url, text, upcoming)
                if not opp:
                    continue
            it["_key"] = listing_key(it)
            fill_meta(it, url, errors)
            if not it["titulek"]:
                continue
            if src.get("vyloucit") and re.search(src["vyloucit"], it["titulek"]):
                continue
            if opp and not opponent_match(src, url, f'{it["titulek"]} {it["perex"]}', upcoming):
                continue
            rec = make_record(it, src["nazev"], matchers)
            if opp:
                rec["souper"] = opp["id"]
            data["clanky"].append(rec)
            index[url] = rec
            known.add(url)
            hits += 1
        added += hits
        report.append(f'{src["nazev"]:10} kandidátů {len(candidates):3}  nových {hits:2}'
                      + (f'  CHYBY: {"; ".join(errors)}' if errors else ""))

    data["aktualizace"] = now_iso()
    enrich(data, cfg)
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
    enrich(data, cfg)
    save_data(data)
    print(f'Přidáno: {rec["titulek"]} ({name})')


def remove(url, cfg):
    url = canon(url)
    data = load_data()
    before = len(data["clanky"])
    data["clanky"] = [c for c in data["clanky"] if c["url"] != url]
    data.setdefault("odebrane", [])
    if url not in data["odebrane"]:
        data["odebrane"].append(url)  # ať ho další běh znovu nepřidá
    enrich(data, cfg)
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
        remove(a.remove, cfg)
    else:
        scan(cfg)


if __name__ == "__main__":
    main()
