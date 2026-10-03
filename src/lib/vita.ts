/**
 * Builds Prof. Sarkar's FACULTY VITA (Iowa State format) from the archived vita (src/data/vita.json, 08/11/2023)
 * plus everything the website has learned since: publications (weekly OpenAlex/Crossref updates, venue updates,
 * contributions), citation metrics, grants, awards, invited talks and student milestones.
 *
 * Rules
 *  - Items from the original vita are reproduced verbatim (author marks +, *, #, underline and italics included).
 *  - New publications are formatted in the same style: lab graduate students/postdocs get "+", undergraduates "*",
 *    the corresponding author (OpenAlex) is underlined.
 *  - Periods: "During current rank at ISU" (Professor since July 2023), "During previous rank at ISU", "Prior to ISU
 *    appointment" (before Aug 2014); numbering continues across periods exactly as in the original.
 */
import vitaData from '../data/vita.json' with { type: 'json' };
import metrics from '../data/scholar-metrics.json' with { type: 'json' };
import pubMeta from '../data/pub-meta.json' with { type: 'json' };
import recentFunding from '../data/funding-recent.json' with { type: 'json' };
import awardsData from '../data/awards.json' with { type: 'json' };
import piPage from '../data/page-principal-investigator.json' with { type: 'json' };
import talksVideo from '../data/talks-video.json' with { type: 'json' };
import profiles from '../data/people-profiles.json' with { type: 'json' };
import { publications, type Pub } from './publications';
import { people } from './people';

export type Grant = { n: string; investigators: string; title: string; agency: string; dates: string; total: string; role: string };
export type Block = { heading: string | null; style: string; items: string[]; grants?: Grant[]; numbers?: string[] };
export type Sub = { id: string; letter?: string; number?: string; title: string; blocks: Block[]; children?: Sub[]; numberingContinues?: boolean };
export type Section = { id: string; title: string; subsections: Sub[] };

const CUR = 'During current rank at ISU', PREV = 'During previous rank at ISU', PRIOR = 'Prior to ISU appointment';
const strip = (s: string) => s.replace(/<[^>]+>/g, '');
const norm = (s: string) => strip(s).toLowerCase().replace(/[^a-z0-9]/g, '');
const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** Similarity of two normalised strings (bigram Dice) — robust to small wording/punctuation differences. */
function sim(a: string, b: string) {
  if (!a || !b) return 0;
  if (a === b) return 1;
  const grams = (s: string) => { const m = new Map<string, number>(); for (let i = 0; i < s.length - 1; i++) { const g = s.slice(i, i + 2); m.set(g, (m.get(g) ?? 0) + 1); } return m; };
  const A = grams(a), B = grams(b); let inter = 0;
  A.forEach((n, g) => (inter += Math.min(n, B.get(g) ?? 0)));
  return (2 * inter) / (a.length - 1 + b.length - 1);
}
/** Paper title inside an original vita item (between the first pair of quotes). */
function titleOf(item: string) {
  const t = strip(item);
  const m = t.match(/[“"]\s*(.+?)\s*[,.]?\s*[”"]/);
  return m ? m[1] : '';
}
const yearOf = (s: string) => {
  const t = strip(s).replace(/https?:\/\/\S+/g, ' ').replace(/\b10\.\d{4,}\/\S+/g, ' ');
  const ys = [...t.matchAll(/(?<![\d.])(19[89]\d|20[0-4]\d)(?![\d])/g)].map((m) => Number(m[1])).filter((y) => y <= new Date().getFullYear() + 1);
  return ys.length ? ys[ys.length - 1] : 0;
};
const periodOfYear = (y: number) => (y >= 2023 ? CUR : y >= 2015 ? PREV : PRIOR);

// ---------------------------------------------------------------- lab roster -> author marks
const STUDENT = new Set(['Post Doctoral Students', 'Doctoral Students', 'Masters Students', 'Research Students on Independent Studies', 'Visiting Scholars',
  'Post-doctorate Alumni', 'Graduate Alumni', 'Masters Alumni', 'Independent Study Alumni', 'Visiting Scholar Alumni']);
