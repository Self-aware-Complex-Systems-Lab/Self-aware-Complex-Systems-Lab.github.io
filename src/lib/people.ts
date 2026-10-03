import raw from '../data/people.json' with { type: 'json' };
import overrides from '../data/people-overrides.json' with { type: 'json' };

export type Person = (typeof raw)[number];

const cat = overrides.category as Record<string, string>;

/** people.json with lab-owner overrides applied (category moves etc.). */
export const people: Person[] = raw.map((p) => (cat[p.name] ? { ...p, category: cat[p.name] } : p));
