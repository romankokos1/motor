#!/usr/bin/env python3
"""
Hlídač hokejových statistik — HC Motor České Budějovice.

Zdroj: hcmotor.cz — oficiální statistiky hráčů klubu (brankáři i hráči
v poli), tabulka pro aktuální sezónu/část soutěže.

Denně stáhne aktuální tabulku, porovná ji s předchozím uloženým stavem
(state.json), vygeneruje statickou HTML stránku (docs/stats.html) se
základní tabulkou statistik a zvýrazněnými změnami od minula.

Kromě toho volitelně načte players_baseline.json — ručně vedený soubor
s výchozím stavem hráčů (konec minulé sezony pro ty, co zůstali v
kádru; stav před příchodem do Motoru pro posily), rozdělený na "za
Motor" a "v celé Extralize". Pokud tenhle soubor existuje, přičte
aktuální sezónu k výchozímu stavu a vygeneruje navíc dvě kariérní
tabulky (za Motor / v Extralize celkem). Tenhle soubor skript sám
nikdy nezapisuje — udržuje ho ručně Gaffer.

Stránku pak zobrazuje GitHub Pages.
"""

import json
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# Skript žije v repu ve složce scripts/, ale výsledná stránka musí jít
# do docs/ v kořeni repa (tam, kde běží GitHub Pages).
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
STATE_FILE = SCRIPT_DIR / "state.json"
BASELINE_FILE = SCRIPT_DIR / "players_baseline.json"
HISTORY_FILE = SCRIPT_DIR / "history.json"
HISTORY_DAYS = 7  # kolik posledních dní se v historii drží
MONTHLY_BOUNDARIES_FILE = SCRIPT_DIR / "month_boundaries.json"
MONTHLY_MONTHS_SHOWN = 3  # kolik posledních měsíců se zobrazuje na stránce
MONTHS_CS = {
    1: "leden", 2: "únor", 3: "březen", 4: "duben", 5: "květen", 6: "červen",
    7: "červenec", 8: "srpen", 9: "září", 10: "říjen", 11: "listopad", 12: "prosinec",
}
SCHEDULE_WATCH_FILE = SCRIPT_DIR / "schedule_watch.json"
SCHEDULE_LOG_FILE = SCRIPT_DIR / "schedule_changes_log.json"
SEASON_ROUNDS = 52  # počet kol základní části - pro rozsah osy X grafu bilance
CLUB_NAME = "České Budějovice"
DOCS_DIR = REPO_ROOT / "docs"
OUTPUT_HTML = DOCS_DIR / "stats.html"

# sezona=2027 -> sezóna 2026/2027.
# POZOR: endpoint statistiky.asp?sezona=...&cast=... (odkazy v navigaci
# "přípravná utkání/základní část/play-off/baráž") v září 2026 hlásil
# "vybrané statistiky nebyly nalezeny" pro všechny hodnoty cast, zatímco
# stats.asp?sezona=... (bez cast) reálná data vrací spolehlivě a
# zřejmě sám ukazuje aktuálně relevantní část sezóny. Používáme proto
# tenhle endpoint; pokud by v budoucnu přestal fungovat (např. v
# play-off), zkus nejdřív ručně v prohlížeči najít správnou URL a
# STATS_URL podle toho uprav.
STATS_URL = "https://hcmotor.cz/stats.asp?sezona=2027"
SCHEDULE_URL = "https://hcmotor.cz/zapasy.asp?sezona=2027"
SEASON_LABEL = "Tipsport extraliga 2026/2027"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def _text(cell) -> str:
    return cell.get_text(strip=True) if cell else ""


def _int(cell) -> int:
    t = _text(cell).replace("−", "-").replace(",", ".")
    if t in ("", "-"):
        return 0
    try:
        return int(t)
    except ValueError:
        m = re.search(r"-?\d+", t)
        return int(m.group()) if m else 0


def _float(cell) -> float:
    t = _text(cell).replace("−", "-").replace(",", ".")
    if t in ("", "-"):
        return 0.0
    try:
        return float(t)
    except ValueError:
        m = re.search(r"-?\d+\.?\d*", t)
        return float(m.group()) if m else 0.0


def _player_id(cell) -> str:
    """Vytáhne id hráče z odkazu hrac.asp?id=NNN, nebo prázdný string."""
    link = cell.find("a") if cell else None
    if not link or not link.get("href"):
        return ""
    m = re.search(r"[?&]id=(\d+)", link["href"])
    return m.group(1) if m else ""


def parse_goalkeepers(table) -> dict:
    """
    {player_id: {"jmeno":..., "cislo":..., "z":..., "min":..., "str":...,
                 "ink":..., "zas":..., "pru":..., "usp":..., "so":...,
                 "a":..., "tm":...}}
    Sloupce: # | jméno | Z | Min | Stř | Ink | Zás | Prů | Úsp | SO | A | TM
    """
    players = {}
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 11:
            continue
        name = _text(cells[1])
        if not name or not re.search(r"[A-Za-zÀ-ž]", name):
            continue
        # Nový hráč často ještě nemá na hcmotor.cz profil (jméno bez odkazu)
        # — dřív se takový řádek zahodil. Teď dostane náhradní ID podle jména.
        pid = _player_id(cells[1]) or f"jm:{name}"
        players[pid] = {
            "jmeno": name,
            "cislo": _text(cells[0]),
            "z": _int(cells[2]),
            "min": _int(cells[3]),
            "str": _int(cells[4]),
            "ink": _int(cells[5]),
            "zas": _int(cells[6]),
            "pru": _float(cells[7]),
            "usp": _float(cells[8]),
            "so": _int(cells[9]),
            "a": _int(cells[10]),
            "tm": _int(cells[11]) if len(cells) > 11 else 0,
        }
    return players


def parse_skaters(table) -> dict:
    """
    {player_id: {"jmeno":..., "cislo":..., "post":..., "z":..., "g":...,
                 "a":..., "b":..., "pm":..., "tm":...}}
    Sloupce: # | jméno | P | Z | G | A | B | +/- | TM
    Prázdné oddělovací řádky (obránci/útočníci) se přeskakují.
    """
    players = {}
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 8:
            continue
        name = _text(cells[1])
        if not name or not re.search(r"[A-Za-zÀ-ž]", name):
            continue
        # Nový hráč často ještě nemá na hcmotor.cz profil (jméno bez odkazu)
        # — dřív se takový řádek zahodil. Teď dostane náhradní ID podle jména.
        pid = _player_id(cells[1]) or f"jm:{name}"
        players[pid] = {
            "jmeno": name,
            "cislo": _text(cells[0]),
            "post": _text(cells[2]),
            "z": _int(cells[3]),
            "g": _int(cells[4]),
            "a": _int(cells[5]),
            "b": _int(cells[6]),
            "pm": _int(cells[7]),
            "tm": _int(cells[8]) if len(cells) > 8 else 0,
        }
    return players


def parse_stats_page(soup: BeautifulSoup) -> dict:
    """
    Najde na stránce tabulku brankářů a tabulku hráčů v poli.
    Rozlišuje je podle záhlaví (obsahuje "brankáři" / "hráči v poli"),
    a když se to nepodaří, podle počtu sloupců (brankáři mají víc).
    """
    tables = soup.find_all("table")
    goalkeepers, skaters = {}, {}

    for table in tables:
        header_text = table.get_text(" ", strip=True).lower()
        first_row_cells = len(table.find("tr").find_all(["td", "th"])) if table.find("tr") else 0

        if "brankář" in header_text[:200]:
            goalkeepers = parse_goalkeepers(table)
        elif "hráči v poli" in header_text[:200] or "hrac" in header_text[:200]:
            skaters = parse_skaters(table)
        elif first_row_cells >= 11:
            goalkeepers = parse_goalkeepers(table)
        elif first_row_cells >= 8:
            skaters = parse_skaters(table)

    return {"goalkeepers": goalkeepers, "skaters": skaters}


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_history() -> list:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def save_history(history: list) -> None:
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_history(history: list, changes: list, corrections: list) -> list:
    """
    Přidá dnešní změny/opravy do historie. Pokud skript dnes už běžel
    (např. kvůli opravě dat), nový běh se PŘIPOJÍ k tomu, co už dnes
    v historii je, místo aby ho přepsal — ať se neztratí změny
    z prvního běhu. Ořízne na posledních HISTORY_DAYS dní. Dny beze
    změn i bez oprav se do historie nepřidávají (nic by se v nich
    stejně nezobrazilo).
    """
    today = datetime.now(ZoneInfo("Europe/Prague")).strftime("%Y-%m-%d")
    existing = next((d for d in history if d["date"] == today), None)
    if changes or corrections:
        if existing is not None:
            existing["changes"] = list(existing.get("changes", [])) + list(changes)
            existing["corrections"] = list(existing.get("corrections", [])) + list(corrections)
        else:
            history.append({"date": today, "changes": list(changes), "corrections": list(corrections)})
    history.sort(key=lambda d: d["date"], reverse=True)
    return history[:HISTORY_DAYS]


def effective_month_key() -> str:
    """
    Skript běží ráno a zachycuje zápas odehraný VČERA večer — takže pro
    měsíční součty se datum běhu bere jako "včerejšek", ne dnešek.
    Díky tomu se zápas zachycený ráno 1. 10. správně započte do září,
    ne do října.
    """
    effective_date = datetime.now(ZoneInfo("Europe/Prague")) - timedelta(days=1)
    return effective_date.strftime("%Y-%m")


def state_to_name_snapshot(state: dict) -> dict:
    """
    Převede state.json (klíčovaný podle ID hráče) na snímek klíčovaný
    podle jména — {"skaters": {jmeno: {z,g,a,b}}, "goalkeepers":
    {jmeno: {z}}}. Tohle je "hraniční snímek" pro měsíční přehled (viz
    build_monthly_from_boundaries).
    """
    snap = {"skaters": {}, "goalkeepers": {}}
    for s in state.get("skaters", {}).values():
        snap["skaters"][s["jmeno"]] = {
            "z": s.get("z", 0), "g": s.get("g", 0), "a": s.get("a", 0), "b": s.get("b", 0),
        }
    for g in state.get("goalkeepers", {}).values():
        snap["goalkeepers"][g["jmeno"]] = {"z": g.get("z", 0)}
    return snap


def load_month_boundaries() -> dict:
    if MONTHLY_BOUNDARIES_FILE.exists():
        return json.loads(MONTHLY_BOUNDARIES_FILE.read_text(encoding="utf-8"))
    return {}


