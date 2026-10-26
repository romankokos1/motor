"""
Fotky hráčů HC Motor — jednotné zpracování pro web, plachtu i články.

Pro každého hráče ze data/soupiska.json:
  1. stáhne fotku z hcmotor.cz (zkusí několik tvarů názvu souboru),
  2. vyřízne hráče z pozadí (rembg),
  3. najde obličej (OpenCV) a podle něj srovná ořez, aby měli všichni
     hlavu ve stejné výšce a stejně velkou,
  4. upraví barvy (lokální kontrast, jemný grading, doostření),
  5. uloží:
       docs/fotky/vyrez/<slug>.webp      400×400, hlava a ramena, průhledné pozadí
       docs/fotky/portret/<slug>.jpg     400×400, s pozadím (i pro články v CMS)
       docs/fotky/portret/<slug>.webp
       docs/fotky/hraci.json             přehled souborů a varování
       docs/fotky/index.html             kontrolní stránka
       docs/fotky/plachta.html           plachta hráčů (otevřít v prohlížeči)

Nezměněné fotky přeskakuje (scripts/fotky_state.json). --vse přepočítá vše,
--jen slug1,slug2 jen vybrané hráče. Ruční opravy: scripts/fotky_upravy.json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SOUPISKA = ROOT / "data" / "soupiska.json"
UPRAVY = ROOT / "scripts" / "fotky_upravy.json"
STATE = ROOT / "scripts" / "fotky_state.json"
OUT = ROOT / "docs" / "fotky"

FOTO_BASE = "https://hcmotor.cz/foto/hraci"
SOUPISKA_URL = "https://hcmotor.cz/soupiska.asp"

# Zvyš, když se změní postup zpracování → přepočítají se všechny fotky.
VERZE_ZPRACOVANI = 2

# Model pro výřez. "isnet-general-use" má čisté okraje u lidí i dresů.
# Alternativa "u2net_human_seg" je rychlejší, ale hrubší kolem vlasů.
MODEL = "isnet-general-use"

# Klubové fotky na hcmotor.cz mají jen 280×280 px a jsou to hlava a ramena.
# Proto čtverec 400 px (zvětšení kolem 1,4×) a obličej tak velký, aby ramena
# sahala ke spodnímu okraji. Až budou originály ve vysokém rozlišení,
# stačí zvednout VYREZ a PORTRET (třeba na 800).

# Výřez bez pozadí (čtverec): obličej 30 % výšky, jeho střed ve 40 %.
VYREZ_W, VYREZ_H = 400, 400
VYREZ_OBLICEJ = 0.30
VYREZ_STRED_Y = 0.40

# Portrét s pozadím (čtverec): obličej 30 % výšky, střed ve 38 %.
PORTRET = 400
PORTRET_OBLICEJ = 0.30
PORTRET_STRED_Y = 0.38

# Síla barevné úpravy 0–1 (0 = beze změny).
GRADING_SILA = 0.6

# Pod touhle šířkou originálu upozorní, že na velký tisk fotka nestačí.
MIN_SIRKA_TISK = 900

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------- pomocné

def translit(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower()


def slug_hrace(h: dict) -> str:
    """'Ole Einar Engeland Andersen' → 'andersen-ole-einar-engeland' (stejně jako docs/h/)."""
    prijmeni = h["prijmeni"]
    zbytek = h["jmeno"].replace(prijmeni, "").strip()
    text = f"{prijmeni} {zbytek}"
    return re.sub(r"[^a-z0-9]+", "-", translit(text)).strip("-")


def sezona_text(sezona: str) -> str:
    """'2027' → '2026/27' (hcmotor.cz značí sezónu rokem jejího konce)."""
    try:
        konec = int(sezona)
        return f"{konec - 1}/{str(konec)[-2:]}"
    except ValueError:
        return sezona


def nacti_json(path: Path, vychozi):
    if not path.exists():
        return vychozi
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def uloz_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


# ---------------------------------------------------------------- stažení

def adresy_ze_soupisky() -> dict[str, str]:
    """
    Projde soupisku na hcmotor.cz a vrátí {název souboru bez přípony: plná adresa}.
    Adresy tam mají ?v=… podle verze fotky, takže změna fotky = změna adresy.
    Když stránka nejde načíst, vrátí prázdný slovník a skript hádá názvy.
    """
    try:
        r = requests.get(SOUPISKA_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! soupiska.asp nejde načíst ({e}), názvy fotek budu hádat")
        return {}
    nalez = {}
    for m in re.finditer(r"""(?:https?://hcmotor\.cz)?/?foto/hraci/\d{4}/([\w\-]+)\.(?:jpe?g|png)(\?v=\d+)?""", r.text, re.I):
        url = m.group(0)
        if not url.startswith("http"):
            url = "https://hcmotor.cz/" + url.lstrip("/")
        nalez.setdefault(m.group(1).lower(), url)
    print(f"  soupiska.asp: nalezeno {len(nalez)} fotek")
    return nalez


def kandidati(h: dict, sezona: str, ze_soupisky: dict[str, str]) -> list[str]:
    last = translit(h["prijmeni"])
    first = translit(h["krestni"])
    nazvy = [f"{last}_{first}"]
    nazvy += [f"{last}_{a}" for a in h.get("alt_krestni", [])]
    nazvy.append(f"{first}_{last}")
    urls = []
    if h.get("url"):
        urls.append(h["url"])
    for n in nazvy:
        if n in ze_soupisky:
            urls.append(ze_soupisky[n])
    urls += [f"{FOTO_BASE}/{sezona}/{n}.jpg" for n in nazvy]
    return list(dict.fromkeys(urls))


def stahni(urls: list[str]) -> tuple[str, bytes] | tuple[None, None]:
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException:
            continue
        typ = r.headers.get("content-type", "")
        if r.status_code == 200 and typ.startswith("image") and len(r.content) > 2000:
            return url, r.content
    return None, None


# ---------------------------------------------------------------- úpravy

_session = None


def vyrez_pozadi(img: Image.Image) -> Image.Image:
    """Vrátí masku (L) hráče. Model se načte jen jednou."""
    global _session
    from rembg import new_session, remove
    if _session is None:
        _session = new_session(MODEL)
    rgba = remove(img, session=_session, post_process_mask=True)
    return rgba.split()[-1]


def krivka(hodnoty: list[float]) -> list[int]:
    """Tónová křivka z 5 bodů (0, 25, 50, 75, 100 %) smíchaná s neutrální podle GRADING_SILA."""
    x = np.linspace(0, 1, len(hodnoty))
    t = np.arange(256) / 255
    y = np.interp(t, x, hodnoty)
    y = GRADING_SILA * y + (1 - GRADING_SILA) * t
    return [int(round(v * 255)) for v in np.clip(y, 0, 1)]


# Stejné křivky jako „Filmový grading“ v ukázce efektů:
# stíny lehce do studena, světla a pleť do tepla.
LUT = (
    krivka([0.02, 0.24, 0.56, 0.86, 1.00])
    + krivka([0.07, 0.27, 0.53, 0.80, 0.96])
    + krivka([0.13, 0.33, 0.50, 0.70, 0.84])
)


def uprav_barvy(img: Image.Image) -> Image.Image:
    """Clarity (lokální kontrast) → grading → kontrast a sytost."""
    r = max(6, round(img.width / 50))
    # u malých fotek slaběji, jinak vznikají světlé lemy kolem nápisů na dresu
    sila = 35 if img.width >= 600 else 20
    img = img.filter(ImageFilter.UnsharpMask(radius=r, percent=sila, threshold=0))
    img = img.point(LUT)
    img = ImageEnhance.Contrast(img).enhance(1.03)
    img = ImageEnhance.Color(img).enhance(1.06)
    return img


def doostri(img: Image.Image, scale: float = 1.0) -> Image.Image:
    """
    Jemné doostření po změně velikosti. Při zmenšení plná síla, při zvětšení
    slabší a nad 1,6× žádné: zvětšenou fotku doostření nespraví, jen přidá lemy.
    U RGBA nechá průhlednost beze změny.
    """
    procent = 60 if scale <= 1.15 else 30 if scale <= 1.6 else 0
    if not procent:
        return img
    f = ImageFilter.UnsharpMask(radius=0.8, percent=procent, threshold=2)
    if img.mode == "RGBA":
        rgb, a = img.convert("RGB"), img.getchannel("A")
        out = rgb.filter(f).convert("RGBA")
        out.putalpha(a)
        return out
    return img.filter(f)


# ---------------------------------------------------------------- obličej

def najdi_oblicej(img: Image.Image, maska: Image.Image | None) -> tuple[tuple[float, float, float, float], str]:
    """
    Vrátí ((x, y, šířka, výška), zdroj). Zdroj je 'detekce', 'odhad' nebo 'stred'.
    Detekce bere jen obličeje v horních 60 % fotky a uvnitř hráče (podle masky),
    aby se nechytila na logo na dresu nebo na fotku v pozadí.
    """
    import cv2

    rgb = np.asarray(img.convert("RGB"))
    gray = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    h, w = gray.shape
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=6, minSize=(int(w * 0.08), int(w * 0.08)))
    m = np.asarray(maska) if maska is not None else None
    vhodne = []
    for (x, y, fw, fh) in faces:
        cx, cy = x + fw / 2, y + fh / 2
        if cy > h * 0.6:
            continue
        if m is not None and m[int(cy), int(cx)] < 128:
            continue
        vhodne.append((fw * fh, (float(x), float(y), float(fw), float(fh))))
    if vhodne:
        return max(vhodne)[1], "detekce"

    # Odhad z masky: hlava = nejvyšší část postavy.
    if m is not None and (m > 128).any():
        rows = np.where((m > 128).any(axis=1))[0]
        top = rows[0]
        vyska_postavy = rows[-1] - top
        pas = m[top: top + max(1, int(vyska_postavy * 0.12))] > 128
        cols = np.where(pas.any(axis=0))[0]
        cx = float(cols.mean()) if len(cols) else w / 2
        fh = max(vyska_postavy * 0.11, h * 0.08)
        return (cx - fh / 2, top + fh * 0.25, fh, fh), "odhad"

    fh = h * 0.15
    return (w / 2 - fh / 2, h * 0.12, fh, fh), "stred"


