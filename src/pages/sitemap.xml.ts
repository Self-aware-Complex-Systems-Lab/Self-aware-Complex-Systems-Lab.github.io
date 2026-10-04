// sitemap.xml for search engines: every public page (noindex pages — contribute forms, 404 — are left out).
import type { APIRoute } from 'astro';
import { SITE, NAV, personHref } from '../lib/site';
import { people } from '../lib/people';

const pages = [...new Set([...NAV.map((n) => n.href), '/cv/', ...people.map(personHref)])];

export const GET: APIRoute = () => {
  const lastmod = new Date().toISOString().slice(0, 10);
  const urls = pages.map((p) => `  <url><loc>${new URL(p, SITE.url).href}</loc><lastmod>${lastmod}</lastmod></url>`).join('\n');
  return new Response(`<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`,
    { headers: { 'Content-Type': 'application/xml' } });
};