def save_month_boundaries(boundaries: dict) -> None:
    MONTHLY_BOUNDARIES_FILE.write_text(
        json.dumps(boundaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_monthly_from_boundaries(boundaries: dict, live_snapshot: dict) -> dict:
    """
    Měsíční přehled se počítá jako rozdíl dvou "hraničních" snímků
    celé sezóny (scripts/month_boundaries.json), ne jako postupné
    sčítání přírůstků po jednotlivých bězích. Díky tomu se do
    aktuálního (posledního, ještě "otevřeného") měsíce automaticky
    promítne i oprava statistik na hcmotor.cz, protože se prostě
    přepočítá "aktuální stav minus stav na začátku měsíce" — přesně
    jak to jde vyčíst z tabulky Aktuální sezóna. Uzavřené měsíce (ne
    ten poslední) se počítají jako rozdíl hranice tohoto měsíce a
    hranice měsíce následujícího, takže zůstávají fixní.
    """
    if not boundaries:
        return {}

    keys = sorted(boundaries.keys())

    def diff(name_key: str, start: dict, end: dict) -> dict:
        result = {}
        all_names = set(start.get(name_key, {})) | set(end.get(name_key, {}))
        for name in all_names:
            s0 = start.get(name_key, {}).get(name, {})
            s1 = end.get(name_key, {}).get(name, {})
            if name_key == "goalkeepers":
                dz = s1.get("z", 0) - s0.get("z", 0)
                if dz:
                    result[name] = {"z": dz}
            else:
                d = {f: s1.get(f, 0) - s0.get(f, 0) for f in ("z", "g", "a", "b")}
                if any(d.values()):
                    result[name] = d
        return result

    monthly = {}
    for i, mk in enumerate(keys):
        start = boundaries[mk]
        end = boundaries[keys[i + 1]] if i + 1 < len(keys) else live_snapshot
        monthly[mk] = {
            "skaters": diff("skaters", start, end),
            "goalkeepers": diff("goalkeepers", start, end),
        }
    return monthly


def load_baseline() -> dict:
    """
    Ručně vedený soubor s výchozím stavem hráčů (konec minulé sezony /
    stav před příchodem do Motoru). Skript ho jen čte, nikdy nezapisuje.

    Formát (klíč = přesně jméno, jak ho zobrazuje hcmotor.cz):
    {
      "Příjmení Jméno": {
        "typ": "skater",                          # nebo "goalkeeper"
        "motor":     {"z": .., "g": .., "a": .., "b": ..},
        "extraliga": {"z": .., "g": .., "a": .., "b": ..}
      }
    }
    U brankářů stačí v "motor"/"extraliga" jen klíč "z" (počet zápasů).
    Klíče začínající podtržítkem (např. "_priklad") se ignorují —
    slouží jen jako dokumentace formátu v souboru samém.
    """
    if not BASELINE_FILE.exists():
        return {}
    data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


MILESTONE_STEP = 50  # hlídáme kulatá čísla po 50 (50, 100, 150, ...)
MILESTONE_LOOKAHEAD = 5  # "blíží se" = chybí max. tolik zápasů/bodů/gólů (kartička na stránce)
ICON_BADGE_LOOKAHEAD = 2  # užší práh jen pro odznak v titulku stránky (ikonka na ploše)

METRIC_LABELS = {"z": "zápas", "g": "gól", "b": "bod"}
SCOPE_LABELS = {"motor": "za Motor", "extraliga": "v Extralize"}


def _old_stats(old_group: dict, pid: str, name: str):
    """Předchozí stav hráče — podle ID, a když nesedí (hráč mezitím
    dostal na hcmotor.cz profil, nebo ho naopak ztratil), podle jména."""
    if pid in old_group:
        return old_group[pid]
    for s in old_group.values():
        if s.get("jmeno") == name:
            return s
    return None


def build_changes(old: dict, new: dict, baseline: dict) -> list:
    """Vrátí seznam textových řádků se změnami od minulého běhu."""
    changes = []
    no_point_players = []  # hráči, co odehráli zápas beze změny bodů — sloučí se do 1 řádku

    old_skaters = old.get("skaters", {})
    new_skaters = new.get("skaters", {})
    for pid, stats in new_skaters.items():
        old_stats = _old_stats(old_skaters, pid, stats["jmeno"])
        if old_stats is None:
            debut = (
                f" — debut: {stats['z']} zápas, {stats['g']}G {stats['a']}A, {stats['b']}b"
                if stats["z"] > 0
                else ""
            )
            changes.append(f"🆕 Nový hráč v tabulce: {stats['jmeno']}{debut}")
            continue
        dz = stats["z"] - old_stats.get("z", 0)
        # Zprávy o zápase/bodech hlásíme jen, když skutečně přibyl
        # odehraný zápas (dz > 0) — jinak by šlo o opravu statistik
        # (viz build_corrections), ne o nový zápas.
        if dz > 0:
            dg = stats["g"] - old_stats.get("g", 0)
            da = stats["a"] - old_stats.get("a", 0)
            db = stats["b"] - old_stats.get("b", 0)
            if db > 0:
                detail = []
                if dg:
                    detail.append(f"{dg}G")
                if da:
                    detail.append(f"{da}A")
                detail_str = f" ({'+'.join(detail)})" if detail else ""
                changes.append(
                    f"🏒 {stats['jmeno']}: +{db}b{detail_str} → celkem {stats['b']}b "
                    f"({stats['g']}G {stats['a']}A, {stats['z']} zápasů)"
                )
            else:
                # Beze změny bodů — nesypeme to jako samostatný řádek na
                # hráče (na zápasový den by to bylo 15-20 řádků), ale
                # sbíráme jméno a sloučíme do jednoho souhrnného řádku níž.
                no_point_players.append(stats["jmeno"])

    if no_point_players:
        n = len(no_point_players)
        jmena = ", ".join(sorted(no_point_players))
        changes.append(f"▫️ Bez bodu odehráli zápas ({n}): {jmena}")

    old_gk = old.get("goalkeepers", {})
    new_gk = new.get("goalkeepers", {})
    for pid, stats in new_gk.items():
        old_stats = _old_stats(old_gk, pid, stats["jmeno"])
        if old_stats is None:
            debut = (
                f" — debut: {stats['z']} zápas, {stats['usp']:.1f}% úspěšnost"
                if stats["z"] > 0
                else ""
            )
            changes.append(f"🆕 Nový brankář v tabulce: {stats['jmeno']}{debut}")
            continue
        dz = stats["z"] - old_stats.get("z", 0)
        # Stejně jako u hráčů v poli — jen když skutečně přibyl zápas.
        if dz > 0:
            dso = stats["so"] - old_stats.get("so", 0)
            changes.append(
                f"🥅 {stats['jmeno']}: odchytal další zápas — "
                f"{stats['usp']:.1f}% úspěšnost, {stats['pru']:.2f} průměr "
                f"({stats['z']} zápasů celkem)"
            )
            if dso > 0:
                changes.append(f"🚫 {stats['jmeno']}: vychytal nulu! (celkem {stats['so']} SO)")

    changes.extend(build_milestone_crossings(old, new, baseline))

    return changes


def build_corrections(old: dict, new: dict) -> list:
    """
    Vrátí seznam hlášení o opravách statistik na hcmotor.cz — tedy o
    změnách hodnot G/A/B/TM (u brankářů Ink/Zás/SO/TM), ke kterým
    došlo BEZE změny počtu odehraných zápasů (Z). Týdenní korekce dat
    se tak nepletou se skutečnými zápasovými změnami v "Změnách od
    minulé aktualizace" — mají vlastní kartičku na stránce.

    Pokud se navíc sníží i Z (vzácné, ale teoreticky možné — např.
    škrtnutí chybně připsaného zápasu), hlásí se to tu také, protože
    zápasy samy o sobě nikdy neubývají.
    """
    items = []

    def deltas_str(old_stats: dict, stats: dict, fields: list) -> list:
        parts = []
        for field, label in fields:
            d = stats.get(field, 0) - old_stats.get(field, 0)
            if d != 0:
                parts.append(f"{'+' if d > 0 else ''}{d}{label}")
        return parts

    old_skaters = old.get("skaters", {})
    for pid, stats in new.get("skaters", {}).items():
        old_stats = _old_stats(old_skaters, pid, stats["jmeno"])
        if old_stats is None:
            continue  # nový hráč — není s čím srovnávat
        dz = stats["z"] - old_stats.get("z", 0)
        parts = deltas_str(old_stats, stats, [("g", "G"), ("a", "A"), ("b", "B"), ("tm", "TM")])
        if dz < 0:
            parts.insert(0, f"{dz}Z")
            items.append(f"📝 {stats['jmeno']}: oprava statistik ({', '.join(parts)})")
        elif dz == 0 and parts:
            items.append(
                f"📝 {stats['jmeno']}: oprava statistik ({', '.join(parts)}) "
                f"— beze změny počtu zápasů"
            )

    old_gk = old.get("goalkeepers", {})
    for pid, stats in new.get("goalkeepers", {}).items():
        old_stats = _old_stats(old_gk, pid, stats["jmeno"])
        if old_stats is None:
            continue
        dz = stats["z"] - old_stats.get("z", 0)
        parts = deltas_str(old_stats, stats, [("ink", "Ink"), ("zas", "Zás"), ("so", "SO"), ("tm", "TM")])
        if dz < 0:
            parts.insert(0, f"{dz}Z")
            items.append(f"📝 {stats['jmeno']}: oprava statistik ({', '.join(parts)})")
        elif dz == 0 and parts:
            items.append(
                f"📝 {stats['jmeno']}: oprava statistik ({', '.join(parts)}) "
                f"— beze změny počtu zápasů"
            )

    return items


def build_milestone_crossings(old: dict, new: dict, baseline: dict) -> list:
    """
    Porovná kariérní součty (baseline + sezóna) před a po tomto běhu a
    nahlásí, když hráč právě překročil kulaté číslo (násobek
    MILESTONE_STEP) v Z/G/B za Motor nebo v Extralize. Počítá se jen
    u hráčů se zadaným baseline pro daný rozsah.
    """
    items = []

    def crossings(old_stats: dict, new_stats: dict, base_scope: dict, metric: str, name: str, scope: str):
        base_val = base_scope.get(metric, 0)
        old_val = base_val + old_stats.get(metric, 0)
        new_val = base_val + new_stats.get(metric, 0)
        old_floor = old_val // MILESTONE_STEP
        new_floor = new_val // MILESTONE_STEP
        if new_floor > old_floor and new_val > 0:
            milestone = new_floor * MILESTONE_STEP
            label = METRIC_LABELS[metric]
            items.append(
                f"🎯 {name}: dosáhl/a {milestone}. {label}u {SCOPE_LABELS[scope]}!"
            )

    old_skaters = old.get("skaters", {})
    new_skaters = new.get("skaters", {})
    for pid, stats in new_skaters.items():
        name = stats["jmeno"]
        b = baseline.get(name)
        if not b or b.get("typ") != "skater":
            continue
        old_stats = _old_stats(old_skaters, pid, name) or {}
        for scope in ("motor", "extraliga"):
            base_scope = b.get(scope)
            if not base_scope:
                continue
            for metric in ("z", "g", "b"):
                crossings(old_stats, stats, base_scope, metric, name, scope)

    old_gk = old.get("goalkeepers", {})
    new_gk = new.get("goalkeepers", {})
    for pid, stats in new_gk.items():
        name = stats["jmeno"]
        b = baseline.get(name)
        if not b or b.get("typ") != "goalkeeper":
            continue
        old_stats = _old_stats(old_gk, pid, name) or {}
        for scope in ("motor", "extraliga"):
            base_scope = b.get(scope)
            if not base_scope:
                continue
            crossings(old_stats, stats, base_scope, "z", name, scope)

    return items


def build_upcoming_milestones(new: dict, baseline: dict) -> list:
    """
    Vrátí seznam hráčů, kterým do nejbližšího kulatého čísla (násobek
    MILESTONE_STEP) chybí nejvýš MILESTONE_LOOKAHEAD zápasů/gólů/bodů,
    zvlášť za Motor a zvlášť v Extralize. Jen pro hráče se zadaným
    baseline pro daný rozsah — bez něj by číslo bylo zavádějící.
    """
    items = []

    def check(name: str, value: int, metric: str, scope: str):
        if value <= 0:
            return
        remainder = value % MILESTONE_STEP
        if remainder == 0:
            return  # milník byl dosažen přesně teď — to hlásí build_milestone_crossings
        chybi = MILESTONE_STEP - remainder
        if chybi <= MILESTONE_LOOKAHEAD:
            items.append({
                "jmeno": name,
                "metric": metric,
                "scope": scope,
                "hodnota": value,
                "milestone": value + chybi,
                "chybi": chybi,
            })

    for scope in ("motor", "extraliga"):
        rows, _ = build_career_rows(new.get("skaters", {}), baseline, "skater", scope)
        for r in rows:
            if not r["ma_baseline"]:
                continue
            check(r["jmeno"], r["z"], "z", scope)
            check(r["jmeno"], r["g"], "g", scope)
            check(r["jmeno"], r["b"], "b", scope)

        gk_rows, _ = build_career_rows(new.get("goalkeepers", {}), baseline, "goalkeeper", scope)
        for r in gk_rows:
            if not r["ma_baseline"]:
                continue
            check(r["jmeno"], r["z"], "z", scope)

    items.sort(key=lambda i: i["chybi"])
    return items


def build_career_rows(current: dict, baseline: dict, player_type: str, scope: str) -> tuple:
    """
    Spočítá kariérní součty (baseline + aktuální sezóna) pro daný typ
    hráče ("skater"/"goalkeeper") a rozsah ("motor"/"extraliga").

    Vrátí (rows, missing) — rows jsou seřazené kariérní řádky (i pro
    hráče bez zadaného výchozího stavu, ti mají "ma_baseline": False
    a kariérní čísla rovná aktuální sezóně), missing je seznam jmen
    hráčů z current, ke kterým chybí baseline vůbec.
    """
    rows = []
    missing = []

    for stats in current.values():
        name = stats["jmeno"]
        b = baseline.get(name)
        has_baseline = bool(b) and b.get("typ") == player_type and scope in b

        if player_type == "goalkeeper":
            base_z = b[scope].get("z", 0) if has_baseline else 0
            rows.append({
                "jmeno": name,
                "z": base_z + stats["z"],
                "ma_baseline": has_baseline,
            })
        else:
            base = b[scope] if has_baseline else {}
            rows.append({
                "jmeno": name,
                "post": stats["post"],
                "z": base.get("z", 0) + stats["z"],
                "g": base.get("g", 0) + stats["g"],
                "a": base.get("a", 0) + stats["a"],
                "b": base.get("b", 0) + stats["b"],
                "ma_baseline": has_baseline,
            })

        if not has_baseline:
            missing.append(name)

    sort_key = (lambda r: r["z"]) if player_type == "goalkeeper" else (lambda r: r["b"])
    rows.sort(key=sort_key, reverse=True)
    return rows, missing


def parse_schedule_page(soup: BeautifulSoup) -> list:
    """
    Rozparsuje https://hcmotor.cz/zapasy.asp?sezona=... — seznam všech
    kol sezóny (odehraných i budoucích). Vrací list dictů:
    {"kolo": int, "domaci": str, "hoste": str, "datum": str, "misto": str,
     "odehrano": bool, "cas": str|None, "vysledek": str|None,
     "vyhra": bool, "prohra": bool}
    "vyhra"/"prohra" jsou z pohledu Motoru — web sám odkaz na výsledek
    značí třídou "win"/"loss", takže se nemusí ručně dohadovat, kdo hrál
    doma/venku.
    """
    games = []
    for game in soup.select("div.game"):
        round_div = game.select_one("div.round")
        teams_div = game.select_one("div.teams")
        score_div = game.select_one("div.score")
        if not round_div or not teams_div or not score_div:
            continue

        round_text = " ".join(round_div.get_text(" ", strip=True).split())
        m = re.match(r"(\d+)\.\s*kolo,?\s*(.*)", round_text)
        if not m:
            continue
        kolo = int(m.group(1))
        rest = m.group(2)
        parts = [p.strip() for p in rest.split(",", 1)]
        datum = parts[0] if parts else ""
        misto = parts[1].strip() if len(parts) > 1 else ""

        teams_text = teams_div.get_text(strip=True)
        domaci, _, hoste = teams_text.partition(" - ")

        link = score_div.find("a")
        if link:
            classes = link.get("class") or []
            games.append({
                "kolo": kolo,
                "domaci": domaci.strip(),
                "hoste": hoste.strip(),
                "datum": datum,
                "misto": misto,
                "odehrano": True,
                "cas": None,
                "vysledek": link.get_text(strip=True),
                "vyhra": "win" in classes,
                "prohra": "loss" in classes,
            })
        else:
            cas_text = score_div.get_text(strip=True)
            games.append({
                "kolo": kolo,
                "domaci": domaci.strip(),
                "hoste": hoste.strip(),
                "datum": datum,
                "misto": misto,
                "odehrano": False,
                "cas": cas_text or None,
                "vysledek": None,
                "vyhra": False,
                "prohra": False,
            })
    return games


def load_schedule_watch() -> dict:
    if SCHEDULE_WATCH_FILE.exists():
        return json.loads(SCHEDULE_WATCH_FILE.read_text(encoding="utf-8"))
    return {}


def save_schedule_watch(data: dict) -> None:
    SCHEDULE_WATCH_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_schedule_changes(old: dict, games: list) -> list:
    """
    Porovná dosud NEODEHRANÉ zápasy s posledně uloženým termínem/místem
    a nahlásí, pokud se něco změnilo (datum, čas, nebo místo). Odehrané
    zápasy se přeskakují — jejich termín se zpětně nemění. První běh
    (žádný předchozí záznam pro dané kolo) nic nehlásí, jen založí stav.
    """
    changes = []
    for g in games:
        if g["odehrano"]:
            continue
        prev = old.get(str(g["kolo"]))
        if prev is None or prev.get("odehrano"):
            continue
        rozdily = []
        if prev.get("datum") != g["datum"]:
            rozdily.append(f'datum {prev.get("datum") or "?"} → {g["datum"]}')
        if prev.get("cas") != g["cas"]:
            rozdily.append(f'čas {prev.get("cas") or "neuveden"} → {g["cas"] or "neuveden"}')
        if prev.get("misto") != g["misto"]:
            rozdily.append(f'místo {prev.get("misto") or "?"} → {g["misto"]}')
        if rozdily:
            soupeř = g["hoste"] if g["domaci"] == CLUB_NAME else g["domaci"]
            changes.append(f'⏰ {g["kolo"]}. kolo ({soupeř}): ' + ", ".join(rozdily))
    return changes


def build_next_match(games: list) -> dict | None:
    """Nejbližší dosud neodehraný zápas (podle nejnižšího čísla kola)."""
    upcoming = [g for g in games if not g["odehrano"]]
    if not upcoming:
        return None
    g = min(upcoming, key=lambda x: x["kolo"])
    doma = g["domaci"] == CLUB_NAME
    return {
        "kolo": g["kolo"],
        "soupeř": g["hoste"] if doma else g["domaci"],
        "doma": doma,
        "datum": g["datum"],
        "cas": g["cas"],
        "misto": g["misto"],
    }


def build_home_away_split(games: list) -> dict:
    """Bilance zvlášť pro domácí a venkovní zápasy (jen odehrané)."""
    played = [g for g in games if g["odehrano"]]

    def wl(lst: list) -> dict:
        return {
            "z": len(lst),
            "v": sum(1 for g in lst if g["vyhra"]),
            "p": sum(1 for g in lst if g["prohra"]),
        }

    return {
        "doma": wl([g for g in played if g["domaci"] == CLUB_NAME]),
        "venku": wl([g for g in played if g["domaci"] != CLUB_NAME]),
    }


def _bodu_za_zapas(vysledek: str | None, vyhra: bool, prohra: bool) -> int:
    """
    Skutečný bodový systém extraligy: výhra v základní hrací době = 3,
    výhra po prodloužení/nájezdech = 2, prohra po prodloužení/nájezdech
    = 1, prohra v základní hrací době = 0. Prodloužení/nájezdy pozná
    podle "p"/"pp" za skóre (např. "2:3p", "2:3pp"), tak jak to značí
    přímo hcmotor.cz.
    """
    if not vysledek:
        return 0
    prodlouzeni = bool(re.search(r"p|sn|n", vysledek))
    if vyhra:
        return 2 if prodlouzeni else 3
    if prohra:
        return 1 if prodlouzeni else 0
    return 0


def build_league_points(games: list) -> int:
    return sum(
        _bodu_za_zapas(g["vysledek"], g["vyhra"], g["prohra"])
        for g in games
        if g["odehrano"]
    )


def build_streaks(games: list) -> dict:
    """
    Aktuální série od posledního odehraného zápasu zpátky: kolikrát v
    řadě Motor vyhrál/prohrál, a kolikrát v řadě hrál doma/venku.
    """
    played = sorted((g for g in games if g["odehrano"]), key=lambda g: g["kolo"], reverse=True)

    vysledek_typ, vysledek_pocet = None, 0
    for g in played:
        typ = "výher" if g["vyhra"] else ("proher" if g["prohra"] else None)
        if typ is None:
            break
        if vysledek_typ is None:
            vysledek_typ = typ
        if typ != vysledek_typ:
            break
        vysledek_pocet += 1

    misto_typ, misto_pocet = None, 0
    for g in played:
        typ = "doma" if g["domaci"] == CLUB_NAME else "venku"
        if misto_typ is None:
            misto_typ = typ
        if typ != misto_typ:
            break
        misto_pocet += 1

    return {
        "vysledek_typ": vysledek_typ,
        "vysledek_pocet": vysledek_pocet,
        "misto_typ": misto_typ,
        "misto_pocet": misto_pocet,
    }


def load_schedule_log() -> list:
    if SCHEDULE_LOG_FILE.exists():
        return json.loads(SCHEDULE_LOG_FILE.read_text(encoding="utf-8"))
    return []


def save_schedule_log(log: list) -> None:
    SCHEDULE_LOG_FILE.write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_schedule_log(log: list, schedule_changes: list) -> list:
    """
    Na rozdíl od 7denní historie se tenhle log NEOŘEZÁVÁ — drží se celou
    sezónu, ať je vidět celoroční přehled, kdy a jak se termíny měnily.
    Nové změny se přidávají s dnešním datem; když skript proběhne
    víckrát za den, prostě se přidají další řádky (nic se nepřepisuje).
    """
    if not schedule_changes:
        return log
    today = datetime.now(ZoneInfo("Europe/Prague")).strftime("%Y-%m-%d")
    log = list(log)
    for c in schedule_changes:
        log.append({"datum": today, "zmena": c})
    return log


def update_schedule_watch(old: dict, games: list) -> dict:
    new = dict(old)
    for g in games:
        new[str(g["kolo"])] = {
            "datum": g["datum"],
            "cas": g["cas"],
            "misto": g["misto"],
            "odehrano": g["odehrano"],
        }
    return new


def build_record_svg(games: list) -> str:
    """
    Graf průběžné bilance Motoru: výhra +1, prohra -1 (jakýmkoliv
    způsobem, i po prodloužení/nájezdech), kumulativně od 1. do
    SEASON_ROUNDS kola. Nehraná kola zatím do grafu nepřidávají bod —
    graf se tak den po dni "dokresluje", jak přibývají odehrané zápasy.

    Barvy bere z CSS proměnných stránky (--pos, --neg…), takže funguje
    ve světlém i tmavém režimu. Úseky nahoru zeleně, dolů červeně, plocha
    mezi linkou a nulou zeleně nad nulou a červeně pod ní; mřížka vodorovná; data bodů jsou v data-pts pro tooltip (JS).
    """
    played = sorted((g for g in games if g["odehrano"]), key=lambda g: g["kolo"])
    if not played:
        return ""

    total = 0
    pts = [(0, 0, "Start sezóny")]
    for g in played:
        if g["vyhra"]:
            total += 1
        elif g["prohra"]:
            total -= 1
        doma = g["domaci"] == CLUB_NAME
        souper = g["hoste"] if doma else g["domaci"]
        pts.append((g["kolo"], total,
                    f'{g["kolo"]}. kolo: {souper} ({"doma" if doma else "venku"}) {g.get("vysledek") or ""}'.strip()))

    width, height = 760, 300
    pad_l, pad_r, pad_t, pad_b = 42, 18, 18, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    x_max = ((SEASON_ROUNDS + 9) // 10) * 10  # zaokrouhlit nahoru na desítku (52 -> 60)
    values = [v for _, v, _ in pts]
    y_step = 2
    y_min = (min(0, min(values)) // y_step) * y_step - y_step
    y_max = -(-(max(0, max(values))) // y_step) * y_step + y_step

    def x_for(kolo) -> float:
        return pad_l + kolo / x_max * plot_w

    def y_for(val) -> float:
        return pad_t + (y_max - val) / (y_max - y_min) * plot_h

    bottom = height - pad_b
    grid = "".join(
        f'<line class="{"g-zero" if t == 0 else "g-grid"}" x1="{pad_l}" y1="{y_for(t):.1f}" '
        f'x2="{width - pad_r}" y2="{y_for(t):.1f}"/>'
        f'<text class="g-axis" x="{pad_l - 8}" y="{y_for(t) + 4:.1f}" text-anchor="end">'
        f'{"+" if t > 0 else ""}{t}</text>'
        for t in range(y_min, y_max + 1, y_step)
    )
    xlabels = "".join(
        f'<text class="g-axis" x="{x_for(t):.1f}" y="{bottom + 18}" text-anchor="middle">{t}</text>'
        for t in range(0, x_max + 1, 10)
    )
    line = " ".join(f"{x_for(k):.1f},{y_for(v):.1f}" for k, v, _ in pts)
    y0 = y_for(0)
    area = (f"M{x_for(pts[0][0]):.1f},{y0:.1f} L" + line.replace(" ", " L")
            + f" L{x_for(pts[-1][0]):.1f},{y0:.1f} Z")
    segs = "".join(
        f'<line class="g-line {"g-up" if b[1] > a[1] else "g-down" if b[1] < a[1] else ""}" '
        f'x1="{x_for(a[0]):.1f}" y1="{y_for(a[1]):.1f}" x2="{x_for(b[0]):.1f}" y2="{y_for(b[1]):.1f}"/>'
        for a, b in zip(pts, pts[1:])
    )
    lk, lv, _ = pts[-1]
    data = json.dumps([[round(x_for(k), 1), round(y_for(v), 1), v, lab] for k, v, lab in pts],
                      ensure_ascii=False).replace("'", "&#39;")

    return f"""
    <div class="chart" data-w="{width}" data-pts='{data}'>
      <svg viewBox="0 0 {width} {height}" role="img"
           aria-label="Průběžná bilance výher a proher HC Motor, aktuálně {lv:+d} po {lk}. kole">
        <defs>
          <clipPath id="g-clip-up"><rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{y0 - pad_t:.1f}"/></clipPath>
          <clipPath id="g-clip-down"><rect x="{pad_l}" y="{y0:.1f}" width="{plot_w}" height="{bottom - y0:.1f}"/></clipPath>
        </defs>
        {grid}{xlabels}
        <path class="g-fill-up" d="{area}" clip-path="url(#g-clip-up)"/>
        <path class="g-fill-down" d="{area}" clip-path="url(#g-clip-down)"/>
        {segs}
        <circle class="g-end {"up" if lv > 0 else "down" if lv < 0 else ""}" cx="{x_for(lk):.1f}" cy="{y_for(lv):.1f}" r="4.5"/>
        <g class="g-hover" visibility="hidden">
          <line class="g-cross" x1="0" y1="{pad_t}" x2="0" y2="{bottom}"/>
          <circle class="g-end" cx="0" cy="0" r="4.5"/>
        </g>
        <rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" fill="transparent" class="g-hit"/>
      </svg>
      <div class="chart-tip" hidden></div>
    </div>
"""


# --- Oficiální zápis o utkání (hokejovyzapis.cz / hokej.cz) ---
#
# hokej.cz má u klubu rozpis zápasů, kde každý řádek nese
# data-href="/zapas/<ID>" — a tohle ID je STEJNÉ jako parametr
# hokejczId v adrese oficiálního zápisu:
#   https://hokejovyzapis.cz/pdf/print/cs-html/?hokejczId=<ID>
#
# Struktura zápisu je trochu zvláštní: tabulka "tab-team" má jeden
# řádek na jednoho hráče soupisky (č., jméno, pozice), ale sloupce
# gólů (čas/S/A1/A2/situace) a trestů (čas/č./min/důvod/od/do) v TÉŽE
# tabulce NEJSOU vázané na hráče z toho řádku — jsou to dva samostatné
# chronologické seznamy (góly týmu, tresty týmu), které se do řádků
# soupisky jen "naskládaly" kvůli tisku. Střelec/nahrávač/trestaný
# hráč se identifikují číslem dresu, které se pak dohledá zpátky v
# soupisce té samé tabulky.
HOKEJCZ_SCHEDULE_URL = "https://www.hokej.cz/klub/banes-motor-c-budejovice/1721/zapasy"
HOKEJCZ_IDS_FILE = SCRIPT_DIR / "hokejcz_zapasy.json"  # ID zápasů dodaná stahovátkem (hokej.cz blokuje GitHub)
HOKEJOVYZAPIS_URL_TMPL = "https://hokejovyzapis.cz/pdf/print/cs-html/?hokejczId={id}"
ZAPIS_STATE_FILE = SCRIPT_DIR / "zapis_state.json"
ZAPIS_GAMES_SHOWN = 5  # kolik posledních zápasů se zobrazuje v záložce Zápas
ZAPIS_VERZE = 8  # 8 = oficiální zkratky trestů, 2 = hráči na ledě, 3 = nejlepší hráči, 4 = soupiska/třetiny/nájezdy/rozhodčí, 5 = pozice hráčů, 6 = sestavy, 7 = hra bez brankáře
ZAPIS_MAX_PER_RUN = 80  # strop stažených zápisů za jeden běh (zpětné doplnění)
LINEUPS_JSON = DOCS_DIR / "sestavy-data.json"  # data pro docs/sestavy.html

# Zkratky přestupků podle oficiálních Pravidel 2018–2022 (zápis o utkání).
# Neznámý kód se zobrazí tak, jak je.
OFFENCE_CODES = {
    "BBB": "nedovolené blokování branky nebo hromadění sněhu",
    "BHL": "brankář u hráčské lavice v přerušené hře",
    "BKH": "bodnutí koncem hole",
    "BPS": "upuštění puku brankářem na vnější síť branky",
    "BSC": "brankář za střední čárou",
    "BSH": "bodnutí špičkou hole",
    "BTK": "bitka",
    "DRZH": "držení hole",
    "DRZP": "držení",
    "FHP": "funkcionář týmu na hrací ploše",
    "FIP": "nafilmovaný pád / přehrávání",
    "HAK": "hákování",
    "HELM": "hraní bez helmy",
    "HOZ": "hození hole / předmětu",
    "HRUB": "hrubost",
    "KOL": "faul kolenem",
    "KOP": "kopnutí",
    "KOUS": "kousnutí",
    "KROS": "krosček",
    "LOK": "faul loktem",
    "NAP": "napadení",
    "NARZ": "naražení zezadu",
    "NBR": "nedovolené bránění",
    "NBRB": "nedovolené bránění brankáři",
    "NESP": "nesportovní chování",
    "NHUL": "nedovolená hůl nebo měření hole",
    "NROZ": "napadání rozhodčích",
    "NTL": "nesprávný příchod nebo odchod z trestné lavice",
    "NVYS": "nedovolená nebo nebezpečná výstroj",
    "NZT": "nedovolený zásah tělem (v ženském hokeji)",
    "OBB": "opuštění brankoviště v průběhu šarvátky",
    "OHL": "opuštění hráčské lavice",
    "OTL": "opuštění trestné lavice",
    "OZH": "odmítnutí zahájit hru",
    "PDK": "podkopnutí",
    "PDOH": "pozdní dohrání",
    "PLIV": "plivnutí",
    "PMH": "příliš mnoho hráčů",
    "PODR": "podrážení",
    "POSH": "posunutí hole",
    "PPB": "přikrytí puku brankářem",
    "SEK": "sekání",
    "SPR": "sevření puku rukou",
    "STH": "porušení postupu při střídání hráčů",
    "TAH": "tahání za vlasy, helmu, mřížku",
    "UHL": "úder hlavou",
    "VRAZ": "vražení na hrazení",
    "VSM": "vysmívání",
    "VYSH": "vysoká hůl",
    "ZAN": "zásah do nohou",
    "ZH": "zdržování hry",
    "ZHOG": "zdržování hry – oslava gólu",
    "ZHPB": "zdržování hry – posunutí branky",
    "ZHPN": "zdržování hry – pozdní nástup",
    "ZHPP": "zdržování hry – padnutí na puk",
    "ZHPV": "zdržování hry – porušení postupu vhazování",
    "ZHUV": "zdržování hry – úprava výstroje",
    "ZHVP": "zdržování hry – vystřelení nebo vyhození puku mimo hřiště",
    "ZHZP": "zdržování hry – zašlapování puku",
    "ZHZU": "zdržování hry – po zakázaném uvolnění",
    "ZHK": "zásah do oblasti hlavy a krku",
    "ZHOL": "zraněný hráč odmítající opustit led",
    "ZLH": "zlomená hůl",
    "ZPD": "zásah proti divákům",
}


def fetch_hokejcz_matches() -> list:
    """
    Rozparsuje rozpis zápasů klubu na hokej.cz — pro každý zápas vrátí
    {"id": str, "den": int, "mesic": int, "domaci": str, "hoste": str}.
    Používá se k dohledání hokejczId pro konkrétní kolo (podle data a
    jmen týmů), protože hcmotor.cz samo žádné takové ID nemá.
    """
    try:
        soup = fetch(HOKEJCZ_SCHEDULE_URL)
    except Exception as exc:
        if HOKEJCZ_IDS_FILE.exists():
            matches = json.loads(HOKEJCZ_IDS_FILE.read_text(encoding="utf-8"))
            print(f"Rozpis na hokej.cz nedostupný ({exc}); používám uložená ID zápasů ({len(matches)}).")
            return matches
        raise
    matches = []
    for row in soup.select("tr.js-preview__link[data-href]"):
        href = row.get("data-href", "")
        m = re.search(r"/zapas/(\d+)", href)
        if not m:
            continue
        match_id = m.group(1)

        names = row.select("span.preview__name--long")
        if len(names) < 2:
            continue
        domaci = names[0].get_text(strip=True)
        hoste = names[1].get_text(strip=True)

        date_text = row.get_text(" ", strip=True)
        dm = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.", date_text)
        if not dm:
            continue
        den, mesic = int(dm.group(1)), int(dm.group(2))

        matches.append({"id": match_id, "den": den, "mesic": mesic, "domaci": domaci, "hoste": hoste})
    return matches


def find_hokejcz_id(game: dict, hokejcz_matches: list) -> str | None:
    """Najde hokejczId pro dané kolo (dict z parse_schedule_page) podle
    data. Jména týmů se záměrně neporovnávají — hokej.cz a hcmotor.cz
    pro stejný klub často používají jiný název (sponzorské jméno vs.
    tradiční), zatímco HOKEJCZ_SCHEDULE_URL je už sám o sobě rozpis
    JEN Motoru, takže shoda v datu je dost (Motor nehraje dva zápasy
    týž den). Vrací None, pokud se nic nenajde."""
    dm = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.", game.get("datum", ""))
    if not dm:
        return None
    den, mesic = int(dm.group(1)), int(dm.group(2))

    for m in hokejcz_matches:
        if m["den"] == den and m["mesic"] == mesic:
            return m["id"]
    return None


def _zapis_time_to_seconds(t: str) -> int:
    mm, _, ss = t.partition(":")
    try:
        return int(mm) * 60 + int(ss)
    except ValueError:
        return 0


def _norm_name(name: str) -> str:
    """'KLOUČEK Milan' -> 'Klouček Milan' (stejný tvar jako na hcmotor.cz).
    Příjmení je v zápisu psané velkými písmeny a jde první."""
    out, surname = [], True
    for tok in name.split():
        if surname and tok.isupper():
            out.append("-".join(p.capitalize() for p in tok.split("-")))
        else:
            surname = False
            out.append(tok)
    return " ".join(out)


def _parse_zapis_team_table(table) -> dict:
    """Rozparsuje jednu tabulku 'tab-team' (jeden tým) ze zápisu.
    Vrátí {"nazev", "soupiska": {cislo: (jmeno, post)}, "goly", "tresty"}.
    U gólů jsou zatím jen čísla hráčů na ledě (_p = vlastní tým,
    _n = soupeř) — na jména je převede až fetch_zapis, protože _n patří
    do soupisky druhého týmu."""
    header = table.select_one("td.team_name")
    nazev = header.get_text(" ", strip=True) if header else ""
    nazev = re.sub(r"\s+\d+\s*$", "", nazev).strip()  # pryč s číslem oddílu na konci

    rows = table.select("tr.values")

    roster = {}
    nastoupili = []
    poradi = []  # soupiska v pořadí zápisu (= po formacích) pro docs/sestavy.html
    for r in rows:
        no = _text(r.select_one("td.value_no"))
        attended = r.select_one("td.value_name")
        name = attended or r.select_one("td.value_name_not_attended")
        if no and name:
            roster[no] = (_norm_name(_text(name)), _text(r.select_one("td.value_pos")))
            if attended:
                nastoupili.append(roster[no][0])
            poradi.append({"c": no, "jmeno": _text(name), "post": roster[no][1], "hral": bool(attended)})

    def rn(no):
        return roster[no][0] if no in roster else f"č. {no}"

    goly = []
    tresty = []
    for r in rows:
        time_tds = r.select("td.value_time")
        goal_time = _text(time_tds[0]) if len(time_tds) > 0 else ""
        scorer_no = _text(r.select_one("td.value_g"))
        if goal_time and scorer_no:
            a1_no = _text(r.select_one("td.value_a1"))
            a2_no = _text(r.select_one("td.value_a2"))
            goly.append({
                "cas": goal_time,
                "vteriny": _zapis_time_to_seconds(goal_time),
                "tym": nazev,
                "strelec": rn(scorer_no),
                "asistence": [rn(n) for n in (a1_no, a2_no) if n],
                "situace": _text(r.select_one("td.value_gs")),
                "_p": [_text(r.select_one(f"td.value_p{k}")) for k in range(1, 7)],
                "_n": [_text(r.select_one(f"td.value_n{k}")) for k in range(1, 7)],
            })

        offence = _text(r.select_one("td.value_offence"))
        start = _text(r.select_one("td.value_start"))
        if offence and start:
            player_no = _text(r.select_one("td.value_no2"))
            end = _text(r.select_one("td.value_end"))
            minuty = _text(r.select_one("td.value_min"))
            if player_no == "HL":
                hrac = "lavička (HL)"
            else:
                hrac = rn(player_no) if player_no else "?"
            tresty.append({
                "cas": start,
                "vteriny": _zapis_time_to_seconds(start),
                "tym": nazev,
                "hrac": hrac,
                "min": minuty,
                "duvod_kod": offence,
                "duvod": OFFENCE_CODES.get(offence, offence),
                "od": start,
                "do": end,
            })

    return {"nazev": nazev, "soupiska": roster, "nastoupili": nastoupili, "poradi": poradi,
            "goly": goly, "tresty": tresty}


def _resolve_on_ice(goly: list, own: dict, opp: dict) -> None:
    """Přepíše čísla na ledě (_p/_n) na jména; brankáři se vynechají
    (na ledě je počítat nechceme, +/- i GF/GA se vedou za hráče v poli)."""
    for g in goly:
        g["na_ledu_za"] = [own[n][0] for n in g.pop("_p") if n in own and own[n][1] != "GK"]
        g["na_ledu_proti"] = [opp[n][0] for n in g.pop("_n") if n in opp and opp[n][1] != "GK"]


def _parse_best_players(soup) -> dict:
    """Nejlepší hráči utkání ze zápisu: řádek s buňkami
    'Nejlepší hráč utkání tým - A' | jméno | '... tým - B' | jméno.
    Hledá se podle textu buňky, ne podle CSS tříd. Vrací {"A": jméno,
    "B": jméno} ve tvaru ze zápisu (Jméno Příjmení); chybějící strana
    se vynechá."""
    out = {}
    for td in soup.find_all(["td", "th"]):
        label = td.get_text(" ", strip=True)
        m = re.search(r"nejlepší hráč utkání.*?-\s*([AB])\s*$", label, re.I)
        if not m:
            continue
        nxt = td.find_next_sibling(["td", "th"])
        name = nxt.get_text(" ", strip=True) if nxt else ""
        if name and "nejlepší" not in name.lower():
            out[m.group(1).upper()] = name
    return out


def _direct_cells(tr) -> list:
    return [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"], recursive=False)]


def _rows_after(header_tr) -> list:
    """Řádky téže tabulky za řádkem hlavičky (i když hlavička leží v
    <thead> a data v <tbody>). Vnořené tabulky se ignorují."""
    table = header_tr.find_parent("table")
    rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
    idx = rows.index(header_tr)
    return [_direct_cells(tr) for tr in rows[idx + 1:]]


def _score_pair(t: str):
    m = re.match(r"\s*(\d+)\s*:\s*(\d+)", t or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _parse_periods(soup) -> list:
    """Tabulka 'Souhrn utkání' (Třetina | GÓLY A:B | Střely A:B | Tresty
    A:B | ...). Vrací [{"tretina": "1"/"2"/"3"/"P"/"SN", "goly": [a,b],
    "strely": [a,b]}] jen pro třetiny, kde něco je."""
    for tr in soup.find_all("tr"):
        cells = _direct_cells(tr)
        if not cells or cells[0].lower() != "třetina":
            continue
        out = []
        for row in _rows_after(tr):
            if not row or row[0] not in ("1", "2", "3", "P", "SN"):
                continue
            g = _score_pair(row[1]) if len(row) > 1 else None
            st = _score_pair(row[2]) if len(row) > 2 else None
            if g or st:
                out.append({"tretina": row[0], "goly": list(g or (0, 0)),
                            "strely": list(st or (0, 0))})
        return out
    return []


def _parse_shootout_raw(soup) -> list:
    """Surové řádky tabulky 'Samostatné nájezdy' (hlavička A|B|BA|BB|A:B,
    opakovaná 4×). Vrací seznam nájezdových kol [[A, B, BA, BB, A:B]],
    po skupinách sloupců (1.–5. kolo v první skupině atd.), prázdná
    kola vynechá."""
    for tr in soup.find_all("tr"):
        cells = _direct_cells(tr)
        if len(cells) < 5 or cells[:5] != ["A", "B", "BA", "BB", "A:B"]:
            continue
        rows = _rows_after(tr)
        groups = len(cells) // 5
        kola = []
        for gi in range(groups):
            for row in rows:
                chunk = row[gi * 5:(gi + 1) * 5]
                if len(chunk) == 5 and any(chunk[:2]):
                    kola.append(chunk)
        return kola
    return []


def _build_shootout(raw: list, domaci: dict, hoste: dict) -> list:
    """Převede surová kola nájezdů na pokusy. Předpoklad: A:B je průběžný
    stav nájezdů po kole — gól se pozná podle toho, o kolik se zvedlo
    skóre dané strany. A/B = číslo střelce domácích/hostí, BA/BB =
    číslo brankáře domácích/hostí."""
    def nm(roster, no):
        return roster[no][0] if no in roster else (f"č. {no}" if no else "")

    pokusy, prev = [], (0, 0)
    for i, (a, b, ba, bb, ab) in enumerate(raw, 1):
        sc = _score_pair(ab) or prev
        if a:
            pokusy.append({"kolo_n": i, "tym": domaci["nazev"], "strelec": nm(domaci["soupiska"], a),
                           "brankar": nm(hoste["soupiska"], bb), "brankar_tym": hoste["nazev"],
                           "gol": sc[0] > prev[0]})
        if b:
            pokusy.append({"kolo_n": i, "tym": hoste["nazev"], "strelec": nm(hoste["soupiska"], b),
                           "brankar": nm(domaci["soupiska"], ba), "brankar_tym": domaci["nazev"],
                           "gol": sc[1] > prev[1]})
        prev = sc
    return pokusy


def _parse_referees(soup) -> dict:
    """{"hlavni": [jména], "carovi": [jména]} z bloku 'Rozhodčí, delegát,
    oficiality' — buňka má na prvním řádku funkci, na druhém jméno."""
    out = {"hlavni": [], "carovi": []}
    for td in soup.find_all("td"):
        lines = [l.strip() for l in td.get_text("\n", strip=True).split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        role = lines[0].lower()
        key = "hlavni" if role == "hlavní rozhodčí" else "carovi" if role == "čárový rozhodčí" else None
        if key and lines[1] not in out[key] and not lines[1].lower().startswith("potvrdil"):
            out[key].append(lines[1])
    return out


def _parse_goalie_changes(soup) -> dict:
    """Tabulka 'Střídání brankářů' (čas | BA | BB) -> {"A": [{"c", "od"}],
    "B": [...]}: kdo chytal od kdy. '--' (hra bez brankáře) se přeskočí,
    takže návrat téhož gólmana do brány se nepočítá jako střídání."""
    for tr in soup.find_all("tr"):
        if _direct_cells(tr)[:3] != ["čas", "BA", "BB"]:
            continue
        out = {"A": [], "B": []}
        for row in _rows_after(tr):
            if len(row) < 3 or not re.match(r"\d+:\d\d$", row[0]):
                continue
            for side, no in (("A", row[1]), ("B", row[2])):
                if no and no.isdigit() and (not out[side] or out[side][-1]["c"] != no):
                    out[side].append({"c": no, "od": row[0]})
        if out["A"] or out["B"]:
            return out
    return {"A": [], "B": []}


def _parse_empty_net(soup) -> dict:
    """Úseky hry bez brankáře z tabulky 'Střídání brankářů': řádek s '--'
    znamená, že tým odvolal gólmana; úsek končí dalším řádkem téže strany
    (návrat brankáře) nebo koncem zápasu. Vrací {"A": [[od_s, do_s], ...],
    "B": [...]} ve vteřinách hry (do_s = None, když se brankář nevrátil)."""
    for tr in soup.find_all("tr"):
        if _direct_cells(tr)[:3] != ["čas", "BA", "BB"]:
            continue
        out, otevrene = {"A": [], "B": []}, {"A": None, "B": None}
        nalezeno = False
        for row in _rows_after(tr):
            if len(row) < 3 or not re.match(r"\d+:\d\d$", row[0]):
                continue
            nalezeno = True
            mm, ss = row[0].split(":")
            sec = int(mm) * 60 + int(ss)
            for side, no in (("A", row[1]), ("B", row[2])):
                prazdno = bool(no) and not no.isdigit()
                if prazdno and otevrene[side] is None:
                    otevrene[side] = sec
                elif not prazdno and no and otevrene[side] is not None:
                    out[side].append([otevrene[side], sec])
                    otevrene[side] = None
        for side in ("A", "B"):
            if otevrene[side] is not None:
                out[side].append([otevrene[side], None])
        if nalezeno:
            return out
    return {"A": [], "B": []}


def _parse_bench(soup) -> dict:
    """'Osoby na hráčské lavici' -> {"A": [{"jmeno", "funkce"}], "B": [...]}.
    První tabulka je domácích, druhá hostů; jméno je ve tvaru Jméno Příjmení."""
    out, sides = {"A": [], "B": []}, iter(("A", "B"))
    for tr in soup.find_all("tr"):
        if _direct_cells(tr)[:2] != ["Příjmení, jméno", "Funkce"]:
            continue
        side = next(sides, None)
        if not side:
            break
        for row in _rows_after(tr):
            if len(row) >= 2 and row[0] and row[1]:
                out[side].append({"jmeno": row[0], "funkce": row[1]})
    return out


def _match_roster_name(name: str, roster: dict) -> str:
    """'Milan Klouček' -> 'Klouček Milan' podle soupisky (porovnává se
    množina slov bez ohledu na pořadí a velikost písmen). Když se nenajde,
    vrátí jméno prohozené na tvar Příjmení Jméno."""
    key = sorted(name.lower().split())
    for jm, _post in roster.values():
        if sorted(jm.lower().split()) == key:
            return jm
    parts = name.split()
    return " ".join(parts[-1:] + parts[:-1]) if len(parts) > 1 else name


def fetch_zapis(hokejcz_id: str) -> dict | None:
    """Stáhne a rozparsuje oficiální zápis o utkání. Vrací None, pokud
    zápis ještě není k dispozici / nejde rozparsovat (např. zápas se
    ještě nehrál)."""
    soup = fetch(HOKEJOVYZAPIS_URL_TMPL.format(id=hokejcz_id))
    tables = soup.select("table.tab-team")
    if len(tables) < 2:
        return None

    domaci = _parse_zapis_team_table(tables[0])
    hoste = _parse_zapis_team_table(tables[1])

    datum = _text(soup.select_one("td.value_date"))
    zacatek = _text(soup.select_one("td.value_start"))
    konec = _text(soup.select_one("td.value_end"))
    divaci = _text(soup.select_one("td.value_spectators"))
    misto = _text(soup.select_one("td.value_venue"))

    if not konec:
        # Zápas ještě neskončil (nebo zápis není kompletní) — nemá
        # smysl ho zpracovávat jako odehraný.
        return None

    best = _parse_best_players(soup)
    najezdy_raw = _parse_shootout_raw(soup)
    _resolve_on_ice(domaci["goly"], domaci["soupiska"], hoste["soupiska"])
    _resolve_on_ice(hoste["goly"], hoste["soupiska"], domaci["soupiska"])
    goly = sorted(domaci["goly"] + hoste["goly"], key=lambda g: g["vteriny"])
    tresty = sorted(domaci["tresty"] + hoste["tresty"], key=lambda t: t["vteriny"])

    skore_domaci = sum(1 for g in goly if g["tym"] == domaci["nazev"])
    skore_hoste = sum(1 for g in goly if g["tym"] == hoste["nazev"])

    return {
        "verze": ZAPIS_VERZE,
        "hokejcz_id": hokejcz_id,
        "domaci": domaci["nazev"],
        "hoste": hoste["nazev"],
        "skore_domaci": skore_domaci,
        "skore_hoste": skore_hoste,
        "datum": datum,
        "zacatek": zacatek,
        "konec": konec,
        "divaci": divaci,
        "misto": misto,
        "goly": goly,
        "tresty": tresty,
        "nejlepsi": {
            strana: {"tym": t["nazev"], "hrac": _match_roster_name(jm, t["soupiska"])}
            for strana, t, jm in (
                (s, t, best.get(s))
                for s, t in (("A", domaci), ("B", hoste))
            )
            if jm
        },
        "nastoupili": {"domaci": domaci["nastoupili"], "hoste": hoste["nastoupili"]},
        "pozice": {"domaci": {jm: post for jm, post in domaci["soupiska"].values()},
                   "hoste": {jm: post for jm, post in hoste["soupiska"].values()}},
        "tretiny": _parse_periods(soup),
        "najezdy_raw": najezdy_raw,
        "najezdy": _build_shootout(najezdy_raw, domaci, hoste),
        "rozhodci": _parse_referees(soup),
        "sestava": _lineup_payload(soup, domaci, hoste),
        "bez_brankare": _parse_empty_net(soup),
    }


def fetch_sestava_predem(hokejcz_id: str) -> dict | None:
    """Sestavy ze zápisu ještě PŘED zápasem (kluby je do zápisu vyplňují
    hodiny předem). Stejný tvar jako zapis["sestava"], ale bez gólů a
    trestů. Vrací None, pokud zápis nemá tabulky týmů nebo v nich zatím
    není žádný nastoupivší hráč."""
    soup = fetch(HOKEJOVYZAPIS_URL_TMPL.format(id=hokejcz_id))
    tables = soup.select("table.tab-team")
    if len(tables) < 2:
        return None
    domaci = _parse_zapis_team_table(tables[0])
    hoste = _parse_zapis_team_table(tables[1])
    hrali = [sum(1 for p in t["poradi"] if p["hral"]) for t in (domaci, hoste)]
    print(f"Sestavy předem {hokejcz_id}: {domaci['nazev']} {hrali[0]} hráčů, {hoste['nazev']} {hrali[1]} hráčů.")
    if not any(hrali):
        return None
    return _lineup_payload(soup, domaci, hoste)


def _lineup_payload(soup, domaci: dict, hoste: dict) -> dict:
    """Surová data sestav pro docs/sestavy.html (formátování řeší stránka)."""
    gch, bench = _parse_goalie_changes(soup), _parse_bench(soup)
    return {
        side: {"nazev": t["nazev"], "hraci": t["poradi"], "brankari": gch[side], "lavicka": bench[side]}
        for side, t in (("A", domaci), ("B", hoste))
    }


def _report_payload(z: dict) -> dict:
    """Údaje pro textový zápis utkání na docs/sestavy.html (branky, tresty,
    rozhodčí, diváci, střely, nájezdy) — jen to, co stránka potřebuje."""
    return {
        "goly": [{k: g.get(k) for k in ("cas", "vteriny", "tym", "strelec", "asistence", "situace",
                                        "na_ledu_za", "na_ledu_proti")}
                 for g in z.get("goly", [])],
        "tresty": [{k: t.get(k) for k in ("cas", "vteriny", "tym", "hrac", "min", "od", "do", "duvod")}
                   for t in z.get("tresty", [])],
        "nejlepsi": z.get("nejlepsi") or {},
        "bez_brankare": z.get("bez_brankare") or {},
        "datum": z.get("datum") or "",
        "rozhodci": z.get("rozhodci") or {},
        "divaci": z.get("divaci") or "",
        "tretiny": z.get("tretiny") or [],
        "najezdy": [{k: p.get(k) for k in ("kolo_n", "tym", "strelec", "gol")}
                    for p in z.get("najezdy") or []],
    }


def write_lineups_json(games: list, zapis_state: dict) -> None:
    """docs/sestavy-data.json: všechna kola Motoru (i budoucí) s hokejczId,
    u odehraných i se sestavou ze zápisu. Stránka sestavy.html si z toho
    nabídne výběr kola. Nesmí shodit běh."""
    try:
        try:
            hk = fetch_hokejcz_matches()
        except Exception as exc:
            print(f"Sestavy: rozpis na hokej.cz nedostupný ({exc}), ID zápasů chybí.")
            hk = []
        zk = {z["kolo"]: z for z in zapis_state.get("zapasy", [])}
        predem = {}  # sestavy neodehraných kol stažené před zápasem (scripts/sestavy_predem.py)
        try:
            for p in json.loads(LINEUPS_JSON.read_text(encoding="utf-8")).get("zapasy", []):
                if p.get("sestava") and not p.get("odehrano"):
                    predem[p["kolo"]] = (p["sestava"], p.get("sestava_cas"))
        except Exception:
            pass
        out = []
        for g in sorted(games, key=lambda g: g["kolo"]):
            z = zk.get(g["kolo"]) or {}
            out.append({
                "kolo": g["kolo"],
                "datum": g.get("datum", ""),
                "domaci": g.get("domaci", ""),
                "hoste": g.get("hoste", ""),
                "odehrano": bool(g.get("odehrano")),
                "cas": g.get("cas") or "",
                "vysledek": g.get("vysledek") or "",
                "hokejcz_id": z.get("hokejcz_id") or find_hokejcz_id(g, hk),
                "sestava": z.get("sestava") or (predem.get(g["kolo"]) or (None, None))[0],
                "sestava_cas": None if z.get("sestava") else (predem.get(g["kolo"]) or (None, None))[1],
                "zapis": _report_payload(z) if z.get("sestava") else None,
            })
        LINEUPS_JSON.write_text(json.dumps(
            {"aktualizovano": datetime.now(ZoneInfo("Europe/Prague")).strftime("%d.%m.%Y %H:%M"), "zapasy": out,
             "kariera": load_baseline()},  # výchozí stav kariér pro milníky v reportáži
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Sestavy: zapsáno {len(out)} kol, se sestavou {sum(1 for x in out if x['sestava'])}.")
    except Exception as exc:
        print(f"Varování: data sestav se nepodařilo zapsat ({exc}).")


def load_zapis_state() -> dict:
    if ZAPIS_STATE_FILE.exists():
        return json.loads(ZAPIS_STATE_FILE.read_text(encoding="utf-8"))
    return {"zpracovana_kola": [], "zapasy": []}


def save_zapis_state(state: dict) -> None:
    ZAPIS_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def update_zapis_state(state: dict, games: list) -> dict:
    """Stáhne oficiální zápisy ke VŠEM odehraným kolům, která ještě nemáme
    ve aktuální verzi (ZAPIS_VERZE) — tzn. i zpětné doplnění celé dosavadní
    sezóny a přepsání starých záznamů bez dat o hráčích na ledě. Rozpis na
    hokej.cz se stahuje jednou na běh. Chyby (web nedostupný, zápis ještě
    není kompletní, změna struktury) se potichu přeskočí — tahle funkce
    nikdy nesmí shodit celý běh statistik."""
    zapasy = {z["kolo"]: z for z in state.get("zapasy", [])}
    chybi = sorted(
        (g for g in games if g.get("odehrano")
         and zapasy.get(g["kolo"], {}).get("verze") != ZAPIS_VERZE),
        key=lambda g: g["kolo"],
    )
    if not chybi:
        return state
    try:
        hokejcz_matches = fetch_hokejcz_matches()
    except Exception as exc:
        print(f"Varování: nepodařilo se načíst rozpis na hokej.cz ({exc}).")
        return state

    stazeno = 0
    for game in chybi[:ZAPIS_MAX_PER_RUN]:
        try:
            hokejcz_id = find_hokejcz_id(game, hokejcz_matches)
            if not hokejcz_id:
                print(f"Zápis: nepodařilo se dohledat hokejczId pro {game['kolo']}. kolo.")
                continue
            zapis = fetch_zapis(hokejcz_id)
            if not zapis:
                print(f"Zápis pro {game['kolo']}. kolo zatím není kompletní, zkusím příště.")
                continue
            zapis["kolo"] = game["kolo"]
            if zapis.get("najezdy_raw"):
                # kontrolní výpis pro ověření formátu tabulky nájezdů
                print(f"Nájezdy {game['kolo']}. kolo (A|B|BA|BB|A:B): {zapis['najezdy_raw']}")
            zapasy[game["kolo"]] = zapis
            stazeno += 1
            time.sleep(0.5)
        except Exception as exc:  # jeden vadný zápis nesmí zastavit ostatní
            print(f"Varování: zápis {game['kolo']}. kola se nepodařilo zpracovat ({exc}).")
    state["zapasy"] = [zapasy[k] for k in sorted(zapasy)]
    state["zpracovana_kola"] = sorted(zapasy)
    print(f"Zápisy: staženo {stazeno}, celkem uloženo {len(zapasy)}.")
    return state


def _is_motor(team: str) -> bool:
    return CLUB_NAME.lower() in team.lower()


def _penalty_incidents(tresty: list) -> list:
    """Spojí navazující tresty téhož hráče za totéž provinění (např. 5 min
    + 20 min ZHK, kdy druhý začíná přesně tam, kde první končí) do jednoho
    incidentu — počítá se pak jako jeden přestupek, minuty se sečtou."""
    out = []
    for t in sorted(tresty, key=lambda x: x["vteriny"]):
        prev = out[-1] if out else None
        if (prev and prev["tym"] == t["tym"] and prev["hrac"] == t["hrac"]
                and prev["duvod_kod"] == t["duvod_kod"] and prev["do"] == t["od"]):
            prev["min"] = int(prev["min"] or 0) + int(t["min"] or 0)
            prev["do"] = t["do"]
        else:
            out.append({**t, "min": int(t["min"]) if str(t["min"]).isdigit() else 0})
    return out


def build_best_players(zapasy: list) -> list:
    """Kolikrát byl který hráč Motoru vyhlášen nejlepším hráčem utkání.
    [{'jmeno', 'pocet', 'kola': [..]}] seřazené podle počtu."""
    acc = {}
    for z in zapasy:
        for v in (z.get("nejlepsi") or {}).values():
            if _is_motor(v["tym"]):
                e = acc.setdefault(v["hrac"], {"jmeno": v["hrac"], "pocet": 0, "kola": []})
                e["pocet"] += 1
                e["kola"].append(z["kolo"])
    return sorted(acc.values(), key=lambda e: (-e["pocet"], e["jmeno"]))


def _best_line(z: dict) -> str:
    """Krátký text 'Motor: X · soupeř: Y' pro jeden zápas (Motor první)."""
    nb = list((z.get("nejlepsi") or {}).values())
    nb.sort(key=lambda v: not _is_motor(v["tym"]))
    return " · ".join(
        f'{"Motor" if _is_motor(v["tym"]) else "soupeř"}: {v["hrac"]}' for v in nb
    )


def _motor_side(z: dict) -> str:
    return "domaci" if _is_motor(z["domaci"]) else "hoste"


def _game_by_kolo(games: list) -> dict:
    return {g["kolo"]: g for g in games or []}


def _result_type(game: dict | None) -> str | None:
    """'V' výhra v základní době, 'VP' výhra po prodl./SN, 'PP' prohra
    po prodl./SN, 'P' prohra v základní době, None = neznámo."""
    if not game or not game.get("odehrano"):
        return None
    pr = bool(re.search(r"p|sn|n", game.get("vysledek") or ""))
    if game.get("vyhra"):
        return "VP" if pr else "V"
    if game.get("prohra"):
        return "PP" if pr else "P"
    return None


def _game_goals(z: dict) -> list:
    """Góly ze hry (bez případného rozhodujícího nájezdu, kdyby ho zápis
    vedl jako gól s časem 65:00 a víc)."""
    if z.get("najezdy"):
        return [g for g in z["goly"] if g["vteriny"] < 3900]
    return list(z["goly"])


def _period_of(sec: int) -> str:
    return "1" if sec < 1200 else "2" if sec < 2400 else "3" if sec < 3600 else "P"


def build_absences(zapasy: list) -> dict:
    """Kdo z Motoru chyběl na soupisce. Kádr pro dané kolo = hráči, kteří
    už v sezóně aspoň jednou nastoupili (do toho kola včetně) — posila tak
    před debutem nechybí. Vrací {"po_kolech": {kolo: [jména]},
    "hraci": {jmeno: {"nastoupil", "chybel", "serie"}}, "navraty":
    {kolo: [(jmeno, kolik)]}} — serie = kolik posledních zápasů v řadě
    chybí, navraty = kdo se v tom kole vrátil po absenci."""
    zz = sorted((z for z in zapasy if z.get("nastoupili")), key=lambda z: z["kolo"])
    seen, po_kolech, hraci, navraty, run = [], {}, {}, {}, {}
    for z in zz:
        hrali = z["nastoupili"][_motor_side(z)]
        for h in hrali:
            if h not in seen:
                seen.append(h)
        chybi = sorted(h for h in seen if h not in hrali)
        po_kolech[z["kolo"]] = chybi
        for h in seen:
            e = hraci.setdefault(h, {"nastoupil": 0, "chybel": 0, "serie": 0})
            if h in hrali:
                if run.get(h):
                    navraty.setdefault(z["kolo"], []).append((h, run[h]))
                run[h] = 0
                e["nastoupil"] += 1
            else:
                run[h] = run.get(h, 0) + 1
                e["chybel"] += 1
            e["serie"] = run[h]
    return {"po_kolech": po_kolech, "hraci": hraci, "navraty": navraty}


def build_gwg(zapasy: list, games: list) -> list:
    """Vítězné góly a první góly zápasu hráčů Motoru.
    [{'jmeno', 'gwg', 'gwg_kola', 'prvni', 'prvni_kola'}]"""
    gk = _game_by_kolo(games)
    acc = {}

    def e(jm):
        return acc.setdefault(jm, {"jmeno": jm, "gwg": 0, "gwg_kola": [], "prvni": 0, "prvni_kola": []})

    for z in zapasy:
        goly = sorted(_game_goals(z), key=lambda g: g["vteriny"])
        if goly and _is_motor(goly[0]["tym"]):
            x = e(goly[0]["strelec"]); x["prvni"] += 1; x["prvni_kola"].append(z["kolo"])
        if not (gk.get(z["kolo"]) or {}).get("vyhra"):
            continue
        mine = [g for g in goly if _is_motor(g["tym"])]
        opp = len(goly) - len(mine)
        if len(mine) > opp:  # při nerozhodném stavu rozhodly nájezdy → bez GWG
            x = e(mine[opp]["strelec"]); x["gwg"] += 1; x["gwg_kola"].append(z["kolo"])
    return sorted(acc.values(), key=lambda r: (-r["gwg"], -r["prvni"], r["jmeno"]))


def build_assist_pairs(zapasy: list) -> dict:
    """Spolupráce u gólů Motoru (ze zápisů).
    'dvojice': [{'nahravac','strelec','n','prim','kola'}] — kolikrát nahrávač
      asistoval střelci (prim = z toho jako první asistence),
    'trojice': [{'hraci': (3 jména), 'n', 'kola'}] — gól, u kterého byli
      všichni tři (střelec + obě asistence), bez ohledu na role."""
    dv, tr = {}, {}
    for z in zapasy:
        for g in _game_goals(z):
            if not _is_motor(g["tym"]):
                continue
            for i, a in enumerate(g.get("asistence") or []):
                e = dv.setdefault((a, g["strelec"]), {"nahravac": a, "strelec": g["strelec"],
                                                      "n": 0, "prim": 0, "kola": []})
                e["n"] += 1
                e["prim"] += i == 0
                e["kola"].append(z["kolo"])
            if len(g.get("asistence") or []) == 2:
                key = tuple(sorted([g["strelec"], *g["asistence"]]))
                e = tr.setdefault(key, {"hraci": key, "n": 0, "kola": []})
                e["n"] += 1
                e["kola"].append(z["kolo"])
    return {
        "dvojice": sorted(dv.values(), key=lambda e: (-e["n"], -e["prim"], e["strelec"])),
        "trojice": sorted(tr.values(), key=lambda e: (-e["n"], e["hraci"])),
    }


def _goal_strength(g: dict, motor_gol: bool) -> str:
    """'ev' / 'pp' / 'sh' z pohledu Motoru podle situace '5/4' apod."""
    m = re.match(r"(\d+)/(\d+)", g.get("situace", ""))
    if not m:
        return "ev"
    a, b = int(m.group(1)), int(m.group(2))
    if a == b:
        return "ev"
    return ("pp" if a > b else "sh") if motor_gol else ("sh" if a > b else "pp")


def build_formations(zapasy: list) -> dict:
    """Formace Motoru na ledě při gólech (ze zápisů, brankáři se nepočítají).
    Obranná dvojice = přesně 2 obránci na ledě, útočná trojice = přesně
    3 útočníci, pětka = 2 obránci + 3 útočníci. Jiné složení (přesilovka
    4F+1D, hra bez brankáře) se do dané kategorie nezapočítá.
    Každá položka: {'hraci', 'gf', 'ga', 'gf_ev', 'ga_ev', 'gf_pp', 'ga_sh', 'kola'}"""
    out = {"dvojice": {}, "trojice": {}, "petky": {}}
    zapasu = 0
    for z in zapasy:
        poz = (z.get("pozice") or {}).get(_motor_side(z))
        if not poz:
            continue
        zapasu += 1
        for g in _game_goals(z):
            if "na_ledu_za" not in g:
                continue
            motor_gol = _is_motor(g["tym"])
            hraci = g["na_ledu_za"] if motor_gol else g["na_ledu_proti"]
            d = sorted(h for h in hraci if poz.get(h) == "D")
            f = sorted(h for h in hraci if poz.get(h) == "F")
            typ = _goal_strength(g, motor_gol)
            keys = []
            if len(d) == 2:
                keys.append(("dvojice", tuple(d)))
            if len(f) == 3:
                keys.append(("trojice", tuple(f)))
            if len(d) == 2 and len(f) == 3:
                keys.append(("petky", tuple(d) + tuple(f)))
            for kat, key in keys:
                e = out[kat].setdefault(key, {"hraci": key, "gf": 0, "ga": 0, "gf_ev": 0, "ga_ev": 0,
                                              "gf_pp": 0, "ga_sh": 0, "kola": set()})
                if motor_gol:
                    e["gf"] += 1
                    e["gf_ev"] += typ == "ev"
                    e["gf_pp"] += typ == "pp"
                else:
                    e["ga"] += 1
                    e["ga_ev"] += typ == "ev"
                    e["ga_sh"] += typ == "sh"
                e["kola"].add(z["kolo"])
    srt = lambda d: sorted(d.values(), key=lambda e: (-(e["gf"] + e["ga"]), -(e["gf"] - e["ga"]), e["hraci"]))
    return {k: srt(v) for k, v in out.items()} | {"zapasu": zapasu}


def build_periods(zapasy: list, games: list, kde: str | None = None) -> dict:
    """Bilance Motoru po třetinách (výhra/remíza/prohra třetiny, góly
    pro/proti, střely pro/proti) + výsledek podle stavu po 1. a 2. třetině.
    kde = "domaci" / "hoste" omezí výpočet na domácí / venkovní zápasy."""
    if kde:
        zapasy = [z for z in zapasy if _motor_side(z) == kde]
    gk = _game_by_kolo(games)
    per = {t: {"v": 0, "r": 0, "p": 0, "gf": 0, "ga": 0, "sf": 0, "sa": 0, "z": 0, "zs": 0}
           for t in ("1", "2", "3", "P")}
    stav = {k: {s: {"z": 0, "V": 0, "VP": 0, "PP": 0, "P": 0} for s in ("vedl", "remiza", "prohraval")}
            for k in ("1", "2")}
    for z in zapasy:
        motor_a = _motor_side(z) == "domaci"
        gf = {t: 0 for t in per}; ga = {t: 0 for t in per}
        for g in _game_goals(z):
            t = _period_of(g["vteriny"])
            (gf if _is_motor(g["tym"]) else ga)[t] += 1
        for t in ("1", "2", "3"):
            e = per[t]; e["z"] += 1; e["gf"] += gf[t]; e["ga"] += ga[t]
            e["v" if gf[t] > ga[t] else "p" if gf[t] < ga[t] else "r"] += 1
        hral_p = any(r["tretina"] == "P" for r in z.get("tretiny", [])) or gf["P"] + ga["P"] > 0 \
            or _result_type(gk.get(z["kolo"])) in ("VP", "PP")
        if hral_p:
            e = per["P"]; e["z"] += 1; e["gf"] += gf["P"]; e["ga"] += ga["P"]
            e["v" if gf["P"] > ga["P"] else "p" if gf["P"] < ga["P"] else "r"] += 1
        for r in z.get("tretiny", []):
            if r["tretina"] in per:
                a, b = r["strely"]
                e = per[r["tretina"]]; e["zs"] += 1
                e["sf"] += a if motor_a else b
                e["sa"] += b if motor_a else a
        res = _result_type(gk.get(z["kolo"]))
        if res:
            for k, lim in (("1", ("1",)), ("2", ("1", "2"))):
                d = sum(gf[t] for t in lim) - sum(ga[t] for t in lim)
                s = stav[k]["vedl" if d > 0 else "prohraval" if d < 0 else "remiza"]
                s["z"] += 1; s[res] += 1
    return {"tretiny": per, "stav": stav}


def build_comebacks(zapasy: list, games: list, kde: str | None = None) -> dict:
    """Otáčení zápasů podle průběhu skóre v ŘÁDNÉ hrací době (do 60:00,
    rozhodující nájezd ani prodloužení do průběhu nepatří).
    Z každého zápisu se z časů gólů složí rozdíl skóre z pohledu Motoru
    a zjistí se, jestli Motor někdy prohrával / vedl (o 1+ a o 2+ góly).
    Konečný výsledek (V/VP/PP/P) se bere z rozpisu zápasů.
    Vrací {"proh1": {...}, "proh2": {...}, "ved1": {...}, "ved2": {...}} —
    v každém z, V, VP, PP, P (počty zápasů podle výsledku)."""
    if kde:
        zapasy = [z for z in zapasy if _motor_side(z) == kde]
    gk = _game_by_kolo(games)
    out = {k: {"z": 0, "V": 0, "VP": 0, "PP": 0, "P": 0} for k in ("proh1", "proh2", "ved1", "ved2")}
    for z in zapasy:
        res = _result_type(gk.get(z["kolo"]))
        if not res:
            continue
        d = lo = hi = 0
        for g in sorted(_game_goals(z), key=lambda g: g["vteriny"]):
            if g["vteriny"] >= 3600:
                break
            d += 1 if _is_motor(g["tym"]) else -1
            lo, hi = min(lo, d), max(hi, d)
        for key, ok in (("proh1", lo <= -1), ("proh2", lo <= -2), ("ved1", hi >= 1), ("ved2", hi >= 2)):
            if ok:
                out[key]["z"] += 1
                out[key][res] += 1
    return out


def build_shootouts(zapasy: list, games: list) -> dict:
    """Nájezdy v sezóně: střelci Motoru, brankáři Motoru, zápasy."""
    gk = _game_by_kolo(games)
    strelci, brankari, zapasy_sn = {}, {}, []
    for z in zapasy:
        pokusy = z.get("najezdy") or []
        if not pokusy:
            continue
        g = gk.get(z["kolo"]) or {}
        souper = z["hoste"] if _motor_side(z) == "domaci" else z["domaci"]
        motor_pokusy = []
        for p in pokusy:
            if _is_motor(p["tym"]):
                e = strelci.setdefault(p["strelec"], {"pokusy": 0, "goly": 0})
                e["pokusy"] += 1; e["goly"] += p["gol"]
                motor_pokusy.append(f'{p["strelec"]} {"✅" if p["gol"] else "❌"}')
            elif p["brankar"]:
                e = brankari.setdefault(p["brankar"], {"najezdy": 0, "zakroky": 0})
                e["najezdy"] += 1; e["zakroky"] += not p["gol"]
        zapasy_sn.append({"kolo": z["kolo"], "souper": souper, "vyhra": bool(g.get("vyhra")),
                          "motor": motor_pokusy})
    return {"strelci": strelci, "brankari": brankari, "zapasy": sorted(zapasy_sn, key=lambda x: -x["kolo"])}


def build_referees(zapasy: list, games: list) -> list:
    """Souhrn rozhodčích v zápasech Motoru: počet, bilance, tresty na zápas."""
    gk = _game_by_kolo(games)
    acc = {}
    for z in zapasy:
        rz = z.get("rozhodci") or {}
        res = _result_type(gk.get(z["kolo"]))
        inc = _penalty_incidents(z["tresty"])
        tm_m = sum(t["min"] for t in inc if _is_motor(t["tym"]))
        tm_s = sum(t["min"] for t in inc if not _is_motor(t["tym"]))
        for role, key in (("hlavní", "hlavni"), ("čárový", "carovi")):
            for jm in rz.get(key, []):
                e = acc.setdefault((jm, role), {"jmeno": jm, "role": role, "z": 0, "V": 0, "VP": 0,
                                                "PP": 0, "P": 0, "tm_m": 0, "tm_s": 0, "kola": []})
                e["z"] += 1; e["tm_m"] += tm_m; e["tm_s"] += tm_s; e["kola"].append(z["kolo"])
                if res:
                    e[res] += 1
    return sorted(acc.values(), key=lambda e: (e["role"] != "hlavní", -e["z"], e["jmeno"]))


def _fmt_n(n) -> str:
    """6318 -> '6 318' (pevná mezera)."""
    return f"{round(n):,}".replace(",", "\u00a0")


def _divaci_int(z: dict) -> int:
    d = re.sub(r"\D", "", str(z.get("divaci") or ""))
    return int(d) if d else 0


def build_attendance(zapasy: list) -> dict:
    """Návštěvnost: domácí a venkovní zápasy Motoru (jen se zadaným číslem)."""
    doma, venku = [], []
    for z in zapasy:
        n = _divaci_int(z)
        if not n:
            continue
        doma_z = _motor_side(z) == "domaci"
        souper = z["hoste"] if doma_z else z["domaci"]
        (doma if doma_z else venku).append({"kolo": z["kolo"], "souper": souper, "n": n,
                                             "datum": z.get("datum", "")})
    return {"doma": sorted(doma, key=lambda x: x["kolo"]), "venku": sorted(venku, key=lambda x: x["kolo"])}


def build_discipline(zapasy: list) -> dict:
    """{'hraci': {jmeno: {kod: {'n': počet, 'min': minuty}}},
        'tym': {'motor': {kod: {...}}, 'souper': {kod: {...}}}, 'zapasu': N}"""
    hraci, motor, souper = {}, {}, {}
    for z in zapasy:
        for t in _penalty_incidents(z["tresty"]):
            kod = t["duvod_kod"]
            bucket = motor if _is_motor(t["tym"]) else souper
            e = bucket.setdefault(kod, {"n": 0, "min": 0})
            e["n"] += 1
            e["min"] += t["min"]
            if _is_motor(t["tym"]) and t["hrac"] != "lavička (HL)":
                h = hraci.setdefault(t["hrac"], {}).setdefault(kod, {"n": 0, "min": 0})
                h["n"] += 1
                h["min"] += t["min"]
    return {"hraci": hraci, "tym": {"motor": motor, "souper": souper}, "zapasu": len(zapasy)}


def build_on_ice(zapasy: list) -> dict:
    """Gólů pro/proti, když byl hráč Motoru na ledě (bez brankářů).
    {jmeno: {'gf','ga','gf_ev','ga_ev','gf_pp','ga_pp','gf_sh','ga_sh'}}
    EV = stejný počet hráčů (situace a==b), PP = Motor v přesilovce,
    SH = Motor v oslabení. Gól s prázdnou klecí apod. se bere podle čísel
    ze zápisu, jak jsou."""
    out = {}
    for z in zapasy:
        for g in z["goly"]:
            if "na_ledu_za" not in g:
                continue  # záznam ve staré verzi — doplní se při dalším běhu
            motor_gol = _is_motor(g["tym"])
            hraci = g["na_ledu_za"] if motor_gol else g["na_ledu_proti"]
            m = re.match(r"(\d+)/(\d+)", g.get("situace", ""))
            if m:
                a, b = int(m.group(1)), int(m.group(2))  # střelecký tým / soupeř
                if a == b:
                    typ = "ev"
                elif a > b:
                    typ = "pp" if motor_gol else "sh"   # střelec v přesilovce
                else:
                    typ = "sh" if motor_gol else "pp"
            else:
                typ = "ev"
            for h in hraci:
                e = out.setdefault(h, {k: 0 for k in
                    ("gf", "ga", "gf_ev", "ga_ev", "gf_pp", "ga_pp", "gf_sh", "ga_sh")})
                d = "gf" if motor_gol else "ga"
                e[d] += 1
                e[f"{d}_{typ}"] += 1
    return out


PAGE_CSS = """
  /* ===== Písma (vlastní, bez volání cizích serverů) ===== */
  @font-face { font-family: "IBM Plex Sans"; font-weight: 400; font-style: normal; font-display: swap; src: url(fonts/ibm-plex-sans-latin-ext-400-normal.woff2) format("woff2"); unicode-range: U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF; }
  @font-face { font-family: "IBM Plex Sans"; font-weight: 400; font-style: normal; font-display: swap; src: url(fonts/ibm-plex-sans-latin-400-normal.woff2) format("woff2"); unicode-range: U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD; }
  @font-face { font-family: "IBM Plex Sans"; font-weight: 500; font-style: normal; font-display: swap; src: url(fonts/ibm-plex-sans-latin-ext-500-normal.woff2) format("woff2"); unicode-range: U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF; }
  @font-face { font-family: "IBM Plex Sans"; font-weight: 500; font-style: normal; font-display: swap; src: url(fonts/ibm-plex-sans-latin-500-normal.woff2) format("woff2"); unicode-range: U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD; }
  @font-face { font-family: "IBM Plex Sans"; font-weight: 600; font-style: normal; font-display: swap; src: url(fonts/ibm-plex-sans-latin-ext-600-normal.woff2) format("woff2"); unicode-range: U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF; }
  @font-face { font-family: "IBM Plex Sans"; font-weight: 600; font-style: normal; font-display: swap; src: url(fonts/ibm-plex-sans-latin-600-normal.woff2) format("woff2"); unicode-range: U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD; }

  /* ===== Tokeny: papír a tiskařská čerň; tmavý režim podle systému ===== */
  :root {
    --bg: #FFFFFF; --surface: #FFFFFF; --surface-2: #F3F4F6;
    --line: #E4E6EA; --line-strong: #C5C9CF;
    --text: #15181C; --text-2: #3F454D; --text-3: #6A717B;
    --accent: #1F5FA8; --accent-2: #6B4FA3; --pos: #1E7B3A; --neg: #C2352A; --warn: #A06A00; --hover: #F3F4F6;
    --f-head: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    --f-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    --f-mono: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    --tabbar-h: 46px;
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #121416; --surface: #121416; --surface-2: #1B1E22;
      --line: #2A2E34; --line-strong: #444A52;
      --text: #ECEEF0; --text-2: #C3C8CE; --text-3: #8F969F;
      --accent: #6EA8F0; --accent-2: #B39DE0; --pos: #4CC27A; --neg: #F0685D; --warn: #D9A441; --hover: #1B1E22;
      color-scheme: dark;
    }
  }

  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  @media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 400 14px/1.5 var(--f-body); font-variant-numeric: tabular-nums;
    -webkit-font-smoothing: antialiased; -webkit-tap-highlight-color: transparent;
  }
  a { color: inherit; text-decoration: none; border-bottom: 1px solid var(--line); transition: border-color .15s ease, color .15s ease; }
  a:hover { color: var(--accent); border-color: var(--accent); }
  p { margin: 8px 0; }
  .wrap { max-width: 1240px; margin: 0 auto; padding: 0 32px 96px; }

  /* ===== Hlavička: jeden tenký řádek ===== */
  .app-header { display: flex; justify-content: space-between; align-items: baseline; gap: 6px 28px; flex-wrap: wrap; padding: 18px 0 14px; }
  h1 { font: 600 19px/1.2 var(--f-head); margin: 0; display: inline; }
  .meta { display: inline; margin-left: 12px; color: var(--text-3); font-size: 13px; }
  .header-side { display: flex; gap: 4px 20px; align-items: baseline; flex-wrap: wrap; font-size: 13px; color: var(--text-3); }
  .header-side a { border-bottom-color: transparent; }
  .header-side a:hover { border-bottom-color: var(--accent); }
  .live { display: inline-flex; align-items: center; font-family: var(--f-mono); font-size: 12px; color: var(--text-2); }

  /* ===== Záložky: textové, podtržení aktivní ===== */
  .tabbar {
    position: sticky; top: 0; z-index: 30; display: flex; gap: 26px; overflow-x: auto;
    height: var(--tabbar-h); margin: 0 0 28px; padding: 0;
    background: var(--bg); border-bottom: 1px solid var(--line-strong);
  }
  .tab-btn {
    position: relative; display: inline-flex; align-items: center; gap: 7px; flex: none;
    padding: 0; border: 0; background: none; color: var(--text-3);
    font: 600 13px/1 var(--f-body); cursor: pointer; transition: color .15s ease;
  }
  .tab-btn svg { display: none; width: 20px; height: 20px; flex-shrink: 0; }
  .tab-btn::after { content: ""; position: absolute; left: 0; right: 0; bottom: -1px; height: 3px; background: var(--accent); transform: scaleX(0); transform-origin: left; transition: transform .2s ease; }
  .tab-btn:hover { color: var(--text); }
  .tab-btn.is-active { color: var(--text); }
  .tab-btn.is-active::after { transform: scaleX(1); }
  .tab-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
  .badge-dot { display: none; position: absolute; top: 12px; right: -9px; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
  .tab-btn.has-badge .badge-dot { display: block; }
  .tabsection.is-hidden { display: none; }

  /* ===== Mřížka: 12 sloupců, tabulky bez karet ===== */
  .bento { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); column-gap: 40px; row-gap: 8px; align-items: start; }
  .bento > * { grid-column: span 12; min-width: 0; }
  .card { padding: 18px 0 32px; border-top: 1px solid var(--line); scroll-margin-top: calc(var(--tabbar-h) + 18px); }
  .card h2 { font: 600 19px/1.2 var(--f-head); color: var(--text); margin: 0 0 4px; display: flex; align-items: center; gap: 10px; }
  .card h2 + p.muted.small { margin-top: 2px; }
  .muted { color: var(--text-3); margin: 0; }
  .small { font-size: 13px; margin: 8px 0 0; line-height: 1.5; }
  .card > p.small:not(.muted) { color: var(--text-2); }
  .section-title { font-size: 13px; font-weight: 600; color: var(--text-3); margin: 14px 0 -4px; }
  .scope-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px 40px; margin-top: 10px; }
  .scope-h { margin: 18px 0 0; font: 700 12px/1 var(--f-body); color: var(--text); }
  .scope-h::before { content: ""; display: inline-block; width: 8px; height: 8px; margin-right: 8px; background: var(--text); }
  .scope:nth-child(2) .scope-h::before { background: var(--accent); }
  .scope:nth-child(3) .scope-h::before { background: var(--text-3); }
  .sg-pos { color: var(--pos) !important; }
  .sg-neg { color: var(--neg) !important; }
  td.sgn-pos, td.sgn-pos strong, td.num.sgn-pos, td.num.sgn-pos strong { color: var(--pos); }
  td.sgn-neg, td.sgn-neg strong, td.num.sgn-neg, td.num.sgn-neg strong { color: var(--neg); }
  .tag { display: inline-block; padding: 1px 8px; border-radius: 3px; font-size: 12px; font-weight: 600; line-height: 1.5; }
  .tag-motor { color: var(--accent); background: color-mix(in oklab, var(--accent) 12%, transparent); }
  .tag-liga { color: var(--accent-2); background: color-mix(in oklab, var(--accent-2) 13%, transparent); }
  .section-title.sc-motor, .section-title.sc-liga { display: flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text); margin: 18px 0 -6px; }
  .section-title.sc-motor::before, .section-title.sc-liga::before { content: ""; width: 10px; height: 10px; background: var(--accent); }
  .section-title.sc-liga::before { background: var(--accent-2); }
  th.c-motor { color: var(--accent); }
  .info-btn {
    flex: none; width: 18px; height: 18px; padding: 0; border: 1px solid var(--text-3); border-radius: 50%;
    background: none; color: var(--text-3); font: italic 600 11px/1 var(--f-body); cursor: pointer; transition: all .15s ease;
  }
  .info-btn:hover, .info-btn[aria-expanded="true"] { color: var(--bg); background: var(--text); border-color: var(--text); }
  p.note { max-width: 62ch; }

  /* ===== Úvodní výsledek (Přehled) ===== */
  .hero { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 56px; padding: 4px 0 40px; }
  .hero-kicker { font: 500 13px/1.3 var(--f-body); color: var(--text-3); }
  .hero-score { display: flex; align-items: baseline; margin: 10px 0 0 -2px; font: 600 clamp(56px, 7vw, 88px)/.9 var(--f-head); font-variant-numeric: tabular-nums; }
  .hero-score i { font-style: normal; font-weight: 700; color: var(--text-3); margin: 0 .04em; position: relative; top: -.06em; }
  .hero.win .hero-score .m { color: var(--pos); }
  .hero.loss .hero-score .m { color: var(--neg); }
  .hero-teams { margin-top: 10px; font: 600 16px/1.3 var(--f-head); }
  .hero-teams span { color: var(--text-3); font-weight: 700; }
  .hero-teams b { color: var(--text); font-weight: 800; }
  .hero-res { margin-top: 6px; font-size: 13px; color: var(--text-2); }
  .hero-goals { list-style: none; margin: 14px 0 0; padding: 0; border-top: 1px solid var(--line); }
  .hero-goals li { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 4px 12px; align-items: baseline; padding: 9px 0 9px 12px; border-bottom: 1px solid var(--line); position: relative; }
  .hero-goals li::before { content: ""; position: absolute; left: 0; top: 10px; bottom: 10px; width: 3px; background: var(--line); }
  .hero-goals li.m::before { background: var(--pos); }
  .hero-goals li.o::before { background: var(--neg); opacity: .55; }
  .hero-goals .t { font: 400 13px var(--f-mono); color: var(--text-3); }
  .hero-goals .who { font-weight: 600; }
  .hero-goals li.o .who { font-weight: 500; color: var(--text-2); }
  .hero-goals .as { color: var(--text-3); font-size: 13px; margin-left: 8px; font-weight: 400; }
  .hero-foot { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px 32px; flex-wrap: wrap; margin-top: 22px; }
  .hero-stats { display: flex; gap: 26px; margin: 0; }
  .hero-stats div { min-width: 0; }
  .hero-stats dt { font: 600 12px/1.2 var(--f-body); color: var(--text-3); }
  .hero-stats dd { margin: 4px 0 0; font: 600 20px/1 var(--f-head); font-variant-numeric: tabular-nums; }
  .hero-stats dd small { font: 500 13px var(--f-body); color: var(--text-3); margin-left: 4px; }
  .form-sq { display: flex; gap: 5px; align-items: center; }
  .form-sq > b { font: 600 12px/1.2 var(--f-body); color: var(--text-3); margin-right: 6px; }
  .fsq { width: 16px; height: 16px; background: var(--text); }
  .fsq-V { background: var(--pos); }
  .fsq-VP { background: transparent; box-shadow: inset 0 0 0 2px var(--pos); }
  .fsq-PP { background: transparent; box-shadow: inset 0 0 0 2px var(--neg); }
  .fsq-P { background: var(--neg); }
  .nextline { display: grid; grid-template-columns: 130px minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, 1.6fr); gap: 6px 24px; align-items: baseline; padding: 16px 0 18px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); margin-bottom: 28px; }
  .nextline .lbl { font: 600 12px/1.2 var(--f-body); color: var(--accent); }
  .nextline .opp { font: 600 20px/1.2 var(--f-head); }
  .nextline .where, .nextline .when { color: var(--text-2); font-size: 13.5px; }

  /* ===== Rozcestník sekce (Sezóna, Bilance) ===== */
  .sec-index { display: none; }
  @media (min-width: 1100px) {
    .bento.has-index { grid-template-columns: 148px minmax(0, 1fr); column-gap: 44px; }
    .bento.has-index > .sec-index { display: block; grid-column: 1; position: sticky; top: calc(var(--tabbar-h) + 24px); align-self: start; }
    .bento.has-index > .sec-body { grid-column: 2; }
  }
  .sec-index ul { list-style: none; margin: 0; padding: 0; border-left: 1px solid var(--line); }
  .sec-index a { display: block; padding: 5px 0 5px 14px; margin-left: -1px; border: 0; border-left: 3px solid transparent; font-size: 13px; line-height: 1.3; color: var(--text-3); transition: color .15s ease, border-color .15s ease; }
  .sec-index a:hover { color: var(--text); }
  .sec-index a.is-on { color: var(--text); font-weight: 600; border-left-color: var(--accent); }

  /* ===== KPI (zbytek: bilance V/VP/PP/P, doma/venku) ===== */
  .kpi { display: flex; flex-direction: column; }
  .kpi h2 { font: 700 12px/1.2 var(--f-body); color: var(--text-3); }
  .kpi-num { font: 600 36px/1 var(--f-head); padding-top: 12px; font-variant-numeric: tabular-nums; }
  .kpi-num i { font-style: normal; color: var(--text-3); font-weight: 700; font-size: .62em; margin: 0 .14em; position: relative; top: -.1em; }
  .kpi-quad { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
  .kpi-quad .kpi-sub { margin-top: 6px; }
  .kpi-num-md { font-size: 32px; }
  .kpi-num-sm { font-size: 26px; padding-top: 6px; }
  .kpi-sub { color: var(--text-3); font-size: 13px; margin-top: 8px; display: flex; align-items: center; }
  .kpi-stack { gap: 28px; }
  .kpi-split { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }

  /* ===== Graf ===== */
  .chart { position: relative; margin-top: 18px; }
  .chart svg { display: block; width: 100%; height: auto; overflow: visible; touch-action: pan-y; }
  .g-grid, .g-zero, .g-line, .g-cross { vector-effect: non-scaling-stroke; }
  .g-grid { stroke: var(--line); stroke-width: 1; }
  .g-zero { stroke: var(--text-3); stroke-width: 1; stroke-dasharray: 3 4; }
  .g-axis { fill: var(--text-3); font-size: 11px; font-family: var(--f-mono); }
  .g-line { fill: none; stroke: var(--text-3); stroke-width: 2.25; stroke-linejoin: miter; stroke-linecap: butt; }
  .g-up { stroke: var(--pos); }
  .g-down { stroke: var(--neg); }
  .g-end { fill: var(--text); stroke: var(--bg); stroke-width: 2; }
  .g-end.up { fill: var(--pos); }
  .g-end.down { fill: var(--neg); }
  .g-halo { display: none; }
  .g-fill-up { fill: var(--pos); opacity: .16; }
  .g-fill-down { fill: var(--neg); opacity: .16; }
  .g-cross { stroke: var(--text); stroke-width: 1; }
  .chart-tip {
    position: absolute; top: 0; transform: translate(-50%, 0); pointer-events: none;
    background: var(--text); color: var(--bg); padding: 6px 10px; font-size: 12px; white-space: nowrap;
  }
  .chart-tip b { font: 700 14px var(--f-mono); margin-right: 8px; }

  /* ===== Tabulky ===== */
  table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 14px; margin-top: 10px; }
  th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  th {
    position: sticky; top: var(--tabbar-h); z-index: 2; background: var(--surface-2);
    color: var(--text-2); font: 600 12px/1.2 var(--f-body);
    padding-top: 9px; padding-bottom: 9px; border-bottom: 1px solid var(--line-strong);
  }
  th:first-child, td:first-child { padding-left: 4px; }
  th:last-child, td:last-child { padding-right: 4px; }
  tbody tr:last-child td { border-bottom: 0; }
  td:first-child { transition: padding-left .15s ease, box-shadow .15s ease; }
  tbody tr:hover td { background: var(--hover); }
  tbody tr:hover td:first-child { box-shadow: inset 2px 0 0 var(--accent); padding-left: 10px; }
  th.num, td.num { text-align: right; font-family: var(--f-mono); font-size: 13px; font-variant-numeric: tabular-nums; }
  th.num { font-size: 12px; }
  td.num { color: var(--text-2); }
  td strong { font-weight: 600; color: var(--text); }
  td.num strong { font-weight: 500; color: var(--text); }
  td:nth-child(2):not(.num), td:first-child:not(.num) { font-weight: 500; }
  tr.no-baseline td { color: var(--text-3); font-style: italic; }
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { color: var(--text); }
  th.sortable::after {
    content: ""; display: inline-block; margin-left: 5px; vertical-align: middle;
    border: 3.5px solid transparent; border-top-color: currentColor; opacity: 0; transform: translateY(2px);
  }
  th.sortable:hover::after { opacity: .5; }
  th.sort-desc { color: var(--text); }
  th.sort-asc { color: var(--text); }
  th.sort-desc::after { opacity: 1; border-top-color: var(--accent); }
  th.sort-asc::after { opacity: 1; border-top-color: transparent; border-bottom-color: var(--accent); transform: translateY(-2px); }
  .lbl-short { display: none; }
  a.bil { border: 0; margin-left: 6px; color: var(--text-3); font-size: .9em; }
  a.bil:hover { color: var(--accent); }
  .small.kv { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 12px; color: var(--text-2); margin: 6px 0 0; }
  .small.kv:first-of-type { margin-top: 6px; }
  .tbl-skaters, .tbl-goalkeepers { max-width: 780px; }
  .tbl-state td:first-child, .tbl-periods td:first-child, .tbl-form-5 td:first-child { white-space: normal; }
  .tbl-comeback tr.grp td { font-weight: 600; color: var(--text-2); background: var(--surface-2); padding-top: 6px; padding-bottom: 6px; }
  .tbl-comeback td:first-child { white-space: normal; }
  .tbl-comeback tbody tr.grp:hover td { background: var(--surface-2); box-shadow: none; padding-left: 4px; }
  .tbl-disc th, .tbl-disc td { padding-left: 4px; padding-right: 4px; }
  .tbl-disc th { }
  .tbl-form-5 td:first-child { min-width: 240px; }
  .scope .lbl-full { display: none; }
  .scope .lbl-short { display: inline; }
  .scope th, .scope td { padding-left: 5px; padding-right: 5px; }
  .scope td.num { font-size: 12px; }

  /* ===== Seznamy, časová osa, rozbalovací bloky ===== */
  .changes { list-style: none; margin: 8px 0 0; padding: 0; }
  .changes li { padding: 9px 0; border-bottom: 1px solid var(--line); color: var(--text-2); }
  .changes li:last-child { border-bottom: 0; }
  .changes li strong { color: var(--text); font-weight: 600; }
  .ev { display: grid; grid-template-columns: 50px 10px minmax(0, 1fr); align-items: baseline; gap: 10px; }
  .ev .dot { margin: 0; align-self: center; }
  .ev-t { color: var(--text-3); font: 400 13px var(--f-mono); }
  .ev-x { white-space: normal; }
  .ev-x .muted { font-size: 13px; margin-left: 6px; }
  details { border-bottom: 1px solid var(--line); }
  details:last-child { border-bottom: 0; }
  summary {
    cursor: pointer; list-style: none; padding: 13px 0; font-weight: 600; color: var(--text);
    display: grid; grid-template-columns: auto minmax(0, 1fr); column-gap: 10px; align-items: baseline; transition: color .15s ease;
  }
  summary:hover { color: var(--accent); }
  summary::-webkit-details-marker { display: none; }
  summary::before {
    content: ""; width: 6px; height: 6px; flex: none; position: relative; top: -2px;
    border-right: 2px solid currentColor; border-bottom: 2px solid currentColor;
    transform: rotate(-45deg); transition: transform .15s ease;
  }
  details[open] > summary::before { transform: rotate(45deg); }
  summary .muted.small { grid-column: 2; font-weight: 400; margin: 0; }
  details > :last-child { margin-bottom: 14px; }

  /* ===== Stavové tečky (bez záře) ===== */
  .dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex: none;
    background: var(--text-3); margin: 0 8px 1px 0; vertical-align: middle;
  }
  .dot-lg { width: 12px; height: 12px; margin: 0; }
  .dot-after { margin: 0 2px 1px 6px; }
  .dot-pos { background: var(--pos); }
  .dot-neg { background: var(--neg); }
  .dot-warn { background: var(--warn); }
  .dot-pos-ring { background: transparent; box-shadow: inset 0 0 0 2px var(--pos); }
  .dot-neg-ring { background: transparent; box-shadow: inset 0 0 0 2px var(--neg); }
  .dot-home { background: var(--accent); }
  .dot-ring { background: transparent; box-shadow: inset 0 0 0 1.5px var(--text-3); }

  /* ===== Vyhledávání ===== */
  .search-box {
    display: block; width: 100%; max-width: 420px; padding: 9px 2px; font: inherit; font-size: 15px; color: var(--text);
    background: none; border: 0; border-bottom: 1px solid var(--line-strong); border-radius: 0; margin-bottom: 16px;
  }
  .search-box::placeholder { color: var(--text-3); }
  .search-box:focus { outline: none; border-bottom-color: var(--accent); }
  tr.search-hidden, details.search-hidden, li.search-hidden { display: none; }
  .tabsection[data-tab="historie"] .card, .tabsection[data-tab="mesice"] .card { max-width: 780px; }
  .tabsection[data-tab="zapas"] .card { max-width: 900px; }

  /* ===== Potáhni-pro-obnovení, skeleton ===== */
  .pull-indicator {
    position: fixed; top: 0; left: 0; right: 0; z-index: 55; display: flex; align-items: center; justify-content: center;
    height: 46px; margin-top: -46px; color: var(--text-3); font-size: 13px;
    background: var(--bg); border-bottom: 1px solid var(--line); transition: margin-top .15s ease, color .15s ease;
  }
  .pull-indicator.is-ready { color: var(--accent); font-weight: 600; }
  .skeleton-overlay { position: fixed; inset: 0; z-index: 60; background: var(--bg); padding: 28px 32px; transition: opacity .2s ease; }
  .skeleton-overlay.is-hidden { opacity: 0; pointer-events: none; }
  .skeleton-block {
    background: linear-gradient(90deg, var(--surface-2) 25%, var(--line) 37%, var(--surface-2) 63%);
    background-size: 400% 100%; animation: skeleton-shimmer 1.4s ease infinite;
    margin: 0 auto 14px; max-width: 1176px;
  }
  @keyframes skeleton-shimmer { 0% { background-position: 100% 50%; } 100% { background-position: 0 50%; } }
  @media (prefers-reduced-motion: reduce) {
    .skeleton-block { animation: none; }
    summary::before, .tab-btn::after, td:first-child { transition: none; }
  }

  /* ===== Rozvržení podle šířky ===== */
  @media (min-width: 980px) {
    .bento > .card { grid-column: span 6; }
    .bento > .hero, .bento > .nextline,
    .bento > .card:has(.tbl-periods), .bento > .card:has(.tbl-state), .bento > .card:has(.tbl-comeback),
    .bento > .card:has(.tbl-skaters), .bento > .card:has(.tbl-goalkeepers),
    .bento > .card:has(.tbl-refs), .bento > .card:has(.tbl-so), .bento > .card:has(.tbl-gwg), .bento > .card:has(.tbl-pairs), .bento > .card:has(.tbl-disc), .bento > .card:has(.tbl-disc-team), .bento > .card:has(thead th:nth-child(6)) { grid-column: span 12; }
    .bento > .card:has(.tbl-milestones) { grid-column: span 8; }
    .bento > .card-changes { grid-column: span 4; }
    .scope-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .bento > .card-chart { grid-column: span 8; }
    .bento > .kpi-stack { grid-column: span 4; }
    .tabsection[data-tab="historie"] .card, .tabsection[data-tab="mesice"] .card, .tabsection[data-tab="zapas"] .card { grid-column: span 12; }
  }
  @media (max-width: 979px) {
    .hero { grid-template-columns: 1fr; gap: 28px; }
    .nextline { grid-template-columns: 1fr 1fr; }
    .nextline .lbl { grid-column: 1 / -1; }
  }

  /* ===== Mobil: obsah se posouvá, záložky dole ===== */
  @media (max-width: 640px) {
    html, body { height: 100%; touch-action: manipulation; }
    body { display: flex; flex-direction: column; height: 100vh; height: 100dvh; overflow: hidden; }
    .wrap { max-width: 100%; flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; padding: 0; }
    .app-header { order: 0; flex: 0 0 auto; padding: 12px 16px 10px; padding-top: calc(12px + env(safe-area-inset-top)); margin: 0; align-items: baseline; border-bottom: 1px solid var(--line-strong); }
    h1 { font-size: 17px; }
    .meta { display: block; margin: 2px 0 0; font-size: 12px; }
    .header-side { font-size: 12px; gap: 2px 14px; }
    .app-content {
      order: 1; flex: 1 1 auto; min-height: 0; overflow-y: auto; -webkit-overflow-scrolling: touch;
      padding: 8px 16px calc(28px + env(safe-area-inset-bottom));
    }
    .bento { column-gap: 0; }
    .card { padding: 12px 0 26px; overflow-x: auto; scroll-margin-top: 8px; }
    .card h2 { font-size: 17px; }
    th { position: static; }
    .hero { padding: 18px 0 26px; gap: 22px; border-top: 0; }
    .hero-score { font-size: 64px; margin-left: -2px; }
    .hero-stats { gap: 22px; }
    .hero-stats dd { font-size: 18px; }
    .nextline { grid-template-columns: 1fr; padding: 14px 0 16px; }
    .kpi-num { font-size: 32px; }
    .kpi-num-md { font-size: 28px; }
    .kpi-num-sm { font-size: 24px; }
    .kpi-split { gap: 16px; }
    .g-axis { font-size: 22px; }
    table { font-size: 13px; }
    th, td { padding: 9px 6px; }
    th { font-size: 11.5px; }
    .lbl-full { display: none; }
    .lbl-short { display: inline; }
    .hide-m { display: none; }
    .small.kv { grid-template-columns: 1fr; gap: 0; }
    .skeleton-overlay { padding: 18px 16px; }

    /* Hráči v poli: jméno + Z/G/A/B */
    .tbl-skaters th:nth-child(1), .tbl-skaters td:nth-child(1),
    .tbl-skaters th:nth-child(3), .tbl-skaters td:nth-child(3),
    .tbl-skaters th:nth-child(8), .tbl-skaters td:nth-child(8),
    .tbl-skaters th:nth-child(9), .tbl-skaters td:nth-child(9) { display: none; }
    /* Brankáři: jméno + Z / Úsp % / SO */
    .tbl-goalkeepers th:nth-child(1), .tbl-goalkeepers td:nth-child(1),
    .tbl-goalkeepers th:nth-child(4), .tbl-goalkeepers td:nth-child(4),
    .tbl-goalkeepers th:nth-child(5), .tbl-goalkeepers td:nth-child(5),
    .tbl-goalkeepers th:nth-child(6), .tbl-goalkeepers td:nth-child(6),
    .tbl-goalkeepers th:nth-child(7), .tbl-goalkeepers td:nth-child(7),
    .tbl-goalkeepers th:nth-child(8), .tbl-goalkeepers td:nth-child(8),
    .tbl-goalkeepers th:nth-child(11), .tbl-goalkeepers td:nth-child(11),
    .tbl-goalkeepers th:nth-child(12), .tbl-goalkeepers td:nth-child(12) { display: none; }

    .tabbar {
      order: 2; position: static; flex: 0 0 auto; height: auto; margin: 0; padding: 4px 4px calc(4px + env(safe-area-inset-bottom));
      gap: 0; overflow: visible; border-bottom: 0; border-top: 1px solid var(--line-strong);
    }
    .tab-btn { flex: 1; min-width: 0; flex-direction: column; gap: 3px; padding: 8px 2px 6px; font-size: 10px; }
    .tab-btn::after { display: none; }
    .tab-btn.is-active { color: var(--accent); }
    .tab-btn svg { display: block; }
    .tab-btn span { font-size: 10px; line-height: 1.1; white-space: nowrap; }
    .badge-dot { top: 5px; right: calc(50% - 15px); }
  }
"""


def render_html(
    new: dict,
    changes: list,
    baseline: dict,
    corrections: list | None = None,
    history: list | None = None,
    monthly: dict | None = None,
    schedule_changes: list | None = None,
    record_svg: str = "",
    schedule_log: list | None = None,
    next_match: dict | None = None,
    home_away: dict | None = None,
    league_points: int = 0,
    streaks: dict | None = None,
    zapis_games: list | None = None,
    games: list | None = None,
) -> str:
    now = datetime.now(ZoneInfo("Europe/Prague")).strftime("%d.%m.%Y %H:%M")

    skaters = sorted(
        new.get("skaters", {}).values(), key=lambda s: s["b"], reverse=True
    )
    goalkeepers = sorted(
        new.get("goalkeepers", {}).values(), key=lambda s: s["z"], reverse=True
    )

    def esc(s) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def lbl(full: str, short: str) -> str:
        return f'<span class="lbl-full">{full}</span><span class="lbl-short">{short}</span>'

    changes_html = (
        "<ul class='changes'>" + "".join(f"<li>{esc(c)}</li>" for c in changes) + "</ul>"
        if changes
        else "<p class='muted'>Od minulého běhu žádné změny.</p>"
    )

    corrections = corrections or []
    if corrections:
        corrections_html = f"""
  <div class="card">
    <h2>📝 Opravy statistik na hcmotor.cz</h2>
    <ul class="changes">{"".join(f"<li>{esc(c)}</li>" for c in corrections)}</ul>
    <p class="muted small">Hodnoty se změnily, aniž by přibyl odehraný zápas —
    typicky týdenní korekce dat na hcmotor.cz, ne nový zápas.</p>
  </div>
"""
    else:
        corrections_html = ""

    history = history or []
    if history:
        day_blocks = []
        for i, day in enumerate(history):
            try:
                date_label = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
            except ValueError:
                date_label = day["date"]
            items = list(day.get("changes", [])) + list(day.get("corrections", []))
            items_html = "".join(f"<li>{esc(c)}</li>" for c in items)
            day_blocks.append(f"""
    <details{" open" if i == 0 else ""}>
      <summary>{esc(date_label)} <span class="muted small">({len(items)})</span></summary>
      <ul class="changes">{items_html}</ul>
    </details>""")
        history_html = f"""
  <div class="card">
    <h2>🗓️ Historie posledních {HISTORY_DAYS} dní</h2>
    {"".join(day_blocks)}
  </div>
"""
    else:
        history_html = ""

    schedule_changes = schedule_changes or []
    if schedule_changes:
        schedule_html = f"""
  <div class="card">
    <h2>⏰ Změna termínu zápasu</h2>
    <ul class="changes">{"".join(f"<li>{esc(c)}</li>" for c in schedule_changes)}</ul>
  </div>
"""
    else:
        schedule_html = ""

    if next_match:
        nm = next_match
        cas_lbl = nm["cas"] if nm["cas"] else "čas bude upřesněn"
        next_match_html = f"""
  <div class="nextline">
    <span class="lbl">Příští zápas</span>
    <span class="opp">{esc(nm["soupeř"])}</span>
    <span class="where"><span class="dot {"dot-home" if nm["doma"] else "dot-ring"}"></span>{"Doma" if nm["doma"] else "Venku"}, {nm["kolo"]}. kolo</span>
    <span class="when">{esc(nm["datum"])}, {esc(cas_lbl)}, {esc(nm["misto"])}</span>
  </div>
"""
    else:
        next_match_html = ""

    schedule_log = schedule_log or []
    if schedule_log:
        log_rows = "".join(
            f"<li>{esc(e['datum'])}: {esc(e['zmena'])}</li>"
            for e in sorted(schedule_log, key=lambda e: e["datum"], reverse=True)
        )
        schedule_log_html = f"""
  <div class="card">
    <h2>📜 Historie změn termínů (celá sezóna)</h2>
    <ul class="changes">{log_rows}</ul>
  </div>
"""
    else:
        schedule_log_html = ""

    if record_svg:
        streaks = streaks or {}
        serie_bits = []
        if streaks.get("vysledek_pocet", 0) >= 2:
            serie_bits.append(f'{streaks["vysledek_pocet"]}× {streaks["vysledek_typ"]} v řadě')
        if streaks.get("misto_pocet", 0) >= 2:
            serie_bits.append(f'{streaks["misto_pocet"]}× {streaks["misto_typ"]} v řadě')
        serie_html = (
            f'<p class="muted small">Aktuální série: {", ".join(serie_bits)}</p>'
            if serie_bits else ""
        )
        record_html = f"""
  <div class="card card-chart">
    <h2>Bilance výher a proher</h2>
    <p class="muted small">Výhra +1, prohra −1 (jakýmkoliv způsobem), kumulativně od 1. kola.
    Body v tabulce (systém 3-2-1-0): <strong>{league_points}</strong></p>
    {record_svg}
    {serie_html}
  </div>
"""
    else:
        record_html = ""

    # --- KPI dlaždice (Přehled + Bilance)
    played_g = sorted((g for g in (games or []) if g.get("odehrano")), key=lambda g: g["kolo"])
    res_counts = {"V": 0, "VP": 0, "PP": 0, "P": 0}
    for g in played_g:
        rt = _result_type(g)
        if rt:
            res_counts[rt] += 1
    DOT_FOR = {"V": "dot-pos", "VP": "dot-pos-ring", "PP": "dot-neg-ring", "P": "dot-neg"}
    RES_WORD = {"V": "výhra", "VP": "výhra po prodl./SN", "PP": "prohra po prodl./SN", "P": "prohra"}

    def _opp(g):
        return g["hoste"] if g["domaci"] == CLUB_NAME else g["domaci"]

    form_dots = "".join(
        f'<span class="dot dot-lg {DOT_FOR.get(_result_type(g), "")}" '
        f'title="{g["kolo"]}. kolo: {esc(_opp(g))} {esc(g.get("vysledek") or "")} ({RES_WORD.get(_result_type(g), "")})"></span>'
        for g in played_g[-5:]
    )
    if played_g:
        streaks = streaks or {}
        s_n, s_t = streaks.get("vysledek_pocet", 0), streaks.get("vysledek_typ")
        ppg = f"{league_points / len(played_g):.2f}".replace(".", ",")
        kpi_points_html = f"""
  <div class="card kpi">
    <h2>Body v tabulce</h2>
    <div class="kpi-num">{league_points}</div>
    <div class="kpi-sub">{ppg} na zápas, {len(played_g)} odehraných</div>
  </div>
"""
        kpi_form_html = f"""
  <div class="card kpi kpi-form">
    <h2>Forma</h2>
    <div class="kpi-num">{s_n}×</div>
    <div class="kpi-sub">{esc(s_t or "")} v řadě</div>
    <div class="form-dots" aria-label="Posledních 5 zápasů">{form_dots}</div>
  </div>
"""
    else:
        kpi_points_html = kpi_form_html = ""

    home_away = home_away or {}
    if home_away and (home_away.get("doma", {}).get("z", 0) or home_away.get("venku", {}).get("z", 0)):
        d, v = home_away["doma"], home_away["venku"]
        home_away_html = f"""
  <div class="card kpi kpi-stack">
    <div>
      <h2>Bilance</h2>
      <div class="kpi-quad">
        <div><div class="kpi-num kpi-num-md">{res_counts["V"]}</div><div class="kpi-sub"><span class="dot dot-pos"></span>V</div></div>
        <div><div class="kpi-num kpi-num-md">{res_counts["VP"]}</div><div class="kpi-sub"><span class="dot dot-pos-ring"></span>VP</div></div>
        <div><div class="kpi-num kpi-num-md">{res_counts["PP"]}</div><div class="kpi-sub"><span class="dot dot-neg-ring"></span>PP</div></div>
        <div><div class="kpi-num kpi-num-md">{res_counts["P"]}</div><div class="kpi-sub"><span class="dot dot-neg"></span>P</div></div>
      </div>
    </div>
    <div class="kpi-split">
      <div><h2>Doma</h2><div class="kpi-num kpi-num-sm"><b class="sg-pos">{d["v"]}</b><i>–</i><b class="sg-neg">{d["p"]}</b></div><div class="kpi-sub">{d["z"]} zápasů</div></div>
      <div><h2>Venku</h2><div class="kpi-num kpi-num-sm"><b class="sg-pos">{v["v"]}</b><i>–</i><b class="sg-neg">{v["p"]}</b></div><div class="kpi-sub">{v["z"]} zápasů</div></div>
    </div>
  </div>
"""
    else:
        home_away_html = ""

    monthly = monthly or {}
    if monthly:
        month_keys = sorted(monthly.keys(), reverse=True)[:MONTHLY_MONTHS_SHOWN]
        month_blocks = []
        for i, mk in enumerate(month_keys):
            year, mon = mk.split("-")
            month_label = f"{MONTHS_CS.get(int(mon), mon)} {year}"
            m = monthly[mk]
            sk_rows = sorted(m.get("skaters", {}).items(), key=lambda kv: kv[1]["b"], reverse=True)
            gk_rows = sorted(m.get("goalkeepers", {}).items(), key=lambda kv: kv[1]["z"], reverse=True)
            sk_html = "".join(
                f"<tr><td>{esc(name)}</td><td>{v['z']}</td><td>{v['g']}</td>"
                f"<td>{v['a']}</td><td><strong>{v['b']}</strong></td></tr>"
                for name, v in sk_rows
            )
            gk_html = "".join(
                f"<tr><td>{esc(name)}</td><td>{v['z']}</td></tr>" for name, v in gk_rows
            )
            total_players = len(sk_rows) + len(gk_rows)
            month_blocks.append(f"""
    <details{" open" if i == 0 else ""}>
      <summary>{esc(month_label)} <span class="muted small">({total_players} hráčů)</span></summary>
      <table>
        <thead><tr><th>Hráč</th><th>Z</th><th>G</th><th>A</th><th>B</th></tr></thead>
        <tbody>{sk_html}</tbody>
      </table>
      <table>
        <thead><tr><th>Brankář</th><th>Z</th></tr></thead>
        <tbody>{gk_html}</tbody>
      </table>
    </details>""")
        monthly_html = f"""
  <div class="card">
    <h2>📅 Měsíční přehled</h2>
    <p class="muted small">Zápas zachycený ranním během se počítá do měsíce,
    kdy se skutečně hrál (většinou večer předtím), ne do dne, kdy proběhl běh skriptu.
    Poslední (ještě "otevřený") měsíc se počítá vždy z aktuálního stavu sezóny, takže
    se do něj promítnou i pozdější opravy statistik na hcmotor.cz; uzavřené měsíce
    zůstávají fixní.</p>
    {"".join(month_blocks)}
  </div>
"""
    else:
        monthly_html = ""

    zapis_all = zapis_games or []
    games = games or []
    gk = _game_by_kolo(games)
    absences = build_absences(zapis_all)

    # --- Úvodní výsledek Přehledu: poslední odehraný zápas písmem
    hero_html = ""
    if played_g:
        lg = played_g[-1]
        lz = next((z for z in zapis_all if z["kolo"] == lg["kolo"]), None)
        vs = re.match(r"\s*(\d+)\s*:\s*(\d+)", lg.get("vysledek") or "")
        if vs:
            sd, sh = vs.group(1), vs.group(2)
        elif lz:
            sd, sh = str(lz["skore_domaci"]), str(lz["skore_hoste"])
        else:
            sd = sh = None
        if sd is not None:
            motor_home = lg["domaci"] == CLUB_NAME
            rt = _result_type(lg)
            word = {"V": "Výhra", "VP": "Výhra po prodloužení či nájezdech",
                    "PP": "Prohra po prodloužení či nájezdech", "P": "Prohra"}.get(rt, "")
            kick = [f'{lg["kolo"]}. kolo', esc(lg.get("datum") or "")]
            if lz and lz.get("divaci"):
                kick.append(f'{esc(lz["divaci"])} diváků')
            def _tm(name):
                return f"<b>{esc(name)}</b>" if name == CLUB_NAME else f"<span>{esc(name)}</span>"
            goals_li = ""
            if lz:
                for g in _game_goals(lz):
                    mot = _is_motor(g["tym"])
                    asi = f'<span class="as">{esc(", ".join(g["asistence"]))}</span>' if g["asistence"] else ""
                    goals_li += (f'<li class="{"m" if mot else "o"}"><span class="t">{esc(g["cas"])}</span>'
                                 f'<span><span class="who">{esc(g["strelec"])}</span>{asi}</span></li>')
            form_sq = "".join(
                f'<span class="fsq fsq-{_result_type(g)}" title="{g["kolo"]}. kolo: {esc(_opp(g))} '
                f'{esc(g.get("vysledek") or "")} ({RES_WORD.get(_result_type(g), "")})"></span>'
                for g in played_g[-5:] if _result_type(g)
            )
            st = streaks or {}
            stats = (f'<div><dt>Body</dt><dd>{league_points}</dd></div>'
                     f'<div><dt>Na zápas</dt><dd>{ppg}</dd></div>')
            if st.get("vysledek_pocet", 0) >= 2:
                stats += (f'<div><dt>Série</dt><dd>{st["vysledek_pocet"]}×'
                          f'<small>{esc(st["vysledek_typ"])}</small></dd></div>')
            hero_html = f"""
  <div class="hero{" win" if rt in ("V", "VP") else " loss" if rt in ("P", "PP") else ""}">
    <div>
      <div class="hero-kicker">{" · ".join(kick)}</div>
      <div class="hero-score" aria-label="Výsledek {sd}:{sh}"><span{' class="m"' if motor_home else ""}>{sd}</span><i>:</i><span{'' if motor_home else ' class="m"'}>{sh}</span></div>
      <div class="hero-teams">{_tm(lg["domaci"])} <span>–</span> {_tm(lg["hoste"])}</div>
      <div class="hero-res">{word}</div>
    </div>
    <div>
      <ol class="hero-goals" aria-label="Střelci" style="list-style:none">{goals_li}</ol>
      <div class="hero-foot">
        <dl class="hero-stats">{stats}</dl>
        <div class="form-sq" aria-label="Posledních 5 zápasů"><b>Forma</b>{form_sq}</div>
      </div>
    </div>
  </div>
"""

    def souper_of(z: dict) -> str:
        g = gk.get(z["kolo"])
        if g:
            return g["hoste"] if g["domaci"] == CLUB_NAME else g["domaci"]
        return z["hoste"] if _motor_side(z) == "domaci" else z["domaci"]

    RES_LBL = {"V": "V", "VP": "VP", "PP": "PP", "P": "P"}

    def pct(a: int, b: int) -> str:
        return f"{100 * a / b:.0f} %" if b else "–"

    # --- karta Zápas: doplňky ke každému zápasu
    def _game_extra_html(z: dict) -> str:
        bits = []
        tr = [r for r in z.get("tretiny", []) if r["tretina"] in ("1", "2", "3", "P")]
        if tr:
            ma = _motor_side(z) == "domaci"
            f = lambda r: f'{r["strely"][0 if ma else 1]}:{r["strely"][1 if ma else 0]}'
            sf = sum(r["strely"][0 if ma else 1] for r in tr)
            sa = sum(r["strely"][1 if ma else 0] for r in tr)
            bits.append(f'Střely Motor–soupeř: {sf}:{sa} ({", ".join(f(r) for r in tr)})')
        rz = z.get("rozhodci") or {}
        if rz.get("hlavni"):
            bits.append(f'🦓 Rozhodčí: {", ".join(rz["hlavni"])}'
                        + (f' · čároví {", ".join(rz["carovi"])}' if rz.get("carovi") else ""))
        chyb = absences["po_kolech"].get(z["kolo"])
        if chyb:
            bits.append(f'🚑 Chyběli: {", ".join(chyb)}')
        if z.get("najezdy"):
            mp = [f'{p["strelec"]} {"✅" if p["gol"] else "❌"}' for p in z["najezdy"] if _is_motor(p["tym"])]
            bits.append(f'🎯 Nájezdy Motoru: {", ".join(mp)}')
        return "".join(f'<p class="small">{esc(b)}</p>' for b in bits)

    zapis_games = sorted(zapis_all, key=lambda z: z["kolo"], reverse=True)[:ZAPIS_GAMES_SHOWN]
    if zapis_games:
        game_blocks = []
        for i, z in enumerate(zapis_games):
            timeline_items = []
            def _ev_key(e):
                if "strelec" not in e and not str(e.get("od", ""))[:1].isdigit():
                    return 10 ** 6  # trest bez času v zápise (TS) na konec
                return e["vteriny"]
            for g in sorted(z["goly"] + z["tresty"], key=_ev_key):
                if "strelec" in g:
                    asist = f" ({', '.join(g['asistence'])})" if g["asistence"] else ""
                    timeline_items.append(
                        f'<li class="ev"><span class="ev-t">{g["cas"]}</span>'
                        f'<span class="dot {"dot-pos" if _is_motor(g["tym"]) else "dot-neg"}" title="gól"></span>'
                        f'<span class="ev-x"><strong>{esc(g["strelec"])}</strong>{esc(asist)} '
                        f'<span class="muted">{esc(g["tym"])}, {esc(g["situace"])}</span></span></li>'
                    )
                elif not str(g.get("od", ""))[:1].isdigit():
                    mn = str(g["min"])
                    timeline_items.append(
                        f'<li class="ev ev-pen"><span class="ev-t">–</span>'
                        f'<span class="dot dot-warn" title="trest"></span>'
                        f'<span class="ev-x">{esc(g["hrac"])}, {esc(mn + (" min" if mn.isdigit() else ""))} '
                        f'<span class="muted">{esc(g["tym"])}, {esc(g["duvod"])}, bez času v zápise</span></span></li>'
                    )
                else:
                    timeline_items.append(
                        f'<li class="ev ev-pen"><span class="ev-t">{g["od"]}</span>'
                        f'<span class="dot dot-warn" title="trest"></span>'
                        f'<span class="ev-x">{esc(g["hrac"])}, {esc(g["min"])} min '
                        f'<span class="muted">{esc(g["tym"])}, {esc(g["duvod"])}, do {g["do"]}</span></span></li>'
                    )
            game_blocks.append(f"""
    <details{" open" if i == 0 else ""}>
      <summary>{z["kolo"]}. kolo: {esc(z["domaci"])} {z["skore_domaci"]}:{z["skore_hoste"]} {esc(z["hoste"])}
        <span class="muted small">({esc(z["datum"])}, {esc(z["divaci"])} diváků)</span></summary>
      {f'<p class="small">⭐ Nejlepší hráči: {esc(_best_line(z))}</p>' if z.get("nejlepsi") else ""}
      {_game_extra_html(z)}
      <ul class="changes">{"".join(timeline_items) or "<li class='muted'>Bez gólů a trestů.</li>"}</ul>
    </details>""")
        zapas_html = f"""
  <div class="card">
    <h2>🏒 Poslední zápasy — průběh</h2>
    <p class="muted small">Časy a čísla hráčů podle oficiálního zápisu o utkání (hokejovyzapis.cz).</p>
    {"".join(game_blocks)}
  </div>
"""
    else:
        zapas_html = ""

    best = build_best_players(zapis_all)
    best_games = sum(1 for z in zapis_all if z.get("nejlepsi"))
    if best:
        best_rows = "".join(
            f"<tr><td>{esc(e['jmeno'])}</td><td><strong>{e['pocet']}</strong></td>"
            f"<td>{esc(', '.join(str(k) for k in sorted(e['kola'])))}</td></tr>"
            for e in best
        )
        best_html = f"""
    <div class="card">
      <h2>⭐ Nejlepší hráč utkání (Motor)</h2>
      <p class="muted small">Podle oficiálních zápisů ({best_games} zápasů s vyhlášením).</p>
      <table class="tbl-best">
        <thead><tr><th>Hráč</th><th>×</th><th>Kola</th></tr></thead>
        <tbody>{best_rows}</tbody>
      </table>
    </div>"""
    else:
        best_html = ""

    # --- Dvojice nahrávač → střelec
    pairs = build_assist_pairs(zapis_all)
    PAIRS_SHOWN = 15
    if pairs["dvojice"]:
        kk = lambda ks: esc(", ".join(str(k) for k in sorted(set(ks))))
        def pair_row(e):
            return (f"<tr><td>{esc(e['nahravac'])}</td><td>{esc(e['strelec'])}</td>"
                    f"<td><strong>{e['n']}</strong></td><td>{e['prim']}</td>"
                    f"<td class='muted'>{kk(e['kola'])}</td></tr>")
        top = pairs["dvojice"][:PAIRS_SHOWN]
        rest = pairs["dvojice"][PAIRS_SHOWN:]
        pair_head = (f"<thead><tr><th>{lbl('Nahrávač','Nahr.')}</th><th>{lbl('Střelec','Stř.')}</th>"
                     f"<th>{lbl('Góly','G')}</th><th>{lbl('z toho 1. asist.','A1')}</th><th>{lbl('Kola','K.')}</th></tr></thead>")
        rest_html = (f"""
      <details>
        <summary>Další dvojice <span class="muted small">({len(rest)})</span></summary>
        <table class="tbl-pairs">{pair_head}<tbody>{"".join(pair_row(e) for e in rest)}</tbody></table>
      </details>""" if rest else "")
        trios = [e for e in pairs["trojice"] if e["n"] >= 2]
        trio_html = (f"""
      <h2 style="margin-top:18px">Trojice u gólu</h2>
      <p class="muted small">Střelec + obě asistence, bez ohledu na to, kdo měl jakou roli
      (jen trojice, které spolu byly u gólu aspoň 2×).</p>
      <table class="tbl-trios">
        <thead><tr><th>{lbl("Hráči","H")}</th><th>{lbl("Góly","G")}</th><th>{lbl("Kola","K.")}</th></tr></thead>
        <tbody>{"".join(f"<tr><td>{esc(' · '.join(e['hraci']))}</td><td><strong>{e['n']}</strong></td><td class='muted'>{kk(e['kola'])}</td></tr>" for e in trios)}</tbody>
      </table>""" if trios else "")
        pairs_html = f"""
    <div class="card">
      <h2>🤝 Nejčastější dvojice nahrávač → střelec</h2>
      <p class="muted small">Z oficiálních zápisů — kolikrát hráč nahrával na gól
      konkrétnímu střelci (první i druhá asistence; sloupec A1 = z toho jako první).</p>
      <table class="tbl-pairs">{pair_head}<tbody>{"".join(pair_row(e) for e in top)}</tbody></table>
      {rest_html}{trio_html}
    </div>"""
    else:
        pairs_html = ""

    # --- Formace na ledě
    form = build_formations(zapis_all)
    FORM_SHOWN = 12
    if any(form[k] for k in ("dvojice", "trojice", "petky")):
        def form_table(rows: list, label: str, cls: str) -> str:
            rows = [e for e in rows if e["gf"] + e["ga"] >= 2]
            if not rows:
                return "<p class='muted small'>Zatím žádná formace s aspoň 2 góly.</p>"
            head = (f"<thead><tr><th>{label}</th><th>GF</th><th>GA</th><th>+/-</th>"
                    f"<th>{lbl('GF 5/5','GF EV')}</th><th>{lbl('GA 5/5','GA EV')}</th>"
                    f"<th>{lbl('GF přesil.','PP')}</th><th>{lbl('GA oslab.','SH')}</th><th>Z</th></tr></thead>")
            def row(e):
                diff = e["gf"] - e["ga"]
                return (f"<tr><td>{esc(' · '.join(e['hraci']))}</td><td>{e['gf']}</td><td>{e['ga']}</td>"
                        f"<td><strong>{'+' if diff > 0 else ''}{diff}</strong></td>"
                        f"<td>{e['gf_ev']}</td><td>{e['ga_ev']}</td><td>{e['gf_pp']}</td><td>{e['ga_sh']}</td>"
                        f"<td>{len(e['kola'])}</td></tr>")
            top, rest = rows[:FORM_SHOWN], rows[FORM_SHOWN:]
            html = f'<table class="{cls}">{head}<tbody>{"".join(row(e) for e in top)}</tbody></table>'
            if rest:
                html += (f'<details><summary>Další <span class="muted small">({len(rest)})</span></summary>'
                         f'<table class="{cls}">{head}<tbody>{"".join(row(e) for e in rest)}</tbody></table></details>')
            return html
        formations_html = f"""
    <div class="card">
      <h2>🧩 Formace na ledě</h2>
      <p class="muted small">Kdo byl spolu na ledě, když padl gól (z oficiálních zápisů,
      {form['zapasu']} zápasů; brankáři se nepočítají). GF = vstřelené, GA = obdržené,
      Z = v kolika zápasech formace byla u gólu. Dvojice = přesně 2 obránci na ledě,
      trojice = přesně 3 útočníci — přesilovky ve složení 4+1 nebo hra bez brankáře se
      do trojic a pětek nedostanou. Ukazují se formace s aspoň 2 góly.</p>
      <h2 style="margin-top:14px">Obranné dvojice</h2>
      {form_table(form["dvojice"], lbl("Obránci","O"), "tbl-form-d")}
      <h2 style="margin-top:18px">Útočné trojice</h2>
      {form_table(form["trojice"], lbl("Útočníci","Ú"), "tbl-form-f")}
      <h2 style="margin-top:18px">Celé pětky (2 + 3)</h2>
      {form_table(form["petky"], lbl("Pětka","5"), "tbl-form-5")}
    </div>"""
    else:
        formations_html = ""

    # --- Kdo chyběl na soupisce
    if absences["hraci"]:
        ab_rows = "".join(
            f"<tr><td>{esc(jm)}</td><td>{e['nastoupil']}</td><td><strong>{e['chybel']}</strong></td>"
            f"<td>{e['serie'] if e['serie'] else '–'}</td></tr>"
            for jm, e in sorted(absences["hraci"].items(),
                                key=lambda kv: (-kv[1]["serie"], -kv[1]["chybel"], kv[0]))
            if e["chybel"]
        )
        absence_html = f"""
    <div class="card">
      <h2>🚑 Kdo chyběl na soupisce</h2>
      <p class="muted small">Podle oficiálních zápisů ({len(absences['po_kolech'])} zápasů). Počítají se jen
      hráči, kteří už v sezóně aspoň jednou nastoupili — posila tedy před debutem nechybí.
      „V řadě" = kolik posledních zápasů po sobě chybí; u hráčů, kteří z kádru odešli,
      bude číslo dál růst.</p>
      <table class="tbl-absence">
        <thead><tr><th>Hráč</th><th>{lbl("Nastoupil","Hr.")}</th><th>{lbl("Chyběl","Ch.")}</th><th>{lbl("V řadě","Řada")}</th></tr></thead>
        <tbody>{ab_rows or "<tr><td colspan='4' class='muted'>Zatím nikdo nechyběl.</td></tr>"}</tbody>
      </table>
    </div>"""
    else:
        absence_html = ""

    # --- Vítězné a první góly
    gwg = build_gwg(zapis_all, games)
    if gwg:
        kola = lambda ks: esc(", ".join(str(k) for k in sorted(ks))) or "–"
        gwg_rows = "".join(
            f"<tr><td>{esc(r['jmeno'])}</td><td><strong>{r['gwg']}</strong></td>"
            f"<td class='muted'>{kola(r['gwg_kola'])}</td><td>{r['prvni']}</td>"
            f"<td class='muted'>{kola(r['prvni_kola'])}</td></tr>"
            for r in gwg
        )
        gwg_html = f"""
    <div class="card">
      <h2>🏆 Vítězné a první góly</h2>
      <p class="muted small">Vítězný gól = gól Motoru, po kterém už soupeř nevyrovnal
      (u výher v nájezdech se nepočítá). 1. gól = Motor otevřel skóre zápasu.</p>
      <table class="tbl-gwg">
        <thead><tr><th>Hráč</th><th>{lbl("Vítězné","VG")}</th><th>{lbl("Kola","K.")}</th><th>{lbl("1. gól","1.G")}</th><th>{lbl("Kola","K.")}</th></tr></thead>
        <tbody>{gwg_rows}</tbody>
      </table>
    </div>"""
    else:
        gwg_html = ""

    # --- Třetiny + stav po třetinách
    SCOPES = (("", "Celkem"), ("domaci", "Doma"), ("hoste", "Venku"))
    pers = {k: build_periods(zapis_all, games, k or None) for k, _ in SCOPES}
    if zapis_all:
        tl = {"1": "1. třetina", "2": "2. třetina", "3": "3. třetina", "P": "Prodloužení"}
        sl = {"vedl": "vedl", "remiza": "nerozhodně", "prohraval": "prohrával"}

        def periods_table(per):
            rows = []
            for t in ("1", "2", "3", "P"):
                e = per["tretiny"][t]
                if not e["z"]:
                    continue
                sf = f"{e['sf']}:{e['sa']}" if e["zs"] else "–"
                avg = f"{e['sf'] / e['zs']:.1f}:{e['sa'] / e['zs']:.1f}" if e["zs"] else "–"
                rows.append(
                    f"<tr><td>{tl[t]}</td><td>{e['v']}</td><td>{e['r']}</td><td>{e['p']}</td>"
                    f"<td class=\"{'sgn-pos' if e['gf'] > e['ga'] else 'sgn-neg' if e['gf'] < e['ga'] else ''}\"><strong>{e['gf']}:{e['ga']}</strong></td><td>{sf}</td><td>{avg}</td></tr>"
                )
            if not rows:
                return "<p class='muted small'>Zatím žádný zápas.</p>"
            return (f"<table class=\"tbl-periods\"><thead><tr><th>Třetina</th><th>V</th><th>R</th><th>P</th>"
                    f"<th>{lbl('Góly','G')}</th><th>{lbl('Střely','Stř')}</th><th>{lbl('Střely/zápas','Ø')}</th></tr></thead>"
                    f"<tbody>{''.join(rows)}</tbody></table>")

        def state_table(per):
            rows = []
            for k in ("1", "2"):
                for st_k in ("vedl", "remiza", "prohraval"):
                    e = per["stav"][k][st_k]
                    if not e["z"]:
                        continue
                    body = 3 * e["V"] + 2 * e["VP"] + e["PP"]
                    rows.append(
                        f"<tr><td>po {k}. třetině {sl[st_k]}</td><td>{e['z']}</td><td>{e['V']}</td>"
                        f"<td>{e['VP']}</td><td>{e['PP']}</td><td>{e['P']}</td><td><strong>{body}</strong></td></tr>"
                    )
            if not rows:
                return "<p class='muted small'>Zatím žádný zápas.</p>"
            return (f"<table class=\"tbl-state\"><thead><tr><th>Stav</th><th>Z</th><th>V</th><th>VP</th><th>PP</th><th>P</th>"
                    f"<th>{lbl('Body','B')}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>")

        def scoped(fn, data=None):
            data = pers if data is None else data
            return ("<div class='scope-grid'>" + "".join(
                f"<div class='scope'><h3 class='scope-h'>{nm}</h3>{fn(data[k])}</div>" for k, nm in SCOPES) + "</div>")

        cbs = {k: build_comebacks(zapis_all, games, k or None) for k, _ in SCOPES}

        def comeback_table(c):
            def cell(n, z, good):
                if not z:
                    return "<td>–</td><td>–</td>"
                cls = ("sgn-pos" if good else "sgn-neg") if n else ""
                pct = f"{round(100 * n / z)} %" if z >= 5 else "–"
                return f'<td class="{cls}"><strong>{n}</strong> z {z}</td><td>{pct}</td>'

            def row(label, n, z, good):
                return f"<tr><td>{label}</td>{cell(n, z, good)}</tr>"
            p1, p2, v1, v2 = c["proh1"], c["proh2"], c["ved1"], c["ved2"]
            if not (p1["z"] or v1["z"]):
                return "<p class='muted small'>Zatím žádný zápas.</p>"
            rows = (
                row("Otočil zápas", p1["V"] + p1["VP"], p1["z"], True)
                + row("Aspoň bod", p1["V"] + p1["VP"] + p1["PP"], p1["z"], True)
                + row("Otočil z manka 2+", p2["V"] + p2["VP"], p2["z"], True)
                + "<tr class='grp'><td colspan='3'>Když Motor vedl</td></tr>"
                + row("Vedení udržel", v1["V"], v1["z"], True)
                + row("Ztratil vedení", v1["PP"] + v1["P"], v1["z"], False)
                + row("Ztratil vedení o 2+", v2["PP"] + v2["P"], v2["z"], False)
            )
            return ("<table class=\"tbl-comeback\"><thead><tr><th>Ukazatel</th><th>Zápasů</th><th>%</th></tr></thead>"
                    "<tbody><tr class='grp'><td colspan='3'>Když Motor prohrával</td></tr>" + rows + "</tbody></table>")

        periods_html = f"""
    <div class="card">
      <h2>⏱️ Bilance po třetinách</h2>
      <p class="muted small">V/R/P = kolikrát Motor třetinu vyhrál / remizoval / prohrál.
      Střely ze souhrnu oficiálních zápisů ({sum(1 for z in zapis_all if z.get('tretiny'))} zápasů).</p>
      {scoped(periods_table)}
    </div>
    <div class="card">
      <h2>📊 Výsledek podle stavu po třetinách</h2>
      <p class="muted small">V = výhra v základní době, VP = výhra po prodloužení/nájezdech,
      PP = prohra po prodloužení/nájezdech, P = prohra. Body podle systému 3-2-1-0.</p>
      {scoped(state_table)}
    </div>
    <div class="card">
      <h2>🔄 Otáčení zápasů</h2>
      <p class="muted small">Podle průběhu skóre v řádné hrací době (60 minut) z oficiálních zápisů.
      Otočil zápas = někdy prohrával, ale nakonec vyhrál (i po prodloužení či nájezdech).
      Aspoň bod = někdy prohrával, ale nakonec získal aspoň bod. 2+ = o dva a více gólů. Vedení udržel = vedl a vyhrál v základní době.
      Ztratil vedení = někdy vedl, ale nakonec nevyhrál ani po prodloužení či nájezdech.
      Procenta se ukazují od pěti zápasů v dané situaci.</p>
      {scoped(comeback_table, cbs)}
    </div>"""
    else:
        periods_html = ""

    # --- Nájezdy
    so = build_shootouts(zapis_all, games)
    if so["zapasy"]:
        so_sh = "".join(
            f"<tr><td>{esc(jm)}</td><td>{e['pokusy']}</td><td><strong>{e['goly']}</strong></td>"
            f"<td>{e['pokusy'] - e['goly']}</td><td>{pct(e['goly'], e['pokusy'])}</td></tr>"
            for jm, e in sorted(so["strelci"].items(), key=lambda kv: (-kv[1]["goly"], -kv[1]["pokusy"], kv[0]))
        )
        so_gk = "".join(
            f"<tr><td>{esc(jm)}</td><td>{e['najezdy']}</td><td><strong>{e['zakroky']}</strong></td>"
            f"<td>{e['najezdy'] - e['zakroky']}</td><td>{pct(e['zakroky'], e['najezdy'])}</td></tr>"
            for jm, e in sorted(so["brankari"].items(), key=lambda kv: (-kv[1]["najezdy"], kv[0]))
        )
        so_games = "".join(
            f"<li>{'✅' if x['vyhra'] else '❌'} <strong>{x['kolo']}. kolo</strong> — "
            f"{esc(souper_of(next(z for z in zapis_all if z['kolo'] == x['kolo'])))}: "
            f"{esc(', '.join(x['motor']) or '–')}</li>"
            for x in so["zapasy"]
        )
        shootout_html = f"""
    <div class="card">
      <h2>🎯 Nájezdy v sezóně</h2>
      <p class="muted small keep">{len(so['zapasy'])} zápasů rozhodnutých nájezdy,
      bilance {sum(x['vyhra'] for x in so['zapasy'])}–{sum(not x['vyhra'] for x in so['zapasy'])}.</p>
      <table class="tbl-so">
        <thead><tr><th>Střelec</th><th>{lbl("Pokusy","Pok")}</th><th>{lbl("Proměnil","G")}</th><th>{lbl("Neproměnil","X")}</th><th>%</th></tr></thead>
        <tbody>{so_sh}</tbody>
      </table>
      <table class="tbl-so-gk">
        <thead><tr><th>Brankář</th><th>{lbl("Nájezdy","N")}</th><th>{lbl("Chytil","Ch")}</th><th>{lbl("Pustil","Pu")}</th><th>%</th></tr></thead>
        <tbody>{so_gk}</tbody>
      </table>
      <ul class="changes">{so_games}</ul>
    </div>"""
    else:
        shootout_html = """
    <div class="card">
      <h2>🎯 Nájezdy v sezóně</h2>
      <p class="muted">Motor zatím v sezóně nehrál zápas rozhodnutý nájezdy.</p>
    </div>"""

    # --- Rozhodčí
    refs = build_referees(zapis_all, games)
    if refs:
        ref_rows = "".join(
            f"<tr><td>{esc(e['jmeno'])}</td><td class='muted'>{esc(e['role'])}</td><td><strong>{e['z']}</strong></td>"
            f"<td>{e['V']}-{e['VP']}-{e['PP']}-{e['P']}</td>"
            f"<td>{e['tm_m'] / e['z']:.1f}</td><td>{e['tm_s'] / e['z']:.1f}</td>"
            f"<td class='muted'>{esc(', '.join(str(k) for k in sorted(e['kola'])))}</td></tr>"
            for e in refs
        )
        referees_html = f"""
    <div class="card">
      <h2>🦓 Rozhodčí v zápasech Motoru</h2>
      <p class="muted small">Bilance V-VP-PP-P z pohledu Motoru, trestné minuty na zápas
      (Motor / soupeř, navazující tresty sloučené).</p>
      <table class="tbl-refs">
        <thead><tr><th>Rozhodčí</th><th>{lbl("Funkce","F")}</th><th>Z</th><th>{lbl("Bilance","Bil.")}</th><th>{lbl("TM Motor","TM M")}</th><th>{lbl("TM soupeř","TM S")}</th><th>{lbl("Kola","K.")}</th></tr></thead>
        <tbody>{ref_rows}</tbody>
      </table>
    </div>"""
    else:
        referees_html = ""

    # --- Diváci
    att = build_attendance(zapis_all)
    if att["doma"] or att["venku"]:
        def att_block(lst: list, nadpis: str) -> str:
            if not lst:
                return ""
            ns = [x["n"] for x in lst]
            mx = max(lst, key=lambda x: x["n"])
            mn = min(lst, key=lambda x: x["n"])
            zk = {z["kolo"]: z for z in zapis_all}
            rows = "".join(
                f"<tr><td>{x['kolo']}.</td><td>{esc(souper_of(zk[x['kolo']]))}</td>"
                f"<td>{esc(x['datum'])}</td><td><strong>{_fmt_n(x['n'])}</strong></td></tr>"
                for x in sorted(lst, key=lambda x: -x["kolo"])
            )
            return f"""
      <p><strong>{nadpis}:</strong> průměr <strong>{_fmt_n(sum(ns) / len(ns))}</strong> ({len(ns)} zápasů) ·
      maximum {_fmt_n(mx['n'])} ({mx['kolo']}. kolo) · minimum {_fmt_n(mn['n'])} ({mn['kolo']}. kolo)</p>
      <details>
        <summary>Jednotlivé zápasy</summary>
        <table class="tbl-att">
          <thead><tr><th>{lbl("Kolo","K.")}</th><th>{lbl("Soupeř","S")}</th><th>Datum</th><th>{lbl("Diváci","D")}</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </details>"""
        attendance_html = f"""
    <div class="card">
      <h2>👥 Diváci</h2>
      {att_block(att["doma"], "🏠 Doma")}{att_block(att["venku"], "🚌 Venku")}
    </div>"""
    else:
        attendance_html = ""

    disc = build_discipline(zapis_all)
    on_ice = build_on_ice(zapis_all)
    on_ice_games = sum(1 for z in zapis_all if any("na_ledu_za" in g for g in z["goly"]))

    def _kody(d: dict) -> list:
        return sorted(d, key=lambda k: (-d[k]["min"], k))

    if disc["hraci"]:
        all_codes = _kody({k: {"min": sum(h.get(k, {}).get("min", 0) for h in disc["hraci"].values())}
                           for h in disc["hraci"].values() for k in h})
        head = "".join(
            f'<th title="{esc(OFFENCE_CODES.get(k, k))}">{esc(k)}</th>' for k in all_codes
        )
        rows = []
        for jm, h in sorted(disc["hraci"].items(),
                            key=lambda kv: (-sum(v["min"] for v in kv[1].values()), kv[0])):
            tot_n = sum(v["n"] for v in h.values())
            tot_m = sum(v["min"] for v in h.values())
            cells = "".join(
                f"<td>{h[k]['n']}</td>" if k in h else "<td class='muted'>-</td>" for k in all_codes
            )
            rows.append(f"<tr><td>{esc(jm)}</td><td><strong>{tot_m}</strong></td><td>{tot_n}</td>{cells}</tr>")
        legend = ", ".join(f"<strong>{esc(k)}</strong> {esc(OFFENCE_CODES.get(k, k))}" for k in all_codes)
        team_rows = []
        for k in _kody({**disc["tym"]["motor"], **disc["tym"]["souper"]}):
            mo = disc["tym"]["motor"].get(k, {"n": 0, "min": 0})
            so = disc["tym"]["souper"].get(k, {"n": 0, "min": 0})
            team_rows.append(
                f"<tr><td>{esc(OFFENCE_CODES.get(k, k))} <span class='muted small'>({esc(k)})</span></td>"
                f"<td>{mo['n']}</td><td>{mo['min']}</td><td>{so['n']}</td><td>{so['min']}</td></tr>"
            )
        discipline_html = f"""
    <div class="card">
      <h2>🟨 Disciplína podle typu</h2>
      <p class="muted small">Počet provinění hráčů Motoru podle oficiálních zápisů
      ({disc['zapasu']} zápasů). Navazující tresty za totéž (např. 5 + 20 min) se
      počítají jako jedno provinění. Význam kódů je pod tabulkou, řadit jde klepnutím
      na sloupec.</p>
      <table class="tbl-disc">
        <thead><tr><th>Hráč</th><th>TM</th><th>Σ</th>{head}</tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
      <p class="muted small">{legend}</p>
    </div>
    <div class="card">
      <h2>⚖️ Tresty: Motor vs. soupeři</h2>
      <table class="tbl-disc-team">
        <thead><tr><th>Provinění</th><th class="c-motor">Motor ×</th><th class="c-motor">Motor min</th><th>Soupeři ×</th><th>Soupeři min</th></tr></thead>
        <tbody>{"".join(team_rows)}</tbody>
      </table>
    </div>"""
    else:
        discipline_html = ""

    if on_ice:
        oi_rows = []
        for jm, e in sorted(on_ice.items(), key=lambda kv: (-(kv[1]["gf"] - kv[1]["ga"]), kv[0])):
            diff = e["gf"] - e["ga"]
            diff_s = f"+{diff}" if diff > 0 else str(diff)
            oi_rows.append(
                f"<tr><td>{esc(jm)}</td><td>{e['gf']}</td><td>{e['ga']}</td><td><strong>{diff_s}</strong></td>"
                f"<td>{e['gf_ev']}</td><td>{e['ga_ev']}</td>"
                f"<td>{e['gf_pp']}</td><td>{e['ga_pp']}</td>"
                f"<td>{e['gf_sh']}</td><td>{e['ga_sh']}</td></tr>"
            )
        on_ice_html = f"""
    <div class="card">
      <h2>🧊 Na ledě: góly pro / proti</h2>
      <p class="muted small">Kolik gólů padlo, když byl hráč Motoru na ledě
      (z oficiálních zápisů, {on_ice_games} zápasů; brankáři se nepočítají).
      GF = vstřelené, GA = obdržené, EV = při stejném počtu hráčů,
      PP = Motor v přesilovce, SH = Motor v oslabení. Součet za celou
      sezónu se může lišit od +/- na hcmotor.cz, pokud chybí některý zápas.</p>
      <table class="tbl-onice">
        <thead><tr><th>Hráč</th><th>GF</th><th>GA</th><th>+/-</th><th>GF EV</th><th>GA EV</th><th>GF PP</th><th>GA PP</th><th>GF SH</th><th>GA SH</th></tr></thead>
        <tbody>{"".join(oi_rows)}</tbody>
      </table>
    </div>"""
    else:
        on_ice_html = ""

    def bil_link(jmeno: str) -> str:
        from urllib.parse import quote
        return (f'<a class="bil" href="bilance-proti-tymum.html#hrac={quote(jmeno)}" '
                f'title="Bilance proti týmům" aria-label="Bilance hráče proti týmům">⇄</a>')

    skater_rows = "".join(
        f"<tr><td>{esc(s['cislo'])}</td><td>{esc(s['jmeno'])}{bil_link(s['jmeno'])}</td><td>{esc(s['post'])}</td>"
        f"<td>{s['z']}</td><td>{s['g']}</td><td>{s['a']}</td>"
        f"<td><strong>{s['b']}</strong></td><td>{s['pm']}</td><td>{s['tm']}</td></tr>"
        for s in skaters
    )

    gk_rows = "".join(
        f"<tr><td>{esc(g['cislo'])}</td><td>{esc(g['jmeno'])}</td><td>{g['z']}</td>"
        f"<td>{g['min']}</td><td>{g['str']}</td><td>{g['ink']}</td><td>{g['zas']}</td>"
        f"<td>{g['pru']:.2f}</td><td>{g['usp']:.1f}</td><td>{g['so']}</td>"
        f"<td>{g['a']}</td><td>{g['tm']}</td></tr>"
        for g in goalkeepers
    )

    # --- Kariérní tabulky (za Motor / v Extralize) ---
    skater_career_motor, missing_sm = build_career_rows(
        new.get("skaters", {}), baseline, "skater", "motor"
    )
    skater_career_liga, missing_sl = build_career_rows(
        new.get("skaters", {}), baseline, "skater", "extraliga"
    )
    gk_career_motor, missing_gm = build_career_rows(
        new.get("goalkeepers", {}), baseline, "goalkeeper", "motor"
    )
    gk_career_liga, missing_gl = build_career_rows(
        new.get("goalkeepers", {}), baseline, "goalkeeper", "extraliga"
    )

    def row_class(r: dict) -> str:
        return "" if r["ma_baseline"] else ' class="no-baseline"'

    def skater_career_rows_html(rows: list) -> str:
        return "".join(
            f"<tr{row_class(r)}><td>{esc(r['jmeno'])}{bil_link(r['jmeno'])}</td><td>{esc(r['post'])}</td>"
            f"<td>{r['z']}</td><td>{r['g']}</td><td>{r['a']}</td>"
            f"<td><strong>{r['b']}</strong></td></tr>"
            for r in rows
        )

    def gk_career_rows_html(rows: list) -> str:
        return "".join(
            f"<tr{row_class(r)}><td>{esc(r['jmeno'])}</td><td>{r['z']}</td></tr>"
            for r in rows
        )

    # --- Blížící se milníky (do MILESTONE_LOOKAHEAD zápasů/gólů/bodů) ---
    upcoming = build_upcoming_milestones(new, baseline)
    # Odznak v titulku stránky (pro ikonku na ploše) — užší práh než kartička,
    # ať odznak upozorní jen na fakt blízké milníky (1-2), ne na celou pětku.
    # Počítáme unikátní hráče, ne řádky (jeden hráč může být blízko milníku
    # zároveň za Motor i v Extralize).
    badge_count = len({i["jmeno"] for i in upcoming if i["chybi"] <= ICON_BADGE_LOOKAHEAD})
    page_title = (
        f"🎯{badge_count} Statistiky hráčů — HC Motor České Budějovice"
        if badge_count
        else "Statistiky hráčů — HC Motor České Budějovice"
    )
    if upcoming:
        milestone_rows = "".join(
            f"<tr><td>{esc(i['jmeno'])}</td>"
            f"<td>{esc(METRIC_LABELS[i['metric']].capitalize())}</td>"
            f"<td><span class=\"tag {'tag-motor' if i['scope'] == 'motor' else 'tag-liga'}\">{esc(SCOPE_LABELS[i['scope']])}</span></td>"
            f"<td>{i['hodnota']}</td>"
            f"<td><strong>{i['milestone']}</strong></td>"
            f"<td>{'<span class=\"dot dot-pos\"></span>' if i['chybi'] <= 1 else ''}{i['chybi']}</td></tr>"
            for i in upcoming
        )
        milestones_html = f"""
  <div class="card">
    <h2>🎯 Blížící se milníky (do {MILESTONE_LOOKAHEAD})</h2>
    <table class="tbl-milestones">
      <thead><tr><th>Hráč</th><th>Co</th><th>Kde</th><th>{lbl("Teď","T")}</th><th>{lbl("Milník","Mil.")}</th><th>{lbl("Chybí","Chy.")}</th></tr></thead>
      <tbody>{milestone_rows}</tbody>
    </table>
  </div>
"""
    else:
        milestones_html = ""

    has_any_baseline = bool(baseline)

    def missing_note(missing: list) -> str:
        if not missing:
            return ""
        return (
            "<p class='muted small'>Bez zadaného výchozího stavu (zobrazena jen "
            "aktuální sezóna): " + esc(", ".join(sorted(missing))) + "</p>"
        )

    if has_any_baseline:
        career_html = f"""
  <h2 class="section-title sc-motor">Kariéra za HC Motor</h2>
  <div class="card">
    <h2>Hráči v poli</h2>
    <table>
      <thead><tr><th>Hráč</th><th>{lbl("Post","P")}</th><th>Z</th><th>G</th><th>A</th><th>B</th></tr></thead>
      <tbody>{skater_career_rows_html(skater_career_motor)}</tbody>
    </table>
    {missing_note(missing_sm)}
  </div>
  <div class="card">
    <h2>Brankáři (počet zápasů)</h2>
    <table>
      <thead><tr><th>Brankář</th><th>Z</th></tr></thead>
      <tbody>{gk_career_rows_html(gk_career_motor)}</tbody>
    </table>
    {missing_note(missing_gm)}
  </div>

  <h2 class="section-title sc-liga">Kariéra v Tipsport extralize celkem</h2>
  <div class="card">
    <h2>Hráči v poli</h2>
    <table>
      <thead><tr><th>Hráč</th><th>{lbl("Post","P")}</th><th>Z</th><th>G</th><th>A</th><th>B</th></tr></thead>
      <tbody>{skater_career_rows_html(skater_career_liga)}</tbody>
    </table>
    {missing_note(missing_sl)}
  </div>
  <div class="card">
    <h2>Brankáři (počet zápasů)</h2>
    <table>
      <thead><tr><th>Brankář</th><th>Z</th></tr></thead>
      <tbody>{gk_career_rows_html(gk_career_liga)}</tbody>
    </table>
    {missing_note(missing_gl)}
  </div>
"""
    else:
        career_html = """
  <div class="card">
    <h2>Kariérní statistiky</h2>
    <p class="muted">Zatím nezadán výchozí stav hráčů (players_baseline.json) —
    jakmile bude k dispozici, přibudou tu kariérní součty za Motor a za
    celou Extraligu.</p>
  </div>
"""

    page = f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(page_title)}</title>

<!-- Přidání na plochu (PWA) -->
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="icon-192.png" type="image/png">
<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#121416" media="(prefers-color-scheme: dark)">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="HC Motor stats">
<link rel="preload" href="fonts/ibm-plex-sans-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<style>{PAGE_CSS}</style>
</head>
<body>
<div id="pull-indicator" class="pull-indicator">↓ Potáhni pro obnovení</div>
<div id="skeleton" class="skeleton-overlay">
  <div class="skeleton-block" style="height:22px;width:70%;"></div>
  <div class="skeleton-block" style="height:14px;width:40%;"></div>
  <div class="skeleton-block" style="height:90px;"></div>
  <div class="skeleton-block" style="height:90px;"></div>
  <div class="skeleton-block" style="height:140px;"></div>
</div>
<div class="wrap">
 <header class="app-header">
  <div>
   <h1>HC Motor České Budějovice</h1><span class="meta">Statistiky, {esc(SEASON_LABEL)}</span>
  </div>
  <div class="header-side">
   <span class="live"><span class="dot dot-pos"></span>Aktualizováno {now}</span>
   <a href="{STATS_URL}">hcmotor.cz</a>
   <a href="bilance-proti-tymum.html">Bilance proti týmům</a>
   <a href="sestavy.html">Sestavy</a>
  </div>
 </header>
 <nav class="tabbar" id="tabbar" aria-label="Navigace sekcí">
  <button class="tab-btn is-active" type="button" data-tab="prehled">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
    <span class="badge-dot"></span>
    <span>Přehled</span>
  </button>
  <button class="tab-btn" type="button" data-tab="zapas">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>
    <span>Zápas</span>
  </button>
  <button class="tab-btn" type="button" data-tab="sezona">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
    <span>Sezóna</span>
  </button>
  <button class="tab-btn" type="button" data-tab="bilance">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
    <span>Bilance</span>
  </button>
  <button class="tab-btn" type="button" data-tab="historie">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
    <span>Historie</span>
  </button>
  <button class="tab-btn" type="button" data-tab="mesice">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
    <span>Měsíce</span>
  </button>
  <button class="tab-btn" type="button" data-tab="kariera">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>
    <span>Kariéra</span>
  </button>
</nav>
 <div class="app-content" id="app-content">
  <section class="tabsection bento" data-tab="prehled">
    {hero_html}{next_match_html}
{milestones_html}
    <div class="card card-changes">
      <h2>Změny od minulé aktualizace</h2>
      {changes_html}
    </div>
{schedule_html}{corrections_html}
  </section>

  <section class="tabsection bento" data-tab="zapas">
    {zapas_html or '<div class="card"><p class="muted">Zatím žádný zpracovaný zápis odehraného zápasu.</p></div>'}
  </section>

  <section class="tabsection bento" data-tab="sezona">
    <div class="card">
      <h2>Hráči v poli</h2>
      <table class="tbl-skaters">
        <thead><tr><th>#</th><th>Hráč</th><th>{lbl("Post","P")}</th><th>Z</th><th>G</th><th>A</th><th>B</th><th>+/-</th><th>{lbl("TM","T")}</th></tr></thead>
        <tbody>{skater_rows}</tbody>
      </table>
    </div>

    <div class="card">
      <h2>Brankáři</h2>
      <table class="tbl-goalkeepers">
        <thead><tr><th>#</th><th>{lbl("Brankář","GK")}</th><th>Z</th><th>{lbl("Min","M")}</th><th>{lbl("Stř","S")}</th><th>{lbl("Ink","I")}</th><th>{lbl("Zás","Zá")}</th><th>{lbl("Prů","Pr")}</th><th>{lbl("Úsp %","Úsp")}</th><th>SO</th><th>A</th><th>{lbl("TM","T")}</th></tr></thead>
        <tbody>{gk_rows}</tbody>
      </table>
    </div>
    {best_html}{gwg_html}{pairs_html}{absence_html}{formations_html}{on_ice_html}{discipline_html}
  </section>

  <section class="tabsection bento" data-tab="bilance">
    {record_html}{home_away_html}{periods_html}{shootout_html}{attendance_html}{referees_html}
  </section>

  <section class="tabsection bento" data-tab="historie">
    <input type="search" class="search-box" id="search-historie" placeholder="Hledat hráče" autocomplete="off">
    {history_html}{schedule_log_html}
  </section>

  <section class="tabsection bento" data-tab="mesice">
    <input type="search" class="search-box" id="search-mesice" placeholder="Hledat hráče" autocomplete="off">
    {monthly_html}
  </section>

  <section class="tabsection bento" data-tab="kariera">
{career_html}
  </section>
 </div>
</div>

<script>
var CURRENT_UPDATED = {json.dumps(now)};

function initTabbar() {{
  try {{
    var buttons = document.querySelectorAll('.tab-btn');
    var sections = document.querySelectorAll('.tabsection');
    if (!buttons.length || !sections.length) return;

    function activate(tab) {{
      for (var i = 0; i < buttons.length; i++) {{
        buttons[i].classList.toggle('is-active', buttons[i].getAttribute('data-tab') === tab);
      }}
      for (var j = 0; j < sections.length; j++) {{
        sections[j].classList.toggle('is-hidden', sections[j].getAttribute('data-tab') !== tab);
      }}
    }}

    var appContent = document.getElementById('app-content');

    for (var k = 0; k < buttons.length; k++) {{
      buttons[k].addEventListener('click', function() {{
        activate(this.getAttribute('data-tab'));
        if (appContent) {{ appContent.scrollTop = 0; }}
        window.scrollTo(0, 0);
        if (window.navigator && typeof window.navigator.vibrate === 'function') {{
          try {{ window.navigator.vibrate(10); }} catch (e) {{}}
        }}
      }});
    }}

    // Výchozí stav (má vliv jen pod 640px, viz .tabsection.is-hidden v CSS) —
    // zbytek sekcí schováme, ať se po přepnutí lišty na mobilu neukazuje
    // něco navíc, co ještě nebylo vybráno.
    activate('prehled');
  }} catch (e) {{
    if (window.console && window.console.error) {{ window.console.error('tabbar init selhal:', e); }}
  }}
}}

function initBadge() {{
  try {{
    var btn = document.querySelector('.tab-btn[data-tab="prehled"]');
    if (!btn) return;
    var lastSeen = null;
    try {{ lastSeen = window.localStorage.getItem('hcmotor_last_seen'); }} catch (e) {{}}
    if (lastSeen && lastSeen !== CURRENT_UPDATED) {{
      btn.classList.add('has-badge');
    }}
    btn.addEventListener('click', function() {{
      btn.classList.remove('has-badge');
      try {{ window.localStorage.setItem('hcmotor_last_seen', CURRENT_UPDATED); }} catch (e) {{}}
    }});
    if (!lastSeen) {{
      try {{ window.localStorage.setItem('hcmotor_last_seen', CURRENT_UPDATED); }} catch (e) {{}}
    }}
  }} catch (e) {{
    if (window.console && window.console.error) {{ window.console.error('badge init selhal:', e); }}
  }}
}}

function initSortableTables() {{
  try {{
    var tables = document.querySelectorAll('table');
    for (var t = 0; t < tables.length; t++) {{
      (function(table) {{
        var thead = table.querySelector('thead');
        var tbody = table.querySelector('tbody');
        if (!thead || !tbody) return;
        var ths = thead.querySelectorAll('th');
        for (var c = 0; c < ths.length; c++) {{
          (function(th, colIndex) {{
            th.classList.add('sortable');
            th.addEventListener('click', function() {{
              var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
              var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
              for (var q = 0; q < rows.length; q++) {{ rows[q]._top = rows[q].getBoundingClientRect().top; }}
              var asc = !th.classList.contains('sort-asc');
              for (var x = 0; x < ths.length; x++) {{
                ths[x].classList.remove('sort-asc', 'sort-desc');
              }}
              th.classList.add(asc ? 'sort-asc' : 'sort-desc');
              rows.sort(function(r1, r2) {{
                var c1 = r1.children[colIndex], c2 = r2.children[colIndex];
                var v1 = c1 ? c1.textContent.trim() : '';
                var v2 = c2 ? c2.textContent.trim() : '';
                var n1 = parseFloat(v1.replace(',', '.').replace('%', ''));
                var n2 = parseFloat(v2.replace(',', '.').replace('%', ''));
                var cmp;
                if (!isNaN(n1) && !isNaN(n2)) {{
                  cmp = n1 - n2;
                }} else {{
                  cmp = v1.localeCompare(v2, 'cs');
                }}
                return asc ? cmp : -cmp;
              }});
              for (var y = 0; y < rows.length; y++) {{
                tbody.appendChild(rows[y]);
              }}
              if (!reduce) {{
                var moved = [];
                for (var f = 0; f < rows.length; f++) {{
                  var d = rows[f]._top - rows[f].getBoundingClientRect().top;
                  if (d) {{
                    rows[f].style.transition = 'none';
                    rows[f].style.transform = 'translateY(' + d + 'px)';
                    moved.push(rows[f]);
                  }}
                }}
                if (moved.length) {{
                  void tbody.offsetHeight;
                  for (var g2 = 0; g2 < moved.length; g2++) {{
                    moved[g2].style.transition = 'transform .18s ease-out';
                    moved[g2].style.transform = '';
                  }}
                  setTimeout(function() {{
                    for (var h2 = 0; h2 < moved.length; h2++) {{ moved[h2].style.transition = ''; }}
                  }}, 220);
                }}
              }}
            }});
          }})(ths[c], c);
        }}
      }})(tables[t]);
    }}
  }} catch (e) {{
    if (window.console && window.console.error) {{ window.console.error('řazení tabulek selhalo:', e); }}
  }}
}}

// Rozcestník dlouhých záložek (Sezóna, Bilance) se zvýrazněním aktuální sekce.
function initSectionIndex() {{
  try {{
    var secs = document.querySelectorAll('.tabsection');
    for (var s = 0; s < secs.length; s++) {{
      (function(sec) {{
        var cards = [];
        for (var i = 0; i < sec.children.length; i++) {{
          var k = sec.children[i];
          if (k.classList.contains('card') && k.querySelector('h2')) cards.push(k);
        }}
        if (cards.length < 8) return;
        var tab = sec.getAttribute('data-tab');
        var body = document.createElement('div');
        body.className = 'sec-body bento';
        var nav = document.createElement('nav');
        nav.className = 'sec-index';
        nav.setAttribute('aria-label', 'Rozcestník sekce');
        var ul = document.createElement('ul');
        var kids = Array.prototype.slice.call(sec.children);
        for (var a = 0; a < kids.length; a++) body.appendChild(kids[a]);
        var links = [];
        for (var n = 0; n < cards.length; n++) {{
          cards[n].id = 'c-' + tab + '-' + n;
          var c = cards[n].querySelector('h2').cloneNode(true);
          var btn = c.querySelector('.info-btn');
          if (btn) c.removeChild(btn);
          var li = document.createElement('li');
          var link = document.createElement('a');
          link.href = '#c-' + tab + '-' + n;
          link.textContent = c.textContent.trim();
          li.appendChild(link);
          ul.appendChild(li);
          links.push(link);
        }}
        nav.appendChild(ul);
        sec.classList.add('has-index');
        sec.appendChild(nav);
        sec.appendChild(body);
        links[0].classList.add('is-on');
        if ('IntersectionObserver' in window) {{
          var io = new IntersectionObserver(function(entries) {{
            for (var e = 0; e < entries.length; e++) {{
              if (!entries[e].isIntersecting) continue;
              for (var l = 0; l < links.length; l++) {{
                links[l].classList.toggle('is-on', links[l].getAttribute('href') === '#' + entries[e].target.id);
              }}
            }}
          }}, {{ rootMargin: '-90px 0px -65% 0px' }});
          for (var o = 0; o < cards.length; o++) io.observe(cards[o]);
        }}
      }})(secs[s]);
    }}
  }} catch (e) {{
    if (window.console && window.console.error) {{ window.console.error('rozcestník selhal:', e); }}
  }}
}}

// Vysvětlivky u nadpisů: tlačítko "i" je rozbalí.
function initInfo() {{
  document.addEventListener('click', function(e) {{
    var b = e.target && e.target.closest ? e.target.closest('.info-btn') : null;
    if (!b) return;
    var note = b.parentNode.nextElementSibling;
    if (!note || !note.classList.contains('note')) return;
    var open = note.hidden;
    note.hidden = !open;
    b.setAttribute('aria-expanded', open ? 'true' : 'false');
  }});
}}

function normalizeText(s) {{
  s = s.toLowerCase();
  try {{ s = s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, ''); }} catch (e) {{}}
  return s;
}}

function initSearchBox(inputId, sectionSelector) {{
  try {{
    var input = document.getElementById(inputId);
    var section = document.querySelector(sectionSelector);
    if (!input || !section) return;
    input.addEventListener('input', function() {{
      var q = normalizeText(input.value.trim());
      var rows = section.querySelectorAll('tbody tr');
      for (var i = 0; i < rows.length; i++) {{
        var match = !q || normalizeText(rows[i].textContent).indexOf(q) !== -1;
        rows[i].classList.toggle('search-hidden', !match);
      }}
      var items = section.querySelectorAll('.changes li');
      for (var j = 0; j < items.length; j++) {{
        var m2 = !q || normalizeText(items[j].textContent).indexOf(q) !== -1;
        items[j].classList.toggle('search-hidden', !m2);
      }}
      var detailsList = section.querySelectorAll('details');
      for (var k = 0; k < detailsList.length; k++) {{
        if (!q) {{ detailsList[k].classList.remove('search-hidden'); continue; }}
        var anyVisible = detailsList[k].querySelector('tr:not(.search-hidden), li:not(.search-hidden)');
        detailsList[k].classList.toggle('search-hidden', !anyVisible);
      }}
    }});
  }} catch (e) {{
    if (window.console && window.console.error) {{ window.console.error('vyhledávání selhalo:', e); }}
  }}
}}

function initPullToRefresh() {{
  try {{
    var indicator = document.getElementById('pull-indicator');
    if (!indicator) return;
    var startY = null;
    var pulling = false;
    var threshold = 70;
    var appContent = document.getElementById('app-content');

    function scrollerTop() {{
      if (appContent && getComputedStyle(appContent).overflowY === 'auto') {{
        return appContent.scrollTop;
      }}
      return window.scrollY;
    }}

    document.addEventListener('touchstart', function(e) {{
      if (scrollerTop() <= 0 && e.touches.length === 1) {{
        startY = e.touches[0].clientY;
        pulling = true;
      }} else {{
        startY = null;
        pulling = false;
      }}
    }}, {{ passive: true }});

    document.addEventListener('touchmove', function(e) {{
      if (!pulling || startY === null) return;
      var delta = e.touches[0].clientY - startY;
      if (delta <= 0) return;
      var clamped = Math.min(delta, 100);
      indicator.style.marginTop = (-46 + clamped) + 'px';
      if (clamped >= threshold) {{
        indicator.classList.add('is-ready');
        indicator.textContent = '↑ Pusť pro obnovení';
      }} else {{
        indicator.classList.remove('is-ready');
        indicator.textContent = '↓ Potáhni pro obnovení';
      }}
    }}, {{ passive: true }});

    document.addEventListener('touchend', function() {{
      if (!pulling) return;
      var isReady = indicator.classList.contains('is-ready');
      indicator.style.marginTop = '-46px';
      indicator.classList.remove('is-ready');
      pulling = false;
      startY = null;
      if (isReady) {{
        indicator.textContent = 'Obnovuji…';
        indicator.style.marginTop = '0px';
        window.location.reload();
      }}
    }}, {{ passive: true }});
  }} catch (e) {{
    if (window.console && window.console.error) {{ window.console.error('pull-to-refresh selhal:', e); }}
  }}
}}

function hideSkeleton() {{
  try {{
    var sk = document.getElementById('skeleton');
    if (!sk) return;
    sk.classList.add('is-hidden');
    setTimeout(function() {{
      if (sk.parentNode) {{ sk.parentNode.removeChild(sk); }}
    }}, 300);
  }} catch (e) {{}}
}}

// Sloupce, kde jsou skoro jen čísla, se zarovnají doprava (tabulková čísla).
// Sloupce +/- : kladné zeleně, záporné červeně.
function initSignedColumns() {{
  try {{
    var tables = document.querySelectorAll('table');
    for (var t = 0; t < tables.length; t++) {{
      var ths = tables[t].querySelectorAll('thead th');
      for (var c = 0; c < ths.length; c++) {{
        if (ths[c].textContent.trim() !== '+/-') continue;
        var rows = tables[t].querySelectorAll('tbody tr');
        for (var r = 0; r < rows.length; r++) {{
          var cell = rows[r].children[c];
          if (!cell) continue;
          var v = parseFloat(cell.textContent.trim().replace('\u2212', '-').replace(',', '.'));
          if (isNaN(v)) continue;
          cell.classList.add(v > 0 ? 'sgn-pos' : v < 0 ? 'sgn-neg' : 'sgn-zero');
        }}
      }}
    }}
  }} catch (e) {{}}
}}

function initNumericColumns() {{
  try {{
    var re = /^[+\\-−]?\\d[\\d\\s\\u00a0]*([.,]\\d+)?(\\s*:\\s*\\d+([.,]\\d+)?)?\\s*%?×?$/;
    var tables = document.querySelectorAll('table');
    for (var t = 0; t < tables.length; t++) {{
      var ths = tables[t].querySelectorAll('thead th');
      var rows = tables[t].querySelectorAll('tbody tr');
      for (var c = 0; c < ths.length; c++) {{
        if (/^(Kola|K\\.)$/.test(ths[c].textContent.trim())) continue;
        var filled = 0, nums = 0;
        for (var r = 0; r < rows.length; r++) {{
          var cell = rows[r].children[c];
          var v = cell ? cell.textContent.trim() : '';
          if (!v || v === '–' || v === '-') continue;
          filled++;
          if (re.test(v)) nums++;
        }}
        if (filled && nums >= filled * 0.8) {{
          ths[c].classList.add('num');
          for (var r2 = 0; r2 < rows.length; r2++) {{
            if (rows[r2].children[c]) rows[r2].children[c].classList.add('num');
          }}
        }}
      }}
    }}
  }} catch (e) {{}}
}}

// Tooltip s křížem u grafu bilance (myš i dotyk).
function initChart() {{
  try {{
    var charts = document.querySelectorAll('.chart[data-pts]');
    for (var i = 0; i < charts.length; i++) {{
      (function(box) {{
        var pts = JSON.parse(box.getAttribute('data-pts'));
        var W = +box.getAttribute('data-w');
        var svg = box.querySelector('svg');
        var hover = svg.querySelector('.g-hover');
        var cross = hover.querySelector('line');
        var dot = hover.querySelector('circle');
        var tip = box.querySelector('.chart-tip');
        function show(clientX) {{
          var rect = svg.getBoundingClientRect();
          var vx = (clientX - rect.left) / rect.width * W;
          var best = pts[0];
          for (var k = 1; k < pts.length; k++) {{
            if (Math.abs(pts[k][0] - vx) < Math.abs(best[0] - vx)) best = pts[k];
          }}
          cross.setAttribute('x1', best[0]); cross.setAttribute('x2', best[0]);
          dot.setAttribute('cx', best[0]); dot.setAttribute('cy', best[1]);
          hover.setAttribute('visibility', 'visible');
          tip.innerHTML = '<b>' + (best[2] > 0 ? '+' : '') + best[2] + '</b>';
          tip.appendChild(document.createTextNode(best[3]));
          tip.hidden = false;
          var px = best[0] / W * rect.width;
          var half = tip.offsetWidth / 2;
          tip.style.left = Math.min(Math.max(px, half), rect.width - half) + 'px';
          tip.style.top = '0px';
        }}
        function hide() {{ hover.setAttribute('visibility', 'hidden'); tip.hidden = true; }}
        svg.addEventListener('pointermove', function(e) {{ show(e.clientX); }});
        svg.addEventListener('pointerdown', function(e) {{ show(e.clientX); }});
        svg.addEventListener('pointerleave', hide);
      }})(charts[i]);
    }}
  }} catch (e) {{
    if (window.console && window.console.error) {{ window.console.error('graf selhal:', e); }}
  }}
}}

function initAll() {{
  initNumericColumns();
  initSignedColumns();
  initChart();
  initInfo();
  initSectionIndex();
  initTabbar();
  initBadge();
  initSortableTables();
  initSearchBox('search-historie', '.tabsection[data-tab="historie"]');
  initSearchBox('search-mesice', '.tabsection[data-tab="mesice"]');
  initPullToRefresh();
  setTimeout(hideSkeleton, 250);
}}

if (document.readyState === 'loading') {{
  document.addEventListener('DOMContentLoaded', initAll);
}} else {{
  initAll();
}}
</script>
</body>
</html>
"""
    # Emoji na začátku nadpisů karet pryč (nadpis nese text, ne ikonku),
    # stavové ✅/❌ (nájezdy, výsledky) jako barevné tečky.
    page = re.sub(r'(<h2[^>]*>)\s*(?:[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF\u2300-\u23FF][\ufe0f\u200d]?)+\s*',
                  r'\1', page)
    page = re.sub(r'<p class="small">\s*(?:[\U0001F000-\U0001FAFF\u2600-\u27BF\u2300-\u23FF\u2B00-\u2BFF][\ufe0f\u200d]?\s*)?([^<:]{3,40}):\s*',
                  r'<p class="small kv"><span class="muted">\1</span><span>', page)
    page = re.sub(r'(<p class="small kv"><span class="muted">[^<]*</span><span>)(.*?)</p>', r'\1\2</span></p>', page)
    def _fold_note(m):
        return (f'{m.group(1)}{m.group(2)}<button class="info-btn" type="button" aria-expanded="false" '
                f'aria-label="Vysvětlivka" title="Vysvětlivka">i</button></h2>\n'
                f'<p class="muted small note" hidden>{m.group(3)}</p>')
    page = re.sub(r'(<h2[^>]*>)([^<]*)</h2>\s*<p class="muted small">(.*?)</p>', _fold_note, page, flags=re.S)
    def _color_plus(m):
        return re.sub(r'(?<![\w/])(\+\d+[A-Za-zěščřžýáíéúůďťň]*)', r'<span class="sg-pos">\1</span>', m.group(0))
    page = re.sub(r'<ul class="changes">.*?</ul>', _color_plus, page, flags=re.S)
    page = page.replace("✅", '<span class="dot dot-pos dot-after" title="ano"></span>')
    page = page.replace("❌", '<span class="dot dot-neg dot-after" title="ne"></span>')
    return page


def main() -> None:
    old_state = load_state()
    baseline = load_baseline()
    history = load_history()
    month_boundaries = load_month_boundaries()
    schedule_watch = load_schedule_watch()
    schedule_log = load_schedule_log()
    zapis_state = load_zapis_state()

    soup = fetch(STATS_URL)
    new_state = parse_stats_page(soup)

    changes = build_changes(old_state, new_state, baseline)
    corrections = build_corrections(old_state, new_state)
    history = update_history(history, changes, corrections)

    month_key = effective_month_key()
    if month_key not in month_boundaries:
        if not month_boundaries:
            # Úplně první běh s tímhle systémem hraničních snímků — bereme,
            # že se instaluje v prvním měsíci sezóny (tak tomu bylo, když
            # se to psalo), takže hranice = nulový stav před sezónou.
            # Pokud by se to nasazovalo později v sezóně, tenhle bootstrap
            # by první (aktuální) měsíc chybně nafouknul o celou dosavadní
            # sezónu — v tom případě over-ridni ručně ten první klíč v
            # scripts/month_boundaries.json na skutečný stav k 1. dni
            # daného měsíce.
            month_boundaries[month_key] = state_to_name_snapshot({})
        else:
            # Běžný přechod do nového měsíce: hranice = sezónní stav těsně
            # před dnešním během (= konec předchozího měsíce).
            month_boundaries[month_key] = state_to_name_snapshot(old_state)
    monthly = build_monthly_from_boundaries(month_boundaries, state_to_name_snapshot(new_state))

    try:
        schedule_soup = fetch(SCHEDULE_URL)
        games = parse_schedule_page(schedule_soup)
    except Exception as exc:  # rozpis nesmí shodit celý běh statistik
        print(f"Varování: nepodařilo se načíst rozpis zápasů ({exc}).")
        games = []

    schedule_changes = build_schedule_changes(schedule_watch, games) if games else []
    schedule_log = update_schedule_log(schedule_log, schedule_changes)
    if games:
        schedule_watch = update_schedule_watch(schedule_watch, games)
    record_svg = build_record_svg(games) if games else ""
    next_match = build_next_match(games) if games else None
    home_away = build_home_away_split(games) if games else {}
    league_points = build_league_points(games) if games else 0
    streaks = build_streaks(games) if games else {}

    if games:
        best_changes = []
        pred = {z["kolo"]: bool(z.get("nejlepsi")) for z in zapis_state.get("zapasy", [])}
        zapis_state = update_zapis_state(zapis_state, games)
        write_lineups_json(games, zapis_state)
        # Hlášení jen u zápasů, které jsme ještě nikdy neměli (ne při
        # zpětném přestahování starých zápisů kvůli nové verzi).
        zapasy_vse = zapis_state.get("zapasy", [])
        nove = sorted((z for z in zapasy_vse if z["kolo"] not in pred), key=lambda z: z["kolo"])
        if nove:
            absences = build_absences(zapasy_vse)
            starsi_doma = [_divaci_int(z) for z in zapasy_vse
                           if z["kolo"] in pred and _motor_side(z) == "domaci"]
            for z in nove:
                k = z["kolo"]
                if z.get("nejlepsi"):
                    best_changes.append(f'⭐ {k}. kolo — nejlepší hráči: {_best_line(z)}')
                chyb = absences["po_kolech"].get(k)
                if chyb:
                    best_changes.append(f'🚑 {k}. kolo — na soupisce chyběli: {", ".join(chyb)}')
                for jm, n in absences["navraty"].get(k, []):
                    best_changes.append(f'↩️ {jm}: návrat do sestavy po {n} '
                                        f'{"zápase" if n == 1 else "zápasech"} ({k}. kolo)')
                mp = [p for p in z.get("najezdy") or [] if _is_motor(p["tym"])]
                if mp:
                    best_changes.append(f'🎯 {k}. kolo — nájezdy Motoru: ' + ", ".join(
                        f'{p["strelec"]} {"✅" if p["gol"] else "❌"}' for p in mp))
                n = _divaci_int(z)
                if _motor_side(z) == "domaci" and n and starsi_doma and n > max(starsi_doma):
                    best_changes.append(f'👥 {k}. kolo — rekordní návštěva sezóny doma: {_fmt_n(n)}')
                if _motor_side(z) == "domaci" and n:
                    starsi_doma.append(n)
        if best_changes:
            changes.extend(best_changes)
            history = update_history(history, best_changes, [])

    if games:
        # Živé doplnění stránky "Bilance proti týmům" (docs/bilance-proti-tymum.html)
        # o právě odehrané zápasy — jen z dat, která už máme. Nesmí shodit běh.
        try:
            import bilance_tymy
            bilance_tymy.zpracuj_beh(old_state, new_state, games, zapis_state)
        except Exception as exc:
            print(f"Varování: živé doplnění bilance se nepodařilo ({exc}).")

    DOCS_DIR.mkdir(exist_ok=True)
    OUTPUT_HTML.write_text(
        render_html(
            new_state, changes, baseline, corrections, history, monthly,
            schedule_changes, record_svg, schedule_log,
            next_match, home_away, league_points, streaks,
            zapis_state.get("zapasy", []),
            games,
        ),
        encoding="utf-8",
    )

    save_state(new_state)
    save_history(history)
    save_month_boundaries(month_boundaries)
    if games:
        save_schedule_watch(schedule_watch)
    save_schedule_log(schedule_log)
    save_zapis_state(zapis_state)
    this_month = monthly.get(month_key, {"skaters": {}, "goalkeepers": {}})
    print(f"Hotovo. Hráčů v poli: {len(new_state['skaters'])}, "
          f"brankářů: {len(new_state['goalkeepers'])}. Změn: {len(changes)}, "
          f"oprav: {len(corrections)}. Historie: {len(history)} dní. "
          f"Měsíc {month_key}: {len(this_month['skaters'])} hráčů, "
          f"{len(this_month['goalkeepers'])} brankářů s produkcí. "
          f"Rozpis: {len(games)} kol, {len(schedule_changes)} změn termínu. "
          f"Výchozí stav zadán pro {len(baseline)} hráčů.")


if __name__ == "__main__":
    main()