# ---------------------------------------------------------------- kompozice

def rozpust_rezy(rgba: Image.Image) -> Image.Image:
    """
    Kde rám originální fotky uřízl hráče (typicky dole v pase, někdy rameno
    na boku), by ve výřezu zůstala ostrá rovná hrana. Tady ji plynule
    rozpustíme: dole přes 10 % výšky, na bocích přes 7 % šířky.
    Horní okraj se nemění (tam je hlava a vzduch).
    """
    a = np.asarray(rgba.getchannel("A")).astype(np.float32) / 255
    h, w = a.shape
    ramp = np.ones_like(a)
    if a[-2:, :].mean() > 0.05:                       # dole
        n = max(1, int(h * 0.10))
        ramp[-n:, :] *= np.linspace(1, 0, n)[:, None]
    if a[:, :2].mean() > 0.05:                         # vlevo
        n = max(1, int(w * 0.07))
        ramp[:, :n] *= np.linspace(0, 1, n)[None, :]
    if a[:, -2:].mean() > 0.05:                        # vpravo
        n = max(1, int(w * 0.07))
        ramp[:, -n:] *= np.linspace(1, 0, n)[None, :]
    out = rgba.copy()
    out.putalpha(Image.fromarray((a * ramp * 255).astype(np.uint8)))
    return out


