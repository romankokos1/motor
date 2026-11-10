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
    return { side: sd, sec: x.vteriny, strelec: raw(sd, x.strelec), asist: (x.asistence || []).map(a => raw(sd, a)), sit: x.situace,
             naLedu: (x.na_ledu_za || []).map(n => raw(sd, n)) };
  });
  m.tresty = z.tresty.map(t => {
    const sd = side(t.tym);
    return { side: sd, min: t.min, sec: t.vteriny, od: toSec(t.od || "") ?? t.vteriny, do: toSec(t.do || ""),
             hrac: /lavička/.test(t.hrac) ? "" : raw(sd, t.hrac) };
  });
  m.nejlepsi = {};
  Object.values(z.nejlepsi || {}).forEach(n => { const sd = side(n.tym); m.nejlepsi[sd] = raw(sd, n.hrac); });
  m.bezGK = { A: (z.bez_brankare || {}).A || [], B: (z.bez_brankare || {}).B || [] };
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
  const res = { goly: [], tresty: [], rozhodci: { hlavni: [], carovi: [] }, divaci: "", strely: null, najezdy: [], jeZapis: true,
                nejlepsi: {}, bezGK: { A: [], B: [] } };
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
        goalsByNo[side].push({ sec: toSec(R(0)), s: R(1), a: [R(2), R(3)].filter(Boolean), sit: R(4),
                               led: [5, 6, 7, 8, 9, 10].map(R).filter(x => /^\d+$/.test(x || "")) });
      }
      if (toSec(R(17)) !== null && R(20)) {
        pensByNo[side].push({ min: R(19), no: R(18), sec: toSec(R(17)), od: toSec(R(21) || "") ?? toSec(R(17)), do: toSec(R(22) || "") });
      }
    }
    res[side] = team;
  });
  if (!ok(res)) return res;

  const nameOf = (side, no) => (res[side].hraci.find(h => h.c === no) || {}).jmeno || (no ? `č. ${no}` : "");
  ["A", "B"].forEach(side => {
    const skater = no => { const h = res[side].hraci.find(x => x.c === no); return h && h.post !== "GK" ? h.jmeno : null; };
    goalsByNo[side].forEach(g => res.goly.push({ side, sec: g.sec, strelec: nameOf(side, g.s), asist: g.a.map(n => nameOf(side, n)), sit: g.sit,
                                                naLedu: g.led.map(skater).filter(Boolean) }));
    pensByNo[side].forEach(p => res.tresty.push({ side, min: p.min, sec: p.sec, od: p.od, do: p.do, hrac: p.no === "HL" ? "" : nameOf(side, p.no) }));
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
      const gk = { A: [], B: [] }, bez = { A: [], B: [] }, otevrene = { A: null, B: null };
      for (const row of rowsAfter(tr).map(cells)) {
        const sec = toSec(row[0] || "");
        if (sec === null) continue;
        [["A", row[1]], ["B", row[2]]].forEach(([s, no]) => {
          if (/^\d+$/.test(no || "")) {
            if (!gk[s].length || gk[s][gk[s].length - 1].c !== no) gk[s].push({ c: no, od: row[0] });
            if (otevrene[s] !== null) { bez[s].push([otevrene[s], sec]); otevrene[s] = null; }
          } else if (no && otevrene[s] === null) otevrene[s] = sec;
        });
      }
      ["A", "B"].forEach(s => { if (otevrene[s] !== null) bez[s].push([otevrene[s], null]); });
      if (gk.A.length || gk.B.length) { out.A.brankari = gk.A; out.B.brankari = gk.B; out.bezGK = bez; break; }
    }
  }
  // nejlepší hráči utkání („Nejlepší hráč utkání tým - A“ | jméno)
  for (const td of doc.querySelectorAll("td, th")) {
    const mm = /nejlepší hráč utkání.*?-\s*([AB])\s*$/i.exec(clean(td.textContent));
    const next = mm && td.nextElementSibling;
    const jm = next ? clean(next.textContent) : "";
    if (!mm || !jm || /nejlepší/i.test(jm)) continue;
    const klic = lc(jm).split(" ").sort().join(" ");
    const h = out[mm[1]].hraci.find(x => { const p = splitPlayer(x.jmeno); return lc(`${p.prijmeni} ${p.jmeno}`).split(" ").sort().join(" ") === klic; });
    if (h) out.nejlepsi[mm[1]] = h.jmeno;
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
let BILANCE = null;       // obsah bilance_data.json (kariérní řádky hráčů; načítá jen stránka reportáže)
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

const JAK_TECH = [
  [/ze vzduchu/, "ze vzduchu"], [/teč|změn\w* směru|sáhl/, "tečí"], [/dorážk|dorazil/, "dorážkou"],
  [/z první/, "střelou z první"], [/bekhend/, "bekhendem"], [/prázdn\w* (bran|klec)/, "do prázdné branky"],
  [/od modré/, "střelou od modré"], [/od mantinelu/, "střelou od mantinelu"],
];
const JAK_SIT = [[/přečíslen/, "po přečíslení"], [/únik|sám na brankáře/, "z úniku"]];

function classify(e, match) {
  const t = lc(e.text), lidi = match(e.text);
  let hraci = lidi.filter(p => !p.gk);
  const brankari = lidi.filter(p => p.gk);
  // „X našel/přihrál Y…“ → akci zakončoval Y
  if (hraci.length >= 2 && hraci[0].side === hraci[1].side && /našel|přihr|posunul|nahrál|poslal|vyslal na/.test(t)) hraci = [hraci[1], hraci[0], ...hraci.slice(2)];
  const ev = [];
  if (/vstřelil\w* branku/.test(t)) {
    const tech = (JAK_TECH.find(([re]) => re.test(t)) || [])[1] || "";
    const sitn = (JAK_SIT.find(([re]) => re.test(t)) || [])[1] || "";
    ev.push({ typ: "gol", tech, sitn, odModre: /od modré/.test(t) });
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
      else if (Math.floor(po.g / 50) > Math.floor(pred.g / 50)) fakta.push({ w: 2, t: po.g % 50 ? `${kdo} překonal hranici ${po.g - po.g % 50} gólů ${kde}` : `${kdo} vstřelil ${po.g}. gól ${kde}`, scope, typ: "g" });
      if (c.g + c.a && pred.b === 0 && !c.g) fakta.push({ w: 3, t: `${kdo} si připsal první bod ${kde}`, scope, typ: "b" });
      else if (Math.floor(po.b / 50) > Math.floor(pred.b / 50)) fakta.push({ w: 2, t: po.b % 50 ? `${kdo} překonal hranici ${po.b - po.b % 50} bodů ${kde}` : `${kdo} si připsal ${po.b}. bod ${kde}`, scope, typ: "b" });
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


// ===== Skloňování mužských příjmení ==========================================
// Vrací 2., 3., 4. a 7. pád a příznak „jiste“. Kde si pravidlo není jisté
// (cizí koncovky, víceslovná jména), věta použije variantu v 1. pádě.
// Výjimky a opravy: tabulka SKLON, klíč = příjmení, hodnota = [koho, komu, koho, kým].

const SKLON = {
  "Lev": ["Lva", "Lvovi", "Lva", "Lvem"],
  "Jones": ["Jonese", "Jonesovi", "Jonese", "Jonesem"],
  "Egle": ["Egleho", "Eglemu", "Egleho", "Eglem"],
  "Macias": ["Maciase", "Maciasovi", "Maciase", "Maciasem"],
  "Havel": ["Havla", "Havlovi", "Havla", "Havlem"],
};

function sklonuj(prijmeni) {
  const s = prijmeni;
  const mk = (gen, dat, acc, ins, jiste = true) => ({ gen, dat, acc, ins, jiste });
  if (SKLON[s]) return mk(...SKLON[s]);
  if (!s || /[\s]/.test(s) || s.length < 3) return mk(s, s, s, s, false);
  const l = s.toLocaleLowerCase("cs");
  const st1 = s.slice(0, -1), st2 = s.slice(0, -2);
  if (/ý$/.test(l)) return mk(st1 + "ého", st1 + "ému", st1 + "ého", st1 + "ým");
  if (/í$/.test(l)) return mk(st1 + "ího", st1 + "ímu", st1 + "ího", st1 + "ím");
  if (/ů$/.test(l)) return mk(s, s, s, s);
  const mekke = { "ň": "n", "ď": "d", "ť": "t" };
  if (/a$/.test(l)) {
    const k = st1.slice(-1);
    const gen = mekke[k] ? st1.slice(0, -1) + mekke[k] + "i" : st1 + (/[žščřcj]$/.test(st1) ? "i" : "y");
    return mk(gen, st1 + "ovi", st1 + "u", st1 + "ou");
  }
  if (/o$/.test(l)) return mk(st1 + "a", st1 + "ovi", st1 + "a", st1 + "em");
  if (/[iy]$/.test(l)) return mk(s + "ho", s + "mu", s + "ho", s + "m");
  if (/[eě]$/.test(l)) return mk(s + "ho", s + "mu", s + "ho", s + "m", false);
  if (/[aáeéěiíoóuúůyýäöü]$/.test(l)) return mk(s, s, s, s, false);
  // souhlásky
  if (/ěk$/.test(l)) return mk(s + "a", s + "ovi", s + "a", s + "em", false);
  if (mekke[l.slice(-1)]) { const k = st1 + mekke[l.slice(-1)]; return mk(k + "ě", s + "ovi", k + "ě", k + "ěm"); }
  if (/ek$/.test(l) && s.length > 4) { const k = st2 + "k"; return mk(k + "a", k + "ovi", k + "a", k + "em"); }
  if (/ec$/.test(l) && s.length > 4) { const c = st2 + "c"; return mk(c + "e", c + "ovi", c + "e", c + "em"); }
  if (/[žščřcjďťň]$/.test(l)) return mk(s + "e", s + "ovi", s + "e", s + "em");
  if (/[xz]$/.test(l)) return mk(s + "e", s + "ovi", s + "e", s + "em", false);
  if (/s$/.test(l)) {                       // souhláska + s (Krastenbergs, Jaks) měkce; samohláska + s nejisté (Kos × Kraus)
    const jiste = /[^aáeéěiíoóuúůyý]s$/.test(l);
    return mk(s + "e", s + "ovi", s + "e", s + "em", jiste);
  }
  return mk(s + "a", s + "ovi", s + "a", s + "em");
}

// ===== Reportáž: analýza zápasu → plán textu → věty ===========================
// 1) analyzeMatch: fakta o zápase (váha gólů, typ příběhu, čísla)
// 2) buildReportage: plán odstavců z položek; každá položka má víc formulací
// 3) realize(stav): složí text; stav = které věty jsou vynechané a která formulace je zvolená

const KOD_TYMU = { "Sparta": "SPA", "Pardubice": "PCE", "Třinec": "TRI", "Vítkovice": "VIT", "Plzeň": "PLZ", "Liberec": "LIB",
  "Hradec": "MHK", "Kometa": "KOM", "Olomouc": "OLO", "Litvínov": "LIT", "Kladno": "KLA", "Ml. Boleslav": "MBL", "Vary": "KVA" };
const DEN_V = { "pondělí": "v pondělí", "úterý": "v úterý", "středa": "ve středu", "čtvrtek": "ve čtvrtek", "pátek": "v pátek", "sobota": "v sobotu", "neděle": "v neděli" };
const ORD_LOK = { 3: "ve třetím", 4: "ve čtvrtém", 5: "v pátém", 6: "v šestém", 7: "v sedmém", 8: "v osmém", 9: "v devátém", 10: "v desátém" };
const ORD_INS = { 2: "druhým", 3: "třetím", 4: "čtvrtým" };
const ORD_FEM = { 2: "druhá", 3: "třetí", 4: "čtvrtá", 5: "pátá", 6: "šestá", 7: "sedmá", 8: "osmá", 9: "devátá", 10: "desátá" };
const KRAT = { 2: "dvakrát", 3: "třikrát", 4: "čtyřikrát", 5: "pětkrát" };
const PRIBEH = { nula: "čisté konto", naprazdno: "bez gólu", obrat: "obrat", ztraceny: "ztracený náskok", marna: "marná stíhací jízda",
  udrzel: "ubráněná výhra po ztrátě náskoku", jasna: "jasný výsledek", obrat3: "obrat ve třetí třetině", ztraceny3: "ztracené vedení ve třetí třetině",
  zaver: "rozhodnutí v závěru", prestrelka: "přestřelka", brankar: "výkon brankáře", presilovky: "přesilovky", tretina: "rozhodující třetina", bezny: "běžný průběh" };
const vKole = n => `${[2, 3, 4, 12, 13, 14].includes(n) || (n >= 20 && n < 50) ? "ve" : "v"} ${n}. kole extraligy`;
const poSekundach = n => (n === 1 ? "po jediné sekundě" : `po ${n} sekundách`);
const velke = t => t.charAt(0).toLocaleUpperCase("cs") + t.slice(1);
const hashStr = s => { let h = 2166136261; for (const ch of String(s)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };

function analyzeMatch(m, kolo, onlineText) {
  const ms = motorSideOf(m), os = ms === "A" ? "B" : "A", doma = ms === "A";
  const entries = onlineText ? parseOnline(onlineText) : [];
  const match = makeMatcher(m);
  const events = [];
  entries.forEach(e => classify(e, match).forEach(ev => events.push({ ...ev, sec: e.sec })));
  const goly = [...m.goly].sort((a, b) => a.sec - b.sec).map(g => ({ ...g }));
  const gM = goly.filter(g => g.side === ms).length, gO = goly.length - gM;
  let sM = gM, sO = gO, poSN = false;
  if (m.najezdy.length && gM === gO) {
    const nM = m.najezdy.filter(p => p.side === ms && p.gol).length, nO = m.najezdy.filter(p => p.side === os && p.gol).length;
    poSN = true; if (nM > nO) sM++; else sO++;
  }
  const vyhra = sM > sO, poPr = !poSN && goly.some(g => g.sec >= 3600);
  const W = vyhra ? ms : os;
  const bez = m.bezGK || { A: [], B: [] };
  const inInt = (list, sec) => (list || []).some(([od, d]) => sec >= od && (d == null || sec <= d));
  const gkAt = (side, sec) => {
    const t = m[side], byNo = Object.fromEntries(t.hraci.map(h => [h.c, h]));
    let cur = null;
    (t.brankari || []).forEach(b => { if ((toSec(b.od || "") ?? 0) <= sec && byNo[b.c]) cur = byNo[b.c].jmeno; });
    return cur || (starterOf(t) || {}).jmeno || null;
  };

  let a = 0, b = 0, vitezny = null;
  const cnt = {}, vzadu = { A: false, B: false };
  goly.forEach((g, i) => {
    const jeM = g.side === ms, conc = g.side === "A" ? "B" : "A";
    g.idx = i;
    g.pred = [a, b];
    const tie = a === b;
    if (jeM) a++; else b++;
    g.po = [a, b];
    g.d0 = jeM ? g.pred[0] - g.pred[1] : g.pred[1] - g.pred[0];
    g.d1 = g.d0 + 1;
    g.skore = jeM ? `${a}:${b}` : `${b}:${a}`;
    g.obrat = g.d0 === 0 && vzadu[g.side];
    const dA = (ms === "A" ? a - b : b - a);
    if (dA < 0) { vzadu.A = true; vzadu.B = false; } else if (dA > 0) { vzadu.B = true; vzadu.A = false; }
    const k0 = g.side + "|" + g.strelec;
    g.nth = cnt[k0] = (cnt[k0] || 0) + 1;
    const mm = /(\d)\s*\/\s*(\d)/.exec(g.sit || "");
    g.sila = strength(g.sit);
    g.pet3 = !!mm && +mm[1] === 5 && +mm[2] === 3;
    g.en = (!!mm && +mm[2] === 6) || inInt(bez[conc], g.sec);
    g.vlastniBez = (!!mm && +mm[1] === 6) || inInt(bez[g.side], g.sec);
    const pens = m.tresty.filter(t => t.side === conc && [2, 4, 5].includes(parseInt(t.min, 10)) && t.od != null);
    const bezi = pens.filter(t => t.od <= g.sec && (t.do ?? t.od + parseInt(t.min, 10) * 60) >= g.sec);
    g.ppSec = g.sila === "pp" && bezi.length === 1 ? g.sec - bezi[0].od : null;
    g.poTrestu = g.sila === "ev" && pens.some(t => t.do != null && g.sec - t.do > 0 && g.sec - t.do <= 8);
    const prev = goly[i - 1];
    g.reply = prev && prev.side !== g.side && g.sec - prev.sec > 0 && g.sec - prev.sec <= 75 ? g.sec - prev.sec : null;
    const k = events.filter(ev => ev.typ === "gol" && Math.abs(ev.sec - g.sec) <= 20)
      .sort((x, y) => Math.abs(x.sec - g.sec) - Math.abs(y.sec - g.sec))[0];
    g.tech = k ? k.tech : ""; g.sitn = k ? k.sitn : "";
    if (/prázdné/.test(g.tech)) { g.en = true; g.tech = ""; }
    g.gk = g.en ? null : gkAt(conc, g.sec);
  });
  // vítězný gól: branka vítěze s pořadovým číslem o jednu vyšším, než kolik dal poražený
  if (!poSN) vitezny = goly.filter(g => g.side === W)[vyhra ? gO : gM] || null;
  const last = goly[goly.length - 1];
  goly.forEach((g, i) => {
    g.posledni = g === last;
    g.vitezny = g === vitezny;
    g.trida = g.vitezny && g.posledni && g.d0 === 0 ? "decisive" : i === 0 ? "open" : g.d1 === 0 ? "tie" : g.d0 === 0 ? "lead" : g.d0 > 0 ? "extend" : "reduce";
    let w = 2;
    if (g.vitezny && (goly.length - i <= 3 || g.sec >= 2400)) w += 3;
    if (["open", "tie", "lead", "decisive"].includes(g.trida)) w += 2;
    if (g.trida === "extend" && g.d1 >= 3) w -= 1;
    if (g.trida === "reduce") w += g.d1 === -1 ? 1 : -1;
    if (g.sila === "sh") w += 1;
    if (g.sec >= 3300 && g.sec < 3600 && Math.abs(g.d1) <= 1) w += 1;
    if (g.sec >= 3600) w += 3;
    if (g.side === ms) w += 0.5;
    if (g.nth >= 3) w += 2;
    if (g.tech || g.sitn) w += 0.5;
    if (g.en) w -= 0.5;
    g.w = w;
  });

  // průběh skóre z pohledu Motoru
  let x = 0, y = 0, worst = [0, 0], best = [0, 0], dotahlM = false, dotahlO = false;
  goly.forEach(g => {
    if (g.side === ms) x++; else y++;
    if (x - y < worst[0] - worst[1]) { worst = [x, y]; dotahlM = false; } else if (worst[1] - worst[0] >= 2 && x === y) dotahlM = true;
    if (x - y > best[0] - best[1]) { best = [x, y]; dotahlO = false; } else if (best[0] - best[1] >= 2 && x === y) dotahlO = true;
  });
  const stavPo = sec => { const v = goly.filter(g => g.sec < sec); const p = v.filter(g => g.side === ms).length; return [p, v.length - p]; };
  const po2 = stavPo(2400);
  const defM = worst[1] - worst[0], leadM = best[0] - best[1], rozdil = Math.abs(sM - sO);

  // rozhodující třetina: vítěz ji vyhrál aspoň o dva a bez ní by nevyhrál
  let rozhTretina = null;
  if (!poSN && !poPr) {
    const reg = goly.filter(g => g.sec < 3600), margin = Math.abs(gM - gO);
    for (const tr of [1, 2, 3]) {
      const v3 = reg.filter(g => Math.floor(g.sec / 1200) + 1 === tr);
      const p = v3.filter(g => g.side === W).length, q = v3.length - p;
      if (p - q >= 2 && p - q >= margin && margin >= 1 && v3.length < reg.length) { rozhTretina = { tr, x: p, y: q }; break; }
    }
  }

  // brankář Motoru
  const t = m[ms], byNo = Object.fromEntries(t.hraci.map(h => [h.c, h]));
  const chytali = (t.brankari || []).filter(q => byNo[q.c]);
  const gkM = starterOf(t);
  const strelyM = m.strely ? m.strely[ms === "A" ? 0 : 1] : null, strelyO = m.strely ? m.strely[ms === "A" ? 1 : 0] : null;
  const enProti = goly.filter(g => g.side === os && g.en).length;
  const zakroky = strelyO != null && new Set(chytali.map(q => q.c)).size <= 1 ? strelyO - gO : null;
  const pp = powerPlays(m, ms);

  // body hráčů v zápase
  const stat = {};
  goly.forEach(g => {
    const add = (raw, k) => { const e = (stat[g.side + "|" + raw] ||= { side: g.side, raw, g: 0, a: 0 }); e[k]++; };
    add(g.strelec, "g"); g.asist.forEach(q => add(q, "a"));
  });
  const vyrazni = Object.values(stat).filter(e => e.side === ms && (e.g >= 2 || e.g + e.a >= 3))
    .sort((p, q) => (q.g + q.a) - (p.g + p.a) || q.g - p.g).slice(0, 2);
  const souperStrelec = Object.values(stat).filter(e => e.side === os && e.g >= 2).sort((p, q) => q.g - p.g)[0] || null;

  let typ = "bezny";
  if (vyhra && gO === 0) typ = "nula";
  else if (!vyhra && gM === 0) typ = "naprazdno";
  else if (vyhra && defM >= 2) typ = "obrat";
  else if (!vyhra && leadM >= 2) typ = "ztraceny";
  else if (!vyhra && defM >= 2 && dotahlM) typ = "marna";
  else if (vyhra && leadM >= 2 && dotahlO) typ = "udrzel";
  else if (rozdil >= 3 && !poSN) typ = "jasna";
  else if (vyhra && po2[0] < po2[1]) typ = "obrat3";
  else if (!vyhra && po2[0] > po2[1]) typ = "ztraceny3";
  else if (poSN || poPr || (vitezny && vitezny.sec >= 3420)) typ = "zaver";
  else if (goly.length >= 9) typ = "prestrelka";
  else if (vyhra && zakroky != null && (zakroky >= 35 || (strelyO - strelyM >= 10 && gO <= 2))) typ = "brankar";
  else if (pp && pp.goly[W] >= 2 && pp.goly[W] * 2 >= (vyhra ? gM : gO)) typ = "presilovky";
  else if (rozhTretina) typ = "tretina";

  return { ms, os, doma, entries, events, goly, gM, gO, sM, sO, poSN, poPr, vyhra, W, vitezny, worst, best, po2, defM, leadM, rozdil,
           rozhTretina, gkM, chytali, zakroky, strelyM, strelyO, enProti, pp, stat, vyrazni, souperStrelec, typ, stavPo, gkAt };
}

function buildReportage(m, namer, kolo, onlineText, delka = "standard") {
  const ms = motorSideOf(m);
  if (!ms || !m.jeZapis) return null;
  const A = analyzeMatch(m, kolo, onlineText);
  const { os, doma, goly, events, vyhra, poSN, poPr, sM, sO, gM, gO, W } = A;
  const L = delka === "kratka" ? 1 : delka === "dlouha" ? 3 : 2;
  const opp = shortTeam(m[os].nazev), T = tvary(opp);
  const team = side => (side === ms ? "Motor" : doma ? "hosté" : "domácí");
  const teamAcc = side => (side === ms ? "Motor" : doma ? "hosty" : "domácí");
  const teamDat = side => (side === ms ? "Motoru" : doma ? "hostům" : "domácím");
  const teamGen = side => (side === ms ? "Motoru" : doma ? "hostů" : "domácích");
  const vb = (side, sg, pl) => (side === ms ? sg : pl);
  const periodOf = sec => (sec >= 3600 ? 4 : Math.floor(sec / 1200) + 1);
  const seed = hashStr(`${kolo}|${m.A.nazev}|${m.B.nazev}|${sM}:${sO}`);
  const sidx = (id, n) => hashStr(seed + "|" + id) % n;
  const volba = (id, list) => list[sidx(id, list.length)];
  const skore = `${sM}:${sO}`;
  const dod = poSN ? " po samostatných nájezdech" : poPr ? " po prodloužení" : "";
  const kdeS = doma ? `doma ${T.s}` : T.v;
  const H = "Hokejisté Motoru";

  // ----- jména: první zmínka celým jménem a s rolí, další pády jen u jistých příjmení -----
  const captain = captainFromOnline(onlineText, m, ms);
  const { st: sezona, zapasy: odehral } = seasonBefore(kolo);
  const lidr = (fn, min) => {
    const arr = Object.entries(sezona).map(([k, s]) => [k, fn(s)]).sort((p, q) => q[1] - p[1]);
    return arr.length && arr[0][1] >= min && (arr.length < 2 || arr[0][1] > arr[1][1]) ? arr[0][0] : null;
  };
  const topStrelec = lidr(s => s.g, 5), topBody = lidr(s => s.g + s.a, 8);
  const byRaw = {};
  ["A", "B"].forEach(sd => m[sd].hraci.forEach(h => (byRaw[h.jmeno] = { ...h, side: sd })));
  const mkCtx = () => {
    const seen = new Set(), gkSeen = new Set();
    const mention = (raw, c = {}) => {
      if (!raw) return "lavička";
      const kratce = namer.pl(raw);
      if (seen.has(raw)) return kratce;
      seen.add(raw);
      const p = splitPlayer(raw), h = byRaw[raw] || {};
      const krestni = p.jmeno.split(" ")[0];
      const alias = JMENA[`${p.prijmeni} ${p.jmeno}`.trim()];
      const plne = alias ? `${krestni} ${alias.replace(/^\p{Lu}\.\s*/u, "")}` : `${krestni ? krestni + " " : ""}${p.prijmeni}`;
      let role = "";
      if (c.gk) role = "brankář";
      else if (h.side === ms) {
        const base = baselineOf(raw), k = playerKey(raw);
        if (raw === captain) role = "kapitán";
        else if (c.gol && base && !(base.extraliga && base.extraliga.z) && (odehral[k] || 0) < 3) role = "nováček";
        else if (c.gol && k === topStrelec) role = "nejlepší střelec týmu";
        else if (c.gol && k === topBody) role = "nejproduktivnější hráč týmu";
        else if (c.gol && h.post === "D") role = "obránce";
      }
      return (role ? role + " " : "") + plne;
    };
    // skloněný tvar (gen/dat/acc/ins); null = příjmení si pravidla nejsou jistá → věta zůstane v 1. pádě
    const obl = (raw, pad) => {
      if (!raw) return null;
      const p = splitPlayer(raw);
      if (JMENA[`${p.prijmeni} ${p.jmeno}`.trim()]) return null;
      const sk = sklonuj(p.prijmeni);
      if (!sk.jiste) return null;
      const d = namer.pl(raw);
      return d.endsWith(p.prijmeni) ? d.slice(0, d.length - p.prijmeni.length) + sk[pad] : null;
    };
    return { seen, gkSeen, mention, obl, prevTyp: null };
  };

  // ----- časové údaje -----
  const specialKdy = g => {
    const zbyva = 3600 - g.sec, p = periodOf(g.sec);
    if (g.sec >= 3600) return `${vMinute(Math.floor((g.sec - 3600) / 60) + 1)} prodloužení`;
    if (zbyva <= 60) return `${sekundTxt(zbyva)} před koncem`;
    if (zbyva <= 120) return "necelé dvě minuty před koncem";
    const doKonce = p * 1200 - g.sec;
    if (p <= 2 && doKonce <= 30) return `${sekundTxt(doKonce)} před koncem ${ORD_GEN[p]} třetiny`;
    return null;
  };
  const casy = (items, pStart, p) => {
    const used = new Set();
    let prev = null;
    items.forEach(it => {
      let k = it.gol ? specialKdy(it.gol) : null;
      if (!k) {
        const gap = prev ? it.sec - (prev.secEnd ?? prev.sec) : null;
        let c = null;
        if (!prev && p && p <= 3 && it.sec - pStart <= 90) c = p === 1 ? "hned v úvodu zápasu" : `hned v úvodu ${ORD_GEN[p]} třetiny`;
        else if (gap !== null && gap <= 40) c = "vzápětí";
        else if (gap !== null && gap <= 80) c = "o minutu později";
        else if (gap !== null && gap <= 150) c = "o dvě minuty později";
        else if (gap !== null && gap <= 210) c = "o tři minuty později";
        if (c && !used.has(c)) { k = c; used.add(c); }
      }
      if (!k && it.gol) k = vMinute(minuteOfSec(it.sec));
      it._K = k; it._first = !prev;
      if (!/^(z|v|bez)/.test(it.id)) prev = it;
    });
  };

  // ----- věta o gólu: tři stavby (čas / střelec / účinek) + rychlá odpověď -----
  const VP = [(J, n) => `se ${J}${n}prosadil`, (J, n) => `${J}${n}skóroval`, (J, n) => `se ${J}${n}trefil`];
  const goalVars = (g, K, ctx) => {
    const jeM = g.side === ms, S = g.skore, id = "g" + g.sec;
    const sila = g.en ? "do prázdné branky" : g.vlastniBez ? "při hře bez brankáře"
      : g.sila === "pp" ? (g.ppSec != null && g.ppSec > 0 && g.ppSec <= 15 ? `${poSekundach(g.ppSec)} přesilovky` : g.pet3 ? "v přesilovce pěti proti třem" : "v přesilovce")
      : g.sila === "sh" ? "v oslabení" : g.poTrestu ? "krátce po skončení přesilovky" : "";
    const jak = g.tech || g.sitn;
    const komu = teamGen(g.side), tAcc = teamAcc(g.side);
    const konec = g.posledni && !poSN && g.sec < 3600 && goly.length > 1;
    let dej, C;
    if (g.trida === "decisive") { dej = `rozhodl o výhře ${komu}`; C = [`O výhře ${komu} rozhodl`, "Vítězný gól dal"]; if (goly.length === 1) C = ["Jediný gól zápasu dal"]; }
    else if (g.trida === "open") { dej = volba(id + "o", ["otevřel skóre", `poslal ${tAcc} do vedení`]); C = ["Skóre otevřel"]; }
    else if (g.trida === "tie") { dej = `${volba(id + "t", ["srovnal", "vyrovnal"])} na ${S}`; C = [`Na ${S} vyrovnal`, `Vyrovnání na ${S} zařídil`]; }
    else if (g.trida === "lead") {
      if (g.obrat && !ctx.obratUsed) { ctx.obratUsed = true; dej = `dokonal obrat na ${S}`; C = [`Obrat na ${S} dokonal`]; }
      else { dej = `poslal ${tAcc} do vedení ${S}`; C = [`Do vedení ${S} poslal ${tAcc}`]; }
    }
    else if (g.trida === "extend") { dej = konec ? `zvýšil na konečných ${S}` : `zvýšil na ${S}`; C = konec ? [`Konečný výsledek ${S} stanovil`, `Na konečných ${S} zvýšil`] : [`Na ${S} zvýšil`]; }
    else { dej = konec ? `snížil na konečných ${S}` : `snížil na ${S}`; C = konec ? [`Na konečných ${S} snížil`] : [`Na ${S} snížil`]; }
    const nthAdv = g.nth >= 2 && PORADI[g.nth] ? `${PORADI[g.nth]} v zápase ` : "";
    const nthIns = g.nth >= 2 && ORD_INS[g.nth] ? `svým ${ORD_INS[g.nth]} gólem v zápase ` : "";
    const hat = g.nth === 3 ? " Zkompletoval tím hattrick." : "";
    const N = () => ctx.mention(g.strelec, { gol: true });
    // asistence: buď „po přihrávce Nováka“ (jistý 2. pád, hráč už v textu byl), nebo samostatná věta
    const sAsist = g.asist.length && (jeM ? L >= 2 : L >= 3);
    const pripravy = () => {
      let J = [jak, sila].filter(Boolean).join(" "), tail = "";
      if (sAsist) {
        const gen = g.asist.length === 1 && !jak && ctx.seen.has(g.asist[0]) && sidx(id + "as", 2) === 0 ? ctx.obl(g.asist[0], "gen") : null;
        if (gen) J = [`po přihrávce ${gen}`, sila].filter(Boolean).join(" ");
        else tail = () => {
          const jm = joinCs(g.asist.map(q => ctx.mention(q)));
          return " " + (g.asist.length === 1 ? ["Asistoval", "Přihrával", "Na gólu se podílel i"][(g.idx + sidx("as1", 3)) % 3]
                                              : ["Asistovali", "Na gólu se podíleli i", "Přihrávali"][(g.idx + sidx("as2", 3)) % 3]) + ` ${jm}.`;
        };
      }
      return { J: J ? J + " " : "", tail: () => (tail ? tail() : "") + hat };
    };
    const vars = [];
    if (g.reply && ["tie", "reduce", "lead"].includes(g.trida))
      vars.push({ typ: "D", f: () => { const { J, tail } = pripravy(); return `${velke(team(g.side))} ${vb(g.side, "odpověděl", "odpověděli")} za ${sekundTxt(g.reply)}, ${N()} ${J}${g.trida === "lead" ? `zařídil vedení ${S}` : dej}.` + tail(); } });
    if (!/^\d/.test(capKdy(K)))
      vars.push({ typ: "T", f: () => { const { J, tail } = pripravy(); return `${capKdy(K)} ${VP[(g.idx + sidx("vp", 3)) % 3](J, nthAdv)} ${N()} a ${dej}.` + tail(); } });
    vars.push({ typ: "S", f: () => {
      const { J, tail } = pripravy();
      const kdo = velke(N());
      const acc = g.gk && !ctx.gkSeen.has(g.gk) && !nthIns ? ctx.obl(g.gk, "acc") : null;
      if (acc) { ctx.gkSeen.add(g.gk); return `${kdo} ${K} ${J}překonal ${acc} a ${dej}.` + tail(); }
      return `${kdo} ${K} ${J}${nthIns}${dej}.` + tail();
    } });
    C.forEach(c => vars.push({ typ: "C", f: () => { const { J, tail } = pripravy(); return `${c} ${K} ${J}${nthIns}${N()}.` + tail(); } }));
    return vars;
  };
  const goalItem = g => ({ id: "g" + g.sec, sec: g.sec, gol: g, fix: !!(g.reply && ["tie", "reduce", "lead"].includes(g.trida)),
                           render: (ctx, it) => goalVars(g, it._K, ctx) });

  // víc méně důležitých gólů jednoho týmu po sobě → jedna věta
  const runItem = run => {
    const f = run[0], l = run[run.length - 1], side = f.side;
    const d = l.sec - f.sec;
    const behem = d <= 60 ? `během ${d} sekund ` : d <= 300 && GEN2[Math.ceil(d / 60)] ? `během ${GEN2[Math.ceil(d / 60)]} minut ` : "";
    const sl = f.d0 === 0 ? ["odskočil na", "odskočili na"] : f.d0 > 0 ? ["zvýšil na", "zvýšili na"]
      : l.d1 < 0 ? ["snížil na", "snížili na"] : l.d1 === 0 ? ["srovnal na", "srovnali na"] : ["otočil na", "otočili na"];
    const jeden = run.every(g => g.strelec === f.strelec);
    return { id: "r" + f.sec, sec: f.sec, secEnd: l.sec, render: (ctx, it) => {
      const pak = it._first ? "" : " pak";
      const list = () => jeden
        ? `${run.length === 2 ? "oba góly" : "všechny góly"} dal ${ctx.mention(f.strelec)} (${run.map(g => minuteOfSec(g.sec) + ".").join(" a ")})`
        : null;
      const jmena = () => joinCs(run.map(g => `${ctx.mention(g.strelec)} (${minuteOfSec(g.sec)}.)`));
      const vars = [{ typ: "R", f: () => `${velke(team(side))}${pak} ${behem}${vb(side, sl[0], sl[1])} ${l.skore}, ${list() || `${volba("r" + f.sec, ["prosadili se", "trefili se"])} ${jmena()}`}.` }];
      if (!jeden && (f.d0 > 0 || l.d1 < 0)) vars.push({ typ: "C", f: () => `Na ${l.skore}${pak} postupně ${f.d0 > 0 ? "zvýšili" : "snížili"} ${jmena()}.` });
      return vars;
    } };
  };
  const prah = L === 1 ? 3.5 : L === 2 ? 2.5 : 1.5;
  const groupGoals = gs => {
    const out = [];
    let run = [];
    const flush = () => { if (run.length >= 2) out.push(runItem(run)); else run.forEach(g => out.push(goalItem(g))); run = []; };
    gs.forEach(g => {
      const low = g.w <= prah && !g.reply;
      if (low && run.length && run[0].side === g.side) run.push(g);
      else { flush(); if (low) run = [g]; else out.push(goalItem(g)); }
    });
    flush();
    return out;
  };

  // ----- nájezdy, hra bez brankáře -----
  const snItems = () => {
    if (!poSN) return [];
    const last = m.najezdy.filter(q => q.side === W && q.gol).pop();
    const out = [{ id: "sn", render: ctx => last
      ? [() => `Prodloužení gól nepřineslo a v nájezdech rozhodl ${ctx.mention(last.strelec)}.`,
         () => `O vítězi rozhodly až nájezdy, ten rozhodující proměnil ${ctx.mention(last.strelec)}.`]
      : ["Prodloužení gól nepřineslo, rozhodly až nájezdy."] }];
    if (L >= 3) {
      const dali = side => [...new Set(m.najezdy.filter(q => q.side === side && q.gol && q !== last).map(q => q.strelec))];
      const mm = dali(ms), oo = dali(os);
      if (mm.length || oo.length) out.push({ id: "sn2", render: ctx => {
        const cast = (side, l) => (l.length ? `za ${teamAcc(side)} ${joinCs(l.map(q => ctx.mention(q)))}` : null);
        return [`V nájezdech se ${last ? "dál " : ""}prosadili ${[cast(ms, mm), cast(os, oo)].filter(Boolean).join(", ")}.`];
      } });
    }
    return out;
  };
  const bezItem = () => {
    const L0 = vyhra ? os : ms;                                    // kdo prohrával
    const zap = ((m.bezGK || {})[L0] || []).filter(([od]) => od >= 3300 && od < 3600).map(([od]) => od);
    const kom = events.filter(e => e.typ === "bezGK" && e.side === L0 && e.sec >= 3300).map(e => e.sec);
    const od = Math.min(...zap, ...kom);
    if (!isFinite(od) || poSN || poPr || goly.some(g => g.sec >= od)) return null;
    const o1 = A.rozdil === 1;
    return { id: "bez", sec: od, render: () => o1
      ? [`${velke(team(L0))} v závěru ${vb(L0, "zkusil", "zkusili")} hru bez brankáře, vyrovnat se ${vb(L0, "mu", "jim")} ale nepodařilo.`,
         `Ani hra bez brankáře v závěru ${teamDat(L0)} vyrovnání nepřinesla.`]
      : [`${velke(team(L0))} v závěru ${vb(L0, "zkusil", "zkusili")} hru bez brankáře, skóre se už ale nezměnilo.`] };
  };

  // ----- události z online komentáře -----
  const eventItems = (evs, gs) => {
    const items = [];
    const prvniGol = gs.length ? gs[0].sec : Infinity, p = evs.length ? periodOf(evs[0].sec) : 0;
    const rane = p === 1 ? evs.find(e => (e.typ === "tyc" || (e.typ === "sance" && e.kdo)) && e.sec < prvniGol) : null;
    if (rane) items.push({ id: "e" + rane.sec, sec: rane.sec, render: ctx =>
      [() => `${velke(team(rane.side))} ${vb(rane.side, "mohl", "mohli")} jít do vedení už ${rane.sec < 120 ? "v úvodu zápasu" : vMinute(minuteOfSec(rane.sec))}, ${ctx.mention(rane.kdo)} ale ${rane.typ === "tyc" ? "trefil jen tyč" : "šanci nevyužil"}.`] });
    evs.filter(e => e.typ === "tyc" && e !== rane).forEach(e => {
      const znovu = events.some(q => q.typ === "tyc" && q.kdo === e.kdo && q.sec < e.sec);
      const co = znovu ? ["znovu trefil jen tyč"] : ["trefil tyč", "orazítkoval tyč", "nastřelil tyč"];
      items.push({ id: "e" + e.sec, sec: e.sec, render: (ctx, it) => co.map(c => () => (it._K ? `${capKdy(it._K)} ${c} ${ctx.mention(e.kdo)}.` : `${velke(ctx.mention(e.kdo))} ${c}.`)) });
    });
    if (L >= 3) {
      [ms, os].forEach(side => {
        const sn = evs.filter(e => e.typ === "sance" && e.kdo && e !== rane && e.side === side);
        const uniq = [...new Map(sn.map(e => [e.kdo, e])).values()].slice(0, 2);
        if (uniq.length === 1) items.push({ id: "e" + uniq[0].sec, sec: uniq[0].sec, render: (ctx, it) =>
          [["měl velkou šanci", ", ale neskóroval"], ["mohl skórovat", ", ale neuspěl"], ["nevyužil velkou šanci", ""]].map(([co, dv]) => () =>
            (it._K ? `${capKdy(it._K)} ${co} ${ctx.mention(uniq[0].kdo)}${dv}.` : `${velke(ctx.mention(uniq[0].kdo))} ${co}${dv}.`)) });
        if (uniq.length === 2) items.push({ id: "e" + uniq[0].sec, sec: uniq[0].sec, render: ctx =>
          [() => `${velke(team(side))} ${vb(side, "měl", "měli")} další velké šance, ${ctx.mention(uniq[0].kdo)} ani ${ctx.mention(uniq[1].kdo)} ale neskórovali.`] });
      });
      gs.forEach(g => {
        const vyz = events.find(e => e.typ === "vyzva" && !e.vzata && Math.abs(e.sec - g.sec) <= 20);
        const conc = g.side === ms ? os : ms;
        if (vyz) items.push({ id: "v" + g.sec, sec: g.sec + 1, render: () => [`${velke(team(conc))} si trenérskou výzvu ${vb(conc, "nevzal", "nevzali")}.`] });
      });
    }
    evs.filter(e => e.typ === "zraneni").forEach(e => {
      const nedohral = events.some(q => q.typ === "nedohral" && q.kdo === e.kdo && q.sec >= e.sec);
      const vratil = events.some(q => q.typ === "navrat" && q.kdo === e.kdo && q.sec > e.sec) ||
                     goly.some(g => g.sec > e.sec && (g.strelec === e.kdo || g.asist.includes(e.kdo)));
      if (items.some(q => q.id === "z" + e.kdo)) return;
      if (nedohral) items.push({ id: "z" + e.kdo, sec: e.sec, render: ctx => [() => `${velke(ctx.mention(e.kdo))} po zásahu ${e.brusle ? "bruslí " : ""}zápas nedohrál.`] });
      else if (!vratil) items.push({ id: "z" + e.kdo, sec: e.sec, render: ctx => [() => `${velke(ctx.mention(e.kdo))} musel ${e.brusle ? "po zásahu bruslí " : ""}na ošetření.`] });
    });
    return items;
  };

  // ----- odstavce po třetinách -----
  const NAZEV = { 1: ["první třetina", "úvodní třetina"], 2: ["druhá třetina", "prostřední třetina"], 3: ["třetí třetina", "závěrečná třetina"] };
  const NAZEV_LOK = { 1: ["v první třetině", "v úvodní třetině"], 2: ["ve druhé třetině", "v prostřední třetině"], 3: ["ve třetí třetině", "v závěrečné třetině"] };
  const odstavce = [];
  const stridej = (ctx, v) => { ctx.op = (ctx.op ?? sidx("op", 2)) + 1; return ctx.op % 2 && v.length > 1 ? [v[1], v[0], ...v.slice(2)] : v; };
  const bez = bezItem();
  if (L === 1) {
    const timed = groupGoals(goly);
    odstavce.push({ pre: [], timed, post: snItems(), p: 0, pStart: 0 });
  } else {
    const pocet = goly.some(g => g.sec >= 3600) || poSN ? 4 : 3;
    for (let p = 1; p <= pocet; p++) {
      const pStart = (p - 1) * 1200;
      const evs = events.filter(e => periodOf(e.sec) === p), gs = goly.filter(g => periodOf(g.sec) === p);
      const pre = [], post = [];
      const tr = (m.tretiny || []).find(r => r.tretina === String(p));
      if (tr && tr.strely && p <= 3) {
        const sm = tr.strely[ms === "A" ? 0 : 1], so = tr.strely[ms === "A" ? 1 : 0];
        const D = sm - so >= 5 ? ms : so - sm >= 5 ? os : null, X = D === ms ? os : ms;
        const sD = Math.max(sm, so), sX = Math.min(sm, so);
        const gD = gs.filter(g => g.side === D).length, gX = gs.length - gD;
        const n0 = velke(NAZEV[p][0]), n1 = velke(NAZEV[p][1]), l0 = NAZEV_LOK[p][0];
        if (D && !gs.length) pre.push({ id: "o" + p, fix: true, render: ctx => stridej(ctx, [
          `${n0} gól nepřinesla, i když ${team(D)} ${vb(D, "soupeře přestřílel", "Motor přestříleli")} ${sD}:${sX}.`,
          `${velke(team(D))} ${vb(D, "měl", "měli")} ${l0} střeleckou převahu ${sD}:${sX}, gól ale nepadl.`]) });
        else if (D && !gD) pre.push({ id: "o" + p, fix: true, render: ctx => stridej(ctx, [
          `${velke(team(D))} ${vb(D, "měl", "měli")} ${l0} střeleckou převahu ${sD}:${sX}, ${gX === 1 ? "jediný gól ale" : "góly ale"} ${vb(X, "dal Motor", `dali ${team(X)}`)}.`]) });
        else if (D) pre.push({ id: "o" + p, fix: true, render: ctx => stridej(ctx, [
          `${n0} patřila ${teamDat(D)}, ${vb(D, "který soupeře přestřílel", "kteří Motor přestříleli")} ${sD}:${sX}.`,
          `${velke(l0)} ${vb(D, "byl střelecky aktivnější Motor", `byli střelecky aktivnější ${team(D)}`)} (${sD}:${sX}).`]) });
        else if (!gs.length) pre.push({ id: "o" + p, fix: true, render: ctx => stridej(ctx, [`${n0} gól nepřinesla.`, `${n1} skončila bez branek.`]) });
      }
      const timed = [...groupGoals(gs), ...eventItems(evs, gs)];
      if (bez && periodOf(bez.sec) === p) timed.push(bez);
      timed.sort((q, r) => q.sec - r.sec);
      if (p <= 2 && (gs.length >= 2 || (L >= 3 && gs.length))) {
        const [x, y] = A.stavPo(p * 1200);
        const dalsi = p === 1 ? "druhé" : "třetí";
        post.push({ id: "s" + p, render: () => [
          `Po ${ORD_GEN[p]} třetině ${x === y ? `bylo ${x}:${y}` : x > y ? `vedl Motor ${x}:${y}` : `vedli ${team(os)} ${y}:${x}`}.`,
          `Do ${dalsi} třetiny se šlo za stavu ${Math.max(x, y)}:${Math.min(x, y)}${x === y ? "" : ` pro ${teamAcc(x > y ? ms : os)}`}.`] });
      }
      if (p === 4) post.push(...snItems());
      if (pre.length || timed.length || post.length) odstavce.push({ pre, timed, post, p, pStart });
    }
  }

  // ----- čísla a souvislosti: každý fakt má úroveň (1 = i v krátké verzi, 3 = jen v dlouhé) -----
  const cisla = [], souvis = [];
  const perexUsed = new Set();
  const fakt = (kam, id, lvl, klic, render, hrac = null) => kam.push({ id, lvl, klic, render, hrac });
  const heroVars = (e, ctx) => {
    const N = () => ctx.mention(e.raw);
    if (e.g >= 3) return e.a ? [() => `${velke(N())} si připsal ${boduTxt(e.g + e.a)} za hattrick a ${e.a === 1 ? "asistenci" : asistTxt(e.a)}.`]
                             : [() => `Hattrickem se blýskl ${N()}.`, () => `${velke(N())} dal tři góly.`];
    if (e.g === 2 && !e.a) return [() => `Dvěma góly se blýskl ${N()}.`, () => `${velke(N())} dal dva góly.`];
    if (!e.g) return [() => `${velke(N())} si připsal ${asistTxt(e.a)}.`, () => `${velke(asistTxt(e.a))} si připsal ${N()}.`];
    return [() => `${velke(N())} si připsal ${boduTxt(e.g + e.a)} (${goluTxt(e.g)} a ${asistTxt(e.a)}).`,
            () => `${velke(boduTxt(e.g + e.a))} (${goluTxt(e.g)} a ${asistTxt(e.a)}) si připsal ${N()}.`];
  };
  A.vyrazni.forEach(e => fakt(cisla, "h" + playerKey(e.raw), e.g >= 3 || e.g + e.a >= 3 ? 1 : 2, "hrac:" + e.raw, ctx => heroVars(e, ctx)));
  if (A.souperStrelec) {
    const e = A.souperStrelec;
    fakt(cisla, "hs", 2, "hrac:" + e.raw, ctx => [() => `Za ${teamAcc(os)} dal ${e.g >= 3 ? "tři góly" : goluTxt(e.g)} ${ctx.mention(e.raw)}.`]);
  }
  // útočná formace u víc gólů Motoru
  const trio = {};
  goly.filter(g => g.side === ms).forEach(g => {
    const f = (g.naLedu || []).filter(r => (byRaw[r] || {}).post === "F");
    if (f.length === 3) { const k = [...f].sort().join("|"); (trio[k] ||= { f, n: 0 }).n++; }
  });
  const utok = Object.values(trio).filter(q => q.n >= 2).sort((p, q) => q.n - p.n)[0];
  if (utok) {
    const por = r => m[ms].hraci.findIndex(h => h.jmeno === r);
    const f = [...utok.f].sort((p, q) => por(p) - por(q));
    const kolik = GEN2[utok.n] || utok.n;
    fakt(cisla, "utok", 2, "utok", ctx => {
      const tri = () => f.map(r => ctx.mention(r)).join(" – ");
      return [() => `U ${kolik} gólů Motoru byl na ledě útok ${tri()}.`, () => `Útok ${tri()} byl na ledě u ${kolik} gólů Motoru.`];
    });
  }
  // přesilovky
  if (A.pp) {
    const pp = A.pp;
    const ppTxt = side => {
      const n = pp.prilez[side], k = pp.goly[side];
      if (n <= 0) return null;
      const subj = velke(team(side)), sg = side === ms;
      if (n === 1) return `${subj} ${k ? (sg ? "proměnil" : "proměnili") : (sg ? "nevyužil" : "nevyužili")} svou jedinou přesilovku`;
      return k ? `${subj} ${sg ? "proměnil" : "proměnili"} ${ACC_CISLO[k] || k} ${zeZ(n)} ${GEN2[n] || n} přesilovek`
               : `${subj} ${sg ? "nevyužil" : "nevyužili"} ani jednu ${zeZ(n)} ${GEN2[n] || n} přesilovek`;
    };
    const parts = [ppTxt(ms), ppTxt(os)].filter(Boolean);
    if (parts.length === 2 && / přesilovek$/.test(parts[0]) && / přesilovek$/.test(parts[1])) parts[1] = parts[1].replace(/ přesilovek$/, "");
    const nM = pp.prilez[ms], nO = pp.prilez[os];
    if (!pp.goly[ms] && !pp.goly[os] && nM > 0 && nO > 0) fakt(cisla, "pp", 2, "pp", () => [nM === nO
      ? (nM === 1 ? "Ani jeden tým svou jedinou přesilovku nevyužil." : `Ani jeden tým nevyužil žádnou ze svých ${GEN2[nM] || nM} přesilovek.`)
      : `Přesilovky gól nepřinesly, Motor měl ${ACC_CISLO[nM] || nM}, ${team(os)} ${ACC_CISLO[nO] || nO}.`]);
    else if (parts.length) fakt(cisla, "pp", 2, "pp", () => [parts.map((t, i) => (i ? t.charAt(0).toLocaleLowerCase("cs") + t.slice(1) : t)).join(", ") + "."]);
  }
  // brankář Motoru
  const ruzni = [...new Set(A.chytali.map(q => q.c))];
  const byNoM = Object.fromEntries(m[ms].hraci.map(h => [h.c, h]));
  if (ruzni.length >= 2) {
    const g1 = byNoM[A.chytali[0].c].jmeno, zm = A.chytali.find(q => q.c !== A.chytali[0].c), g2 = byNoM[zm.c].jmeno;
    const sec = toSec(zm.od || "") ?? 0;
    const inkas = goly.filter(g => g.side === os && g.sec <= sec);
    const poGolu = inkas.length && sec - inkas[inkas.length - 1].sec <= 90
      ? ` po ${({ 1: "prvním", 2: "druhém", 3: "třetím", 4: "čtvrtém", 5: "pátém", 6: "šestém" })[inkas.length] || inkas.length + "."} inkasovaném gólu` : "";
    if (sec === 1200 || sec === 2400) fakt(cisla, "gk", 2, "gk", ctx => [() => `Do ${sec === 1200 ? "druhé" : "třetí"} třetiny už nenastoupil ${ctx.mention(g1, { gk: true })}, v brance ho nahradil ${ctx.mention(g2)}.`]);
    else if (sec > 0) fakt(cisla, "gk", 2, "gk", ctx => [() => `${velke(ctx.mention(g1, { gk: true }))} ${vMinute(minuteOfSec(sec))}${poGolu} opustil branku, nahradil ho ${ctx.mention(g2)}.`]);
  } else if (A.gkM && A.zakroky != null && A.strelyO > 0) {
    const raw = A.gkM.jmeno, celk = A.strelyO - A.enProti, zak = A.zakroky;
    if (gO === 0) fakt(cisla, "gk", 1, "gk", ctx => [() => `${velke(ctx.mention(raw, { gk: true }))} udržel čisté konto, kryl všech ${celk} střel.`,
                                                   () => `${velke(ctx.mention(raw, { gk: true }))} kryl všech ${celk} střel a udržel čisté konto.`]);
    else if (celk > zak && zak > 0) fakt(cisla, "gk", zak >= 35 || (zak >= 25 && zak / celk >= 0.94) ? 2 : 3, "gk",
      ctx => [() => `${velke(ctx.mention(raw, { gk: true }))} kryl ${zak} z ${celk} střel.`, () => `${velke(ctx.mention(raw, { gk: true }))} si připsal ${zak} zákroků.`]);
  }
  // střely
  if (A.strelyM != null) {
    const sm = A.strelyM, so = A.strelyO, kontrast = (!vyhra && sm - so >= 8) || (vyhra && so - sm >= 8);
    const pritom = kontrast ? "přitom " : "";
    if (sm !== so) fakt(cisla, "strely", kontrast ? 2 : 3, "strely", () => sm > so
      ? [`Na střely ${pritom}vyhrál Motor ${sm}:${so}.`, `Motor ${pritom}soupeře přestřílel ${sm}:${so}.`]
      : [`Na střely ${pritom}${doma ? "vyhráli hosté" : "vyhráli domácí"} ${so}:${sm}.`, `${velke(team(os))} ${pritom}Motor přestříleli ${so}:${sm}.`]);
    else fakt(cisla, "strely", 3, "strely", () => [`Střely na branku skončily ${sm}:${so}.`]);
  }
  // tresty do konce utkání
  [...new Set(m.tresty.filter(t => [20, 25].includes(parseInt(t.min, 10)) && t.hrac).map(t => t.hrac))].slice(0, 2)
    .forEach((raw, i) => fakt(cisla, "dku" + i, 2, "dku", ctx => [() => `${velke(ctx.mention(raw))} dostal trest do konce utkání.`]));
  // nejlepší hráči utkání
  if (m.nejlepsi && m.nejlepsi[ms] && m.nejlepsi[os])
    fakt(cisla, "nej", 3, "nej", ctx => [() => `Nejlepšími hráči utkání byli vyhlášeni ${ctx.mention(m.nejlepsi[ms])} a ${ctx.mention(m.nejlepsi[os])}.`]);

  // milníky
  const fakta = careerFacts(m, namer, kolo);
  fakta.forEach((f, i) => fakt(souvis, "mil" + i, f.w >= 3 ? 1 : 2, "mil" + i, ctx => [() => fillTpl(f, r => ctx.mention(r))], f.raw || null));
  // bodové a gólové série hráčů (ze zápisů sezony)
  if (DATA && kolo != null) {
    const pred = DATA.zapasy.filter(g => g.kolo < kolo && g.sestava && g.zapis).sort((p, q) => q.kolo - p.kolo);
    const serie = (raw, jenGoly) => {
      const k = playerKey(raw);
      let n = 1;
      for (const g of pred) {
        const sd = isMotor(g.sestava.A.nazev) ? "A" : "B", nazev = g.sestava[sd].nazev;
        if (!g.sestava[sd].hraci.some(h => h.hral && playerKey(h.jmeno) === k)) continue;
        const bod = g.zapis.goly.some(q => q.tym === nazev && (playerKey(q.strelec) === k || (!jenGoly && (q.asistence || []).some(s => playerKey(s) === k))));
        if (!bod) break;
        n++;
      }
      return n;
    };
    const kand = [];
    Object.values(A.stat).filter(e => e.side === ms).forEach(e => {
      const ng = e.g ? serie(e.raw, true) : 0, nb = serie(e.raw, false);
      if (ng >= 3 && ORD_LOK[ng]) kand.push({ raw: e.raw, n: ng + 0.5, t: `skóroval ${ORD_LOK[ng]} zápase po sobě` });
      else if (nb >= 3 && ORD_LOK[nb]) kand.push({ raw: e.raw, n: nb, t: `bodoval ${ORD_LOK[nb]} zápase v řadě` });
    });
    kand.sort((p, q) => q.n - p.n).slice(0, 2).forEach((q, i) =>
      fakt(souvis, "ser" + i, q.n >= 5 ? 1 : 2, "ser" + i, ctx => [() => `${velke(ctx.mention(q.raw))} ${q.t}.`], q.raw));
  }
  // kariérní góly střelců proti dnešnímu soupeři (z bilancí)
  let bilanceInfo = "";
  if (typeof BILANCE !== "undefined" && BILANCE && BILANCE.hraci && KOD_TYMU[opp]) {
    const kod = KOD_TYMU[opp];
    const hra = DATA && kolo != null ? DATA.zapasy.find(g => g.kolo === kolo) : null;
    const zid = hra ? String(hra.hokejcz_id || "") : "";
    let top = null;
    Object.values(A.stat).filter(e => e.side === ms && e.g).forEach(e => {
      const k = playerKey(e.raw);
      const rows = (Object.entries(BILANCE.hraci).find(([jm]) => playerKey(jm) === k) || [])[1];
      if (!rows) return;
      const sez = {}, maxS = Math.max(...rows.map(r => +r.season || 0));
      rows.forEach(r => { const c = (sez[r.season] ||= {}); c[r.a] = (c[r.a] || 0) + 1; c[r.b] = (c[r.b] || 0) + 1; });
      const klub = s => Object.entries(sez[s]).sort((p, q) => q[1] - p[1])[0][0];
      const dnes = r => (zid && String(r.zid || "") === zid) || (hra && +r.season === maxS && r.kolo === `${kolo}.` && /^Tipsport extraliga$/.test(r.comp));
      const driv = rows.filter(r => (r.a === kod || r.b === kod) && klub(r.season) !== kod && !dnes(r)).reduce((s, r) => s + (r.g || 0), 0);
      const celkem = driv + e.g;
      if (celkem >= 5 && (!top || celkem > top.n)) top = { raw: e.raw, n: celkem };
    });
    bilanceInfo = " · bilance hráčů načteny";
    if (top) fakt(souvis, "vs", 2, "vs", ctx => [() => `${velke(ctx.mention(top.raw))} dal ${T.dat} v extralize už ${top.n}. gól.`], top.raw);
  }
  // série týmu a vzájemné zápasy
  const sf = seasonFacts(kolo, vyhra, opp);
  if (sf) {
    const n = sf.serie, k = sf.ukoncena;
    if (n >= 2 && PORADI[n]) fakt(souvis, "serie", n >= 3 ? 1 : 2, "serie", () => [
      `Motor ${vyhra ? "vyhrál" : "prohrál"} ${PORADI[n]} v řadě.`, `Pro Motor je to ${ORD_FEM[n]} ${vyhra ? "výhra" : "porážka"} v řadě.`]);
    else if (k >= 3 && GEN_CISLO[k]) fakt(souvis, "serie", 1, "serie", () => [
      `Motor ukončil sérii ${GEN_CISLO[k]} ${vyhra ? "proher" : "výher"}.`, `Motor ${vyhra ? "vyhrál" : "prohrál"} poprvé po ${GEN_CISLO[k]} zápasech.`]);
    if (sf.r) {
      const r = sf.r, poradi = VZAJEMNY[sf.vzajemnych + 1] || "dalším";
      fakt(souvis, "vzaj", 2, "vzaj", () => [
        !r.win && vyhra ? `Motor soupeři oplatil porážku ${r.motor}:${r.souper} z ${sf.posl.kolo}. kola.`
        : r.win && !vyhra ? `Soupeř Motoru oplatil porážku ${r.souper}:${r.motor} z ${sf.posl.kolo}. kola.`
        : r.win ? `Soupeře Motor porazil i ve ${poradi} vzájemném zápase sezóny.` : `Se soupeřem Motor prohrál i ve ${poradi} vzájemném zápase sezóny.`]);
    }
    if (!fakta.some(f => f.debut)) {
      const hrali = new Set();
      DATA.zapasy.filter(g => g.kolo < kolo && g.sestava).forEach(g => {
        const t = isMotor(g.sestava.A.nazev) ? g.sestava.A : g.sestava.B;
        t.hraci.filter(h => h.hral).forEach(h => hrali.add(playerKey(h.jmeno)));
      });
      const nove = hrali.size ? m[ms].hraci.filter(h => h.hral && h.post !== "GK" && !hrali.has(playerKey(h.jmeno))).map(h => h.jmeno) : [];
      if (nove.length) fakt(souvis, "nove", 3, "nove", ctx => [() => `Poprvé v sezóně ${nove.length === 1 ? "nastoupil" : "nastoupili"} ${joinCs(nove.map(r => ctx.mention(r)))}.`]);
    }
  }
  // diváci
  const div = Number((m.divaci || "").replace(/\D/g, ""));
  if (div) {
    let dov = "";
    if (doma && DATA && kolo != null) {
      const dr = DATA.zapasy.filter(g => g.kolo < kolo && g.zapis && isMotor(g.domaci)).map(g => Number(String(g.zapis.divaci || "").replace(/\D/g, ""))).filter(Boolean);
      if (dr.length >= 4 && div > Math.max(...dr)) dov = ", nejvíc v sezóně";
      else if (dr.length >= 4 && div < Math.min(...dr)) dov = ", nejméně v sezóně";
    }
    const pocet = div.toLocaleString("cs-CZ").replace(/ /g, " ");
    fakt(souvis, "div", 2, "div", () => [`Utkání sledovalo ${pocet} diváků${dov}.`, `Na zápas přišlo ${pocet} diváků${dov}.`]);
  }
  // další zápas
  if (DATA && kolo != null) {
    const dal = DATA.zapasy.filter(g => g.kolo > kolo).sort((p, q) => p.kolo - q.kolo)[0];
    if (dal) {
      const dDoma = isMotor(dal.domaci), dT = tvary(shortTeam(dDoma ? dal.hoste : dal.domaci));
      const den = DEN_V[lc((dal.datum || "").split(" ")[0])];
      const kde = dDoma ? `doma ${dT.s}` : dT.v;
      fakt(souvis, "dalsi", 3, "dalsi", () => [`V dalším kole hraje Motor ${den ? den + " " : ""}${kde}.`, `Další zápas čeká Motor ${den ? den + " " : ""}${kde}.`]);
    }
  }

  // ----- perex: výsledek podle typu příběhu, klíčový moment, jedna souvislost -----
  const w = A.worst, bst = A.best, typ = A.typ;
  const zaklad = [`${H} ${vyhra ? "vyhráli" : "prohráli"} ${kdeS} ${skore}${dod}.`];
  if (kolo != null) zaklad.push(`${H} ${vKole(kolo)} ${vyhra ? (doma ? `porazili doma ${T.acc}` : `zvítězili ${T.v}`) : (doma ? `podlehli doma ${T.dat}` : `prohráli ${T.v}`)} ${skore}${dod}.`);
  const zac = `${H} ${vyhra ? "vyhráli" : "prohráli"} ${kdeS} ${skore}${dod}`;
  const kdeM = doma ? `doma ${T.s}` : T.v;
  let p1 = zaklad;
  if (typ === "obrat") p1 = [`${zac}, přestože prohrávali už ${w[0]}:${w[1]}.`, `${H} ${kdeM} otočili zápas ze stavu ${w[0]}:${w[1]} a vyhráli ${skore}${dod}.`];
  else if (typ === "ztraceny") p1 = [`${zac}, přestože vedli už ${bst[0]}:${bst[1]}.`, `${H} ${kdeM} neudrželi vedení ${bst[0]}:${bst[1]} a prohráli ${skore}${dod}.`];
  else if (typ === "marna") p1 = [`${zac}, přestože dotáhli ztrátu ${w[0]}:${w[1]}.`, `${H} ${kdeM} smazali ztrátu ${w[0]}:${w[1]}, přesto prohráli ${skore}${dod}.`];
  else if (typ === "udrzel") p1 = [`${zac}, i když přišli o vedení ${bst[0]}:${bst[1]}.`, `${H} ${kdeM} ztratili vedení ${bst[0]}:${bst[1]}, přesto vyhráli ${skore}${dod}.`];
  else if (typ === "obrat3") p1 = [`${zac}, přestože po dvou třetinách prohrávali ${A.po2[0]}:${A.po2[1]}.`];
  else if (typ === "ztraceny3") p1 = [`${zac}, přestože po dvou třetinách vedli ${A.po2[0]}:${A.po2[1]}.`];
  else if (typ === "naprazdno") p1 = [zaklad[0], `${H} ${kdeM} vyšli střelecky naprázdno a prohráli ${skore}.`];
  else if (typ === "jasna") {
    const sila = vyhra ? "jasně " : A.rozdil >= 4 ? "vysoko " : "";
    p1 = [`${H} ${vyhra ? "vyhráli" : "prohráli"} ${kdeS} ${sila}${skore}.`];
    if (kolo != null) p1.push(`${H} ${vKole(kolo)} ${vyhra ? (doma ? `přehráli doma ${T.acc}` : `zvítězili ${T.v} jasně`) : (doma ? `podlehli doma ${T.dat} ${sila}`.trim() : `prohráli ${T.v} ${sila}`.trim())} ${skore}.`);
  }
  else if (typ === "prestrelka") p1 = [`${zac} v zápase, ve kterém padlo ${goly.length} gólů.`, ...zaklad.slice(1)];
  else if (typ === "presilovky") { const n = A.pp.goly[W]; p1 = [`${zac}, ${KRAT[n] || n + "krát"} ${vyhra ? "se prosadili v přesilovce" : "inkasovali v oslabení"}.`]; }
  else if (typ === "tretina") { const r = A.rozhTretina; p1 = [`${zac}, rozhodla ${TRETINA[r.tr]} třetina, kterou ${vyhra ? `vyhráli ${r.x}:${r.y}` : `prohráli ${r.y}:${r.x}`}.`]; }

  const perex = [{ id: "p1", render: () => p1 }];
  const gkFakt = cisla.find(f => f.klic === "gk");
  const pridej = (id, f) => { perex.push({ id, render: f.render }); perexUsed.add(f.klic); };
  const hrdina = vyhra ? A.vyrazni[0] : null;
  const snLast = poSN ? m.najezdy.filter(q => q.side === W && q.gol).pop() : null;
  if (snLast) perex.push({ id: "p2", render: ctx => [() => `V nájezdech rozhodl ${ctx.mention(snLast.strelec)}.`, () => `Rozhodující nájezd proměnil ${ctx.mention(snLast.strelec)}.`] });
  else if (typ === "nula" && gkFakt) pridej("p2", gkFakt);
  else if (A.vitezny && typ !== "jasna" && typ !== "naprazdno") {
    const v = A.vitezny, kdy = specialKdy(v) || vMinute(minuteOfSec(v.sec));
    const e = A.stat[v.side + "|" + v.strelec];
    const dva = e && e.g >= 2 ? `, který skóroval ${KRAT[e.g] || e.g + "krát"}` : "";
    if (dva) perexUsed.add("hrac:" + v.strelec);
    perex.push({ id: "p2", render: ctx => goly.length === 1
      ? [() => `Jediný gól zápasu dal ${kdy} ${ctx.mention(v.strelec)}.`]
      : [...(v.d0 === 0 ? [() => `O výhře ${teamGen(W)} rozhodl ${kdy} ${ctx.mention(v.strelec)}${dva}.`] : []),
         () => `Vítězný gól dal ${kdy} ${ctx.mention(v.strelec)}${dva}.`] });
  }
  else if (hrdina) pridej("p2", cisla.find(f => f.klic === "hrac:" + hrdina.raw));
  else if (!vyhra && A.souperStrelec) pridej("p2", cisla.find(f => f.klic === "hrac:" + A.souperStrelec.raw));
  else if (A.rozhTretina) { const r = A.rozhTretina; perex.push({ id: "p2", render: () => [`O výsledku rozhodla ${TRETINA[r.tr]} třetina, kterou ${vyhra ? "Motor vyhrál" : `${team(os)} vyhráli`} ${r.x}:${r.y}.`] }); }
  else if (Math.abs(A.stavPo(1200)[0] - A.stavPo(1200)[1]) >= 2) { const [x, y] = A.stavPo(1200); perex.push({ id: "p2", render: () => [`Už po první třetině ${x > y ? "vedli" : "prohrávali"} ${x}:${y}.`] }); }
  else if (goly.length) perex.push({ id: "p2", render: ctx => [() => `Skóre otevřel ${vMinute(minuteOfSec(goly[0].sec))} ${ctx.mention(goly[0].strelec)}.`] });
  if (L >= 2 || perex.length < 2) {
    const milnik = souvis.find(f => /^mil/.test(f.klic) && fakta[+f.klic.slice(3)].w >= 2 && !fakta[+f.klic.slice(3)].raws);
    const serieF = souvis.find(f => f.klic === "serie" && f.lvl === 1);
    const hF = hrdina && !perexUsed.has("hrac:" + hrdina.raw) ? cisla.find(f => f.klic === "hrac:" + hrdina.raw) : null;
    const treti = (typ === "brankar" && gkFakt && !perexUsed.has("gk") ? gkFakt : null) || hF || milnik || serieF;
    if (treti) pridej("p3", treti);
  }

  // ----- závěrečné odstavce podle délky -----
  // o jednom hráči nejvýš jedna souvislost (v dlouhé verzi dvě), ať se odstavec netočí kolem jednoho jména
  const naHrace = {};
  const zbyle = list => list.filter(f => {
    if (f.lvl > L || perexUsed.has(f.klic) || (f.id === "hs" && L >= 2)) return false;
    if (f.hrac) { naHrace[f.hrac] = (naHrace[f.hrac] || 0) + 1; if (naHrace[f.hrac] > (L >= 3 ? 2 : 1)) return false; }
    return true;
  });
  let konec = [];
  if (L === 1) konec = [[...zbyle(cisla), ...zbyle(souvis)].slice(0, 2)];
  else if (L === 2) konec = [zbyle(cisla).slice(0, 4), zbyle(souvis).slice(0, 4)];
  else konec = [zbyle(cisla), zbyle(souvis)];
  konec.filter(k => k.length).forEach(k => odstavce.push({ pre: k, timed: [], post: [], p: 0, pStart: 0 }));

  // jednoznačná id položek (stav úprav se váže na id)
  const idSeen = new Set();
  [perex, ...odstavce.map(o => [...o.pre, ...o.timed, ...o.post])].flat().forEach(it => { while (idSeen.has(it.id)) it.id += "_"; idSeen.add(it.id); });

  // ----- skládání textu -----
  const norm = v => (typeof v === "function" ? { f: v } : typeof v === "string" ? { f: () => v } : v);
  const lint = vety => {
    const out = [], text = vety.join(" ");
    if (/undefined|null|NaN/.test(text)) out.push("v textu chybí údaj");
    if (/ {2,}| [.,]|\.\.|,,/.test(text)) out.push("mezery nebo interpunkce");
    if (vety.some(v => /^\p{Ll}/u.test(v))) out.push("věta začíná malým písmenem");
    if (new Set(vety).size < vety.length) out.push("opakuje se stejná věta");
    const prvni = vety.map(v => lc(v.split(" ")[0]));
    if (prvni.some((s, i) => i >= 2 && s === prvni[i - 1] && s === prvni[i - 2])) out.push("tři věty po sobě začínají stejně");
    return out;
  };
  const realize = (state = {}) => {
    const off = state.off || {}, vi = state.vi || {};
    const one = (item, ctx) => {
      if (off[item.id]) return { id: item.id, off: true, text: null, n: 0 };
      const vars = item.render(ctx, item).map(norm), n = vars.length;
      let i = item.fix ? 0 : sidx(item.id, n);
      if (!item.fix && n > 1 && vars[i].typ && vars[i].typ === ctx.prevTyp) i = (i + 1) % n;
      i = (i + (vi[item.id] || 0)) % n;
      const text = vars[i].f();
      ctx.prevTyp = vars[i].typ || null;
      return { id: item.id, text, n };
    };
    const pc = mkCtx();
    const perexOut = perex.map(it => one(it, pc));
    const bc = mkCtx();
    const odst = odstavce.map(o => {
      casy(o.timed.filter(it => !off[it.id]), o.pStart, o.p);
      return [...o.pre, ...o.timed, ...o.post].map(it => one(it, bc));
    });
    const spoj = list => list.filter(s => !s.off).map(s => s.text).join(" ");
    const perexText = spoj(perexOut), text = odst.map(spoj).filter(Boolean).join("\n\n");
    return { perex: perexOut, odstavce: odst, perexText, text, varovani: lint([...perexOut, ...odst.flat()].filter(q => !q.off).map(q => q.text)) };
  };

  // ----- titulky -----
  const tit = buildHeadlines(m, namer, kolo);
  const tyceM = events.filter(e => e.typ === "tyc" && e.side === ms).length;
  if (tyceM >= 2) tit.unshift(`Motor ${KRAT[tyceM] || tyceM + "krát"} trefil tyč, ${vyhra ? `přesto porazil ${T.acc}` : `${T.dat} podlehl`} ${skore}`);
  const milTit = fakta.find(f => f.w >= 2 && !f.raws);
  if (milTit) tit.splice(1, 0, `${milTit.text.replace(/\.$/, "")}, Motor ${vyhra ? `porazil ${T.acc}` : `podlehl ${T.dat}`} ${skore}`);

  const golyKom = events.filter(e => e.typ === "gol").length;
  const sparovane = goly.filter(g => events.some(e => e.typ === "gol" && Math.abs(e.sec - g.sec) <= 20)).length;
  const nesedi = A.entries.length && goly.length && sparovane < Math.min(goly.length, golyKom);
  const kontrola = `příběh zápasu: ${PRIBEH[typ]} · ` +
    (A.entries.length ? `záznamů v komentáři: ${A.entries.length} · gólů v komentáři: ${golyKom}, se zápisem sedí ${sparovane}` +
       ` · z komentáře: popis gólu ${goly.filter(g => g.tech || g.sitn).length}×, tyčky ${events.filter(e => e.typ === "tyc").length}, ` +
       `šance ${events.filter(e => e.typ === "sance").length}, zranění ${events.filter(e => e.typ === "zraneni").length}`
     : "bez online komentáře — jen ze zápisu") +
    (nesedi ? " — ⚠️ komentář možná patří k jinému zápasu" : "") + (captain ? ` · kapitán: ${namer.pl(captain)}` : "") + bilanceInfo;
  const r0 = realize();
  return { titulky: [...new Set(tit)].slice(0, 6), perex: r0.perexText, text: r0.text, kontrola, realize, typ };
}
