// Print dist/cv/index.html to dist/cv/Soumik_Sarkar_CV.pdf (run after `astro build`).
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { chromium } from '@playwright/test';

const DIST = new URL('../dist/', import.meta.url).pathname;
const TYPES = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };

const server = createServer(async (req, res) => {
  let p = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^(\.\.[/\\])+/, '');
  let f = join(DIST, p);
  try { if ((await stat(f)).isDirectory()) f = join(f, 'index.html'); } catch {}
  try { res.writeHead(200, { 'content-type': TYPES[extname(f)] ?? 'application/octet-stream' }); res.end(await readFile(f)); }
  catch { res.writeHead(404); res.end(); }
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`http://localhost:${port}/cv/`, { waitUntil: 'networkidle' });
await page.pdf({
  path: join(DIST, 'cv', 'Soumik_Sarkar_CV.pdf'), format: 'Letter', printBackground: true, preferCSSPageSize: true,
  displayHeaderFooter: true, headerTemplate: '<span></span>',
  footerTemplate: '<div style="font-size:11px;width:100%;text-align:center;font-family:Times New Roman,Liberation Serif,serif"><span class="pageNumber"></span></div>',
});
await browser.close();
server.close();
console.log('wrote dist/cv/Soumik_Sarkar_CV.pdf');
