export const SITE = {
  name: 'Self-aware Complex Systems Laboratory',
  short: 'SCSLab',
  university: 'Iowa State University',
  original: 'https://sites.google.com/view/scslab-isu/home',
  archivedOn: '2026-10-03',
};

export const NAV = [
  { href: '/', label: 'Home' },
  { href: '/principal-investigator/', label: 'Principal Investigator' },
  { href: '/research/', label: 'Research' },
  { href: '/people/', label: 'People' },
  { href: '/publications/', label: 'Publications' },
  { href: '/alumni/', label: 'Alumni' },
  { href: '/gallery/', label: 'Gallery' },
  { href: '/contact/', label: 'Contact' },
];

export const CURRENT_CATEGORIES = [
  'Principal Investigator',
  'Post Doctoral Students',
  'Doctoral Students',
  'Masters Students',
  'Research Students on Independent Studies',
];
export const ALUMNI_CATEGORIES = ['Post-doctorate Alumni', 'Graduate Alumni', 'Undergraduate Alumni'];

export const slug = (s: string) =>
  s.toLowerCase().replace(/^dr\.?\s+/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

/** Turn bare URLs inside archived text into links without altering the text itself. */
export const linkify = (t: string) =>
  t
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/(https?:\/\/[^\s,)]+[^\s,).])/g, '<a href="$1" rel="noopener">$1</a>');

const esc = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** Render archived text with its original hyperlinks re-attached to the original anchor text. */
export function withLinks(text: string, links: { href: string; text: string }[] = []) {
  let html = esc(text);
  const used = new Set<string>();
  for (const l of links) {
    if (!l.text || used.has(l.text) || l.href.includes('sites.google.com/view/scslab-isu/principal-investigator#')) continue;
    used.add(l.text);
    html = html.replace(esc(l.text), `<a href="${l.href}" rel="noopener">${esc(l.text)}</a>`);
  }
  return links.length ? html : linkify(text);
}
