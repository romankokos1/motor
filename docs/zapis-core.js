// Společný kód stránek sestavy.html a reportaz.html (čtení zápisu, jména, texty).
// Upravuje se jen tady; obě stránky ho načítají.

// ===== Nastavení (uprav podle potřeby) =====================================

// Stálé výjimky ve jménech — klíč „Příjmení Jméno“ (jak je v zápisu),
// hodnota = přesně to, co se vypíše. Mají přednost před automatickými iniciálami.
const JMENA = {
  "Nedorost Václav": "V. Nedorost ml.",
  "Vrbata David": "D. Vrbata",
  "Hořava Miloslav": "M. Hořava mladší",
  "Šťastný David": "D. Šťastný",
};

// Krátké názvy týmů — první shoda s oficiálním názvem v zápisu vyhrává.
const TYMY = [
  [/motor|budějovice/i, "Motor"],
  [/sparta/i, "Sparta"],
  [/pardubice|dynamo/i, "Pardubice"],
  [/třinec|oceláři/i, "Třinec"],
  [/vítkovice/i, "Vítkovice"],
  [/plzeň|škoda/i, "Plzeň"],
  [/liberec|tygři/i, "Liberec"],
  [/hradec|mountfield/i, "Hradec"],
  [/kometa|brno/i, "Kometa"],
  [/olomouc/i, "Olomouc"],
  [/litvínov|verva/i, "Litvínov"],
  [/kladno|rytíři/i, "Kladno"],
  [/boleslav/i, "Ml. Boleslav"],
  [/vary|energie/i, "Vary"],
  [/zlín|berani/i, "Zlín"],
  [/jihlava|dukla/i, "Jihlava"],
];

// Tvary názvů soupeřů pro úvod a titulky:
// s = s kým, v = kde (plný název), acc = koho (porazil), dat = komu (podlehl),
// ins = čím (výhra nad), vk = kde (krátce, do titulku)
const TVARY = {
  "Sparta":       { s: "se Spartou", v: "na Spartě", acc: "Spartu", dat: "Spartě", ins: "Spartou", vk: "na Spartě" },
  "Pardubice":    { s: "s Pardubicemi", v: "v Pardubicích", acc: "Pardubice", dat: "Pardubicím", ins: "Pardubicemi", vk: "v Pardubicích" },
  "Třinec":       { s: "s Třincem", v: "v Třinci", acc: "Třinec", dat: "Třinci", ins: "Třincem", vk: "v Třinci" },
  "Vítkovice":    { s: "s Vítkovicemi", v: "ve Vítkovicích", acc: "Vítkovice", dat: "Vítkovicím", ins: "Vítkovicemi", vk: "ve Vítkovicích" },
  "Plzeň":        { s: "s Plzní", v: "v Plzni", acc: "Plzeň", dat: "Plzni", ins: "Plzní", vk: "v Plzni" },
  "Liberec":      { s: "s Libercem", v: "v Liberci", acc: "Liberec", dat: "Liberci", ins: "Libercem", vk: "v Liberci" },
  "Hradec":       { s: "s Hradcem Králové", v: "v Hradci Králové", acc: "Hradec", dat: "Hradci", ins: "Hradcem", vk: "v Hradci" },
  "Kometa":       { s: "s Kometou", v: "v Brně", acc: "Kometu", dat: "Kometě", ins: "Kometou", vk: "v Brně" },
  "Olomouc":      { s: "s Olomoucí", v: "v Olomouci", acc: "Olomouc", dat: "Olomouci", ins: "Olomoucí", vk: "v Olomouci" },
  "Litvínov":     { s: "s Litvínovem", v: "v Litvínově", acc: "Litvínov", dat: "Litvínovu", ins: "Litvínovem", vk: "v Litvínově" },
  "Kladno":       { s: "s Kladnem", v: "na Kladně", acc: "Kladno", dat: "Kladnu", ins: "Kladnem", vk: "na Kladně" },
  "Ml. Boleslav": { s: "s Mladou Boleslaví", v: "v Mladé Boleslavi", acc: "Boleslav", dat: "Boleslavi", ins: "Boleslaví", vk: "v Boleslavi" },
  "Vary":         { s: "s Karlovými Vary", v: "v Karlových Varech", acc: "Vary", dat: "Varům", ins: "Vary", vk: "ve Varech" },
  "Zlín":         { s: "se Zlínem", v: "ve Zlíně", acc: "Zlín", dat: "Zlínu", ins: "Zlínem", vk: "ve Zlíně" },
  "Jihlava":      { s: "s Jihlavou", v: "v Jihlavě", acc: "Jihlavu", dat: "Jihlavě", ins: "Jihlavou", vk: "v Jihlavě" },
};
const tvary = opp => TVARY[opp] || { s: `s ${opp}`, v: `v ${opp}`, acc: opp, dat: opp, ins: opp, vk: `v ${opp}` };

const ZAPIS_URL = id => `https://hokejovyzapis.cz/pdf/print/cs-html/?hokejczId=${id}`;
const DATA_URL = "sestavy-data.json";

// ===== Pomocné ==============================================================

const $ = id => document.getElementById(id);
const clean = t => (t || "").replace(/\s+/g, " ").trim();
const cellEls = tr => [...tr.children].filter(c => /^T[DH]$/.test(c.tagName));
const cells = tr => cellEls(tr).map(c => clean(c.textContent));
const isUpperTok = t => /\p{Lu}/u.test(t) && t === t.toLocaleUpperCase("cs");
const lc = s => (s || "").toLocaleLowerCase("cs");

