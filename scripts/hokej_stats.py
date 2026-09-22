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
MONTHLY_FILE = SCRIPT_DIR / "monthly.json"
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
        pid = _player_id(cells[1])
        name = _text(cells[1])
        if not pid or not name:
            continue
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
        pid = _player_id(cells[1])
        name = _text(cells[1])
        if not pid or not name:
            continue
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


def build_monthly_deltas(old: dict, new: dict) -> dict:
    """
    Vrátí přírůstky Z/G/A/B (u brankářů jen Z) za TENTO běh — jen ze
    skutečných zápasů (dz > 0, včetně debutu), ne z oprav statistik
    (viz build_corrections). Tohle je vstup pro update_monthly.
    """
    deltas = {"skaters": {}, "goalkeepers": {}}

    old_skaters = old.get("skaters", {})
    for pid, stats in new.get("skaters", {}).items():
        old_stats = old_skaters.get(pid)
        if old_stats is None:
            if stats["z"] > 0:
                deltas["skaters"][stats["jmeno"]] = {
                    "z": stats["z"], "g": stats["g"], "a": stats["a"], "b": stats["b"],
                }
            continue
        dz = stats["z"] - old_stats.get("z", 0)
        if dz > 0:
            deltas["skaters"][stats["jmeno"]] = {
                "z": dz,
                "g": stats["g"] - old_stats.get("g", 0),
                "a": stats["a"] - old_stats.get("a", 0),
                "b": stats["b"] - old_stats.get("b", 0),
            }

    old_gk = old.get("goalkeepers", {})
    for pid, stats in new.get("goalkeepers", {}).items():
        old_stats = old_gk.get(pid)
        if old_stats is None:
            if stats["z"] > 0:
                deltas["goalkeepers"][stats["jmeno"]] = {"z": stats["z"]}
            continue
        dz = stats["z"] - old_stats.get("z", 0)
        if dz > 0:
            deltas["goalkeepers"][stats["jmeno"]] = {"z": dz}

    return deltas


def load_monthly() -> dict:
    if MONTHLY_FILE.exists():
        return json.loads(MONTHLY_FILE.read_text(encoding="utf-8"))
    return {}