const UNDERGRAD = new Set(['Undergraduate Researchers', 'Undergraduate Alumni']);
const ALIASES: Record<string, string[]> = {
  'Bernard Lee Xian Yeow': ['Xian Yeow Lee'], 'Russell Kai Liang Tan': ['Kai Liang Tan', 'Russell Tan'], 'Sin Yong Tan (Evan)': ['Sin Yong Tan'],
  'Jaydeep-Ravindra Rade': ['Jaydeep Rade'], 'Sambit Gadhai': ['Sambit Ghadai'], 'Zahid Hasan': ['Md Zahid Hasan'], 'Truong Tran': ['Troung Tran'],
  'Fateme Fotouhi Ardakani': ['Fateme Fotouhi'], 'Muhammad Arbab Arshad': ['Arbab Arshad'], 'Luis G. Riera': ['Luis Riera'],
};
const key2 = (name: string) => { const t = name.replace(/\(.*?\)/g, '').replace(/\./g, ' ').trim().split(/\s+/); return t.length ? `${t[0][0]?.toLowerCase()}|${norm(t[t.length - 1])}` : ''; };
const markOf = new Map<string, string>();
for (const p of people) {
  if (/soumik sarkar/i.test(p.name)) continue;
  const mark = STUDENT.has(p.category ?? '') ? '+' : UNDERGRAD.has(p.category ?? '') ? '*' : '';
  if (!mark) continue;
  for (const n of [p.name.replace(/^Dr\.\s*/, ''), ...(ALIASES[p.name] ?? [])]) markOf.set(key2(n), mark);
}
const corresponding = (pubMeta as { byTitle: Record<string, { corresponding: string[] }> }).byTitle;

/** "Ashutosh Kumar Nirala" -> "A. K. Nirala" (hyphenated first names keep their parts: "H.-J. Yang"). */
function initials(name: string) {
  const parts = name.replace(/\./g, '. ').trim().split(/\s+/).filter(Boolean);
  if (parts.length < 2) return name;
  const last = parts.pop()!;
  return [...parts.map((p) => p.split('-').map((x) => (x.length <= 2 && x.endsWith('.') ? x : `${x[0].toUpperCase()}.`)).join('-')), last].join(' ');
}
function authorList(p: Pub) {
  const sarkarCorresponding = (corresponding[norm(p.title)]?.corresponding ?? []).some((n) => key2(n) === key2('Soumik Sarkar'));
  const names = (p.authors ?? '').split(/\s+and\s+|,\s*/).map((a) => a.trim()).filter(Boolean);
  return names.map((n) => {
    const k = key2(n); let s = esc(initials(n)) + (markOf.get(k) ?? '');
    if (sarkarCorresponding && k === key2('Soumik Sarkar')) s = `<u>${s}</u>`;   // "_ denotes corresponding authorship of the candidate"
    return s;
  }).join(', ');
}
const cleanVenue = (v: string | null) => {
  let s = (v ?? '').replace(/\s*\((19|20)\d{2}\)\s*$/, '').replace(/,\s*$/, '');
  s = s.replace(/^(.+?)\s+[\d(),\s-]+,\s*(19|20)\d{2},\s*(Vol\.)/, '$1, $3');   // drop a duplicated "190, 199-273, 2025," before "Vol."
  return s;
};
function formatPub(p: Pub) {
  const doi = p.doi ? ` <a href="https://doi.org/${esc(p.doi)}">https://doi.org/${esc(p.doi)}</a>` : p.url && !/scholar\.google/.test(p.url) ? ` <a href="${esc(p.url)}">${esc(p.url)}</a>` : '';
  const venue = cleanVenue(p.venue);
  return `${authorList(p)}, "<i>${esc(p.title)}</i>,"${venue ? ` ${esc(venue)},` : ''} ${p.year ?? ''}.${doi}`.replace(/\s+\./, '.');
}