def umisti_vyrez(rgba: Image.Image, face, W: int, H: int, upr: dict) -> tuple[Image.Image, float]:
    """
    Hlava a ramena: obličej je vždy ve stejné výšce (VYREZ_STRED_Y) a velikost
    se zvolí tak, aby ramena došla až ke spodnímu okraji, jinak by hráč visel
    uprostřed karty. Velikost obličeje se přitom drží v rozumném rozmezí kolem
    VYREZ_OBLICEJ, aby nebyl nikdo výrazně větší nebo menší než ostatní.
    """
    fx, fy, fw, fh = face
    cy_src = fy + fh / 2
    radky = np.where((np.asarray(rgba.getchannel("A")) > 128).any(axis=1))[0]
    if len(radky) and radky[-1] > cy_src:
        na_spodek = ((1 - VYREZ_STRED_Y) * H) / (radky[-1] - cy_src)
        podil = min(max(fh * na_spodek / H, VYREZ_OBLICEJ * 0.85), VYREZ_OBLICEJ * 1.35)
    else:
        podil = VYREZ_OBLICEJ
    scale = (podil * upr.get("zoom", 1.0) * H) / fh
    nove = rgba.resize((max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale))), Image.LANCZOS)
    cx, cy = (fx + fw / 2) * scale, (fy + fh / 2) * scale
    ox = W / 2 + upr.get("posun_x", 0) * W - cx
    oy = VYREZ_STRED_Y * H + upr.get("posun_y", 0) * H - cy
    platno = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # plátno je prázdné, takže stačí obyčejné vložení (zvládne i záporný posun)
    platno.paste(nove, (round(ox), round(oy)))
    return platno, scale


def orizni_portret(img: Image.Image, face, size: int, upr: dict) -> tuple[Image.Image, float]:
    fx, fy, fw, fh = face
    strana = fh / (PORTRET_OBLICEJ * upr.get("zoom", 1.0))
    strana = min(strana, img.width, img.height)
    cx, cy = fx + fw / 2, fy + fh / 2
    left = cx - strana / 2 - upr.get("posun_x", 0) * strana
    top = cy - PORTRET_STRED_Y * strana - upr.get("posun_y", 0) * strana
    left = min(max(left, 0), img.width - strana)
    top = min(max(top, 0), img.height - strana)
    vyrez = img.crop((round(left), round(top), round(left + strana), round(top + strana)))
    return vyrez.resize((size, size), Image.LANCZOS), size / strana


# ---------------------------------------------------------------- hlavní běh

