#!/usr/bin/env python3
"""
Bilance hráčů Motoru proti jednotlivým týmům extraligy.

Pro každého hráče z scripts/players_baseline.json (typ "skater") stáhne z
hokej.cz tabulku jeho zápasů za všechny dostupné sezóny
(https://www.hokej.cz/hrac/<slug>/<id>/match?season=<rok>), nechá jen
soutěže odpovídající COMP_RE (výchozí: extraliga + její play off/out) a
uloží je do scripts/bilance_state.json. Z toho vyrobí docs/bilance_data.json,
který načítá stránka docs/bilance-proti-tymum.html.

Minulé sezóny se stahují jen jednou, znovu se tahá jen nejnovější sezóna,
takže další běhy jsou rychlé. Stav se ukládá po každém hráči — když běh
spadne nebo vyprší čas, příště se pokračuje tam, kde skončil.

Kontrola správnosti (pole "kontrola" v bilance_data.json):
  1. v každém řádku musí platit B = G + A,
  2. součet řádků aktuální sezóny musí sedět s boxem Zápasy/G/A/B/+-/TM
     nahoře na stránce hráče,
  3. součet extraligových sezón před aktuální musí sedět s kariérními
     čísly v players_baseline.json (klíč "extraliga"; bere se varianta
     bez play off i s ním).
"""
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
BASELINE_FILE = SCRIPT_DIR / "players_baseline.json"
IDS_FILE = SCRIPT_DIR / "bilance_hraci.json"      # ručně vedené {jméno: "/hrac/slug/id"}
STATE_FILE = SCRIPT_DIR / "bilance_state.json"
OUTPUT_JSON = REPO_ROOT / "docs" / "bilance_data.json"

BASE = "https://www.hokej.cz"
CLUB_PAGES = [  # kde se hledají odkazy na hráče Motoru (zkouší se všechny)
    "/klub/banes-motor-c-budejovice/1721",
    "/klub/banes-motor-c-budejovice/1721/soupiska",
    "/klub/banes-motor-c-budejovice/1721/hraci",
]
SEED_IDS = {"Štencel Jan": "/hrac/jan-stencel/13684"}

# Které soutěže se berou. Výchozí = extraliga (základní část i play off/out
# se jmenují "...extralig..."), bez juniorských/dorosteneckých extraligových
# soutěží. Chceš-li přidat Chance ligu apod., uprav tady.
COMP_RE = re.compile(r"extralig", re.I)
COMP_EXCLUDE_RE = re.compile(r"junior|dorost|9\. tříd|U\d\d|\bml\.|\bst\.", re.I)
PLAYOFF_RE = re.compile(r"play\s*-?\s*(off|out)|baráž", re.I)

DELAY = 1.0          # pauza mezi požadavky (s)
EMPTY_STOP = 3       # po kolika po sobě jdoucích sezónách bez jediného řádku se končí
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
}