// ---------------------------------------------------------------- helpers over the original vita
export type VitaMeta = { title: string; name: string; department: string; rank: string; originalDate: string; date: string };
const vita = vitaData as unknown as { meta: Omit<VitaMeta, 'date'>; sections: Section[] };
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
function findSub(sections: Section[], id: string): Sub {
  const walk = (subs: Sub[]): Sub | undefined => { for (const s of subs) { if (s.id === id) return s; const c = walk(s.children ?? []); if (c) return c; } };
  for (const s of sections) { const r = walk(s.subsections); if (r) return r; }
  throw new Error(`vita section ${id} not found`);
}
const block = (sub: Sub, heading: string) => {
  let b = sub.blocks.find((x) => x.heading === heading);
  if (!b) { b = { heading, style: 'numbered', items: [] }; sub.blocks.push(b); }
  return b;
};

/** Merge site publications of `categories` into a vita publication subsection (originals kept verbatim). */
const VITA_YEAR = 2023;   // the archived vita is complete up to 08/2023; only later work is added automatically
let ALL_ORIGINAL_TITLES: string[] = [];
function mergePublications(sub: Sub, categories: string[], extraFilter: (p: Pub) => boolean = () => true) {
  const originals = sub.blocks.flatMap((b, bi) => b.items.map((item, i) => ({ item, period: b.heading ?? CUR, title: norm(titleOf(item)), year: yearOf(item), order: bi * 1000 + i })));
  const seenAnywhere = (t: string) => ALL_ORIGINAL_TITLES.some((o) => o && (sim(o, t) >= 0.85 || (t.length > 30 && (o.includes(t) || t.includes(o)))));
  const added: { item: string; period: string; year: number; order: number }[] = [];
  for (const p of publications) {
    if (!categories.includes(p.category) || !extraFilter(p)) continue;
    if ((p.year ?? 0) < VITA_YEAR) continue;
    const t = norm(p.title);
    if (seenAnywhere(t)) continue;
    added.push({ item: formatPub(p), period: periodOfYear(p.year ?? 0), year: p.year ?? 0, order: -1 });
  }
  for (const period of [CUR, PREV, PRIOR]) {
    const b = sub.blocks.find((x) => x.heading === period);
    const mine = [...originals.filter((o) => o.period === period), ...added.filter((a) => a.period === period)]
      .sort((a, b) => b.year - a.year || a.order - b.order);
    if (b) b.items = mine.map((m) => m.item); else if (mine.length) sub.blocks.push({ heading: period, style: 'numbered', items: mine.map((m) => m.item) });
  }
  sub.blocks.sort((a, b) => [CUR, PREV, PRIOR].indexOf(a.heading ?? '') - [CUR, PREV, PRIOR].indexOf(b.heading ?? ''));
  const count = (period?: string) => sub.blocks.filter((b) => !period || b.heading === period).reduce((n, b) => n + b.items.length, 0);
  const withStudents = sub.blocks.reduce((n, b) => n + b.items.filter((i) => /\+/.test(strip(i))).length, 0);
  return { total: count(), afterIsu: count(CUR) + count(PREV), current: count(CUR), withStudents, added: added.length };
}

