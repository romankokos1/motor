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
RUCNE_FILE = SCRIPT_DIR / "bilance_rucne.json"   # ruční určení týmu u nejednoznačných zápasů {"Jméno|YYYY-MM-DD": "KÓD"}
LIVE_FILE = SCRIPT_DIR / "bilance_live.json"      # řádky doplněné automaticky z hcmotor.cz
CURRENT_SEASON = 2026                              # sezóna 2026/27 (rok začátku)
OUTPUT_JSON = REPO_ROOT / "docs" / "bilance_data.json"

BASE = "https://www.hokej.cz"
CLUB_PAGES = [  # kde se hledají odkazy na hráče Motoru
    "/klub/banes-motor-c-budejovice/1721/soupiska",
]
SEED_IDS = {"Štencel Jan": "/hrac/jan-stencel/13684"}

# Které soutěže se berou. Výchozí = extraliga (základní část i play off/out
# se jmenují "...extralig..."), bez juniorských/dorosteneckých extraligových
# soutěží. Chceš-li přidat Chance ligu apod., uprav tady.
# Play off extraligy se v minulosti jmenovalo podle sponzora ("Generali play off",
# "Česká pojišťovna play off") — bez slova "extraliga", proto druhá alternativa.
COMP_RE = re.compile(r"extralig|^(Generali\s+)?(Česká pojišťovna\s+)?play\s*-?\s*off", re.I)
COMP_EXCLUDE_RE = re.compile(r"junior|dorost|9\. tříd|U\d\d|\bml\.|\bst\.|baráž", re.I)
PLAYOFF_RE = re.compile(r"play\s*-?\s*(off|out)|baráž", re.I)

DELAY = 1.0          # pauza mezi požadavky (s)
EMPTY_STOP = 3       # po kolika po sobě jdoucích sezónách bez jediného řádku se končí
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
}


# ---------------------------------------------------------------- utility
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.headers.update({
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "cs,en;q=0.8",
})
ROSTER_URL = BASE + CLUB_PAGES[0]


def fetch(url: str, referer: str | None = None) -> BeautifulSoup:
    time.sleep(DELAY)
    r = SESSION.get(url, headers={"Referer": referer or ROSTER_URL}, timeout=30)
    if r.status_code != 200:
        # krátká diagnostika (WAF/Cloudflare se obvykle prozradí hlavičkami)
        raise RuntimeError(
            f"HTTP {r.status_code} server={r.headers.get('server')} "
            f"cf-ray={r.headers.get('cf-ray')} tělo={r.text[:120]!r}")
    return BeautifulSoup(r.text, "html.parser")


def player_url(path: str, token: str | None, season: str | None = None) -> str:
    """URL stránky zápasů hráče. Odkazy na hokej.cz nesou parametr ?t=…
    (token ze stránky soupisky), bez kterého server vrací 403."""
    q = []
    if token:
        q.append(f"t={token}")
    if season:
        q.append(f"season={season}")
    return f"{BASE}{path}/match" + ("?" + "&".join(q) if q else "")


def roster_tokens() -> dict:
    """{'/hrac/slug/id': 't-token'} z odkazů v tabulkách soupisky."""
    out = {}
    soup = fetch(ROSTER_URL, referer=BASE + "/")
    for a in soup.select('table.table-soupiska a[href*="/hrac/"]'):
        href = a.get("href", "")
        m = re.search(r"(/hrac/[a-z0-9\-]+/\d+)(?:\?(.*))?$", href)
        if not m:
            continue
        tm = re.search(r"(?:^|&)t=([A-Za-z0-9]+)", m.group(2) or "")
        out[m.group(1)] = tm.group(1) if tm else None
    return out


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
        box = box_from_text(txt)
    return {"sezony": sezony, "vybrana": vybrana, "radky": radky, "box": box}


def box_from_text(txt: str) -> dict | None:
    """Box Zápasy/Góly/Asistence/Body/+-/TM z textu hlavičky hráče."""
    if not txt:
        return None
    def grab(lbl):
        m = re.search(re.escape(lbl) + r"\s+(-?\d+)", txt)
        return int(m.group(1)) if m else None
    return {"z": grab("Zápasy"), "g": grab("Góly"), "a": grab("Asistence"),
            "b": grab("Body"), "pm": grab("+/-"), "tm": grab("TM"), "text": txt[:160]}


