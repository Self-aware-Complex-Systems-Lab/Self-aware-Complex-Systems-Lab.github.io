import raw from '../data/people.json' with { type: 'json' };
import added from '../data/people-added.json' with { type: 'json' };
import overrides from '../data/people-overrides.json' with { type: 'json' };

export type Person = (typeof raw)[number];

const cat = overrides.category as Record<string, string>;
const photo = (overrides as { photo?: Record<string, string> }).photo ?? {};

/** Members added later through the Contribute form (same shape as people.json, text lives in people-profiles.json). */
const newcomers = (added as unknown as Partial<Person>[]).map((p) => ({
  category: null, contactEmailAsListed: null, lines: [], details: [], bio: [], links: [], photo: null, photoManifestId: null,
  rawBlockText: '', source: 'contribute form', photoMatch: '', ...p,
})) as Person[];

/** people.json + newcomers, with lab-owner overrides applied (section moves, new photos). */
export const people: Person[] = [...raw, ...newcomers].map((p) => ({
  ...p,
  ...(cat[p.name] ? { category: cat[p.name] } : {}),
  ...(photo[p.name] ? { photo: photo[p.name] } : {}),
}));
