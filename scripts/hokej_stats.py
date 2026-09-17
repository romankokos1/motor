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
from datetime import datetime
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


def build_changes(old: dict, new: dict) -> list:
    """Vrátí seznam textových řádků se změnami od minulého běhu."""
    changes = []

    old_skaters = old.get("skaters", {})
    new_skaters = new.get("skaters", {})
    for pid, stats in new_skaters.items():
        old_stats = old_skaters.get(pid)
        if old_stats is None:
            changes.append(f"🆕 Nový hráč v tabulce: {stats['jmeno']}")
            continue
        dg = stats["g"] - old_stats.get("g", 0)
        da = stats["a"] - old_stats.get("a", 0)
        db = stats["b"] - old_stats.get("b", 0)
        dz = stats["z"] - old_stats.get("z", 0)
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
        elif dz > 0:
            changes.append(f"▫️ {stats['jmeno']}: odehrál další zápas ({stats['z']} celkem)")

    old_gk = old.get("goalkeepers", {})
    new_gk = new.get("goalkeepers", {})
    for pid, stats in new_gk.items():
        old_stats = old_gk.get(pid)
        if old_stats is None:
            changes.append(f"🆕 Nový brankář v tabulce: {stats['jmeno']}")
            continue
        dz = stats["z"] - old_stats.get("z", 0)
        dso = stats["so"] - old_stats.get("so", 0)
        if dz > 0:
            changes.append(
                f"🥅 {stats['jmeno']}: odchytal další zápas — "
                f"{stats['usp']:.1f}% úspěšnost, {stats['pru']:.2f} průměr "
                f"({stats['z']} zápasů celkem)"
            )
        if dso > 0:
            changes.append(f"🚫 {stats['jmeno']}: vychytal nulu! (celkem {stats['so']} SO)")

    return changes


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


def render_html(new: dict, changes: list, baseline: dict) -> str:
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

    changes_html = (
        "<ul class='changes'>" + "".join(f"<li>{esc(c)}</li>" for c in changes) + "</ul>"
        if changes
        else "<p class='muted'>Od minulého běhu žádné změny.</p>"
    )

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
      <thead><tr><th>Hráč</th><th>Post</th><th>Z</th><th>G</th><th>A</th><th>B</th></tr></thead>
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
      <thead><tr><th>Hráč</th><th>Post</th><th>Z</th><th>G</th><th>A</th><th>B</th></tr></thead>
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
<title>Statistiky hráčů — HC Motor České Budějovice</title>
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

  <h2 class="section-title">Aktuální sezóna</h2>
  <div class="card">
    <h2>Hráči v poli</h2>
    <table>
      <thead><tr><th>#</th><th>Hráč</th><th>Post</th><th>Z</th><th>G</th><th>A</th><th>B</th><th>+/-</th><th>TM</th></tr></thead>
      <tbody>{skater_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Brankáři</h2>
    <table>
      <thead><tr><th>#</th><th>Brankář</th><th>Z</th><th>Min</th><th>Stř</th><th>Ink</th><th>Zás</th><th>Prů</th><th>Úsp %</th><th>SO</th><th>A</th><th>TM</th></tr></thead>
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

    soup = fetch(STATS_URL)
    new_state = parse_stats_page(soup)

    changes = build_changes(old_state, new_state)

    DOCS_DIR.mkdir(exist_ok=True)
    OUTPUT_HTML.write_text(render_html(new_state, changes, baseline), encoding="utf-8")

    save_state(new_state)
    print(f"Hotovo. Hráčů v poli: {len(new_state['skaters'])}, "
          f"brankářů: {len(new_state['goalkeepers'])}. Změn: {len(changes)}. "
          f"Výchozí stav zadán pro {len(baseline)} hráčů.")


if __name__ == "__main__":
    main()
