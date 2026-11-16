"""Doplní do docs/sestavy-data.json sestavy NEODEHRANÝCH zápasů Motoru
z oficiálního zápisu (kluby je tam vyplňují před zápasem). Prohlížeč na
hokejovyzapis.cz sám nedosáhne (web neposílá CORS hlavičky), proto to
dělá tenhle skript na straně serveru.

Spouští se jednou denně. Dopředu se dívá šetrně:
  - den před zápasem: jeden dotaz,
  - v den zápasu: počká na okno od 3 hodin před výkopem a pak každých
    15 minut zkouší zápis znovu až do výkopu (po každé změně sestav hned
    uloží a nahraje do repa),
  - ostatní dny skončí okamžitě bez jediného dotazu na web."""
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hokej_stats as h

PRAHA = ZoneInfo("Europe/Prague")
PRED_VYKOPEM = timedelta(hours=3)     # odkdy začít zkoušet
PO_VYKOPU = timedelta(minutes=5)      # dokdy
INTERVAL = 15 * 60                    # vteřin mezi dotazy
VYCHOZI_VYKOP = "17:30"


def datum_zapasu(txt: str, dnes: date) -> date | None:
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.", txt or "")
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    kandidati = []
    for rok in (dnes.year - 1, dnes.year, dnes.year + 1):
        try:
            kandidati.append(date(rok, mo, d))
        except ValueError:
            pass
    return min(kandidati, key=lambda x: abs((x - dnes).days)) if kandidati else None


def vykop(g: dict, dt: date) -> datetime:
    m = re.search(r"(\d{1,2})[:.](\d{2})", g.get("cas") or "") or re.search(r"(\d{1,2})[:.](\d{2})", VYCHOZI_VYKOP)
    return datetime(dt.year, dt.month, dt.day, int(m.group(1)), int(m.group(2)), tzinfo=PRAHA)


def nacti() -> dict:
    return json.loads(h.LINEUPS_JSON.read_text(encoding="utf-8"))


def zkus_stahnout(kolo: int) -> bool:
    """Stáhne sestavy kola a uloží je, pokud se změnily. Vrací True při změně."""
    data = nacti()  # vždy čerstvě z disku: mezitím mohl běžet jiný workflow
    g = next((x for x in data["zapasy"] if x["kolo"] == kolo), None)
    if not g or not g.get("hokejcz_id"):
        return False
    try:
        sestava = h.fetch_sestava_predem(g["hokejcz_id"])
    except Exception as exc:
        print(f"{kolo}. kolo: sestavu se nepodařilo stáhnout ({exc}).")
        return False
    if not sestava:
        print(f"{kolo}. kolo: sestavy zatím nejsou v zápisu.")
        return False
    if sestava == g.get("sestava"):
        print(f"{kolo}. kolo: beze změny.")
        return False
    g["sestava"] = sestava
    g["sestava_cas"] = datetime.now(PRAHA).strftime("%d.%m.%Y %H:%M")
    h.LINEUPS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{kolo}. kolo: sestavy uloženy.")
    return True


def nahraj() -> None:
    """Commit + push souboru se sestavami (v GitHub Actions)."""
    def run(*cmd):
        return subprocess.run(cmd, check=False).returncode
    run("git", "config", "user.name", "hokej-hlidac-bot")
    run("git", "config", "user.email", "actions@github.com")
    run("git", "add", "docs/sestavy-data.json")
    if run("git", "diff", "--cached", "--quiet") == 0:
        return
    run("git", "commit", "-m", "Sestavy před zápasem [skip ci]")
    for i in range(1, 6):
        if run("git", "pull", "--rebase", "-X", "theirs", "origin", "main") == 0 \
                and run("git", "push", "origin", "HEAD:main") == 0:
            return
        run("git", "rebase", "--abort")
        time.sleep(i * 10)
    print("Varování: nahrání sestav do repa se nepovedlo.")


def main() -> int:
    if not h.LINEUPS_JSON.exists():
        print("Chybí docs/sestavy-data.json, nic k doplnění.")
        return 0
    ted = datetime.now(PRAHA)
    dnes = ted.date()
    dnes_zapasy, zitra_zapasy = [], []
    for g in nacti()["zapasy"]:
        if g.get("odehrano") or g.get("zapis") or not g.get("hokejcz_id"):
            continue
        dt = datum_zapasu(g.get("datum", ""), dnes)
        if dt == dnes:
            dnes_zapasy.append((g["kolo"], vykop(g, dt)))
        elif dt == dnes + timedelta(days=1):
            zitra_zapasy.append(g["kolo"])

    for kolo in zitra_zapasy:  # den předem jen jeden dotaz
        if zkus_stahnout(kolo):
            nahraj()
    if not dnes_zapasy:
        if not zitra_zapasy:
            print("Dnes ani zítra se nehraje, nic nedělám.")
        return 0

    for kolo, start in dnes_zapasy:
        okno_od, okno_do = start - PRED_VYKOPEM, start + PO_VYKOPU
        print(f"{kolo}. kolo: výkop {start:%H:%M}, sleduji {okno_od:%H:%M}–{okno_do:%H:%M}.")
        cekat = (okno_od - datetime.now(PRAHA)).total_seconds()
        if cekat > 0:
            print(f"Čekám {int(cekat // 60)} min na začátek okna.")
            time.sleep(cekat)
        while True:
            if zkus_stahnout(kolo):
                nahraj()
            if datetime.now(PRAHA) + timedelta(seconds=INTERVAL) > okno_do:
                break
            time.sleep(INTERVAL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