def zpracuj(h: dict, slug: str, url: str, data: bytes, upr: dict) -> dict:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    varovani = []

    maska = None
    if not upr.get("bez_vyrezu"):
        maska = vyrez_pozadi(img)
        podil = np.asarray(maska).mean() / 255
        if podil < 0.08 or podil > 0.92:
            varovani.append(f"výřez je podezřelý (hráč zabírá {podil:.0%} plochy)")

    if upr.get("oblicej"):
        face, zdroj = tuple(upr["oblicej"]), "ručně"
    else:
        face, zdroj = najdi_oblicej(img, maska)
    if zdroj in ("odhad", "stred"):
        varovani.append("obličej nenalezen, ořez je odhadnutý")

    upravena = uprav_barvy(img)

    (OUT / "vyrez").mkdir(parents=True, exist_ok=True)
    (OUT / "portret").mkdir(parents=True, exist_ok=True)
    soubory = {}

    if maska is not None:
        rgba = upravena.convert("RGBA")
        rgba.putalpha(maska)
        rgba = rozpust_rezy(rgba)
        vyrez, scale = umisti_vyrez(rgba, face, VYREZ_W, VYREZ_H, upr)
        if scale > 1.3:
            varovani.append(f"výřez se zvětšuje {scale:.1f}×, může být měkký")
        doostri(vyrez, scale).save(OUT / "vyrez" / f"{slug}.webp", "WEBP", quality=90, method=6)
        soubory["vyrez"] = f"vyrez/{slug}.webp"

    portret, scale_p = orizni_portret(upravena, face, PORTRET, upr)
    portret = doostri(portret, scale_p)
    portret.save(OUT / "portret" / f"{slug}.jpg", "JPEG", quality=88, optimize=True, progressive=True)
    portret.save(OUT / "portret" / f"{slug}.webp", "WEBP", quality=86, method=6)
    soubory["portret_jpg"] = f"portret/{slug}.jpg"
    soubory["portret_webp"] = f"portret/{slug}.webp"
    if scale_p > 1.3:
        varovani.append(f"portrét se zvětšuje {scale_p:.1f}×, může být měkký")

    if img.width < MIN_SIRKA_TISK:
        varovani.append(f"originál má jen {img.width}×{img.height} px, na velký tisk nestačí")

    return {
        "slug": slug,
        "cislo": h.get("cislo"),
        "jmeno": h["jmeno"],
        "pozice": h["pozice"],
        "zdroj": url,
        "originál": [img.width, img.height],
        "oblicej": [round(v) for v in face],
        "oblicej_zdroj": zdroj,
        "soubory": soubory,
        "varovani": varovani,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Zpracování fotek hráčů HC Motor")
    ap.add_argument("--vse", action="store_true", help="přepočítat i nezměněné fotky")
    ap.add_argument("--jen", default="", help="jen vybraní hráči, slugy oddělené čárkou")
    args = ap.parse_args()

    soupiska = nacti_json(SOUPISKA, {})
    hraci = soupiska.get("hraci", [])
    sezona = str(soupiska.get("sezona", "2027"))
    upravy = nacti_json(UPRAVY, {})
    state = nacti_json(STATE, {})
    stary_manifest = {m["slug"]: m for m in nacti_json(OUT / "hraci.json", {}).get("hraci", [])}
    jen = {s.strip() for s in args.jen.split(",") if s.strip()}

    if not hraci:
        # Nic neukládat: prázdný výsledek by přepsal hotové fotky.
        print(f"✗ Soupiska {SOUPISKA.relative_to(ROOT)} chybí nebo je prázdná, končím bez změn.")
        return 1

    print(f"Fotky hráčů: {len(hraci)} na soupisce")
    ze_soupisky = adresy_ze_soupisky()

    manifest, chyby, zpracovano = [], 0, 0
    for h in hraci:
        slug = slug_hrace(h)
        if jen and slug not in jen:
            if slug in stary_manifest:
                manifest.append(stary_manifest[slug])
            continue
        upr = {k: v for k, v in upravy.get(slug, {}).items()}
        hh = dict(h, **({"url": upr["url"]} if upr.get("url") else {}))

        url, data = stahni(kandidati(hh, sezona, ze_soupisky))
        if not data:
            print(f"  ✗ {h['jmeno']}: fotka nenalezena")
            chyby += 1
            manifest.append({"slug": slug, "cislo": h.get("cislo"), "jmeno": h["jmeno"], "pozice": h["pozice"],
                             "zdroj": None, "soubory": {}, "varovani": ["fotka na hcmotor.cz nenalezena, doplň 'url' v soupisce"]})
            continue

        otisk = hashlib.sha1(data + json.dumps(upr, sort_keys=True).encode() + str(VERZE_ZPRACOVANI).encode()).hexdigest()[:12]
        hotovo = (OUT / "portret" / f"{slug}.jpg").exists()
        if not args.vse and state.get(slug) == otisk and hotovo and slug in stary_manifest:
            print(f"  = {h['jmeno']}: beze změny")
            manifest.append(dict(stary_manifest[slug], cislo=h.get("cislo"), jmeno=h["jmeno"], pozice=h["pozice"]))
            continue

        try:
            zaznam = zpracuj(h, slug, url, data, upr)
        except Exception as e:  # jeden vadný hráč nesmí shodit ostatní
            print(f"  ✗ {h['jmeno']}: {e}")
            chyby += 1
            manifest.append({"slug": slug, "cislo": h.get("cislo"), "jmeno": h["jmeno"], "pozice": h["pozice"],
                             "zdroj": url, "soubory": {}, "varovani": [f"zpracování selhalo: {e}"]})
            continue
        zaznam["verze"] = otisk
        manifest.append(zaznam)
        state[slug] = otisk
        zpracovano += 1
        var = f" — {'; '.join(zaznam['varovani'])}" if zaznam["varovani"] else ""
        print(f"  ✓ {h['jmeno']} ({zaznam['oblicej_zdroj']}){var}")

    # hráči, kteří ze soupisky odešli, ze stavu zmizí (soubory zůstanou)
    platne = {slug_hrace(h) for h in hraci}
    state = {k: v for k, v in state.items() if k in platne}

    uloz_json(STATE, state)
    uloz_json(OUT / "hraci.json", {
        "aktualizovano": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sezona": sezona,
        "hraci": manifest,
    })
    data_json = json.dumps(manifest, ensure_ascii=False)
    (OUT / "index.html").write_text(KONTROLA_HTML.replace("__DATA__", data_json), encoding="utf-8")
    plachta = (PLACHTA_HTML.replace("__DATA__", data_json)
               .replace("__SEZONA__", sezona_text(sezona))
               .replace("__STAV__", datetime.now(timezone.utc).astimezone().strftime("%-d. %-m. %Y")))
    (OUT / "plachta.html").write_text(plachta, encoding="utf-8")

    print(f"Hotovo: zpracováno {zpracovano}, chyb {chyby}, celkem {len(manifest)}")
    return 1 if hraci and chyby == len(hraci) else 0


# ---------------------------------------------------------------- kontrolní stránka

KONTROLA_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kontrola fotek hráčů</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,600;0,800;1,800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#0d0f12; --panel:#161a1f; --panel-2:#1e242b; --border:#2a323b;
    --text:#e8ebee; --muted:#8a94a0; --accent:#3fa9f5; --warn:#f5a83f; --bad:#e5534b;
    --gk:#f5a83f; --def:#3fa9f5; --fwd:#e5534b;
    --sans:'IBM Plex Sans', system-ui, sans-serif;
    --mono:'IBM Plex Mono', ui-monospace, monospace;
    --cond:'Barlow Condensed', 'Arial Narrow', sans-serif;
    color-scheme:dark;
  }
  *{box-sizing:border-box;}
  body{margin:0; background:var(--bg); color:var(--text); font:14px/1.4 var(--sans);
       padding:24px max(16px, env(safe-area-inset-right, 0px)) 60px max(16px, env(safe-area-inset-left, 0px));}
  .wrap{max-width:1180px; margin:0 auto;}
  h1{font-size:20px; margin:0; font-weight:600;}
  .sub{font:12px var(--mono); color:var(--muted); margin-top:4px;}
  .bar{display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:18px 0;}
  .pill{font:12px var(--mono); padding:6px 10px; border-radius:20px; background:var(--panel); border:1px solid var(--border);}
  .pill b{color:var(--text);}
  .pill.warn{border-color:var(--warn); color:var(--warn);}
  .bar button{font:500 13px var(--sans); background:var(--panel-2); color:var(--text); border:1px solid var(--border);
              border-radius:8px; padding:7px 12px; cursor:pointer;}
  .bar button[aria-pressed="true"]{border-color:var(--accent); color:var(--accent);}
  .bar button:focus-visible{outline:2px solid var(--accent); outline-offset:2px;}

  .grid{display:grid; grid-template-columns:repeat(auto-fill, minmax(250px, 1fr)); gap:16px;}
  .p{background:var(--panel); border:1px solid var(--border); border-radius:12px; overflow:hidden; min-width:0;}
  .p.G{--pos:var(--gk);} .p.D{--pos:var(--def);} .p.F{--pos:var(--fwd);}

  /* náhled finální karty: výřez + číslo za hráčem */
  .card{position:relative; aspect-ratio:1; overflow:hidden; container-type:inline-size;
        background:radial-gradient(ellipse at 50% 28%, color-mix(in srgb, var(--pos) 55%, #0b0f14) 0%, #0b0f14 72%);}
  .card .num{position:absolute; inset:2% 0 auto; text-align:center; font:800 italic 70cqw/.85 var(--cond);
             color:transparent; -webkit-text-stroke:2px color-mix(in srgb, var(--pos) 70%, #fff); opacity:.55;}
  .card img{position:absolute; inset:0; width:100%; height:100%; object-fit:contain;
            -webkit-mask-image:linear-gradient(to bottom, #000 82%, transparent 100%);
            mask-image:linear-gradient(to bottom, #000 82%, transparent 100%);}
  .card .nm{position:absolute; left:0; right:0; bottom:0; padding:28px 12px 10px;
            background:linear-gradient(to top, rgba(8,11,15,.92), transparent);
            font:800 7.5cqw/1 var(--cond); text-transform:uppercase; color:#fff;}
  .card .nm small{display:block; font:600 4.5cqw/1.2 var(--cond); letter-spacing:.08em; color:var(--pos);}
  .card .none{position:absolute; inset:0; display:grid; place-items:center; font:12px var(--mono); color:var(--muted);}

  .row{display:grid; grid-template-columns:1fr 1fr; gap:1px; background:var(--border);}
  .row figure{margin:0; background:var(--panel-2); position:relative;}
  .row img{display:block; width:100%; aspect-ratio:1; object-fit:cover; object-position:top;}
  .row img.alpha{object-fit:contain; background:repeating-conic-gradient(#2a323b 0 25%, #1e242b 0 50%) 0 0/16px 16px;}
  .row figcaption{position:absolute; left:6px; bottom:6px; font:10px var(--mono); background:rgba(8,11,15,.7); padding:2px 6px; border-radius:4px;}
  .meta{padding:10px 12px 12px; font:11px var(--mono); color:var(--muted); display:flex; flex-direction:column; gap:6px;}
  .meta a{color:var(--accent);}
  .warns{display:flex; flex-direction:column; gap:4px;}
  .warns span{color:var(--warn);}
  .warns span.bad{color:var(--bad);}
  .slug{color:var(--text);}
</style>
</head>
<body>
<div class="wrap">
  <h1>Kontrola fotek hráčů</h1>
  <div class="sub" id="sub"></div>
  <div class="bar" id="bar">
    <span class="pill" id="sum"></span>
    <span class="pill warn" id="wsum"></span>
    <button type="button" id="onlyWarn" aria-pressed="false">Jen s varováním</button>
  </div>
  <div class="grid" id="grid"></div>
</div>
<script>
const DATA = __DATA__;
const POS = {G:'Brankář', D:'Obránce', F:'Útočník'};
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const v = p => p.verze ? '?v=' + p.verze : '';

const grid = document.getElementById('grid');
const withWarn = DATA.filter(p => p.varovani && p.varovani.length).length;
document.getElementById('sum').innerHTML = '<b>' + DATA.filter(p => p.soubory && p.soubory.portret_jpg).length + '</b> / ' + DATA.length + ' zpracováno';
document.getElementById('wsum').textContent = withWarn + ' s varováním';
document.getElementById('sub').textContent = 'Výřez bez pozadí · portrét s pozadím · kliknutím na obrázek otevřeš soubor';

function render(onlyWarn){
  grid.innerHTML = DATA.filter(p => !onlyWarn || (p.varovani && p.varovani.length)).map(p => {
    const f = p.soubory || {};
    const card = f.vyrez
      ? '<img src="' + f.vyrez + v(p) + '" alt="' + esc(p.jmeno) + '" loading="lazy">'
      : '<div class="none">bez výřezu</div>';
    const warns = (p.varovani || []).map(w => '<span class="' + (/nenalezena|selhalo/.test(w) ? 'bad' : '') + '">! ' + esc(w) + '</span>').join('');
    return '<article class="p ' + p.pozice + '">'
      + '<div class="card">' + (p.cislo != null ? '<div class="num">' + p.cislo + '</div>' : '') + card
      + '<div class="nm"><small>' + (p.cislo != null ? '#' + p.cislo + ' · ' : '') + POS[p.pozice] + '</small>' + esc(p.jmeno) + '</div></div>'
      + (!p.zdroj ? '' : '<div class="row">'
      + '<figure>' + (p.zdroj ? '<a href="' + esc(p.zdroj) + '" target="_blank" rel="noopener"><img src="' + esc(p.zdroj) + '" alt="" loading="lazy"></a>' : '') + '<figcaption>originál</figcaption></figure>'
      + '<figure>' + (f.portret_jpg ? '<a href="' + f.portret_jpg + v(p) + '" target="_blank"><img src="' + f.portret_jpg + v(p) + '" alt="" loading="lazy"></a>' : '') + '<figcaption>portrét</figcaption></figure>'
      + '</div>')
      + '<div class="meta"><span class="slug">' + esc(p.slug) + '</span>'
      + (p['originál'] ? '<span>originál ' + p['originál'].join('×') + ' px · obličej: ' + esc(p.oblicej_zdroj) + '</span>' : '')
      + (f.vyrez ? '<span><a href="' + f.vyrez + v(p) + '" target="_blank">výřez</a> · <a href="' + f.portret_webp + v(p) + '" target="_blank">portrét webp</a></span>' : '')
      + (warns ? '<div class="warns">' + warns + '</div>' : '')
      + '</div></article>';
  }).join('');
}
const btn = document.getElementById('onlyWarn');
btn.addEventListener('click', () => {
  const on = btn.getAttribute('aria-pressed') !== 'true';
  btn.setAttribute('aria-pressed', on);
  render(on);
});
render(false);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- plachta

PLACHTA_HTML = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Soupiska HC Motor __SEZONA__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,500;0,600;0,700;0,800;1,800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  /* Plachta: sekce podle pozic, karta = výřez hráče, za hlavou obrys čísla, pod ním jmenovka.
     Barvy z dresu Motoru: žlutá, nebeská modrá z límce, tmavá modrá. */
  :root{
    --night:#08121f;
    --card:#10223a;
    --card-2:#0b182b;
    --ink:#eef3f8;
    --mute:#93a7bd;
    --yellow:#ffd21f;
    --sky:#38b6e8;
    --cond:'Barlow Condensed', 'Arial Narrow', sans-serif;
    --mono:'IBM Plex Mono', ui-monospace, Consolas, monospace;
    color-scheme:dark;
  }
  *{box-sizing:border-box;}
  html{-webkit-text-size-adjust:100%;}
  body{
    margin:0; background:var(--night); color:var(--ink);
    font:14px/1.4 var(--cond);
    padding:28px max(16px, env(safe-area-inset-right, 0px)) 64px max(16px, env(safe-area-inset-left, 0px));
  }
  .wrap{max-width:1240px; margin:0 auto;}

  /* hlavička */
  .top{display:flex; justify-content:space-between; align-items:flex-end; gap:16px 24px; flex-wrap:wrap; margin-bottom:26px;}
  .kicker{font:500 11px/1 var(--mono); letter-spacing:.16em; text-transform:uppercase; color:var(--yellow);}
  h1{margin:8px 0 0; font:800 34px/1 var(--cond); text-transform:uppercase; letter-spacing:.01em;}
  h1 span{color:var(--sky);}
  .sub{margin-top:6px; font:400 12px/1.3 var(--mono); color:var(--mute);}
  .sub b{color:var(--ink); font-weight:500;}

  .tools{display:flex; gap:10px; flex-wrap:wrap; align-items:center;}
  .seg{display:flex; background:var(--card-2); border:1px solid #1d3352; border-radius:8px; padding:3px;}
  .seg button, .print{
    font:600 14px/1 var(--cond); letter-spacing:.06em; text-transform:uppercase;
    color:var(--mute); background:none; border:0; border-radius:6px; padding:8px 12px; cursor:pointer;
  }
  .seg button[aria-pressed="true"]{background:var(--yellow); color:var(--night);}
  .seg button:hover:not([aria-pressed="true"]){color:var(--ink);}
  .print{background:var(--card); border:1px solid #1d3352; color:var(--ink); padding:11px 14px;}
  .print:hover{border-color:var(--yellow);}
  button:focus-visible{outline:2px solid var(--sky); outline-offset:2px;}

  /* sekce */
  .grp + .grp{margin-top:30px;}
  .grp h2{display:flex; align-items:baseline; gap:10px; margin:0 0 12px; font:700 22px/1 var(--cond); text-transform:uppercase; letter-spacing:.05em;}
  .grp h2 em{font:400 12px/1 var(--mono); font-style:normal; color:var(--mute); letter-spacing:0;}
  .grp h2::after{content:""; flex:1; height:2px; align-self:center; background:linear-gradient(90deg, var(--yellow), transparent 70%);}
  .grid{display:grid; grid-template-columns:repeat(auto-fill, minmax(168px, 1fr)); gap:12px;}

  /* karta */
  .pl{background:var(--card-2); color:var(--ink); border-radius:4px; overflow:hidden; container-type:inline-size; min-width:0;}
  .ph{
    position:relative; aspect-ratio:1; overflow:hidden;
    background:
      radial-gradient(circle at 50% 42%, rgba(56,182,232,.28), transparent 62%),
      linear-gradient(180deg, #14304f, var(--card));
  }
  .ph .num{
    position:absolute; right:-3cqw; top:-9cqw;
    font:800 italic 82cqw/1 var(--cond); letter-spacing:-.05em;
    color:transparent; -webkit-text-stroke:1.5px rgba(56,182,232,.5);
    user-select:none;
  }
  .ph img{position:absolute; inset:0; width:100%; height:100%; object-fit:cover; display:block; transition:transform .35s ease; transform-origin:50% 100%;}
  .pl:hover .ph img{transform:scale(1.03);}
  .foto-portret .ph .num{display:none;}
  .ph .none{position:absolute; inset:0; display:grid; place-items:center; font:400 11px var(--mono); color:var(--mute);}

  .nm{border-top:3px solid var(--yellow); padding:6cqw 7cqw 6.5cqw;}
  .fi{display:block; font:600 7cqw/1.05 var(--cond); letter-spacing:.1em; text-transform:uppercase; color:var(--mute); overflow-wrap:anywhere;}
  .la{display:block; margin-top:1.5cqw; font:800 13cqw/.95 var(--cond); text-transform:uppercase; overflow-wrap:anywhere;}
  .mt{display:flex; justify-content:space-between; align-items:baseline; margin-top:4.5cqw; font:500 5.4cqw/1 var(--mono); color:var(--mute); text-transform:uppercase; letter-spacing:.04em;}
  .mt b{font:800 italic 8cqw/1 var(--cond); color:var(--yellow); letter-spacing:0;}

  @media (max-width:420px){
    h1{font-size:28px;}
    .grid{grid-template-columns:repeat(2, minmax(0, 1fr)); gap:10px;}
  }
  @media (prefers-reduced-motion:reduce){ .ph img{transition:none;} }

  /* tisk: A4 na výšku, 8 karet vedle sebe, celá soupiska na jedné stránce */
  @media print{
    @page{size:A4; margin:9mm;}
    body{background:#fff; color:#08121f; padding:0;}
    .tools{display:none;}
    .top{margin-bottom:4mm; padding-top:1mm;}
    h1{font-size:20pt;}
    .sub{color:#555;} .sub b{color:#08121f;}
    .kicker{color:#08121f;}
    .grp + .grp{margin-top:5mm;}
    .grp h2{font-size:12pt; margin-bottom:2.5mm; color:#08121f;}
    .grp h2 em{color:#555;}
    .grid{grid-template-columns:repeat(8, 1fr); gap:2mm;}
    .pl{break-inside:avoid;}
    .pl, .ph, .grp h2::after{-webkit-print-color-adjust:exact; print-color-adjust:exact;}
    .pl:hover .ph img{transform:none;}
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <div class="kicker">HC Motor České Budějovice</div>
      <h1>Soupiska <span>__SEZONA__</span></h1>
      <div class="sub">A-tým · <b id="count"></b> · stav k __STAV__</div>
    </div>
    <div class="tools">
      <div class="seg" role="group" aria-label="Pozice" id="segPos">
        <button type="button" data-pos="" aria-pressed="true">Všichni</button>
        <button type="button" data-pos="G" aria-pressed="false">Brankáři</button>
        <button type="button" data-pos="D" aria-pressed="false">Obránci</button>
        <button type="button" data-pos="F" aria-pressed="false">Útočníci</button>
      </div>
      <div class="seg" role="group" aria-label="Fotka" id="segFoto">
        <button type="button" data-foto="vyrez" aria-pressed="true">Výřez</button>
        <button type="button" data-foto="portret" aria-pressed="false">Portrét</button>
      </div>
      <button type="button" class="print" id="print">Tisk / PDF</button>
    </div>
  </header>
  <main id="roster"></main>
</div>
<script>
const DATA = __DATA__;
const SKUPINY = [['G', 'Brankáři'], ['D', 'Obránci'], ['F', 'Útočníci']];
const POZICE = {G:'Brankář', D:'Obránce', F:'Útočník'};
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const hraci = DATA.slice().sort((a, b) => (a.cislo ?? 999) - (b.cislo ?? 999));

let stav = {pos:'', foto:'vyrez'};
try { stav.foto = localStorage.getItem('plachta-foto') || 'vyrez'; } catch (e) {}

function karta(p){
  const f = p.soubory || {};
  const v = p.verze ? '?v=' + p.verze : '';
  const src = stav.foto === 'vyrez' && f.vyrez ? f.vyrez : f.portret_jpg;
  const casti = p.jmeno.trim().split(/\\s+/);
  const prijmeni = casti.pop();
  const cislo = p.cislo != null ? p.cislo : '';
  return '<article class="pl">'
    + '<div class="ph">'
    + (cislo !== '' && stav.foto === 'vyrez' && f.vyrez ? '<span class="num" aria-hidden="true">' + cislo + '</span>' : '')
    + (src ? '<img src="' + src + v + '" alt="' + esc(p.jmeno) + '" loading="lazy">' : '<div class="none">bez fotky</div>')
    + '</div>'
    + '<div class="nm"><span class="fi">' + esc(casti.join(' ')) + '</span><span class="la">' + esc(prijmeni) + '</span>'
    + '<div class="mt"><span>' + POZICE[p.pozice] + '</span>' + (cislo !== '' ? '<b>#' + cislo + '</b>' : '') + '</div></div>'
    + '</article>';
}

function vykresli(){
  document.body.classList.toggle('foto-portret', stav.foto === 'portret');
  document.getElementById('roster').innerHTML = SKUPINY
    .filter(([pos]) => !stav.pos || stav.pos === pos)
    .map(([pos, nazev]) => {
      const lide = hraci.filter(p => p.pozice === pos);
      if (!lide.length) return '';
      return '<section class="grp"><h2>' + nazev + '<em>' + lide.length + '</em></h2>'
        + '<div class="grid">' + lide.map(karta).join('') + '</div></section>';
    }).join('');
  document.querySelectorAll('#segPos button').forEach(b => b.setAttribute('aria-pressed', b.dataset.pos === stav.pos));
  document.querySelectorAll('#segFoto button').forEach(b => b.setAttribute('aria-pressed', b.dataset.foto === stav.foto));
}

document.getElementById('count').textContent = hraci.length + ' hráčů';
document.getElementById('segPos').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  stav.pos = b.dataset.pos; vykresli();
});
document.getElementById('segFoto').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  stav.foto = b.dataset.foto;
  try { localStorage.setItem('plachta-foto', stav.foto); } catch (e) {}
  vykresli();
});
document.getElementById('print').addEventListener('click', () => window.print());
vykresli();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