def import_raw(state: dict, raw: dict, ids: dict) -> int:
    """Načte soubor z bilance-stahovatko.js (stažený v prohlížeči) do stavu."""
    cesta_na_jmeno = {v: k for k, v in ids.items()}
    n = 0
    for path, e in raw.items():
        name = cesta_na_jmeno.get(path)
        if not name:
            continue  # brankář / hráč mimo seznam
        entry = state["hraci"].setdefault(name, {"url": path})
        entry["url"] = path
        entry["nejnovejsi"] = e.get("nejnovejsi")
        sezony = {}
        for s, v in e["sezony"].items():
            rows = []
            for r in v["radky"]:
                if comp_wanted(r["comp"]):
                    r["season"] = int(s)
                    rows.append(r)
            sezony[s] = {"radky": rows, "raw": len(v["radky"]),
                         "box": box_from_text(v.get("boxText", "")) if s == e.get("nejnovejsi") else None}
        entry.setdefault("sezony", {}).update(sezony)  # slučuje: dřívější sezóny zůstanou
        entry["stazeno"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        n += 1
    return n


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
        # jen tabulky soupisky — jinde na stránce jsou odkazy na cizí hráče
        for a in soup.select('table.table-soupiska a[href*="/hrac/"]'):
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


def scrape_player(name: str, path: str, entry: dict, token: str | None = None) -> dict:
    """Doplní entry["sezony"][rok] = {"radky": [...], "raw": N, "box": ...}."""
    sezony = entry.setdefault("sezony", {})
    first = parse_player_page(fetch(player_url(path, token)))
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
            page = parse_player_page(fetch(player_url(path, token, s)))
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

    if not all_rows:
        problemy.append("žádná data (stažení selhalo nebo hráč nemá extraligové zápasy)")

    zle = [r for r in all_rows if r["p"] != r["g"] + r["as"]]
    if zle:
        problemy.append(f"{len(zle)} řádků, kde B ≠ G+A (např. {zle[0]['dt']} {zle[0]['zapas']})")

    chyby = [s for s, v in sezony.items() if v.get("chyba")]
    if chyby:
        problemy.append("sezóny se nepodařilo stáhnout: " + ", ".join(sorted(chyby)))

    newest = entry.get("nejnovejsi")
    cur = sezony.get(newest) if newest else None
    box = cur.get("box") if cur else None
    box_comp = re.split(r"\s+\d{4}-\d{4}", (box or {}).get("text", ""))[0] if box else ""
    if box and box.get("z") is not None and not comp_wanted(box_comp):
        info.append(f"box aktuální sezóny je za soutěž „{box_comp}“, ne za extraligu — kontrola přeskočena")
    elif box and box.get("z") is not None:
        s_ = _sum(cur["radky"])
        rozdily = [f"{k.upper()}: řádky {s_[k]} × box {box[k]}" for k in ("z", "g", "a", "b", "pm")
                   if box.get(k) is not None and s_[k] != box[k]]
        if rozdily:
            problemy.append(f"aktuální sezóna {newest} nesedí s boxem na stránce hráče ({'; '.join(rozdily)})")
        else:
            info.append(f"sezóna {newest} sedí s boxem ({s_['z']} Z, {s_['b']} B)")
        if box.get("tm") is not None and s_["tm"] != box["tm"]:
            info.append(f"TM se liší (řádky {s_['tm']} × box {box['tm']}) — jen informativně")
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


def build_output(state: dict, baseline: dict, live: dict | None = None) -> dict:
    live = live if live is not None else load_live()
    omax = official_max_dt(state)
    rucne = json.loads(RUCNE_FILE.read_text(encoding="utf-8")) if RUCNE_FILE.exists() else {}
    hraci, kontrola = {}, {}
    for name, entry in sorted(state["hraci"].items()):
        rows = [dict(r, **({"fix": rucne[f"{name}|{r['dt']}"]} if f"{name}|{r['dt']}" in rucne else {}))
                for s in entry.get("sezony", {}).values() for r in s["radky"]]
        zive = [r for r in live.get("radky", {}).get(name, []) if r["dt"] > omax]
        hraci[name] = sorted(rows + zive, key=lambda r: r["dt"])
        k = build_kontrola(name, entry, baseline)
        cur = [r for r in hraci[name] if r.get("season") == CURRENT_SEASON]
        hc = live.get("hcmotor", {}).get(name)
        if hc and cur:
            s_ = _sum(cur)
            rozdily = [f"{x.upper()}: stránka {s_[x]} × hcmotor {hc[x]}" for x in ("z", "g", "a", "b") if s_[x] != hc[x]]
            if rozdily:
                k["problemy"].append("součet aktuální sezóny (hokej.cz + doplněné zápasy) nesedí s hcmotor.cz ("
                                     + "; ".join(rozdily) + ") — nejspíš oprava statistik, při příštím importu z hokej.cz se srovná")
                k["ok"] = False
            else:
                k["info"].append("zápasy, góly, asistence a body sedí s hcmotor.cz")
            if s_["pm"] != hc["pm"]:
                # +/- se počítá na každém webu trochu jinak (např. gól bez brankáře),
                # rozdíl o 1–2 je běžný; platí hokej.cz — jen informativně
                k["info"].append(f"+/- se liší (hokej.cz {s_['pm']} × hcmotor {hc['pm']}) — jiné počítání webů, platí hokej.cz")
        if zive:
            k["info"].append(f"{len(zive)} zápasů doplněno automaticky z hcmotor.cz (bez TOI)")
        kontrola[name] = k
    # opravy bez přiřazeného zápasu, které už jsou v datech z hokej.cz (součet
    # hráče v aktuální sezóně se shoduje s hcmotor.cz), nejsou čeho se bát — vynechat
    cekajici = []
    for k in live.get("korekce", []):
        cur = [r for r in hraci.get(k["jmeno"], []) if r.get("season") == CURRENT_SEASON]
        hc = live.get("hcmotor", {}).get(k["jmeno"])
        if hc and cur:
            s_ = _sum(cur)
            if all(s_[x] == hc[x] for x in LIVE_FIELDS if k.get(x)):
                continue
        cekajici.append(k)
    return {"vygenerovano": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hraci": hraci, "kontrola": kontrola, "korekce": cekajici,
            "pristi": live.get("pristi"),
            "cisla": {**CISLA_VYCHOZI, **live.get("cisla", {})},
            "neprirazeno": live.get("neprirazeno", [])}


# ---------------------------------------------------------------- živé doplňování
# Mezi ručními importy z hokej.cz se nové zápasy doplňují automaticky z dat,
# která už denní běh hokej_stats.py stahuje z hcmotor.cz: rozdíl sezónních
# součtů hráče proti včerejšku = jeho řádek za nově odehraný zápas (soupeř
# a datum z rozpisu). TOI chybí (zůstane prázdné). Až se příště nahrají
# oficiální data z hokej.cz, živé řádky za zápasy, které už v nich jsou,
# se zahodí a platí oficiální. Pozdější opravy statistik (změna bez
# nového zápasu) se přičtou k poslednímu živému řádku hráče.
TEAM_CODES = [
    (r"kladno|rytíři", "KLA"), (r"vítkovice|ostrava", "VIT"), (r"liberec|tygři", "LIB"),
    (r"plzeň|škoda", "PLZ"), (r"kometa|brno", "KOM"), (r"sparta", "SPA"),
    (r"pardubice|dynamo", "PCE"), (r"litvínov|verva", "LIT"), (r"karlovy vary|energie", "KVA"),
    (r"olomouc|mora", "OLO"), (r"hradec|mountfield", "MHK"), (r"boleslav", "MBL"),
    (r"třinec|oceláři", "TRI"), (r"zlín|berani", "ZLN"), (r"chomutov|piráti", "CHM"),
    (r"jihlava|dukla", "JIH"), (r"budějovice|motor", "CEB"),
]
# Čísla dresů pro dlaždice na stránce (výchozí; při denním běhu se přepíšou
# aktuálními čísly z hcmotor.cz)
CISLA_VYCHOZI = {
    "Štencel Jan": 7, "Nordsäter Lucas": 8, "Pýcha Pavel": 12, "Nedorost Václav": 13,
    "Vála Ondřej": 14, "Vráblík Roman": 69, "Andersen Ole Einar Engeland": 79,
    "Kundrátek Tomáš": 84, "Kachyňa Ondřej": 98, "Chlubna Tomáš": 10, "Novák Pavel": 11,
    "Lantoši Róbert": 16, "Toman Matěj": 20, "Koláček Josef": 22, "Zachar Marek": 26,
    "Humeník Matyáš": 27, "Krastenbergs Renars": 29, "Lev Jakub": 29, "Hejduk Marek": 37,
    "Hoch Štěpán": 42, "Ordoš Jan": 45, "Drančák Samuel": 46, "Beránek Martin": 56,
    "Ahl Filip": 61, "Pour Jakub": 64, "Bulíř Michal": 88, "Parker Bell": 92, "Bell Parker": 92,
    "Olesen Nick Alexander": 95,
}
LIVE_FIELDS = ("z", "g", "a", "b", "pm", "tm")


def team_code(name: str) -> str:
    for rx, code in TEAM_CODES:
        if re.search(rx, name, re.I):
            return code
    print(f"Bilance: neznámý tým '{name}', kód odvozen z názvu — doplň do TEAM_CODES.")
    return _ascii(name)[:3].upper() or "???"


def _game_date(datum: str) -> str | None:
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.", datum or "")
    if not m:
        return None
    den, mesic = int(m.group(1)), int(m.group(2))
    rok = CURRENT_SEASON if mesic >= 7 else CURRENT_SEASON + 1
    return f"{rok}-{mesic:02d}-{den:02d}"


def load_live() -> dict:
    empty = {"sezona": CURRENT_SEASON, "radky": {}, "zpracovano": [], "korekce": [],
             "neprirazeno": [], "hcmotor": {}}
    if LIVE_FILE.exists():
        data = json.loads(LIVE_FILE.read_text(encoding="utf-8"))
        if data.get("sezona") == CURRENT_SEASON:
            for k, v in empty.items():
                data.setdefault(k, v)
            return data
    return empty


def save_live(live: dict) -> None:
    LIVE_FILE.write_text(json.dumps(live, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def official_max_dt(state: dict) -> str:
    """Datum posledního oficiálního (z hokej.cz) zápasu aktuální sezóny."""
    best = "0000-00-00"
    for e in state.get("hraci", {}).values():
        for r in e.get("sezony", {}).get(str(CURRENT_SEASON), {}).get("radky", []):
            best = max(best, r["dt"])
    return best


def _skater_totals(st: dict) -> dict:
    return {s["jmeno"]: {k: s.get(k, 0) for k in LIVE_FIELDS} for s in st.get("skaters", {}).values()}


def _pristi_zapas(games: list) -> dict | None:
    """Nejbližší neodehraný zápas Motoru (pro zápasovou nápovědu na stránce)."""
    budouci = [g for g in games if not g.get("odehrano")]
    if not budouci:
        return None
    g = min(budouci, key=lambda x: x["kolo"])
    doma = bool(re.search(r"budějovice|motor", g["domaci"], re.I))
    return {"kolo": g["kolo"], "soupez": team_code(g["hoste"] if doma else g["domaci"]),
            "doma": doma, "datum": _game_date(g.get("datum")), "cas": g.get("cas")}


def zpracuj_beh(old_state: dict, new_state: dict, games: list) -> None:
    """Volá denní běh hokej_stats.py po stažení nových statistik."""
    state = load_state()
    if not state["hraci"] or not old_state.get("skaters"):
        print("Bilance živě: není s čím porovnávat (chybí import nebo předchozí stav).")
        return
    live = load_live()
    baseline = load_baseline()
    live["pristi"] = _pristi_zapas(games)
    old, new = _skater_totals(old_state), _skater_totals(new_state)
    live["hcmotor"] = new
    live["cisla"] = {x["jmeno"]: x.get("cislo") for x in new_state.get("skaters", {}).values() if x.get("cislo")}

    omax = official_max_dt(state)
    hotove = set(live["zpracovano"])
    pending = []
    for g in sorted((g for g in games if g.get("odehrano")), key=lambda g: g["kolo"]):
        dt = _game_date(g["datum"])
        if dt and dt > omax and g["kolo"] not in hotove:
            pending.append((g, dt))

    deltas = {}
    for name, t in new.items():
        if name not in state["hraci"] or name not in old:
            continue
        d = {k: t[k] - old[name][k] for k in LIVE_FIELDS}
        if any(d.values()):
            deltas[name] = d

    pouzito = set()
    for name, d in deltas.items():
        if d["z"] > 0:
            if not pending:
                live["neprirazeno"].append({"jmeno": name, **d, "poznamka": "nový zápas, ale v rozpisu žádný nezpracovaný"})
                continue
            vyber = pending[-d["z"]:]
            for i, (g, dt) in enumerate(vyber):
                posledni = i == len(vyber) - 1
                sk = re.match(r"(\d+)\s*:\s*(\d+)", g.get("vysledek") or "")
                live["radky"].setdefault(name, []).append({
                    "dt": dt, "kolo": f"{g['kolo']}.", "comp": "Tipsport extraliga",
                    "a": team_code(g["domaci"]), "b": team_code(g["hoste"]),
                    "sa": int(sk.group(1)) if sk else None, "sb": int(sk.group(2)) if sk else None,
                    "ot": bool(re.search(r"p", g.get("vysledek") or "")),
                    "g": d["g"] if posledni else 0, "as": d["a"] if posledni else 0,
                    "p": d["b"] if posledni else 0, "pm": d["pm"] if posledni else 0,
                    "tm": d["tm"] if posledni else 0, "toi": 0, "zid": None,
                    "season": CURRENT_SEASON, "zivy": True,
                    **({"odhad": True} if d["z"] > 1 else {}),
                })
                pouzito.add(g["kolo"])
        else:
            # oprava statistik bez nového zápasu → přičíst k poslednímu živému řádku
            radky = live["radky"].get(name)
            if radky:
                r = radky[-1]
                r["g"] += d["g"]; r["as"] += d["a"]; r["p"] += d["b"]; r["pm"] += d["pm"]; r["tm"] += d["tm"]
                r["korigovano"] = True
            else:
                live["korekce"].append({"jmeno": name, **d, "datum": datetime.now(timezone.utc).date().isoformat()})
    if pouzito:
        live["zpracovano"] = sorted(hotove | {g["kolo"] for g, _ in pending if g["kolo"] <= max(pouzito)})
    live["korekce"] = live["korekce"][-50:]
    live["neprirazeno"] = live["neprirazeno"][-50:]
    save_live(live)

    out = build_output(state, baseline, live)
    OUTPUT_JSON.parent.mkdir(exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Bilance živě: nových zápasů {len(pouzito)}, změn u {len(deltas)} hráčů, "
          f"kontrola OK u {sum(k['ok'] for k in out['kontrola'].values())}/{len(out['kontrola'])}.")


def main() -> None:
    import sys
    baseline = load_baseline()
    jmena = [n for n, v in baseline.items() if v.get("typ") == "skater"]
    state = load_state()
    if "--import" in sys.argv:
        raw = json.loads(Path(sys.argv[sys.argv.index("--import") + 1]).read_text(encoding="utf-8"))
        print(f"Import: {import_raw(state, raw, load_ids())} hráčů ze souboru.")
        save_state(state)
        out = build_output(state, baseline)
        out["nenalezeno"] = [n for n in jmena if n not in state["hraci"]]
        OUTPUT_JSON.parent.mkdir(exist_ok=True)
        OUTPUT_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        for n, k in out["kontrola"].items():
            for p in k["problemy"]:
                print(f"  ⚠ {n}: {p}")
        print(f"Hotovo: {len(out['hraci'])} hráčů, kontrola OK u {sum(k['ok'] for k in out['kontrola'].values())}.")
        return
    try:
        tokens = roster_tokens()
        print(f"Soupiska: {len(tokens)} odkazů na hráče, token "
              f"{'nalezen' if any(tokens.values()) else 'NENALEZEN'}.")
    except Exception as exc:
        print(f"Soupiska se nepodařilo načíst ({exc}).")
        tokens = {}
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
            scrape_player(name, path, entry, tokens.get(path))
        except Exception as exc:
            print(f"  CHYBA: {exc}")
            continue
        save_state(state)

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
    if not any(out["hraci"].values()):
        raise SystemExit("Nepodařilo se stáhnout žádného hráče — viz chyby výše.")


if __name__ == "__main__":
    main()
