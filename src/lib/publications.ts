import archived from '../data/publications.json' with { type: 'json' };
import added from '../data/publications-added.json' with { type: 'json' };
import removals from '../data/publication-removals.json' with { type: 'json' };
import pubLinks from '../data/publication-links.json' with { type: 'json' };
import venueData from '../data/publication-venues.json' with { type: 'json' };

export type Pub = {
  date?: string | null;
  category: string; categoryLabel: string | null; title: string; authors: string | null; venue: string | null;
  year: number | null; url: string | null; doi: string | null; citationsAsOfArchive?: string | null;
  key?: string; projectPage?: string; code?: string;
};

const LINKS = pubLinks.links as Record<string, { projectPage?: string; code?: string }>;
const sortKey = (p: Pub) => p.date ?? `${p.year ?? 0}`;
const LABEL: Record<string, string> = { journals: 'Journal Articles', conferences: 'Conference Proceedings', preprints: 'Preprints' };
const VENUES = venueData.venues as Record<string, { category: string; venue: string; year: number }>;
/** Papers first listed as preprints that were later accepted (evidence in publication-venues.json). */
const withVenue = (k: string, p: Pub): Pub => {
  const v = VENUES[k];
  return v ? { ...p, category: v.category, categoryLabel: LABEL[v.category], venue: v.venue, year: v.year } : p;
};

const hidden = new Set(removals.removals.map((r) => r.key));

/** All publications, newest additions first, with duplicates (see migration/scripts/dedupe_pubs.py) removed. */
export const publications: Pub[] = [
  ...(added as Pub[]).map((p, i) => ({ p, k: `added:${i}` })),
  ...(archived as Pub[]).map((p, i) => ({ p, k: `archived:${i}` })),
]
  .filter(({ k }) => !hidden.has(k))
  .map(({ p, k }) => ({ ...withVenue(k, p), ...LINKS[k], key: k, title: p.title.replace(/\s+/g, ' ').trim() }))
  .map((p) => ({ ...p, venue: p.venue?.replace(/\barXiv\s*\(Cornell University\)/i, 'arXiv').replace(/,\s*Cornell University(?=\s*\(\d{4}\)|\s*$)/i, '') ?? null }))
  .sort((a, b) => sortKey(b).localeCompare(sortKey(a)));

/** Look up a publication by its stable key ("added:3", "archived:120"). */
export const pubByKey = new Map<string, Pub>([
  ...(added as Pub[]).map((p, i) => [`added:${i}`, p] as const),
  ...(archived as Pub[]).map((p, i) => [`archived:${i}`, p] as const),
].map(([k, p]) => [k, { ...withVenue(k, p), ...LINKS[k], key: k, title: p.title.replace(/\s+/g, ' ').trim() }]));