function properCase(tok) {
  return tok.toLocaleLowerCase("cs")
    .replace(/(^|[-'’])(\p{L})/gu, (m, p, ch) => p + ch.toLocaleUpperCase("cs"))
    .replace(/^Mc(\p{L})/u, (m, ch) => "Mc" + ch.toLocaleUpperCase("cs"));
}

// „KLOUČEK Milan“ -> {prijmeni: "Klouček", jmeno: "Milan"}; „Klouček Milan“ -> totéž
function splitPlayer(raw) {
  const toks = clean(raw).split(" ");
  const sur = [];
  while (toks.length && isUpperTok(toks[0])) sur.push(properCase(toks.shift()));
  if (!sur.length && toks.length) sur.push(toks.shift());
  return { prijmeni: sur.join(" "), jmeno: toks.join(" ") };
}

// „Róbert Petrovický“ / „Miloslav Hořava ml.“ -> {prijmeni, jmeno, pripona}
function splitCoach(raw) {
  const toks = clean(raw).split(" ");
  let pripona = "";
  if (toks.length > 2 && /^(ml\.?|st\.?|mladší|starší|jr\.?|sr\.?)$/i.test(toks[toks.length - 1])) pripona = toks.pop();
  const prijmeni = toks.pop() || "";
  return { prijmeni, jmeno: toks.join(" "), pripona };
}

function shortTeam(nazev) {
  for (const [re, kratce] of TYMY) if (re.test(nazev)) return kratce;
  return nazev;
}
const isMotor = nazev => shortTeam(nazev) === "Motor";

function joinCs(list) {
  return list.length < 2 ? list.join("") : list.slice(0, -1).join(", ") + " a " + list[list.length - 1];
}

function toSec(t) {
  const m = /^(\d+):(\d\d)$/.exec(clean(t));
  return m ? +m[1] * 60 + +m[2] : null;
}
const minuteOfSec = s => Math.floor(s / 60) + 1;
const minuteOf = t => { const s = toSec(t); return s === null ? null : minuteOfSec(s); };

const chunk = (arr, n) => { const out = []; for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n)); return out; };

function pair(t) {
  const m = /^\s*(\d+)\s*:\s*(\d+)/.exec(t || "");
  return m ? [+m[1], +m[2]] : null;
}

// Text buňky po řádcích (<br> a blokové prvky = nový řádek)
function cellLines(el) {
  const c = el.cloneNode(true);
  c.querySelectorAll("br").forEach(b => b.replaceWith("\n"));
  c.querySelectorAll("div, p, tr, li").forEach(b => b.append("\n"));
  return c.textContent.split("\n").map(clean).filter(Boolean);
}

// ===== Model zápasu ==========================================================
// { A: tým, B: tým, goly, tresty, rozhodci, divaci, strely, najezdy, jeZapis }
// tým = { nazev, hraci: [{c, jmeno, post, hral}], brankari: [{c, od}], lavicka: [{jmeno, funkce}] }
// goly = [{side, sec, strelec, asist: [], sit}]  (jména v podobě ze soupisky)
// tresty = [{side, min, hrac}], najezdy = [{side, strelec, gol}]

const emptyTeam = nazev => ({ nazev, hraci: [], brankari: [], lavicka: [] });
const ok = r => r && r.A.hraci.length && r.B.hraci.length;

// Z denních dat (sestavy-data.json): jména gólů jsou ve tvaru „Příjmení Jméno“
function modelFromData(g) {
  const s = g.sestava;
  const m = { A: s.A, B: s.B, goly: [], tresty: [], rozhodci: { hlavni: [], carovi: [] },
              divaci: "", strely: null, najezdy: [], jeZapis: !!g.zapis };
  if (!g.zapis) return m;
  const z = g.zapis;
  const side = tym => (tym === s.A.nazev ? "A" : "B");
  const index = {};
  ["A", "B"].forEach(sd => s[sd].hraci.forEach(h => {
    const p = splitPlayer(h.jmeno);
    index[sd + "|" + lc(`${p.prijmeni} ${p.jmeno}`)] = h.jmeno;
  }));
  const raw = (sd, name) => index[sd + "|" + lc(name)] || name;
  m.goly = z.goly.map(x => {
    const sd = side(x.tym);
    return { side: sd, sec: x.vteriny, strelec: raw(sd, x.strelec), asist: (x.asistence || []).map(a => raw(sd, a)), sit: x.situace };
  });
  m.tresty = z.tresty.map(t => {
    const sd = side(t.tym);
    return { side: sd, min: t.min, sec: t.vteriny, hrac: /lavička/.test(t.hrac) ? "" : raw(sd, t.hrac) };
  });
  m.rozhodci = z.rozhodci || m.rozhodci;
  m.divaci = z.divaci;
  m.strely = sumShots(z.tretiny || []);
  m.tretiny = z.tretiny || [];
  m.najezdy = (z.najezdy || []).map(p => { const sd = side(p.tym); return { side: sd, strelec: raw(sd, p.strelec), gol: p.gol }; });
  return m;
}

function sumShots(tretiny) {
  const rows = tretiny.filter(r => ["1", "2", "3", "P"].includes(r.tretina));
  if (!rows.length) return null;
  return rows.reduce((a, r) => [a[0] + r.strely[0], a[1] + r.strely[1]], [0, 0]);
}

// ===== Parsování HTML zápisu (stažený zápis nebo schránka) ==================
// Prohlížeč při kopírování často zahodí CSS třídy, proto se soupiska, góly
// i tresty čtou podle hlavičky tabulky a pořadí sloupců. Sloupce se počítají
// od konce řádku, protože jméno bývá ve vnořené tabulce s C/A.

const TEAM_COLS = ["čas", "S", "A1", "A2", "HS", "P1", "P2", "P3", "P4", "P5", "P6",
                   "N1", "N2", "N3", "N4", "N5", "N6", "čas", "č.", "Min.", "důvod", "Od", "Do"];

function parseZapis(html, text) {
  if (html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const r = parseTeams(doc);
    if (ok(r)) { addRest(doc, r); return r; }
  }
  if (text) {
    const r = parseText(text);
    if (ok(r)) return r;
  }
  return null;
}

const notAttended = el => {
  for (let e = el; e && e.tagName !== "TR"; e = e.parentElement) {
    if (/not_attended/.test(e.className || "")) return true;
    if (/line-through/.test((e.getAttribute && e.getAttribute("style")) || "")) return true;
  }
  return !!el.querySelector?.("[class*=not_attended], [style*=line-through]");
};

function teamLabels(doc) {
  const out = {};
  for (const td of doc.querySelectorAll("td, th")) {
    const t = clean(td.textContent);
    const side = /^Domácí tým \(A\)$/.test(t) ? "A" : /^Hostující tým \(B\)$/.test(t) ? "B" : null;
    if (side && !out[side]) {
      const next = td.nextElementSibling;
      out[side] = next ? clean(next.textContent).replace(/\s+\d+\s*$/, "") : "";
    }
  }
  return out;
}

function parseTeams(doc) {
  const headers = [...doc.querySelectorAll("tr")].filter(tr => {
    const c = cells(tr);
    return c.includes("A1") && c.includes("HS") && c.includes("důvod");
  });
  if (headers.length < 2) return null;
  const labels = teamLabels(doc);
  const res = { goly: [], tresty: [], rozhodci: { hlavni: [], carovi: [] }, divaci: "", strely: null, najezdy: [], jeZapis: true };
  const goalsByNo = { A: [], B: [] }, pensByNo = { A: [], B: [] };

  headers.slice(0, 2).forEach((htr, k) => {
    const side = k ? "B" : "A";
    const hc = cells(htr);
    const tail = hc.slice(-TEAM_COLS.length);
    if (tail.join("|") !== TEAM_COLS.join("|")) console.warn("Neočekávané sloupce zápisu:", hc);
    const table = htr.closest("table");
    const named = table.querySelector("td.team_name");
    const nazev = labels[side] || (named ? clean(named.textContent).replace(/\s+\d+\s*$/, "") : (k ? "Hosté" : "Domácí"));
    const team = emptyTeam(nazev);
    const rows = [...table.rows];
    for (const tr of rows.slice(rows.indexOf(htr) + 1)) {
      const els = cellEls(tr);
      if (els.length < TEAM_COLS.length) continue;
      const v = els.map(e => clean(e.textContent));
      const R = i => v[v.length - TEAM_COLS.length + i];   // i = index v TEAM_COLS
      const post = v[v.length - TEAM_COLS.length - 1];
      const no = v[0];
      if (/^\d{1,3}$/.test(no) && /^(GK|D|F)$/.test(post)) {
        const nameEl = els[1];
        const inner = nameEl.querySelector("td");
        const jmeno = clean((inner || nameEl).textContent).replace(/(\s+[CAJ])+$/, "");
        if (jmeno) team.hraci.push({ c: no, jmeno, post, hral: !notAttended(nameEl) });
      }
      if (toSec(R(0)) !== null && R(1)) {
        goalsByNo[side].push({ sec: toSec(R(0)), s: R(1), a: [R(2), R(3)].filter(Boolean), sit: R(4) });
      }
      if (toSec(R(17)) !== null && R(20)) {
        pensByNo[side].push({ min: R(19), no: R(18), sec: toSec(R(17)) });
      }
    }
    res[side] = team;
  });
  if (!ok(res)) return res;

  const nameOf = (side, no) => (res[side].hraci.find(h => h.c === no) || {}).jmeno || (no ? `č. ${no}` : "");
  ["A", "B"].forEach(side => {
    goalsByNo[side].forEach(g => res.goly.push({ side, sec: g.sec, strelec: nameOf(side, g.s), asist: g.a.map(n => nameOf(side, n)), sit: g.sit }));
    pensByNo[side].forEach(p => res.tresty.push({ side, min: p.min, sec: p.sec, hrac: p.no === "HL" ? "" : nameOf(side, p.no) }));
  });
  res.goly.sort((a, b) => a.sec - b.sec);
  return res;
}

function rowsAfter(headerTr) {
  const rows = [...headerTr.closest("table").rows];
  return rows.slice(rows.indexOf(headerTr) + 1);
}

function addRest(doc, out) {
  const trs = [...doc.querySelectorAll("tr")];
  // střídání brankářů
  for (const tr of trs) {
    const c = cells(tr);
    if (c[0] === "čas" && c[1] === "BA" && c[2] === "BB") {
      const gk = { A: [], B: [] };
      for (const row of rowsAfter(tr).map(cells)) {
        if (toSec(row[0] || "") === null) continue;
        [["A", row[1]], ["B", row[2]]].forEach(([s, no]) => {
          if (/^\d+$/.test(no || "") && (!gk[s].length || gk[s][gk[s].length - 1].c !== no)) gk[s].push({ c: no, od: row[0] });
        });
      }
      if (gk.A.length || gk.B.length) { out.A.brankari = gk.A; out.B.brankari = gk.B; break; }
    }
  }
  // lavička (trenéři)
  const sides = ["A", "B"];
  for (const tr of trs) {
    const c = cells(tr);
    if (c[0] === "Příjmení, jméno" && c[1] === "Funkce") {
      const s = sides.shift();
      if (!s) break;
      out[s].lavicka = rowsAfter(tr).map(cells).filter(r => r[0] && r[1]).map(r => ({ jmeno: r[0], funkce: r[1] }));
    }
  }
  // souhrn po třetinách → střely
  for (const tr of trs) {
    if (cells(tr)[0] !== "Třetina") continue;
    const tret = [];
    for (const r of rowsAfter(tr).map(cells)) {
      if (!["1", "2", "3", "P", "SN"].includes(r[0])) continue;
      const g = pair(r[1]), st = pair(r[2]);
      if (g || st) tret.push({ tretina: r[0], goly: g || [0, 0], strely: st || [0, 0] });
    }
    out.strely = sumShots(tret);
    out.tretiny = tret;
    break;
  }
  // rozhodčí
  for (const td of doc.querySelectorAll("td")) {
    const lines = cellLines(td);
    if (lines.length < 2) continue;
    const role = lc(lines[0]);
    const key = role === "hlavní rozhodčí" ? "hlavni" : role === "čárový rozhodčí" ? "carovi" : null;
    if (key && !out.rozhodci[key].includes(lines[1]) && !/^potvrdil/i.test(lines[1])) out.rozhodci[key].push(lines[1]);
  }
  // diváci
  const sp = doc.querySelector("td.value_spectators");
  if (sp) out.divaci = clean(sp.textContent);
  else {
    for (const td of doc.querySelectorAll("td, th")) {
      const lines = cellLines(td);
      if (!lines.length || !/^počet diváků/i.test(lines[0])) continue;
      const inCell = lines.slice(1).find(l => /^\d[\d\s]*$/.test(l));
      if (inCell) { out.divaci = inCell; break; }
      const tr = td.parentElement, idx = cellEls(tr).indexOf(td);
      const below = tr.nextElementSibling && cellEls(tr.nextElementSibling)[idx];
      const right = td.nextElementSibling;
      const cand = [below, right].map(e => e && clean(e.textContent)).find(t => /^\d[\d\s]*$/.test(t || ""));
      if (cand) { out.divaci = cand; break; }
    }
  }
  // samostatné nájezdy: A | B | BA | BB | A:B (stav po kole), skupiny po 5 sloupcích
  for (const tr of trs) {
    const c = cells(tr);
    if (c.length < 5 || c.slice(0, 5).join("|") !== "A|B|BA|BB|A:B") continue;
    const groups = Math.floor(c.length / 5);
    const rows = rowsAfter(tr).map(cells);
    const kola = [];
    for (let gi = 0; gi < groups; gi++) for (const r of rows) {
      const ch = r.slice(gi * 5, gi * 5 + 5);
      if (ch.length === 5 && (ch[0] || ch[1])) kola.push(ch);
    }
    let prev = [0, 0];
    const nm = (side, no) => (out[side].hraci.find(h => h.c === no) || {}).jmeno || `č. ${no}`;
    for (const [a, b, , , ab] of kola) {
      const sc = pair(ab) || prev;
      if (a) out.najezdy.push({ side: "A", strelec: nm("A", a), gol: sc[0] > prev[0] });
      if (b) out.najezdy.push({ side: "B", strelec: nm("B", b), gol: sc[1] > prev[1] });
      prev = sc;
    }
    break;
  }
}

// Záloha: čistý text bez HTML — jen soupisky a trenéři
function parseText(text) {
  const t = text.replace(/ /g, " ");
  const cut = t.search(/Hostující tým \(B\)/);
  const res = { A: emptyTeam("Domácí"), B: emptyTeam("Hosté"), goly: [], tresty: [],
                rozhodci: { hlavni: [], carovi: [] }, divaci: "", strely: null, najezdy: [], jeZapis: false };
  const mA = /Domácí tým \(A\)\s*([^\n\t]+)/.exec(t), mB = /Hostující tým \(B\)\s*([^\n\t]+)/.exec(t);
  if (mA) res.A.nazev = clean(mA[1]).replace(/\s+\d+\s*$/, "");
  if (mB) res.B.nazev = clean(mB[1]).replace(/\s+\d+\s*$/, "");
  const re = /(?:^|\s)(\d{1,3})\s+(\p{Lu}[\p{Lu}'’\- ]*\p{Lu}\s+[^\t\n\d]*?)\s+(\d{10})\s+(GK|D|F)(?=\s|$)/gu;
  let m;
  while ((m = re.exec(t))) {
    const side = cut >= 0 && m.index > cut ? "B" : "A";
    res[side].hraci.push({ c: m[1], jmeno: clean(m[2]).replace(/(\s+[CAJ])+$/, ""), post: m[4], hral: true });
  }
  const blocks = t.split(/Příjmení, jméno\s+Funkce/).slice(1, 3);
  blocks.forEach((blk, k) => {
    for (const line of blk.split(/\n/)) {
      const p = line.split(/\t+/).map(clean).filter(Boolean);
      if (p.length >= 2 && /trenér|asist/i.test(p[1])) res[k ? "B" : "A"].lavicka.push({ jmeno: p[0], funkce: p[1] });
      if (/Hostující tým|Hlavní pořadatel|Rozhodčí/.test(line)) break;
    }
  });
  return res;
}

// ===== Jména (společné pro sestavy i zápis) =================================

function makeNamer(m) {
  const count = {};
  const bump = p => { const k = lc(p.prijmeni); count[k] = (count[k] || 0) + 1; };
  const people = { A: {}, B: {} };
  ["A", "B"].forEach(side => {
    const t = m[side];
    t.hraci.filter(h => h.hral || h.post === "GK").forEach(h => bump(splitPlayer(h.jmeno)));
    coachesOf(t).forEach(bump);
  });
  const display = (p, extra = "") => {
    const alias = JMENA[`${p.prijmeni} ${p.jmeno}`.trim()];
    if (alias) return alias;
    const dup = count[lc(p.prijmeni)] > 1 && p.jmeno;
    return (dup ? p.jmeno[0] + ". " : "") + p.prijmeni + (extra ? " " + extra : "");
  };
  return { pl: raw => (raw ? display(splitPlayer(raw)) : "lavička"), coach: c => display(c, c.pripona) };
}

function coachesOf(t) {
  const lav = t.lavicka || [];
  const head = lav.filter(o => /hlavní\s*trenér/i.test(o.funkce)).map(o => ({ ...splitCoach(o.jmeno), head: true }));
  const asst = lav.filter(o => /asist/i.test(o.funkce)).map(o => ({ ...splitCoach(o.jmeno), head: false }))
    .sort((a, b) => a.prijmeni.localeCompare(b.prijmeni, "cs"));
  return [...head, ...asst];
}

// ===== Sestavy ==============================================================
// Brankář (náhradník v závorce, při střídání s minutou) – obránci po dvojicích
// – útočníci po trojicích (13. útočník jako další útok). Trenéři.
// Uvnitř dvojic a trojic se pořadí ze zápisu obrací (Štencel, Kundrátek → Kundrátek, Štencel).

function buildLines(m, namer, motorFirst) {
  let out = ["A", "B"].map(side => {
    const t = m[side];
    const byNo = Object.fromEntries(t.hraci.map(h => [h.c, h]));
    const goalies = t.hraci.filter(h => h.post === "GK");
    const changes = (t.brankari || []).filter(b => byNo[b.c]);
    const starter = changes.length ? byNo[changes[0].c] : (goalies.find(h => h.hral) || goalies[0]);
    const enter = {};
    changes.slice(1).forEach(b => { if (b.c !== changes[0].c && !(b.c in enter)) enter[b.c] = minuteOf(b.od); });
    const others = goalies.filter(h => h !== starter)
      .sort((a, b) => (a.c in enter ? 0 : 1) - (b.c in enter ? 0 : 1))
      .map(h => (h.c in enter ? `${enter[h.c]}. ` : "") + namer.pl(h.jmeno));
    let gk = starter ? namer.pl(starter.jmeno) : "?";
    if (others.length) gk += ` (${others.join(", ")})`;

    const played = t.hraci.filter(h => h.hral);
    const obr = played.filter(h => h.post === "D").map(h => namer.pl(h.jmeno));
    const uto = played.filter(h => h.post === "F").map(h => namer.pl(h.jmeno));
    // zápis vede formace zprava doleva, v textu se píšou obráceně
    const grp = (arr, n) => chunk(arr, n).map(g => g.slice().reverse().join(", "));
    const parts = [gk, ...grp(obr, 2), ...grp(uto, 3)];

    const coachNames = coachesOf(t).map(namer.coach);
    const trener = coachNames.length === 0 ? "" : (coachNames.length === 1 ? " Trenér " : " Trenéři ") + joinCs(coachNames) + ".";
    const text = `${shortTeam(t.nazev)}: ${parts.join(" – ")}.${trener}`;

    const nehrali = t.hraci.filter(h => !h.hral && h.post !== "GK").map(h => namer.pl(h.jmeno));
    return { nazev: t.nazev, text, check: { gk: goalies.length, d: obr.length, f: uto.length, nehrali, trenéři: coachNames.length } };
  });
  if (motorFirst && !isMotor(out[0].nazev) && isMotor(out[1].nazev)) out = [out[1], out[0]];
  return out;
}

// ===== Zápis utkání =========================================================

// „5/4“ z pohledu střílejícího týmu; hráči nad 5 (power play bez brankáře) se nepočítají
function strength(sit) {
  const mm = /(\d)\s*\/\s*(\d)/.exec(sit || "");
  if (!mm) return "ev";
  const a = Math.min(+mm[1], 5), b = Math.min(+mm[2], 5);
  return a > b ? "pp" : a < b ? "sh" : "ev";
}

function buildReport(m, namer, bold) {
  const warn = [];
  const parts = [];
  const L = label => (bold ? `<b>${label}:</b>` : `${label}:`);
  const goly = [...m.goly].sort((a, b) => a.sec - b.sec);

  const goalTxt = side => goly.filter(g => g.side === side).map(g => `${minuteOfSec(g.sec)}. ${namer.pl(g.strelec)}` +
    (g.asist.length ? ` (${g.asist.map(namer.pl).join(", ")})` : "")).join(", ");
  // tým bez gólu se nevypisuje: „Branky a nahrávky: 5. X, 20. Y.“ / „Branky a nahrávky: – 10. Z.“
  const ga = goalTxt("A"), gb = goalTxt("B");
  if (ga || gb) parts.push(`${L("Branky a nahrávky")} ${ga}${gb ? (ga ? " – " : "– ") + gb : ""}.`);

  if (m.najezdy.length) {
    const sa = m.najezdy.filter(p => p.side === "A" && p.gol).length;
    const sb = m.najezdy.filter(p => p.side === "B" && p.gol).length;
    const win = sa > sb ? "A" : "B";
    const last = m.najezdy.filter(p => p.side === win && p.gol).pop();
    if (last) parts.push(`${L("Rozhodující nájezd")} ${namer.pl(last.strelec)}.`);
  }

  const lastName = n => clean(n.replace(/\([^)]*\)/g, "")).split(" ").pop();
  const hl = (m.rozhodci.hlavni || []).map(lastName), car = (m.rozhodci.carovi || []).map(lastName);
  if (hl.length) parts.push(`${L("Rozhodčí")} ${hl.join(", ")}${car.length ? " – " + car.join(", ") : ""}.`);
  else warn.push("v zápisu nejsou rozhodčí");

  const pen = { A: 0, B: 0 }, navic = [];
  m.tresty.forEach(t => {
    const mins = parseInt(t.min, 10);
    if (mins === 2 || mins === 5) pen[t.side] += 1;
    else if (mins === 4) pen[t.side] += 2;
    else if (mins >= 10) navic.push(`${namer.pl(t.hrac)} (${shortTeam(m[t.side].nazev)}) ${mins} min`);
  });
  parts.push(`${L("Vyloučení")} ${pen.A}:${pen.B}${navic.length ? ", navíc " + navic.join(", ") : ""}.`);

  const cnt = { pp: { A: 0, B: 0 }, sh: { A: 0, B: 0 } };
  goly.forEach(g => { const s = strength(g.sit); if (s !== "ev") cnt[s][g.side] += 1; });
  parts.push(`${L("Využití")} ${cnt.pp.A}:${cnt.pp.B}.`);
  parts.push(`${L("V oslabení")} ${cnt.sh.A}:${cnt.sh.B}.`);

  const div = (m.divaci || "").replace(/\D/g, "");
  if (div) parts.push(`${L("Diváci")} ${div}.`); else warn.push("chybí počet diváků");
  if (m.strely) parts.push(`${L("Střely na branku")} ${m.strely[0]}:${m.strely[1]}.`); else warn.push("chybí souhrn střel");

  // průběh: stav vždy, když se střídá tým, který skóroval
  const prubeh = [];
  let sc = [0, 0];
  goly.forEach((g, i) => {
    sc = g.side === "A" ? [sc[0] + 1, sc[1]] : [sc[0], sc[1] + 1];
    const next = goly[i + 1];
    if (!next || next.side !== g.side) prubeh.push(`${sc[0]}:${sc[1]}`);
  });
  if (prubeh.length) parts.push(`${L("Průběh utkání")} ${prubeh.join(", ")}.`);

  return { text: parts.join(" "), warn };
}

// ===== Změny v sestavě Motoru oproti minulému zápasu ========================

function motorSideOf(m) { return isMotor(m.A.nazev) ? "A" : isMotor(m.B.nazev) ? "B" : null; }

function starterOf(t) {
  const byNo = Object.fromEntries(t.hraci.map(h => [h.c, h]));
  const ch = (t.brankari || []).filter(b => byNo[b.c]);
  if (ch.length) return byNo[ch[0].c];
  const g = t.hraci.filter(h => h.post === "GK");
  return g.find(h => h.hral) || g[0] || null;
}

function previousGame(kolo) {
  if (!DATA) return null;
  const cand = DATA.zapasy.filter(g => g.sestava && (kolo == null || g.kolo < kolo));
  return cand.length ? cand[cand.length - 1] : null;
}

function buildChanges(m, namer, kolo) {
  const ms = motorSideOf(m);
  const prev = previousGame(kolo);
  if (!ms || !prev) return "";
  const ps = isMotor(prev.sestava.A.nazev) ? "A" : "B";
  const now = m[ms], before = prev.sestava[ps];
  const key = h => lc(h.jmeno);
  const skaters = t => t.hraci.filter(h => h.hral && h.post !== "GK");
  const nowSet = new Set(skaters(now).map(key)), befSet = new Set(skaters(before).map(key));
  const chybi = skaters(before).filter(h => !nowSet.has(key(h))).map(h => namer.pl(h.jmeno));
  const nove = skaters(now).filter(h => !befSet.has(key(h))).map(h => namer.pl(h.jmeno));
  const sNow = starterOf(now), sBef = starterOf(before);
  const souper = prev.sestava[ps === "A" ? "B" : "A"].nazev;
  const kde = ps === "A" ? "doma" : "venku";
  const bits = [];
  if (chybi.length) bits.push(`chybí ${joinCs(chybi)}`);
  if (nove.length) bits.push(`nově ${joinCs(nove)}`);
  if (sNow && sBef && key(sNow) !== key(sBef)) bits.push(`v brance ${namer.pl(sNow.jmeno)} (minule ${namer.pl(sBef.jmeno)})`);
  const head = `Oproti ${prev.kolo}. kolu (${kde} ${shortTeam(souper)}${prev.vysledek ? " " + prev.vysledek : ""})`;
  return bits.length ? `${head}: ${bits.join("; ")}.` : `${head} beze změny v sestavě.`;
}

// ===== Návrh úvodu z průběhu =================================================
// Pevná pravidla nad daty, nic se nevymýšlí. Hráči jsou podmětem věty
// („Bell srovnal…“), takže se jejich jména nemusí skloňovat.

const CISLO = { 2: ["dva", "dvě", "Dvěma"], 3: ["tři", "tři", "Třemi"], 4: ["čtyři", "čtyři", "Čtyřmi"], 5: ["pět", "pět", "Pěti"] };
const goluTxt = n => n === 1 ? "gól" : `${(CISLO[n] || [n])[0]} ${n < 5 ? "góly" : "gólů"}`;
const asistTxt = n => n === 1 ? "asistence" : `${(CISLO[n] || [n])[1]} ${n < 5 ? "asistence" : "asistencí"}`;
const boduTxt = n => `${(CISLO[n] || [n])[0]} ${n < 5 ? "body" : "bodů"}`;

// „ve 38. minutě“ / „v 57. minutě“ (podle toho, jak se číslovka čte)
function vMinute(min) {
  const ve = [2, 3, 4, 12, 13, 14].includes(min) || (min >= 20 && min < 50);
  return `${ve ? "ve" : "v"} ${min}. minutě`;
}

const PORADI = { 2: "podruhé", 3: "potřetí", 4: "počtvrté", 5: "popáté", 6: "pošesté", 7: "posedmé", 8: "poosmé", 9: "podeváté", 10: "podesáté" };
const GEN_CISLO = { 3: "tří", 4: "čtyř", 5: "pěti", 6: "šesti", 7: "sedmi", 8: "osmi", 9: "devíti", 10: "deseti" };
const TRETINA = { 1: "první", 2: "druhá", 3: "třetí" };
const VZAJEMNY = { 2: "druhém", 3: "třetím", 4: "čtvrtém" };
const sekundTxt = n => `${n} ${n === 1 ? "sekundu" : n < 5 ? "sekundy" : "sekund"}`;

// výsledek odehraného kola z pohledu Motoru (z rozpisu): {win, motor, souper}
function motorResult(g) {
  const sc = g && g.odehrano && pair(g.vysledek);
  if (!sc) return null;
  const doma = isMotor(g.domaci);
  const [mm, oo] = doma ? sc : [sc[1], sc[0]];
  return { win: mm > oo || (mm === oo && /sn|p/.test(g.vysledek) && doma === (sc[0] > sc[1])), motor: mm, souper: oo };
}

// Fakta ze sezóny: aktuální série (včetně tohoto zápasu), ukončená série, předchozí vzájemný zápas
function seasonFacts(kolo, vyhra, opp) {
  if (!DATA || kolo == null) return null;
  const pred = DATA.zapasy.filter(g => g.kolo < kolo && g.odehrano).sort((a, b) => a.kolo - b.kolo);
  const vysl = pred.map(motorResult).filter(Boolean);
  let n = 0;
  for (let i = vysl.length - 1; i >= 0 && vysl[i].win === vyhra; i--) n++;
  let k = 0;
  for (let i = vysl.length - 1; i >= 0 && vysl[i].win !== vyhra; i--) k++;
  const vzajemne = pred.filter(g => [g.domaci, g.hoste].some(t => !isMotor(t) && shortTeam(t) === opp));
  const posl = vzajemne[vzajemne.length - 1];
  return { serie: n + 1, ukoncena: k, posl, r: motorResult(posl), vzajemnych: vzajemne.length };
}

// Souvislosti ze sezóny: série, předchozí vzájemný zápas, debuty
function seasonContext(m, namer, kolo, vyhra, opp) {
  const f = seasonFacts(kolo, vyhra, opp);
  if (!f) return [];
  const vety = [];
  const n = f.serie - 1, k = f.ukoncena;
  if (n + 1 >= 2 && PORADI[n + 1]) vety.push(`Motor tak ${vyhra ? "vyhrál" : "prohrál"} ${PORADI[n + 1]} v řadě.`);
  else if (k >= 3 && GEN_CISLO[k]) vety.push(`Motor tak ukončil sérii ${GEN_CISLO[k]} ${vyhra ? "proher" : "výher"}.`);

  const vzajemne = { length: f.vzajemnych };
  const posl = f.posl, r = f.r;
  if (r) {
    const poradi = VZAJEMNY[vzajemne.length + 1] || "dalším";
    if (!r.win && vyhra) vety.push(`Motor tak soupeři oplatil porážku ${r.motor}:${r.souper} z ${posl.kolo}. kola.`);
    else if (r.win && !vyhra) vety.push(`Soupeř tak Motoru oplatil porážku ${r.souper}:${r.motor} z ${posl.kolo}. kola.`);
    else if (r.win && vyhra) vety.push(`Soupeře Motor porazil i ve ${poradi} vzájemném zápase sezóny.`);
    else vety.push(`Se soupeřem Motor prohrál i ve ${poradi} vzájemném zápase sezóny.`);
  }

  const ms = motorSideOf(m);
  const hrali = new Set();
  DATA.zapasy.filter(g => g.kolo < kolo && g.sestava).forEach(g => {
    const t = isMotor(g.sestava.A.nazev) ? g.sestava.A : g.sestava.B;
    t.hraci.filter(h => h.hral).forEach(h => hrali.add(lc(h.jmeno)));
  });
  if (hrali.size) {
    const nove = m[ms].hraci.filter(h => h.hral && h.post !== "GK" && !hrali.has(lc(h.jmeno))).map(h => namer.pl(h.jmeno));
    if (nove.length) vety.push(`Poprvé v sezóně ${nove.length === 1 ? "nastoupil" : "nastoupili"} ${joinCs(nove)}.`);
  }
  return vety;
}

function buildStory(m, namer, kolo) {
  const ms = motorSideOf(m);
  if (!ms) return "";
  const os = ms === "A" ? "B" : "A";
  const goly = [...m.goly].sort((a, b) => a.sec - b.sec);
  const gM = goly.filter(g => g.side === ms).length, gO = goly.length - gM;
  let sM = gM, sO = gO, poSN = false;
  if (m.najezdy.length && gM === gO) {
    const nM = m.najezdy.filter(p => p.side === ms && p.gol).length;
    const nO = m.najezdy.filter(p => p.side === os && p.gol).length;
    poSN = true; if (nM > nO) sM += 1; else sO += 1;
  }
  const vyhra = sM > sO;
  const poPr = !poSN && goly.some(g => g.sec >= 3600);
  const opp = shortTeam(m[os].nazev);
  const { s: sKym, v: kde } = tvary(opp);
  const doma = ms === "A";
  const oppSubj = doma ? "hosté" : "domácí", oppAcc = doma ? "hosty" : "domácí", oppGen = doma ? "hostů" : "domácích";
  const cap = t => t.charAt(0).toLocaleUpperCase("cs") + t.slice(1);
  const nm = g => namer.pl(g.strelec);

  // průběh skóre z pohledu Motoru: nejhorší a nejlepší moment
  let a = 0, b = 0, worst = [0, 0], best = [0, 0];
  goly.forEach(g => {
    if (g.side === ms) a++; else b++;
    if (a - b < worst[0] - worst[1]) worst = [a, b];
    if (a - b > best[0] - best[1]) best = [a, b];
  });

  // 1. věta: výsledek, případně obrat
  let veta1 = `Hokejisté Motoru ${vyhra ? "vyhráli" : "prohráli"} ${doma ? "doma " + sKym : kde} ${sM}:${sO}` +
    (poSN ? " po samostatných nájezdech" : poPr ? " po prodloužení" : "");
  if (vyhra && worst[1] - worst[0] >= 2) veta1 += `, přestože prohrávali ${worst[0]}:${worst[1]}`;
  if (!vyhra && best[0] - best[1] >= 2) veta1 += `, přestože vedli ${best[0]}:${best[1]}`;
  const vety = [veta1 + "."];

  // úseky: střídání střelců mezi týmy, rozdělené i v místě vyrovnání
  const segs = [];
  let ra = 0, rb = 0, tie = false;
  goly.forEach(g => {
    const last = segs[segs.length - 1];
    if (last && last.side === g.side && !tie) last.g.push(g); else segs.push({ side: g.side, g: [g], pred: [ra, rb] });
    if (g.side === ms) ra++; else rb++;
    tie = ra === rb;
    segs[segs.length - 1].po = [ra, rb];
  });

  const klauzule = [];   // {text, konec: sekunda posledního gólu}
  let srovnani = 0;
  // přesilovka/oslabení se zmíní nejvýš u dvou posledních takových gólů (jinak to zní jako výčet)
  const zvlastni = new Set(segs.filter(sg => sg.g.length === 1 && strength(sg.g[0].sit) !== "ev").map(sg => sg.g[0]).slice(-2));
  segs.forEach((seg, i) => {
    const jeM = seg.side === ms;
    const [pa, pb] = seg.pred, [qa, qb] = seg.po;
    const pred = jeM ? pa - pb : pb - pa, po = jeM ? qa - qb : qb - qa;
    const skore = jeM ? `${qa}:${qb}` : `${qb}:${qa}`;
    const posledni = i === segs.length - 1;
    const g0 = seg.g[0];
    const pp = g => (!zvlastni.has(g) ? "" : strength(g.sit) === "pp" ? " přesilovkovou trefou" : strength(g.sit) === "sh" ? " trefou v oslabení" : "");
    let t;
    if (seg.g.length === 1) {
      const prev = segs[i - 1];
      const opet = prev && prev.side === seg.side && prev.g.length === 1 && prev.g[0].strelec === g0.strelec ? "opět " : "";
      const zbyva = 3600 - g0.sec;
      const kdo = opet + nm(g0);
      const dulezity = po === 0 || (posledni && pred === 0 && po > 0);
      const kdy = g0.sec >= 3600 ? "v prodloužení"
        : dulezity && zbyva <= 60 ? `${sekundTxt(zbyva)} před koncem`
        : dulezity && zbyva <= 120 ? "necelé dvě minuty před koncem"
        : vMinute(minuteOfSec(g0.sec));
      if (posledni && pred === 0 && po > 0 && !poSN)
        t = `o výhře ${jeM ? "Motoru" : oppGen} rozhodl ${kdy} ${kdo}${pp(g0)}`;
      else if (i === 0) t = `skóre otevřel ${kdy} ${kdo}${pp(g0)}`;
      else if (po === 0) t = `${kdo} ${kdy}${pp(g0)} ${(srovnani++ % 2) ? "vyrovnal" : "srovnal"} na ${skore}`;
      else if (pred === 0) t = `${kdo} ${kdy}${pp(g0)} poslal ${jeM ? "Motor" : oppAcc} do vedení ${skore}`;
      else if (pred > 0) t = `${kdo} ${kdy}${pp(g0)} zvýšil na ${skore}`;
      else t = `${kdo} ${kdy}${pp(g0)} snížil na ${skore}`;
    } else {
      const subj = jeM ? "Motor" : oppSubj;
      const v = (sg, pl) => (jeM ? sg : pl);
      const sloveso = i === 0 ? v("vedl", "vedli") : po === 0 ? v("srovnal na", "srovnali na")
        : pred === 0 ? v("odskočil na", "odskočili na")
        : pred > 0 ? v("zvýšil na", "zvýšili na") : v("snížil na", "snížili na");
      const konec = minuteOfSec(seg.g[seg.g.length - 1].sec);
      const kdyKonec = i === 0 && konec <= 30 ? ` po ${konec} minutách` : "";
      const jmena = [...new Set(seg.g.map(nm))];
      const kdo = jmena.length === 1
        ? `${seg.g.length === 2 ? "oba góly" : "všechny " + (CISLO[seg.g.length] || [seg.g.length])[0] + " góly"} dal ${jmena[0]}`
        : `skórovali ${joinCs(jmena)}`;
      t = `${subj} ${sloveso.startsWith("vedl") ? sloveso + kdyKonec : sloveso} ${skore}, ${kdo}`;
    }
    klauzule.push({ text: t, konec: seg.g[seg.g.length - 1].sec });
  });

  if (segs.length === 1) {
    const s0 = segs[0];
    klauzule.length = 0;
    const kdo = s0.side === ms ? "Motoru" : oppGen;
    if (s0.g.length === 1) vety.push(`Jediný gól zápasu dal ${vMinute(minuteOfSec(s0.g[0].sec))} ${nm(s0.g[0])}.`);
    else vety.push(`Góly ${kdo} dali ${joinCs(s0.g.map(g => `${nm(g)} (${minuteOfSec(g.sec)}.)`))}.`);
  }

  // dlouhý zápas: první dvě třetiny jednou větou, podrobně jen závěr
  let vybrane = klauzule;
  if (klauzule.length > 5) {
    const do40 = goly.filter(g => g.sec < 2400);
    const x = do40.filter(g => g.side === ms).length, y = do40.length - x;
    const stav = x === y ? `bylo ${x}:${y}` : x > y ? `vedl Motor ${x}:${y}` : `vedli ${oppSubj} ${y}:${x}`;
    vety.push(`Po dvou třetinách ${stav}.`);
    vybrane = klauzule.filter(k => k.konec >= 2400);
  }
  for (let i = 0; i < vybrane.length; i += 2) vety.push(cap(vybrane.slice(i, i + 2).map(k => k.text).join(", ")) + ".");

  if (poSN) {
    const win = vyhra ? ms : os;
    const last = m.najezdy.filter(p => p.side === win && p.gol).pop();
    if (last) vety.push(`V nájezdech rozhodl ${namer.pl(last.strelec)}.`);
  }

  // rozhodující třetina: vítěz ji vyhrál aspoň o dva a bez ní by nevyhrál
  if (!poSN && !poPr) {
    const reg = goly.filter(g => g.sec < 3600);
    const margin = Math.abs(gM - gO);
    for (const tr of [1, 2, 3]) {
      const v3 = reg.filter(g => Math.floor(g.sec / 1200) + 1 === tr);
      const x = v3.filter(g => g.side === (vyhra ? ms : os)).length, y = v3.length - x;
      if (x - y >= 2 && x - y >= margin && margin >= 1 && v3.length < reg.length) {
        const kdo = vyhra ? "Motor vyhrál" : `${oppSubj} vyhráli`;
        vety.push(`Rozhodující byla ${TRETINA[tr]} třetina, kterou ${kdo} ${x}:${y}.`);
        break;
      }
    }
  }
  // rychlý sled: dva góly jednoho týmu do 60 sekund
  for (let i = 1; i < goly.length; i++) {
    const d = goly[i].sec - goly[i - 1].sec;
    if (goly[i].side === goly[i - 1].side && d <= 60 && d > 0) {
      const kdo = goly[i].side === ms ? "Motor" : oppSubj;
      vety.push(`Během ${d} ${d === 1 ? "sekundy" : "sekund"} ${goly[i].side === ms ? "dal" : "dali"} ${kdo} dva góly (${nm(goly[i - 1])}, ${nm(goly[i])}).`);
      break;
    }
  }

  // výrazní hráči Motoru (max. dva), u soupeře jen víc gólů
  const stat = {};
  goly.forEach(g => {
    const add = (raw, k) => { const e = (stat[g.side + "|" + raw] ||= { side: g.side, raw, g: 0, a: 0 }); e[k]++; };
    add(g.strelec, "g"); g.asist.forEach(x => add(x, "a"));
  });
  const vyrazni = Object.values(stat).filter(e => e.side === ms && (e.g >= 2 || e.g + e.a >= 3))
    .sort((x, y) => (y.g + y.a) - (x.g + x.a) || y.g - x.g).slice(0, 2);
  vyrazni.forEach(e => {
    const kdo = namer.pl(e.raw);
    if (e.g >= 3 && !e.a) vety.push(`Hattrickem se blýskl ${kdo}.`);
    else if (e.g >= 2 && !e.a) vety.push(`${(CISLO[e.g] || [, , e.g])[2]} góly se blýskl ${kdo}.`);
    else if (!e.g) vety.push(`${kdo} si připsal ${asistTxt(e.a)}.`);
    else vety.push(`${kdo} si připsal ${boduTxt(e.g + e.a)} (${goluTxt(e.g)} a ${asistTxt(e.a)}).`);
  });
  const souperStrelec = Object.values(stat).filter(e => e.side === os && e.g >= 2).sort((x, y) => y.g - x.g)[0];
  if (souperStrelec && !vety.join(" ").includes(namer.pl(souperStrelec.raw)))
    vety.push(`Za ${oppAcc} dal ${goluTxt(souperStrelec.g)} ${namer.pl(souperStrelec.raw)}.`);

  // brankář Motoru a střely
  const t = m[ms];
  const byNo = Object.fromEntries(t.hraci.map(h => [h.c, h]));
  const chytali = new Set((t.brankari || []).filter(x => byNo[x.c]).map(x => x.c));
  const st = starterOf(t);
  if (st && chytali.size <= 1) {
    if (gO === 0) vety.push(`${namer.pl(st.jmeno)} udržel čisté konto.`);
    else if (m.strely) {
      const zakroky = m.strely[ms === "A" ? 1 : 0] - gO;
      if (zakroky >= 35 || (vyhra && zakroky >= 28)) vety.push(`Brankář ${namer.pl(st.jmeno)} zlikvidoval ${zakroky} z ${zakroky + gO} střel.`);
    }
  }
  if (m.strely) {
    const sm = m.strely[ms === "A" ? 0 : 1], so = m.strely[ms === "A" ? 1 : 0];
    if (!vyhra && sm - so >= 8) vety.push(`Na střely přitom vyhrál Motor ${sm}:${so}.`);
    if (vyhra && so - sm >= 8) vety.push(`Na střely přitom vyhrál soupeř ${so}:${sm}.`);
  }
  vety.push(...seasonContext(m, namer, kolo, vyhra, opp));
  return vety.join(" ").replace(/\.\./g, ".");
}

// ===== Titulky ===============================================================
// Několik variant od nejzajímavější po obyčejný výsledek; vybírá se ručně.

const SERIE_TIT = { 3: "Třetí", 4: "Čtvrtá", 5: "Pátá", 6: "Šestá", 7: "Sedmá", 8: "Osmá", 9: "Devátá", 10: "Desátá" };

function buildHeadlines(m, namer, kolo) {
  const ms = motorSideOf(m);
  if (!ms) return [];
  const os = ms === "A" ? "B" : "A";
  const goly = [...m.goly].sort((a, b) => a.sec - b.sec);
  const gM = goly.filter(g => g.side === ms).length, gO = goly.length - gM;
  let sM = gM, sO = gO, poSN = false;
  if (m.najezdy.length && gM === gO) {
    const nM = m.najezdy.filter(p => p.side === ms && p.gol).length;
    const nO = m.najezdy.filter(p => p.side === os && p.gol).length;
    poSN = true; if (nM > nO) sM += 1; else sO += 1;
  }
  const vyhra = sM > sO, poPr = !poSN && goly.some(g => g.sec >= 3600);
  const doma = ms === "A";
  const opp = shortTeam(m[os].nazev), T = tvary(opp);
  const skore = `${sM}:${sO}`;
  const kde = doma ? "doma" : T.vk;
  const varianta = (kolo || 0) % 3;
  const out = [];

  // průběh: nejhorší/nejlepší stav, rozhodující gól
  let a = 0, b = 0, worst = [0, 0], best = [0, 0], rozhodl = null;
  goly.forEach(g => {
    const predTie = a === b;
    if (g.side === ms) a++; else b++;
    if (a - b < worst[0] - worst[1]) worst = [a, b];
    if (a - b > best[0] - best[1]) best = [a, b];
    if (predTie) rozhodl = g;   // poslední gól, který šel ze srovnaného stavu
  });
  const vitezny = !poSN && rozhodl && rozhodl === goly[goly.length - 1] ? rozhodl : null;

  // obrat
  if (vyhra && worst[1] - worst[0] >= 2) out.push(`Motor otočil z ${worst[0]}:${worst[1]} a porazil ${T.acc}`);
  if (!vyhra && best[0] - best[1] >= 2) out.push(`Motor ztratil vedení ${best[0]}:${best[1]} a podlehl ${T.dat}`);
  // srovnal Motor až po své největší ztrátě?
  let ca = 0, cb = 0, poZtrate = false, dosazeno = false;
  goly.forEach(g => {
    if (g.side === ms) ca++; else cb++;
    if (ca === worst[0] && cb === worst[1]) dosazeno = true;
    else if (dosazeno && ca === cb) poZtrate = true;
  });
  if (!vyhra && worst[1] - worst[0] >= 2 && poZtrate)
    out.push(`Motor dotáhl ztrátu ${worst[0]}:${worst[1]}, přesto podlehl ${T.dat}`);

  // kdo rozhodl
  if (vyhra && vitezny && vitezny.side === ms) {
    const zbyva = 3600 - vitezny.sec;
    const kdy = vitezny.sec >= 3600 ? "v prodloužení" : zbyva <= 60 ? `${sekundTxt(zbyva)} před koncem` : zbyva <= 120 ? "v závěru" : "";
    out.push(`${namer.pl(vitezny.strelec)} rozhodl${kdy ? " " + kdy : ""} o výhře nad ${T.ins}`);
  }
  if (!vyhra && vitezny && vitezny.side === os) {
    const zbyva = 3600 - vitezny.sec;
    const kdy = vitezny.sec >= 3600 ? " v prodloužení" : zbyva <= 60 ? ` ${sekundTxt(zbyva)} před koncem` : zbyva <= 120 ? " v závěru" : "";
    out.push(`${namer.pl(vitezny.strelec)} rozhodl${kdy} o porážce Motoru`);
  }
  if (vyhra && poSN) {
    const last = m.najezdy.filter(p => p.side === ms && p.gol).pop();
    if (last) out.push(`${namer.pl(last.strelec)} rozhodl v nájezdech o výhře nad ${T.ins}`);
  }
  // výrazný střelec
  // výrazný střelec vítěze (při shodě má přednost ten, kdo rozhodl)
  const winSide = vyhra ? ms : os;
  const goals = {};
  goly.filter(g => g.side === winSide).forEach(g => { goals[g.strelec] = (goals[g.strelec] || 0) + 1; });
  const top = Object.entries(goals).sort((x, y) => y[1] - x[1] || (y[0] === vitezny?.strelec) - (x[0] === vitezny?.strelec))[0];
  if (top && top[1] >= 2) {
    const kdo = namer.pl(top[0]);
    if (vyhra) out.push(top[1] >= 3 ? `${kdo} hattrickem sestřelil ${T.acc}` : `Dvougólový ${kdo} dovedl Motor k výhře nad ${T.ins}`);
    else if (!poSN && !poPr) out.push(`${kdo} ${top[1] >= 3 ? "hattrickem" : "dvěma góly"} složil Motor`);
  }
  // čisté konto
  if (vyhra && gO === 0) {
    const st = starterOf(m[ms]);
    if (st) out.push(`${namer.pl(st.jmeno)} vychytal nulu, Motor porazil ${T.acc} ${skore}`);
  }
  // vysoký výsledek
  if (vyhra && sM - sO >= 4) out.push(`Motor rozstřílel ${T.acc} ${skore}`);
  if (!vyhra && sO - sM >= 3) out.push(`Motor byl ${doma ? "doma" : T.vk} bez šance, prohrál ${skore}`);

  // série a odveta
  const f = seasonFacts(kolo, vyhra, opp);
  if (f) {
    if (f.serie >= 3 && SERIE_TIT[f.serie])
      out.push(vyhra ? `${SERIE_TIT[f.serie]} výhra v řadě, Motor porazil ${T.acc}` : `Motor prohrál ${PORADI[f.serie]} v řadě, tentokrát ${doma ? "doma s " + T.ins : T.vk}`);
    else if (f.ukoncena >= 3 && GEN_CISLO[f.ukoncena])
      out.push(vyhra ? `Motor ukončil sérii ${GEN_CISLO[f.ukoncena]} proher` : `Motoru skončila série ${GEN_CISLO[f.ukoncena]} výher`);
    if (f.r && !f.r.win && vyhra) out.push(`Motor oplatil ${T.dat} porážku z ${f.posl.kolo}. kola`);
  }

  // obyčejný výsledek (vždy)
  const vitez = ["porazil", "zdolal", "přehrál"][varianta];
  const dodatek = poSN ? " po nájezdech" : poPr ? " v prodloužení" : "";
  if (vyhra) out.push(doma ? `Motor doma ${vitez} ${T.acc} ${skore}${dodatek}` : `Motor vyhrál ${T.vk} ${skore}${dodatek}`);
  else out.push(poSN || poPr ? `Motor padl ${doma ? "doma s " + T.ins : T.vk} až ${poSN ? "v nájezdech" : "v prodloužení"}`
                             : (doma ? `Motor doma podlehl ${T.dat} ${skore}` : `Motor prohrál ${T.vk} ${skore}`));
  return [...new Set(out)].slice(0, 5);
}

let DATA = null;          // obsah sestavy-data.json
let currentKolo = null;   // kolo vybrané v rozpisu

// ===== Reportáž z online komentáře (onlajny.com) =============================
// Bez AI: z komentáře se berou jen události (tyčky, šance, zranění, jak padl gól),
// góly, skóre a střely vždy ze zápisu. Text komentátora se nepřebírá.

function parseOnline(text) {
  // Záznam začíná časem hry – buď na samostatném řádku („58:52“), nebo na začátku
  // textu („58:52 A klidně mohlo být…“), podle toho, jak prohlížeč text zkopíroval.
  const raw = text.replace(/\r/g, "").split("\n");
  const entries = [];
  let cur = null;
  const zavri = /^(Začala|.*třetina skončila|Konec zápasu|Utkání právě začalo)/;
  for (const line of raw) {
    if (/^\s*$/.test(line)) {
      if ((line.match(/\t/g) || []).length >= 2) cur = null;     // souhrn komentátora / reklama
      continue;
    }
    let t = line.trim();
    if (/^\d{2}:\d{2}\s.+\s-\s\d+:\d+$/.test(t)) continue;        // přehled branek „09:51 David ŠŤASTNÝ - 0:1“
    const mt = /^(\d{2}):(\d{2})(?:\s+(.*))?$/.exec(t);
    if (mt && +mt[1] <= 70) {
      cur = { sec: +mt[1] * 60 + +mt[2], sit: "", text: [] };
      entries.push(cur);
      if (!mt[3]) continue;
      t = mt[3];
    }
    if (!cur) continue;
    const ms = /^(\d\/\d)(?:\s+(.*))?$/.exec(t);
    if (ms) { cur.sit = ms[1]; if (!ms[2]) continue; t = ms[2]; }
    if (/^(\p{Lu}[\p{L}'’-]+ \p{Lu}\.,? ?)+$/u.test(t)) continue;           // hráči na ledě
    if (/Sledujte|Tipsport|Komerční přestávka/i.test(t)) continue;
    if (/^Střely (na branku|po)/.test(t) || /^Další třetina začne/.test(t)) { cur = null; continue; }
    // dlouhý odstavec bez času = shrnutí komentátora, ne záznam (ten bývá do ~450 znaků)
    if (cur.text.length && t.length > 300) { cur = null; continue; }
    if (!cur.text.length && t.length > 520) { cur = null; continue; }
    cur.text.push(t);
    if (zavri.test(t)) cur = null;
  }
  entries.forEach(e => (e.text = e.text.join(" ")));
  return entries.filter(e => e.text).sort((a, b) => a.sec - b.sec);
}

// Hledání hráčů ze soupisky v textu (i ve skloňovaných tvarech)
function makeMatcher(m) {
  const people = [];
  ["A", "B"].forEach(side => m[side].hraci.filter(h => h.hral || h.post === "GK").forEach(h => {
    const p = splitPlayer(h.jmeno), s = lc(p.prijmeni.split(" ").pop());
    const stems = new Set([s]);
    if (/[aeiouyáéíóúůý]$/.test(s) && s.length > 3) stems.add(s.slice(0, -1));
    if (/e[kcl]$/.test(s)) stems.add(s.slice(0, -2) + s.slice(-1));
    people.push({ side, raw: h.jmeno, gk: h.post === "GK", first: lc(p.jmeno.split(" ")[0] || ""), s, stems: [...stems] });
  }));
  const tokens = txt => lc(txt).split(/[^\p{L}]+/u).filter(Boolean);
  return txt => {
    const tk = tokens(txt), found = [];
    tk.forEach((w, i) => {
      const cand = people.filter(p => p.s.length <= 3
        ? (w === p.s || new RegExp(`^${p.s}(a|ovi|em|u|e)$`).test(w))
        : p.stems.some(st => w.startsWith(st)));
      let hit = cand.length === 1 ? cand[0] : cand.find(p => p.first && tk[i - 1] && tk[i - 1].startsWith(p.first.slice(0, 3)));
      if (hit && !found.includes(hit)) found.push(hit);
    });
    return found;
  };
}

const JAK = [
  [/ze vzduchu/, "ze vzduchu"], [/teč|změn\w* směru|sáhl/, "tečí"], [/dorážk|dorazil/, "dorážkou"],
  [/z první/, "střelou z první"], [/bekhend/, "bekhendem"], [/prázdn\w* (bran|klec)/, "do prázdné branky"],
  [/přečíslen/, "po přečíslení"], [/únik|sám na brankáře/, "z úniku"], [/od modré/, "střelou od modré"],
  [/od mantinelu/, "střelou od mantinelu"],
];

function classify(e, match) {
  const t = lc(e.text), lidi = match(e.text);
  let hraci = lidi.filter(p => !p.gk);
  const brankari = lidi.filter(p => p.gk);
  // „X našel/přihrál Y…“ → akci zakončoval Y
  if (hraci.length >= 2 && hraci[0].side === hraci[1].side && /našel|přihr|posunul|nahrál|poslal|vyslal na/.test(t)) hraci = [hraci[1], hraci[0], ...hraci.slice(2)];
  const ev = [];
  if (/vstřelil\w* branku/.test(t)) {
    const jak = (JAK.find(([re]) => re.test(t)) || [])[1] || "";
    ev.push({ typ: "gol", jak });
    if (/challenge|trenérsk\w* výzv/.test(t)) ev.push({ typ: "vyzva", vzata: !/nebere|nevzal|nebral/.test(t) });
    return ev;
  }
  const tyc = /(tref\w*|trhuj\w*|orazít\w*|nastřel\w*)\s+(jen(om)?\s+|pouze\s+|ještě\s+)?(horní\s+|levou\s+|pravou\s+|zadní\s+)?(tyč|břevn)|(zastavil[ao]?|zachránil[ao]?)\s+(jen\s+)?(tyč|břevno)|(tyč|břevno)\s+(zastavil|zachránil)/;
  if (tyc.test(t) && hraci[0]) ev.push({ typ: "tyc", side: hraci[0].side, kdo: hraci[0].raw });
  else if (/(obrovsk|stoprocentn|vyložen|gólov\w* šanc|velk\w* šanc|velk\w* možnost)|sám na brankář|sám před|jen gólmana|samostatn\w* únik|přestřelil horní/.test(t)
           && !/ofsajd|zazděn/.test(t)) {
    const kdo = hraci.find(p => true);
    const side = kdo ? kdo.side : (brankari[0] ? (brankari[0].side === "A" ? "B" : "A") : null);
    if (side) ev.push({ typ: "sance", side, kdo: kdo && kdo.side === side ? kdo.raw : null });
  }
  if (/ošetřen|šití|zraněn|zůstává ležet|zůstal ležet|kulh|odstoupil/.test(t) && hraci[0])
    ev.push({ typ: "zraneni", side: hraci[0].side, kdo: hraci[0].raw, brusle: /brusl/.test(t) });
  if (/(pro něj|pro něho)[^.]*skončil|není ani na střídačce|už se nevrátí|nedohraje/.test(t) && hraci[0])
    ev.push({ typ: "nedohral", side: hraci[0].side, kdo: hraci[0].raw });
  if (/je (zpátky )?na ledě|vrátil se/.test(t) && hraci[0]) ev.push({ typ: "navrat", kdo: hraci[0].raw });
  if (/odvolal\w*|odvoláv\w*|bez brankáře|šestého hráče|šestým hráčem/.test(t)) {
    const side = /domác|motor|jihočeš|budějovic/.test(t) ? "A" : /host|západočeš|vary|energie/.test(t) ? "B" : null;
    if (side) ev.push({ typ: "bezGK", side });
  }
  if (/oddechov|time-?out/.test(t)) ev.push({ typ: "timeout" });
  if (brankari[0] && /(zákrok|vyrazil|chytil|zasáhl|zasahuje|lapačk|beton|poradil|schoval|zlikvid)/.test(t))
    ev.push({ typ: "zakrok", kdo: brankari[0].raw, side: brankari[0].side, velky: /šanc|sám|únik|obrovsk|skvěl|parád/.test(t) });
  return ev;
}

// ----- pomocné pro reportáž ---------------------------------------------------

const ACC_CISLO = { 1: "jednu", 2: "dvě", 3: "tři", 4: "čtyři", 5: "pět", 6: "šest" };
const GEN2 = { 2: "dvou", 3: "tří", 4: "čtyř", 5: "pěti", 6: "šesti", 7: "sedmi", 8: "osmi" };
const zeZ = n => ([2, 3, 4, 6, 7].includes(n) ? "ze" : "z");
const ORD_NOM = { 1: "První", 2: "Druhá", 3: "Třetí" };
const ORD_GEN = { 1: "první", 2: "druhé", 3: "třetí" };

// klíč hráče pro porovnání napříč zdroji („KLOUČEK Milan“ i „Klouček Milan“)
const playerKey = raw => { const p = splitPlayer(raw); return lc(`${p.prijmeni} ${p.jmeno.split(" ")[0] || ""}`.trim()); };

// „3 sekundy před koncem“ na začátku věty → „Tři sekundy před koncem“
const SLOVY = { 1: "Jednu", 2: "Dvě", 3: "Tři", 4: "Čtyři", 5: "Pět", 6: "Šest", 7: "Sedm", 8: "Osm", 9: "Devět", 10: "Deset" };
const capKdy = t => { const m = /^(\d+) (.*)$/.exec(t); return m && SLOVY[+m[1]] ? `${SLOVY[+m[1]]} ${m[2]}` : t.charAt(0).toLocaleUpperCase("cs") + t.slice(1); };

// postupně vybírá z nabídky formulací, aby se v jednom textu neopakovaly
function makeVary() {
  const n = {};
  return (key, list) => { n[key] = (n[key] || 0) + 1; return list[(n[key] - 1) % list.length]; };
}

// kapitán Motoru z úvodních sestav online komentáře („… Kundrátek (C) …“)
function captainFromOnline(text, m, ms) {
  if (!text) return null;
  const line = text.split("\n").find(l => /\(C\)/.test(l) && /motor|budějovic/i.test(l));
  const mm = line && /([\p{L}'’-]+)\s*\(C\)/u.exec(line);
  if (!mm) return null;
  const h = m[ms].hraci.find(x => lc(splitPlayer(x.jmeno).prijmeni) === lc(mm[1]));
  return h ? h.jmeno : null;
}

// statistiky hráčů Motoru v sezóně před daným kolem (ze zápisů v datech)
function seasonBefore(kolo) {
  const st = {}, zapasy = {};
  if (!DATA || kolo == null) return { st, zapasy };
  DATA.zapasy.filter(g => g.kolo < kolo && g.sestava).forEach(g => {
    const side = isMotor(g.sestava.A.nazev) ? "A" : "B";
    const nazev = g.sestava[side].nazev;
    g.sestava[side].hraci.filter(h => h.hral).forEach(h => {
      const k = playerKey(h.jmeno);
      (st[k] ||= { z: 0, g: 0, a: 0 }).z++;
      zapasy[k] = (zapasy[k] || 0) + 1;
    });
    (g.zapis?.goly || []).filter(x => x.tym === nazev).forEach(x => {
      (st[playerKey(x.strelec)] ||= { z: 0, g: 0, a: 0 }).g++;
      (x.asistence || []).forEach(a => ((st[playerKey(a)] ||= { z: 0, g: 0, a: 0 }).a++));
    });
  });
  return { st, zapasy };
}

function baselineOf(raw) {
  const kar = DATA && DATA.kariera;
  if (!kar) return null;
  const k = playerKey(raw);
  for (const [jm, v] of Object.entries(kar)) if (playerKey(jm) === k) return v;
  return null;
}

// milníky hráčů Motoru v tomto zápase: kulatá čísla po 50, první gól/bod, debut
function careerFacts(m, namer, kolo) {
  const ms = motorSideOf(m);
  if (!ms || !DATA || !DATA.kariera || kolo == null) return [];
  const { st } = seasonBefore(kolo);
  const now = {};
  m[ms].hraci.filter(h => h.hral || (h.post === "GK" && (m[ms].brankari || []).some(b => b.c === h.c)))
    .forEach(h => (now[playerKey(h.jmeno)] = { raw: h.jmeno, gk: h.post === "GK", z: 1, g: 0, a: 0 }));
  m.goly.filter(g => g.side === ms).forEach(g => {
    if (now[playerKey(g.strelec)]) now[playerKey(g.strelec)].g++;
    g.asist.forEach(a => { if (now[playerKey(a)]) now[playerKey(a)].a++; });
  });
  const out = [];
  Object.entries(now).forEach(([k, c]) => {
    const base = baselineOf(c.raw);
    if (!base) return;
    const s = st[k] || { z: 0, g: 0, a: 0 };
    const kdo = "{kdo}";
    const fakta = [];
    ["extraliga", "motor"].forEach(scope => {
      const b = base[scope] || {};
      const pred = { z: (b.z || 0) + s.z, g: (b.g || 0) + s.g, b: (b.b || 0) + s.g + s.a };
      const po = { z: pred.z + 1, g: pred.g + c.g, b: pred.b + c.g + c.a };
      const kde = scope === "extraliga" ? "v extralize" : "za Motor";
      if (pred.z === 0) fakta.push({ w: 3, t: scope === "extraliga" ? `${kdo} si odbyl premiéru v extralize` : `${kdo} poprvé nastoupil za Motor`, scope, typ: "z" });
      else if (Math.floor(po.z / 50) > Math.floor(pred.z / 50)) fakta.push({ w: 2, t: `${kdo} odehrál ${po.z}. zápas ${kde}`, scope, typ: "z" });
      if (c.gk) return;
      if (c.g && pred.g === 0) fakta.push({ w: 3, t: `${kdo} vstřelil první gól ${scope === "extraliga" ? "v extralize" : "za Motor"}`, scope, typ: "g" });
      else if (Math.floor(po.g / 50) > Math.floor(pred.g / 50)) fakta.push({ w: 2, t: `${kdo} vstřelil ${po.g}. gól ${kde}`, scope, typ: "g" });
      if (c.g + c.a && pred.b === 0 && !c.g) fakta.push({ w: 3, t: `${kdo} si připsal první bod ${kde}`, scope, typ: "b" });
      else if (Math.floor(po.b / 50) > Math.floor(pred.b / 50)) fakta.push({ w: 2, t: `${kdo} si připsal ${po.b}. bod ${kde}`, scope, typ: "b" });
    });
    // stejný typ v obou rozsazích: stačí extraliga (první gól v extralize je i první za Motor)
    const vyber = fakta.filter(f => !(f.scope === "motor" && fakta.some(x => x.scope === "extraliga" && x.typ === f.typ && (x.w === 3 || f.w === 3))));
    const prem = vyber.find(f => f.scope === "extraliga" && f.typ === "z" && f.w === 3);
    const prvniGol = vyber.find(f => f.scope === "extraliga" && f.typ === "g" && f.w === 3);
    if (prem && prvniGol) {
      out.push({ raw: c.raw, tpl: "{kdo} v extraligové premiéře skóroval.", w: 4 });
      vyber.splice(vyber.indexOf(prem), 1); vyber.splice(vyber.indexOf(prvniGol), 1);
    }
    vyber.forEach(f => out.push({ raw: c.raw, tpl: f.t + ".", w: f.w,
      debut: f.typ === "z" && f.w === 3 ? f.scope : null }));
  });
  // víc debutů stejného druhu → jedna věta
  ["extraliga", "motor"].forEach(scope => {
    const d = out.filter(f => f.debut === scope);
    if (d.length < 2) return;
    d.forEach(f => out.splice(out.indexOf(f), 1));
    out.push({ raws: d.map(f => f.raw), w: 3, debut: scope,
      tpl: scope === "extraliga" ? "V extralize debutovali {kdo}." : "Za Motor poprvé nastoupili {kdo}." });
  });
  out.forEach(f => (f.text = fillTpl(f, namer.pl)));
  return out.sort((a, b) => b.w - a.w).slice(0, 4);
}

function fillTpl(f, jm) {
  const t = f.tpl.replace("{kdo}", f.raws ? joinCs(f.raws.map(jm)) : jm(f.raw));
  return t.charAt(0).toLocaleUpperCase("cs") + t.slice(1);
}

// první zmínka: role + křestní jméno („kapitán Tomáš Kundrátek“), pak jen příjmení
function makeMention(m, namer, kolo, captain) {
  const ms = motorSideOf(m);
  const seen = new Set();
  const { zapasy } = seasonBefore(kolo);
  const byRaw = {};
  ["A", "B"].forEach(sd => m[sd].hraci.forEach(h => (byRaw[h.jmeno] = { ...h, side: sd })));
  return (raw, ctx = {}) => {
    if (!raw) return "lavička";
    const kratce = namer.pl(raw);
    if (seen.has(raw)) return kratce;
    seen.add(raw);
    const p = splitPlayer(raw), h = byRaw[raw] || {};
    const krestni = p.jmeno.split(" ")[0];
    const alias = JMENA[`${p.prijmeni} ${p.jmeno}`.trim()];
    const plne = alias ? `${krestni} ${alias.replace(/^\p{Lu}\.\s*/u, "")}` : `${krestni ? krestni + " " : ""}${p.prijmeni}`;
    let role = "";
    if (h.side === ms) {
      const base = baselineOf(raw);
      if (raw === captain) role = "kapitán";
      else if (ctx.gol && base && !(base.extraliga && base.extraliga.z) && (zapasy[playerKey(raw)] || 0) < 3) role = "nováček";
      else if (ctx.gol && h.post === "D") role = "obránce";
    }
    return (role ? role + " " : "") + plne;
  };
}

// přesilovky: počet příležitostí z trestů (vzájemné tresty se ruší), góly ze situace
function powerPlays(m, ms) {
  const os = ms === "A" ? "B" : "A";
  const pen = m.tresty.filter(t => [2, 4, 5].includes(parseInt(t.min, 10)));
  const klic = t => `${t.sec ?? ""}|${parseInt(t.min, 10)}`;
  const zbyt = { A: [], B: [] };
  ["A", "B"].forEach(sd => pen.filter(t => t.side === sd).forEach(t => zbyt[sd].push(klic(t))));
  const ruseno = { A: 0, B: 0 };
  [...zbyt.A].forEach(k => {
    if (!k.startsWith("|")) {
      const i = zbyt.B.indexOf(k);
      if (i >= 0) { zbyt.B.splice(i, 1); ruseno.A++; ruseno.B++; }
    }
  });
  const prilez = { [ms]: pen.filter(t => t.side === os).length - ruseno[os], [os]: pen.filter(t => t.side === ms).length - ruseno[ms] };
  const goly = { [ms]: 0, [os]: 0 };
  m.goly.forEach(g => { if (strength(g.sit) === "pp") goly[g.side]++; });
  if (goly[ms] > prilez[ms] || goly[os] > prilez[os]) return null;   // nesedí → raději nic
  return { prilez, goly };
}

function buildReportage(m, namer, kolo, onlineText, delka = "standard") {
  const ms = motorSideOf(m);
  if (!ms || !m.jeZapis) return null;
  const os = ms === "A" ? "B" : "A";
  const doma = ms === "A";
  const dlouha = delka === "dlouha", kratka = delka === "kratka";
  const match = makeMatcher(m);
  const entries = onlineText ? parseOnline(onlineText) : [];
  const events = [];
  entries.forEach(e => classify(e, match).forEach(ev => events.push({ ...ev, sec: e.sec })));
  const captain = captainFromOnline(onlineText, m, ms);
  const vary = makeVary();
  const N = raw => namer.pl(raw);
  const cap = t => t.charAt(0).toLocaleUpperCase("cs") + t.slice(1);
  const team = side => (side === ms ? "Motor" : doma ? "hosté" : "domácí");
  const teamAcc = side => (side === ms ? "Motor" : doma ? "hosty" : "domácí");
  const teamDat = side => (side === ms ? "Motoru" : doma ? "hostům" : "domácím");
  const vb = (side, sg, plural) => (side === ms ? sg : plural);
  const periodOf = sec => (sec >= 3600 ? 4 : Math.floor(sec / 1200) + 1);
  const KRAT = { 2: "dvakrát", 3: "třikrát", 4: "čtyřikrát" };

  const goly = [...m.goly].sort((a, b) => a.sec - b.sec);
  let a = 0, b = 0;
  goly.forEach(g => {
    g.pred = [a, b]; if (g.side === ms) a++; else b++; g.po = [a, b];
    const k = events.filter(ev => ev.typ === "gol" && Math.abs(ev.sec - g.sec) <= 20)
      .sort((x, y) => Math.abs(x.sec - g.sec) - Math.abs(y.sec - g.sec))[0];
    g.jak = k ? k.jak : "";
  });

  // ----- tělo reportáže -----
  const mention = makeMention(m, namer, kolo, captain);
  const specialKdy = g => {
    const zbyva = 3600 - g.sec;
    if (g.sec >= 3600) return "v prodloužení";
    if (zbyva <= 60) return `${sekundTxt(zbyva)} před koncem`;
    if (zbyva <= 120) return "necelé dvě minuty před koncem";
    return null;
  };
  const goalText = (g, kdy) => {
    const jeM = g.side === ms;
    const [pa, pb] = g.pred, [qa, qb] = g.po;
    const pred = jeM ? pa - pb : pb - pa, po = jeM ? qa - qb : qb - qa;
    const skore = jeM ? `${qa}:${qb}` : `${qb}:${qa}`;
    const s = strength(g.sit);
    const jak = [g.jak, s === "pp" ? "v přesilovce" : s === "sh" ? "v oslabení" : ""].filter(Boolean).join(" ");
    const j = jak ? jak + " " : "";
    const kdo = mention(g.strelec, { gol: true });
    const sRoli = /^(kapitán|nováček|obránce) /.test(kdo);
    const sloveso = vary("gol", [`se ${j}prosadil`, `${j}skóroval`, `se ${j}trefil`, sRoli ? `se ${j}prosadil` : `${j}překonal brankáře`]);
    const posledni = g === goly[goly.length - 1];
    let dej;
    if (pa + pb === 0) dej = `a poslal ${teamAcc(g.side)} do vedení`;
    else if (po === 0) dej = `a ${vary("srovnal", ["srovnal", "vyrovnal"])} na ${skore}`;
    else if (pred === 0 && posledni && !m.najezdy.length) dej = `a rozhodl o výhře ${jeM ? "Motoru" : doma ? "hostů" : "domácích"}`;
    else if (pred === 0) dej = `a poslal ${teamAcc(g.side)} do vedení ${skore}`;
    else if (pred > 0) dej = `a zvýšil na ${skore}`;
    else dej = `a snížil na ${skore}`;
    let v = `${capKdy(kdy)} ${sloveso} ${kdo} ${dej}.`;
    if (jeM && g.asist.length && !kratka) {
      const jm = joinCs(g.asist.map(x => mention(x)));
      v += " " + (g.asist.length === 1
        ? vary("as1", [`Asistoval ${jm}.`, `Přihrával ${jm}.`, `Na gólu se podílel i ${jm}.`])
        : vary("as2", [`Asistovali ${jm}.`, `Na gólu se podíleli i ${jm}.`, `Přihrávali ${jm}.`]));
    }
    return v;
  };

  // položky se seřadí podle času; časový údaj („vzápětí“, „o dvě minuty později“) se doplní podle odstupu
  const renderItems = (items, pStart, p) => {
    const used = new Set();
    let prev = null;
    return items.sort((x, y) => x.sec - y.sec).map(it => {
      let kdy = it.gol ? specialKdy(it.gol) : null;
      if (!kdy) {
        const gap = prev ? it.sec - prev.sec : null;
        let c = null;
        if (!prev && it.sec - pStart <= 90 && p) c = p === 1 ? "hned v úvodu zápasu" : `hned v úvodu ${ORD_GEN[p]} třetiny`;
        else if (gap !== null && gap <= 40) c = "vzápětí";
        else if (gap !== null && gap <= 80) c = "o minutu později";
        else if (gap !== null && gap <= 150) c = "o dvě minuty později";
        else if (gap !== null && gap <= 210) c = "o tři minuty později";
        if (c && !used.has(c)) { kdy = c; used.add(c); }
      }
      if (!kdy && it.gol) kdy = vMinute(minuteOfSec(it.sec));
      prev = it;
      return it.render(kdy);
    });
  };

  const goalItem = g => ({ sec: g.sec, gol: g, render: kdy => goalText(g, kdy) });
  const pre = kdy => (kdy ? cap(kdy) + " " : "");
  const odstavce = [];

  if (kratka) {
    const items = goly.map(goalItem);
    const v = renderItems(items, 0, 0);
    if (m.najezdy.length) {
      const win = m.najezdy.filter(x => x.side === ms && x.gol).length > m.najezdy.filter(x => x.side === os && x.gol).length ? ms : os;
      const last = m.najezdy.filter(x => x.side === win && x.gol).pop();
      if (last) v.push(`V nájezdech rozhodl ${mention(last.strelec)}.`);
    }
    if (v.length) odstavce.push(v.join(" "));
  } else {
    const pocet = goly.some(g => g.sec >= 3600) || m.najezdy.length ? 4 : 3;
    for (let p = 1; p <= pocet; p++) {
      const pStart = (p - 1) * 1200;
      const evs = events.filter(e => periodOf(e.sec) === p);
      const gs = goly.filter(g => periodOf(g.sec) === p);
      const v = [];
      // charakter třetiny ze střel v zápisu
      const tr = (m.tretiny || []).find(r => r.tretina === (p === 4 ? "P" : String(p)));
      if (tr && p <= 3) {
        const sm = tr.strely[ms === "A" ? 0 : 1], so = tr.strely[ms === "A" ? 1 : 0];
        if (sm - so >= 5) v.push(`${ORD_NOM[p]} třetina patřila Motoru, který soupeře přestřílel ${sm}:${so}.`);
        else if (so - sm >= 5) v.push(`${ORD_NOM[p]} třetina patřila ${teamDat(os)}, kteří Motor přestříleli ${so}:${sm}.`);
        else if (!gs.length) v.push(`${ORD_NOM[p]} třetina byla vyrovnaná a gól nepřinesla.`);
      }
      const items = gs.map(goalItem);
      const prvniGol = gs.length ? gs[0].sec : Infinity;
      const rane = p === 1 ? evs.find(e => (e.typ === "tyc" || (e.typ === "sance" && e.kdo)) && e.sec < prvniGol) : null;
      if (rane) items.push({ sec: rane.sec, render: () =>
        `${cap(team(rane.side))} ${vb(rane.side, "mohl", "mohli")} jít do vedení už ${rane.sec < 120 ? "v úvodu zápasu" : vMinute(minuteOfSec(rane.sec))}, ${mention(rane.kdo)} ale ${rane.typ === "tyc" ? "trefil jen tyč" : "šanci nevyužil"}.` });
      evs.filter(e => e.typ === "tyc" && e !== rane).forEach(e => {
        const znovu = events.some(x => x.typ === "tyc" && x.kdo === e.kdo && x.sec < e.sec);
        const co = znovu ? "znovu trefil jen tyč" : vary("tyc", ["trefil tyč", "orazítkoval tyč", "nastřelil tyč"]);
        items.push({ sec: e.sec, render: kdy => kdy ? `${cap(kdy)} ${co} ${mention(e.kdo)}.` : `${mention(e.kdo)} ${co}.` });
      });
      if (dlouha) {
        [ms, os].forEach(side => {
          const sn = evs.filter(e => e.typ === "sance" && e.kdo && e !== rane && e.side === side);
          const uniq = [...new Map(sn.map(e => [e.kdo, e])).values()].slice(0, 2);
          if (uniq.length === 1) {
            const [co, dovetek] = vary("sance", [["měl velkou šanci", ", ale neskóroval"], ["mohl skórovat", ", ale neuspěl"], ["nevyužil velkou šanci", ""]]);
            items.push({ sec: uniq[0].sec, render: kdy => kdy ? `${cap(kdy)} ${co} ${mention(uniq[0].kdo)}${dovetek}.` : `${mention(uniq[0].kdo)} ${co}${dovetek}.` });
          }
          if (uniq.length === 2) items.push({ sec: uniq[0].sec, render: () => `${cap(team(side))} ${vb(side, "měl", "měli")} další velké šance, ${mention(uniq[0].kdo)} ani ${mention(uniq[1].kdo)} ale neskórovali.` });
        });
        evs.filter(e => e.typ === "bezGK").slice(0, 1).forEach(e =>
          items.push({ sec: e.sec, render: () => `${cap(team(e.side))} v závěru ${vb(e.side, "hrál", "hráli")} bez brankáře.` }));
        gs.forEach(g => {
          const vyz = events.find(e => e.typ === "vyzva" && !e.vzata && Math.abs(e.sec - g.sec) <= 20);
          if (vyz) { const conc = g.side === ms ? os : ms; items.push({ sec: g.sec + 1, render: () => `${cap(team(conc))} si trenérskou výzvu ${vb(conc, "nevzal", "nevzali")}.` }); }
        });
      }
      evs.filter(e => e.typ === "zraneni").forEach(e => {
        const nedohral = events.some(x => x.typ === "nedohral" && x.kdo === e.kdo && x.sec >= e.sec);
        const vratil = events.some(x => x.typ === "navrat" && x.kdo === e.kdo && x.sec > e.sec) ||
                       goly.some(g => g.sec > e.sec && (g.strelec === e.kdo || g.asist.includes(e.kdo)));
        if (nedohral) items.push({ sec: e.sec, render: () => `${mention(e.kdo)} po zásahu ${e.brusle ? "bruslí " : ""}zápas nedohrál.` });
        else if (!vratil) items.push({ sec: e.sec, render: () => `${mention(e.kdo)} musel ${e.brusle ? "po zásahu bruslí " : ""}na ošetření.` });
      });
      v.push(...renderItems(items, pStart, p));
      if (p <= 2) {
        const x = goly.filter(g => g.sec < p * 1200 && g.side === ms).length, y = goly.filter(g => g.sec < p * 1200).length - x;
        v.push(`Po ${ORD_GEN[p]} třetině ${x === y ? `bylo ${x}:${y}` : x > y ? `vedl Motor ${x}:${y}` : `vedli ${team(os)} ${y}:${x}`}.`);
      }
      if (p === 4 && m.najezdy.length) {
        const win = m.najezdy.filter(x => x.side === ms && x.gol).length > m.najezdy.filter(x => x.side === os && x.gol).length ? ms : os;
        const last = m.najezdy.filter(x => x.side === win && x.gol).pop();
        v.push(`Prodloužení gól nepřineslo${last ? `, v nájezdech rozhodl ${mention(last.strelec)}` : ""}.`);
      }
      if (v.length) odstavce.push(v.join(" "));
    }
  }

  // ----- závěr -----
  const story = buildStory(m, namer, kolo);
  const vety = story.split(/(?<=\.)\s+(?=\p{Lu})/u);
  const fakta = careerFacts(m, namer, kolo);
  const zaver = [];
  if (!kratka) {
    const pp = powerPlays(m, ms);
    if (pp) {
      const ppTxt = side => {
        const n = pp.prilez[side], k = pp.goly[side];
        if (n <= 0) return null;
        const subj = cap(team(side)), sg = side === ms;
        if (n === 1) return `${subj} ${k ? (sg ? "proměnil" : "proměnili") : (sg ? "nevyužil" : "nevyužili")} svou jedinou přesilovku`;
        return k ? `${subj} ${sg ? "proměnil" : "proměnili"} ${ACC_CISLO[k] || k} ${zeZ(n)} ${GEN2[n] || n} přesilovek`
                 : `${subj} ${sg ? "nevyužil" : "nevyužili"} ani jednu ${zeZ(n)} ${GEN2[n] || n} přesilovek`;
      };
      const parts = [ppTxt(ms), ppTxt(os)].filter(Boolean);
      if (parts.length === 2 && / přesilovek$/.test(parts[0]) && / přesilovek$/.test(parts[1])) parts[1] = parts[1].replace(/ přesilovek$/, "");
      if (parts.length) zaver.push(parts.map((t, i) => (i ? t.charAt(0).toLocaleLowerCase("cs") + t.slice(1) : t)).join(", ") + ".");
    }
    const zakroky = {};
    events.filter(e => e.typ === "zakrok").forEach(e => (zakroky[e.kdo] = (zakroky[e.kdo] || 0) + (e.velky ? 2 : 1)));
    Object.entries(zakroky).filter(([, n]) => n >= 6).sort((x, y) => y[1] - x[1]).slice(0, 1).forEach(([kdo]) => {
      const side = m.A.hraci.some(h => h.jmeno === kdo) ? "A" : "B";
      zaver.push(`${cap(mention(kdo))} několikrát podržel ${teamAcc(side)}.`);
    });
    vety.filter(t => /si připsal|se blýskl|zlikvidoval|čisté konto/.test(t)).forEach(t => zaver.push(t));
  }
  fakta.forEach(f => zaver.push(fillTpl(f, mention)));
  vety.filter(t => /v řadě|ukončil sérii|oplatil|vzájemném/.test(t) || (dlouha && /Na střely přitom/.test(t)) ||
                   (dlouha && /Poprvé v sezóně/.test(t) && !fakta.some(f => f.debut)))
      .forEach(t => zaver.push(t.replace("Na střely přitom vyhrál", "Na střely vyhrál")));
  const div = (m.divaci || "").replace(/\D/g, "");
  if (div && !kratka) zaver.push(`Utkání sledovalo ${Number(div).toLocaleString("cs-CZ")} diváků.`);
  if (zaver.length) odstavce.push(zaver.join(" "));

  // ----- perex: výsledek + rozhodující moment (s celým jménem) -----
  const perexMention = makeMention(m, namer, kolo, captain);
  let ta = 0, tb = 0, vitezny = null;
  goly.forEach(g => { const tie = ta === tb; if (g.side === ms) ta++; else tb++; if (tie) vitezny = g; });
  if (vitezny !== goly[goly.length - 1] || m.najezdy.length) vitezny = null;
  const perex = [vety[0]];
  let worst = [0, 0], dot = false, seen = false, wa = 0, wb = 0;
  goly.forEach(g => {
    if (g.side === ms) wa++; else wb++;
    if (wa - wb < worst[0] - worst[1]) { worst = [wa, wb]; seen = true; dot = false; }
    else if (seen && wa === wb) dot = true;
  });
  const vyhraM = /vyhráli/.test(vety[0]);
  if (vitezny) {
    const kdy = specialKdy(vitezny) || vMinute(minuteOfSec(vitezny.sec));
    const komu = vitezny.side === ms ? "Motoru" : doma ? "hostů" : "domácích";
    const rozhodl = `o výhře ${komu} ${!vyhraM && dot && worst[1] - worst[0] >= 2 ? "ale " : ""}rozhodl ${kdy} ${perexMention(vitezny.strelec)}`;
    perex.push(!vyhraM && dot && worst[1] - worst[0] >= 2 ? `Motor dotáhl ztrátu ${worst[0]}:${worst[1]}, ${rozhodl}.` : cap(rozhodl) + ".");
  } else if (vety[1]) perex.push(vety[1]);
  const milnik = fakta.find(f => f.w >= 2 && !f.raws);
  if (milnik && perex.length < 3) perex.push(fillTpl(milnik, perexMention));

  // ----- titulky -----
  const tit = buildHeadlines(m, namer, kolo);
  const opp = shortTeam(m[os].nazev), T = tvary(opp);
  const sc = vety[0].match(/(\d+:\d+)/);
  const tyceM = events.filter(e => e.typ === "tyc" && e.side === ms).length;
  if (tyceM >= 2 && sc) tit.unshift(`Motor ${KRAT[tyceM] || tyceM + "krát"} trefil tyč, ${vyhraM ? `přesto porazil ${T.acc}` : `${T.dat} podlehl`} ${sc[1]}`);
  if (milnik && sc) tit.splice(1, 0, `${milnik.text.replace(/\.$/, "")}, Motor ${vyhraM ? `porazil ${T.acc}` : `podlehl ${T.dat}`} ${sc[1]}`);

  const golyKom = events.filter(e => e.typ === "gol").length;
  const sparovane = goly.filter(g => events.some(e => e.typ === "gol" && Math.abs(e.sec - g.sec) <= 20)).length;
  const nesedi = entries.length && goly.length && sparovane < Math.min(goly.length, golyKom);
  return {
    titulky: [...new Set(tit)].slice(0, 6),
    perex: perex.join(" "),
    text: odstavce.join("\n\n"),
    kontrola: (entries.length ? `záznamů v komentáři: ${entries.length} · gólů v komentáři: ${golyKom}, se zápisem sedí ${sparovane}` +
               ` · z komentáře: popis gólu ${goly.filter(g => g.jak).length}×, tyčky ${events.filter(e => e.typ === "tyc").length}, ` +
               `šance ${events.filter(e => e.typ === "sance").length}, zranění ${events.filter(e => e.typ === "zraneni").length}`
             : "bez online komentáře — jen ze zápisu") +
              (nesedi ? " — ⚠️ komentář možná patří k jinému zápasu" : "") + (captain ? ` · kapitán: ${N(captain)}` : ""),
  };
}