// ---------------------------------------------------------------- build
export function buildVita() {
  const sections = clone(vita.sections);
  ALL_ORIGINAL_TITLES = ['II.A.1', 'II.A.3', 'II.A.2b'].flatMap((id) => findSub(sections, id).blocks.flatMap((b) => b.items.map((i) => norm(titleOf(i)))));

  // I.D Honors: originals + newer awards (awards.json), newest first
  const honors = findSub(sections, 'I.D').blocks[0];
  for (const a of awardsData.awards) {
    const t = a.text.replace(/,\s*((19|20)\d{2})$/, ' ($1)');
    if (!honors.items.some((h) => sim(norm(h), norm(t)) >= 0.6 || norm(h).includes(norm(t.split('(')[0])))) honors.items.push(t);
  }
  honors.items.sort((a, b) => yearOf(b) - yearOf(a));

  // II.A.1 journals, II.A.3 conferences, book chapters
  const J = mergePublications(findSub(sections, 'II.A.1'), ['journals'], (p) => !/chapter/i.test(p.categoryLabel ?? '') && (p as Pub & { type?: string }).type !== 'book-chapter');
  const K = mergePublications(findSub(sections, 'II.A.3'), ['conferences']);
  const C = mergePublications(findSub(sections, 'II.A.2b'), ['journals'], (p) => (p as Pub & { type?: string }).type === 'book-chapter');

  // II.A summary bullets 1–2 (3–4 kept verbatim)
  const sum = findSub(sections, 'II.A').blocks[0];
  sum.items[0] = `<i>Total of ${J.total + C.total + K.total} publications including ${J.total} peer reviewed journal papers (${J.afterIsu} after joining ISU – ${J.current} at the current rank, ${J.withStudents} with ISU students/postdocs), Total ${C.total} book chapters (${C.afterIsu} after joining ISU – ${C.current} at the current rank, ${C.withStudents} with ISU students/postdocs) and ${K.total} peer reviewed conference papers (${K.afterIsu} after joining ISU – ${K.current} at the current rank, ${K.withStudents} with ISU students and postdocs).</i>`;
  const m = metrics as { citations: number; hIndex: number; i10Index: number; collected: string };
  const d = new Date(m.collected + 'T00:00:00');
  sum.items[1] = `<i>My published work received a cumulative ${m.citations} citations with h-index of ${m.hIndex} and i10 index of ${m.i10Index} according to OpenAlex (data collected on ${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}/${d.getFullYear()}).</i>`;

  // II.A.3b invited talks: originals + newer talks from the PI page and verified recordings
  const talks = findSub(sections, 'II.A.3b');
  const talkItems = talks.blocks.filter((b) => b.heading).flatMap((b) => b.items);
  const known = (t: string) => talkItems.some((x) => sim(norm(x), norm(t)) >= 0.7);
  const newTalks: string[] = [];
  const piTalks = (piPage.find((s) => s.heading === 'Invited Talks')?.items ?? []).map((i) => i.text);
  for (const t of piTalks) if (yearOf(t) >= 2023 && !known(t)) { const [title, ...rest] = t.split(', '); newTalks.push(`<i>${esc(title)}</i>, ${esc(rest.join(', '))}${/\.$/.test(t) ? '' : '.'}`); }
  for (const v of talksVideo as { title: string; event: string; date: string }[]) {
    if (new Date(v.date) < new Date('2023-08-12')) continue;
    const t = `${v.title}, ${v.event}`;
    if (!known(t) && !newTalks.some((x) => sim(norm(x), norm(t)) >= 0.6)) newTalks.push(`<i>${esc(v.title)}</i>, ${esc(v.event)}, ${new Date(v.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}.`);
  }
  newTalks.sort((a, b) => yearOf(b) - yearOf(a));
  const curTalks = block(talks, CUR); curTalks.items = [...newTalks, ...curTalks.items];
  const nTalks = talks.blocks.filter((b) => b.heading).reduce((n, b) => n + b.items.length, 0);
  const isuTalks = talks.blocks.filter((b) => b.heading === CUR || b.heading === PREV).reduce((n, b) => n + b.items.length, 0);
  talks.blocks[0].items[0] = `<i>${nTalks} invited talks (${isuTalks} after joining ISU – ${curTalks.items.length} at the current rank) at various universities, academic conferences, companies and government labs.</i>`;

  // II.C funded grants: originals + newer grants (funding-recent.json)
  const grants = findSub(sections, 'II.C');
  const allGrants = grants.blocks.flatMap((b) => b.grants ?? []);
  const cur = grants.blocks.find((b) => b.heading === CUR)!;
  let next = allGrants.length;
  let addedFunds = 0;
  const parsed = recentFunding.grants.map((g) => {
    const m2 = g.text.match(/^(.*?) \(as (.*?)\)(?: sponsored by (.*?))? \((\$[\d,]+)(?:, (.*?))?\)$/);
    return m2 ? { title: m2[1], role: m2[2], agency: m2[3] ?? '', total: m2[4], dates: m2[5] ?? '' } : null;
  }).filter((x): x is NonNullable<typeof x> => !!x);
  for (const g of parsed.reverse()) {
    if (allGrants.some((o) => sim(norm(o.title), norm(g.title)) >= 0.8)) continue;
    addedFunds += Number(g.total.replace(/[$,]/g, ''));
    cur.grants = [...(cur.grants ?? []), { n: `Grant ${++next}`, investigators: /^PI$/i.test(g.role.trim()) ? 'Soumik Sarkar (ISU ME)' : 'Soumik Sarkar (ISU ME) and others', title: g.title, agency: g.agency.replace(/^the /, ''), dates: g.dates, total: g.total, role: g.role }];
  }
  const every = grants.blocks.flatMap((b) => b.grants ?? []);
  const asPI = every.filter((g) => /^(PI|Lead PI)\b/i.test(g.role.trim())).length;
  const totalM = (53.2 + addedFunds / 1e6).toFixed(1);
  grants.blocks[0].items[0] = `<i>Total ${every.length} federal, state and industry grants (${asPI} as PI) from a variety of sources including NSF, USDA-NIFA, AFOSR, DARPA, NIH, DOT, DOE, DoD and ARPA-E</i>`;
  grants.blocks[0].items[1] = `<i>Total funding of approximately $${totalM}M (approximately $7.5M allocated to the Sarkar research group as of 08/2023)</i>`;

  // II-T.C supervision: move graduated "in progress" students, add new students, recount
  const sup = findSub(sections, 'II-T.C');
  const prog = sup.blocks.find((b) => b.heading === 'In progress')!;
  const curSup = sup.blocks.find((b) => b.heading === CUR)!;
  const P = profiles as Record<string, { education: string[]; currentPosition?: string | null; joined?: string | null }>;
  const byName = (n: string) => people.find((p) => key2(p.name.replace(/^Dr\.\s*/, '')) === key2(n) || (ALIASES[p.name] ?? []).some((a) => key2(a) === key2(n)));
  const stillInProgress: string[] = [];
  for (const it of prog.items) {
    const name = strip(it).split(',')[0];
    const person = byName(name);
    const deg = /PhD/.test(it) ? 'Ph.D.' : 'M.S.';
    const done = person ? (P[person.name]?.education ?? []).find((e) => e.replace(/^PhD/, 'Ph.D.').startsWith(deg) && /Iowa State/.test(e) && yearOf(e) <= new Date().getFullYear()) : undefined;
    const finished = person && (/Alumni/.test(person.category ?? '') || !!done);   // alumni, or a completed ISU degree on the profile (e.g. now a postdoc)
    if (!finished) { stillInProgress.push(it); continue; }
    const year = done ? yearOf(done) : '';
    const pos = P[person!.name]?.currentPosition;
    curSup.items.push(strip(it).replace(/\s*[–-]\s*[A-Z][a-z]+ \d{4},\s*work in progress\s*[–-]\s*degree expected .*$/, ` – ${year || 'completed'}${pos ? `, now ${pos.replace(/^(a|an)\s+/i, '')}` : ''}.`));
  }
  const listed = (n: string) => [...curSup.items, ...stillInProgress, ...sup.blocks.flatMap((b) => b.items)].some((i) => key2(strip(i).split(',')[0]) === key2(n));
  for (const p of people) {
    if (!['Doctoral Students', 'Masters Students'].includes(p.category ?? '') || listed(p.name)) continue;
    const joined = P[p.name]?.joined;
    stillInProgress.push(`${p.name}, ${p.category === 'Doctoral Students' ? 'PhD' : 'MS'}, ${joined ? `${joined} – ` : ''}work in progress.`);
  }
  prog.items = stillInProgress;
  const grad = [...(sup.blocks.find((b) => b.heading === PREV)?.items ?? []), ...curSup.items];
  const phd = (l: string[]) => l.filter((i) => /,\s*PhD\b/.test(strip(i))).length, ms = (l: string[]) => l.filter((i) => /,\s*MS\b/.test(strip(i))).length;
  const gh = sup.blocks.find((b) => /^Graduated/.test(b.heading ?? ''));
  if (gh) gh.heading = `Graduated (${phd(grad)} PhD – ${phd(curSup.items)} at the current rank, ${ms(grad)} MS – ${ms(curSup.items)} at the current rank)`;

  const today = new Date();
  return {
    meta: <VitaMeta>{ ...vita.meta, date: `${String(today.getMonth() + 1).padStart(2, '0')}/${String(today.getDate()).padStart(2, '0')}/${today.getFullYear()}` },
    sections,
    stats: { journalsAdded: J.added, conferencesAdded: K.added, chaptersAdded: C.added, talksAdded: newTalks.length },
  };
}