# ---------------------------------------------------------------- utility
def fetch(url: str) -> BeautifulSoup:
    time.sleep(DELAY)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def _ascii(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", _ascii(s)))


def _int(s: str) -> int:
    s = (s or "").strip().replace("−", "-")
    try:
        return int(s)
    except ValueError:
        return 0


def comp_wanted(comp: str) -> bool:
    return bool(COMP_RE.search(comp)) and not COMP_EXCLUDE_RE.search(comp)


# ---------------------------------------------------------------- parsování
def parse_player_page(soup: BeautifulSoup) -> dict:
    """Vrátí {"sezony": [hodnoty z výběru sezón], "vybrana": str|None,
    "radky": [...všechny řádky tabulky...], "box": {...}|None}."""
    sel = soup.select_one("select[name=season]")
    sezony, vybrana = [], None
    if sel:
        for o in sel.select("option"):
            sezony.append(o.get("value"))
            if o.has_attr("selected"):
                vybrana = o.get("value")

    radky = []
    table = soup.select_one("table.table-stats")
    if table:
        for tr in table.select("tr"):
            td = tr.select("td")
            if len(td) < 11:
                continue
            dm = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", td[0].get_text(strip=True))
            if not dm:
                continue
            a = td[4].select_one("a")
            m = re.search(r"/zapas/(\d+)", a.get("href", "")) if a else None
            skore_txt = " ".join(td[4].get_text(" ", strip=True).split())
            sk = re.match(r"(\d+)\s*:\s*(\d+)\s*(.*)$", skore_txt)
            zapas = " ".join(td[3].get_text(" ", strip=True).split())
            tymy = re.split(r"\s*[–—-]\s*", zapas)
            if len(tymy) != 2:
                continue  # nečekaný formát zápasu — bez týmů nejde zařadit
            radky.append({
                "dt": f"{dm.group(3)}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}",
                "kolo": td[1].get_text(strip=True),
                "comp": td[2].get_text(strip=True),
                "a": tymy[0], "b": tymy[1],
                "sa": int(sk.group(1)) if sk else None,
                "sb": int(sk.group(2)) if sk else None,
                "ot": bool(sk and sk.group(3).strip()),
                "g": _int(td[5].get_text()), "as": _int(td[6].get_text()),
                "p": _int(td[7].get_text()), "pm": _int(td[8].get_text()),
                "tm": _int(td[9].get_text()), "toi": _toi(td[10].get_text(strip=True)),
                "zid": m.group(1) if m else None,
            })

    box = None
    vals = {}
    for t in soup.select(".person-info-stats-title"):
        label = t.get_text(" ", strip=True)
        nxt = t.find_next_sibling()
        raw = nxt.get_text(" ", strip=True) if nxt else ""
        if raw == "" and t.parent:  # hodnota může být v sousedním prvku rodiče
            raw = t.parent.get_text(" ", strip=True).replace(label, "", 1).strip()
        vals[label] = raw
    if vals:
        parent = soup.select_one(".person-info-stats-title").find_parent()
        txt = " ".join(parent.parent.get_text(" ", strip=True).split()) if parent and parent.parent else ""
        def grab(lbl):
            m = re.search(re.escape(lbl) + r"\s+(-?\d+)", txt)
            return int(m.group(1)) if m else None
        box = {"z": grab("Zápasy"), "g": grab("Góly"), "a": grab("Asistence"),
               "b": grab("Body"), "pm": grab("+/-"), "tm": grab("TM"), "text": txt[:160]}
    return {"sezony": sezony, "vybrana": vybrana, "radky": radky, "box": box}


def _toi(t: str) -> int:
    m = re.match(r"(\d+):(\d+)", t or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def _season_of(radek_dt: str) -> int:
    y, m = int(radek_dt[:4]), int(radek_dt[5:7])
    return y if m >= 7 else y - 1


# ---------------------------------------------------------------- hráči
def load_baseline() -> dict:
    data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_ids() -> dict:
    ids = dict(SEED_IDS)
    if IDS_FILE.exists():
        ids.update(json.loads(IDS_FILE.read_text(encoding="utf-8")))
    return ids


def discover_player_urls(names: list, known: dict) -> dict:
    """Najde /hrac/<slug>/<id> pro jména, která ještě nemáme — v odkazech
    na stránkách klubu. Shoda podle tokenů slugu a jména bez diakritiky."""
    chybi = [n for n in names if n not in known]
    if not chybi:
        return known
    links = {}
    for page in CLUB_PAGES:
        try:
            soup = fetch(BASE + page)
        except Exception as exc:
            print(f"Klub {page}: nedostupné ({exc})")
            continue
        for a in soup.select('a[href*="/hrac/"]'):
            m = re.search(r"(/hrac/([a-z0-9\-]+)/(\d+))", a.get("href", ""))
            if m:
                links[m.group(1)] = (m.group(2), a.get_text(" ", strip=True))
    for n in chybi:
        nt = _tokens(n)
        shody = []
        for path, (slug, txt) in links.items():
            st = _tokens(slug.replace("-", " "))
            if st and (st <= nt or nt <= st or (txt and _tokens(txt) == nt)):
                shody.append(path)
        if len(shody) == 1:
            known[n] = shody[0]
        elif len(shody) > 1:
            print(f"Víc možných odkazů pro {n}: {shody} — doplň ručně do bilance_hraci.json")
        else:
            print(f"Hráč {n}: odkaz nenalezen — doplň ručně do bilance_hraci.json")
    return known


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"hraci": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def scrape_player(name: str, path: str, entry: dict) -> dict:
    """Doplní entry["sezony"][rok] = {"radky": [...], "raw": N, "box": ...}."""
    sezony = entry.setdefault("sezony", {})
    first = parse_player_page(fetch(f"{BASE}{path}/match"))
    available = [s for s in first["sezony"] if s and s.isdigit()] or []
    available.sort(key=int, reverse=True)
    if not available:
        raise RuntimeError("na stránce nejsou sezóny — změnila se struktura?")
    newest = available[0]

    empty = 0
    for s in available:
        cached = sezony.get(s)
        if cached is not None and s != newest and not cached.get("chyba"):
            empty = empty + 1 if cached["raw"] == 0 else 0
            if empty >= EMPTY_STOP:
                break
            continue
        try:
            page = parse_player_page(fetch(f"{BASE}{path}/match?season={s}"))
        except Exception as exc:
            print(f"  {name} {s}: chyba ({exc})")
            sezony[s] = {"radky": [], "raw": -1, "chyba": str(exc)}
            continue
        rows = []
        for r in page["radky"]:
            if comp_wanted(r["comp"]):
                r["season"] = int(s)
                rows.append(r)
        sezony[s] = {"radky": rows, "raw": len(page["radky"]),
                     "box": page["box"] if s == newest else None}
        empty = empty + 1 if not page["radky"] else 0
        if empty >= EMPTY_STOP:
            break
    entry["stazeno"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry["nejnovejsi"] = newest
    return entry


# ---------------------------------------------------------------- kontrola
def _sum(rows: list) -> dict:
    return {"z": len(rows), "g": sum(r["g"] for r in rows), "a": sum(r["as"] for r in rows),
            "b": sum(r["p"] for r in rows), "pm": sum(r["pm"] for r in rows),
            "tm": sum(r["tm"] for r in rows)}


def build_kontrola(name: str, entry: dict, baseline: dict) -> dict:
    sezony = entry.get("sezony", {})
    problemy, info = [], []
    all_rows = [r for s in sezony.values() for r in s["radky"]]

    zle = [r for r in all_rows if r["p"] != r["g"] + r["as"]]
    if zle:
        problemy.append(f"{len(zle)} řádků, kde B ≠ G+A (např. {zle[0]['dt']} {zle[0]['zapas']})")

    chyby = [s for s, v in sezony.items() if v.get("chyba")]
    if chyby:
        problemy.append("sezóny se nepodařilo stáhnout: " + ", ".join(sorted(chyby)))

    newest = entry.get("nejnovejsi")
    cur = sezony.get(newest) if newest else None
    if cur and cur.get("box") and cur["box"].get("z") is not None:
        s = _sum(cur["radky"])
        box = cur["box"]
        rozdily = [f"{k.upper()}: řádky {s[k]} × box {box[k]}" for k in ("z", "g", "a", "b", "pm", "tm")
                   if box.get(k) is not None and s[k] != box[k]]
        if rozdily:
            problemy.append(f"aktuální sezóna {newest} nesedí s boxem na stránce hráče ({'; '.join(rozdily)})")
        else:
            info.append(f"sezóna {newest} sedí s boxem ({s['z']} Z, {s['b']} B)")
    elif newest:
        info.append("box aktuální sezóny nenalezen — kontrola přeskočena")

    base = (baseline.get(name) or {}).get("extraliga")
    if base and all(k in base for k in ("z", "g", "a", "b")) and newest:
        minule = [r for s, v in sezony.items() if s != newest for r in v["radky"]]
        zakl = [r for r in minule if not PLAYOFF_RE.search(r["comp"])]
        varianty = {"základní část": _sum(zakl), "se play off": _sum(minule)}
        shoda = [n for n, v in varianty.items() if all(v[k] == base[k] for k in ("z", "g", "a", "b"))]
        if shoda:
            info.append(f"kariéra před touto sezónou sedí s baseline ({shoda[0]})")
        else:
            v = varianty["se play off"]
            problemy.append(
                "kariéra před touto sezónou nesedí s baseline "
                f"(stránka: {v['z']} Z/{v['g']} G/{v['a']} A/{v['b']} B, "
                f"základní část {varianty['základní část']['z']} Z/{varianty['základní část']['b']} B; "
                f"baseline: {base['z']} Z/{base['g']} G/{base['a']} A/{base['b']} B)")
    else:
        info.append("baseline extraligy chybí — kariérní kontrola přeskočena")

    return {"ok": not problemy, "problemy": problemy, "info": info,
            "sezon": len([1 for v in sezony.values() if v["radky"]]), "zapasu": len(all_rows)}


def build_output(state: dict, baseline: dict) -> dict:
    hraci, kontrola = {}, {}
    for name, entry in sorted(state["hraci"].items()):
        rows = [r for s in entry.get("sezony", {}).values() for r in s["radky"]]
        hraci[name] = sorted(rows, key=lambda r: r["dt"])
        kontrola[name] = build_kontrola(name, entry, baseline)
    return {"vygenerovano": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hraci": hraci, "kontrola": kontrola}


def main() -> None:
    baseline = load_baseline()
    jmena = [n for n, v in baseline.items() if v.get("typ") == "skater"]
    state = load_state()
    ids = discover_player_urls(jmena, load_ids())
    nenalezeno = [n for n in jmena if n not in ids]

    for i, name in enumerate(jmena, 1):
        path = ids.get(name)
        if not path:
            continue
        print(f"[{i}/{len(jmena)}] {name} ({path})")
        entry = state["hraci"].setdefault(name, {"url": path})
        entry["url"] = path
        try:
            scrape_player(name, path, entry)
        except Exception as exc:
            print(f"  CHYBA: {exc}")
            continue
        save_state(state)

    OUTPUT_JSON.parent.mkdir(exist_ok=True)
    out = build_output(state, baseline)
    out["nenalezeno"] = nenalezeno
    OUTPUT_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ok = sum(1 for k in out["kontrola"].values() if k["ok"])
    print(f"Hotovo: {len(out['hraci'])} hráčů, kontrola OK u {ok}, nenalezeno {len(nenalezeno)}.")
    for n, k in out["kontrola"].items():
        for p in k["problemy"]:
            print(f"  ⚠ {n}: {p}")


if __name__ == "__main__":
    main()