def save_monthly(monthly: dict) -> None:
    MONTHLY_FILE.write_text(
        json.dumps(monthly, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_monthly(monthly: dict, month_key: str, deltas: dict) -> dict:
    """Přičte přírůstky z tohoto běhu do součtů daného měsíce (aditivně)."""
    month = monthly.setdefault(month_key, {"skaters": {}, "goalkeepers": {}})

    for name, d in deltas.get("skaters", {}).items():
        cur = month["skaters"].setdefault(name, {"z": 0, "g": 0, "a": 0, "b": 0})
        for k in ("z", "g", "a", "b"):
            cur[k] += d.get(k, 0)

    for name, d in deltas.get("goalkeepers", {}).items():
        cur = month["goalkeepers"].setdefault(name, {"z": 0})
        cur["z"] += d.get("z", 0)

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


def build_changes(old: dict, new: dict, baseline: dict) -> list:
    """Vrátí seznam textových řádků se změnami od minulého běhu."""
    changes = []
    no_point_players = []  # hráči, co odehráli zápas beze změny bodů — sloučí se do 1 řádku

    old_skaters = old.get("skaters", {})
    new_skaters = new.get("skaters", {})
    for pid, stats in new_skaters.items():
        old_stats = old_skaters.get(pid)
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
        old_stats = old_gk.get(pid)
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
        old_stats = old_skaters.get(pid)
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
        old_stats = old_gk.get(pid)
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
        old_stats = old_skaters.get(pid, {})
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
        old_stats = old_gk.get(pid, {})
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
    prodlouzeni = bool(re.search(r"p", vysledek))
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
    SVG graf průběžné bilance Motoru: výhra +1, prohra -1 (jakýmkoliv
    způsobem, i po prodloužení/nájezdech), kumulativně od 1. do
    SEASON_ROUNDS kola. Nehraná kola zatím do grafu nepřidávají bod —
    graf se tak den po dni "dokresluje", jak přibývají odehrané zápasy.
    """
    played = sorted((g for g in games if g["odehrano"]), key=lambda g: g["kolo"])
    if not played:
        return ""

    cumulative = []
    total = 0
    for g in played:
        if g["vyhra"]:
            total += 1
        elif g["prohra"]:
            total -= 1
        cumulative.append((g["kolo"], total))

    # Bod (0, 0) jako výchozí stav před 1. kolem — pak jeden bod za
    # každé odehrané kolo, přesně jak chtěl Gaffer ("začíná se na 0").
    points_xy = [(0, 0)] + cumulative

    width, height = 760, 340
    pad_l, pad_r, pad_t, pad_b = 34, 14, 14, 26
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    x_max = ((SEASON_ROUNDS + 9) // 10) * 10  # zaokrouhlit nahoru na desítku (52 -> 60)
    x_step = 10

    values = [v for _, v in points_xy]
    raw_min, raw_max = min(values), max(values)
    y_step = 2
    y_min = (min(0, raw_min) // y_step) * y_step - y_step
    y_max = -(-(max(0, raw_max)) // y_step) * y_step + y_step

    def x_for(kolo) -> float:
        return pad_l + kolo / x_max * plot_w

    def y_for(val) -> float:
        return pad_t + (y_max - val) / (y_max - y_min) * plot_h

    # Vodorovné (Y) a svislé (X) mřížkové čáry, jako v Excelu.
    y_ticks = list(range(y_min, y_max + 1, y_step))
    x_ticks = list(range(0, x_max + 1, x_step))

    hgrid = "".join(
        f'<line x1="{pad_l}" y1="{y_for(t):.1f}" x2="{width - pad_r}" y2="{y_for(t):.1f}" '
        f'stroke="#e5e7eb" stroke-width="1"/>'
        f'<text x="{pad_l - 8}" y="{y_for(t) + 4:.1f}" font-size="11" fill="#6b7280" '
        f'text-anchor="end">{t}</text>'
        for t in y_ticks
    )
    vgrid = "".join(
        f'<line x1="{x_for(t):.1f}" y1="{pad_t}" x2="{x_for(t):.1f}" y2="{height - pad_b}" '
        f'stroke="#e5e7eb" stroke-width="1"/>'
        f'<text x="{x_for(t):.1f}" y="{height - pad_b + 16}" font-size="11" fill="#6b7280" '
        f'text-anchor="middle">{t}</text>'
        for t in x_ticks
    )

    points_str = " ".join(f"{x_for(k):.1f},{y_for(v):.1f}" for k, v in points_xy)
    dots = "".join(
        f'<circle cx="{x_for(k):.1f}" cy="{y_for(v):.1f}" r="3.5" fill="#0b1f3a"/>'
        for k, v in points_xy
    )

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="auto" role="img"
         aria-label="Průběžná bilance výher a proher HC Motor">
      <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" fill="#ffffff"
            stroke="#e5e7eb"/>
      {hgrid}
      {vgrid}
      <polyline points="{points_str}" fill="none" stroke="#0b1f3a" stroke-width="2"/>
      {dots}
    </svg>
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
        misto_lbl = "🏠 doma" if nm["doma"] else "🚌 venku"
        cas_lbl = nm["cas"] if nm["cas"] else "čas bude upřesněn"
        next_match_html = f"""
  <div class="card">
    <h2>🏒 Příští zápas</h2>
    <p><strong>{nm["kolo"]}. kolo:</strong> {esc(nm["soupeř"])} ({misto_lbl})</p>
    <p class="muted small">{esc(nm["datum"])} · {esc(cas_lbl)} · {esc(nm["misto"])}</p>
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
            f'<p class="muted small">Aktuální série: {" · ".join(serie_bits)}</p>'
            if serie_bits else ""
        )
        record_html = f"""
  <div class="card">
    <h2>📈 Bilance výher a proher</h2>
    <p class="muted small">Výhra +1, prohra -1 (jakýmkoliv způsobem), kumulativně od 1. kola.
    Body v tabulce (systém 3-2-1-0): <strong>{league_points}</strong></p>
    {record_svg}
    {serie_html}
  </div>
"""
    else:
        record_html = ""

    home_away = home_away or {}
    if home_away and (home_away.get("doma", {}).get("z", 0) or home_away.get("venku", {}).get("z", 0)):
        d, v = home_away["doma"], home_away["venku"]
        home_away_html = f"""
  <div class="card">
    <h2>🏠 Bilance doma / venku</h2>
    <table>
      <thead><tr><th></th><th>Z</th><th>V</th><th>P</th></tr></thead>
      <tbody>
        <tr><td>🏠 Doma</td><td>{d["z"]}</td><td>{d["v"]}</td><td>{d["p"]}</td></tr>
        <tr><td>🚌 Venku</td><td>{v["z"]}</td><td>{v["v"]}</td><td>{v["p"]}</td></tr>
      </tbody>
    </table>
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
    kdy se skutečně hrál (většinou večer předtím), ne do dne, kdy proběhl běh skriptu.</p>
    {"".join(month_blocks)}
  </div>
"""
    else:
        monthly_html = ""

    skater_rows = "".join(
        f"<tr><td>{esc(s['cislo'])}</td><td>{esc(s['jmeno'])}</td><td>{esc(s['post'])}</td>"
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
            f"<tr{row_class(r)}><td>{esc(r['jmeno'])}</td><td>{esc(r['post'])}</td>"
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
            f"<td>{esc(SCOPE_LABELS[i['scope']])}</td>"
            f"<td>{i['hodnota']}</td>"
            f"<td><strong>{i['milestone']}</strong></td>"
            f"<td>{i['chybi']}</td></tr>"
            for i in upcoming
        )
        milestones_html = f"""
  <div class="card">
    <h2>🎯 Blížící se milníky (do {MILESTONE_LOOKAHEAD})</h2>
    <table>
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
  <h2 class="section-title">Kariéra za HC Motor</h2>
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

  <h2 class="section-title">Kariéra v Tipsport extralize celkem</h2>
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

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(page_title)}</title>

<!-- Přidání na plochu (PWA) -->
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="icon-192.png" type="image/png">
<meta name="theme-color" content="#c8102e">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="HC Motor stats">
<style>
  :root {{
    --red: #c8102e; --navy: #0b1f3a; --bg: #f4f5f7; --card: #ffffff;
    --muted: #6b7280; --border: #e5e7eb;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--navy); margin: 0; padding: 24px 16px;
  }}
  .wrap {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .updated {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 4px; }}
  .season {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 24px; }}
  .section-title {{
    font-size: 1.15rem; margin: 32px 0 12px; color: var(--navy);
    border-bottom: 2px solid var(--red); padding-bottom: 6px;
  }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 20px; margin-bottom: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    overflow-x: auto;
  }}
  .card h2 {{ font-size: 1.05rem; margin: 0 0 12px; color: var(--red); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  th {{ color: var(--muted); font-weight: 600; font-size: 0.76rem; text-transform: uppercase; }}
  tr.no-baseline {{ color: var(--muted); font-style: italic; }}
  .changes {{ list-style: none; margin: 0; padding: 0; }}
  .changes li {{ padding: 6px 0; border-bottom: 1px solid var(--border); }}
  .changes li:last-child {{ border-bottom: none; }}
  .muted {{ color: var(--muted); margin: 0; }}
  .small {{ font-size: 0.78rem; margin-top: 10px; }}
  .lbl-short {{ display: none; }}
  details {{ border-bottom: 1px solid var(--border); padding: 8px 0; }}
  details:last-child {{ border-bottom: none; }}
  details > summary {{
    cursor: pointer; font-weight: 600; list-style: none; padding: 4px 0;
  }}
  details > summary::-webkit-details-marker {{ display: none; }}
  details > summary::before {{ content: "▸ "; color: var(--red); }}
  details[open] > summary::before {{ content: "▾ "; }}
  details .changes {{ margin-top: 6px; }}

  /* kompaktnější zobrazení na výšku na mobilu */
  @media (max-width: 600px) {{
    body {{ padding: 14px 8px; }}
    .wrap {{ max-width: 100%; }}
    h1 {{ font-size: 1.2rem; }}
    .section-title {{ font-size: 1rem; margin: 24px 0 10px; }}
    .card {{ padding: 12px 10px; margin-bottom: 14px; border-radius: 10px; }}
    .card h2 {{ font-size: 0.95rem; }}
    table {{ font-size: 0.72rem; }}
    th, td {{ padding: 4px 5px; }}
    th {{ font-size: 0.62rem; }}
    .lbl-full {{ display: none; }}
    .lbl-short {{ display: inline; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🏒 Statistiky hráčů — HC Motor České Budějovice</h1>
  <div class="updated">Naposledy aktualizováno: {now}</div>
  <div class="season">{esc(SEASON_LABEL)} · zdroj: <a href="{STATS_URL}">hcmotor.cz</a></div>

  <div class="card">
    <h2>Změny od minulé aktualizace</h2>
    {changes_html}
  </div>
{milestones_html}{next_match_html}{schedule_html}{corrections_html}{history_html}{record_html}{home_away_html}{monthly_html}{schedule_log_html}
  <h2 class="section-title">Aktuální sezóna</h2>
  <div class="card">
    <h2>Hráči v poli</h2>
    <table>
      <thead><tr><th>#</th><th>Hráč</th><th>{lbl("Post","P")}</th><th>Z</th><th>G</th><th>A</th><th>B</th><th>+/-</th><th>{lbl("TM","T")}</th></tr></thead>
      <tbody>{skater_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Brankáři</h2>
    <table>
      <thead><tr><th>#</th><th>{lbl("Brankář","GK")}</th><th>Z</th><th>{lbl("Min","M")}</th><th>{lbl("Stř","S")}</th><th>{lbl("Ink","I")}</th><th>{lbl("Zás","Zá")}</th><th>{lbl("Prů","Pr")}</th><th>{lbl("Úsp %","Úsp")}</th><th>SO</th><th>A</th><th>{lbl("TM","T")}</th></tr></thead>
      <tbody>{gk_rows}</tbody>
    </table>
  </div>
{career_html}
</div>
</body>
</html>
"""


def main() -> None:
    old_state = load_state()
    baseline = load_baseline()
    history = load_history()
    monthly = load_monthly()
    schedule_watch = load_schedule_watch()
    schedule_log = load_schedule_log()

    soup = fetch(STATS_URL)
    new_state = parse_stats_page(soup)

    changes = build_changes(old_state, new_state, baseline)
    corrections = build_corrections(old_state, new_state)
    history = update_history(history, changes, corrections)

    monthly_deltas = build_monthly_deltas(old_state, new_state)
    month_key = effective_month_key()
    monthly = update_monthly(monthly, month_key, monthly_deltas)

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

    DOCS_DIR.mkdir(exist_ok=True)
    OUTPUT_HTML.write_text(
        render_html(
            new_state, changes, baseline, corrections, history, monthly,
            schedule_changes, record_svg, schedule_log,
            next_match, home_away, league_points, streaks,
        ),
        encoding="utf-8",
    )

    save_state(new_state)
    save_history(history)
    save_monthly(monthly)
    if games:
        save_schedule_watch(schedule_watch)
    save_schedule_log(schedule_log)
    print(f"Hotovo. Hráčů v poli: {len(new_state['skaters'])}, "
          f"brankářů: {len(new_state['goalkeepers'])}. Změn: {len(changes)}, "
          f"oprav: {len(corrections)}. Historie: {len(history)} dní. "
          f"Měsíc {month_key}: {len(monthly_deltas['skaters'])} hráčů, "
          f"{len(monthly_deltas['goalkeepers'])} brankářů s přírůstkem. "
          f"Rozpis: {len(games)} kol, {len(schedule_changes)} změn termínu. "
          f"Výchozí stav zadán pro {len(baseline)} hráčů.")


if __name__ == "__main__":
    main()
