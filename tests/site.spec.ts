import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { people } from '../src/lib/people';
import { publications } from '../src/lib/publications';

const PAGES = ['/', '/principal-investigator/', '/research/', '/people/', '/publications/', '/alumni/', '/news/', '/gallery/', '/contact/', '/contribute/', '/contribute-token/'];

for (const path of PAGES) {
  test.describe(path, () => {
    test('loads, has title + h1, no horizontal scroll, no broken images', async ({ page }) => {
      const res = await page.goto(path);
      expect(res?.status()).toBe(200);
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(page).toHaveTitle(/SCSLab/);
      // force lazy images to load
      await page.evaluate(async () => {
        document.querySelectorAll('img[loading="lazy"]').forEach((i) => ((i as HTMLImageElement).loading = 'eager'));
        await Promise.all([...document.images].map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))));
      });
      const broken = await page.evaluate(() => [...document.images].filter((i) => !i.complete || i.naturalWidth === 0).map((i) => i.src));
      expect(broken).toEqual([]);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });

    test('no serious accessibility violations', async ({ page }) => {
      await page.goto(path);
      const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
      const serious = r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
      expect(serious.map((v) => `${v.id}: ${v.nodes.length} × ${v.nodes[0]?.target}`)).toEqual([]);
    });

    test('internal links resolve', async ({ page, request }) => {
      await page.goto(path);
      const hrefs = await page.evaluate(() => [...new Set([...document.querySelectorAll('a[href^="/"]')].map((a) => (a as HTMLAnchorElement).getAttribute('href')!.split('#')[0]))]);
      for (const h of hrefs) expect((await request.get(h)).status(), h).toBe(200);
    });
  });
}

test('every person is rendered with their own photo', async ({ page }) => {
  const seen = new Map<string, string>();
  for (const path of ['/people/', '/alumni/']) {
    await page.goto(path);
    const cards = await page.$$eval('article.person', (els) => els.map((e) => ({ name: (e as HTMLElement).dataset.name!, img: e.querySelector('img')?.getAttribute('src') ?? null })));
    for (const c of cards) seen.set(c.name, c.img ?? '');
  }
  for (const p of people) expect(seen.get(p.name), p.name).toBe(p.photo);
  expect(seen.size).toBe(people.length);
});

test('publications: no duplicate titles', async ({ page }) => {
  await page.goto('/publications/');
  const titles = await page.$$eval('li.pub > p:first-child', (els) => els.map((e) => e.textContent!.toLowerCase().replace(/[^a-z0-9]/g, '')));
  expect(titles.length - new Set(titles).size).toBe(0);
});

test('publications: all listed, search and filters work', async ({ page }) => {
  await page.goto('/publications/');
  await expect(page.locator('li.pub')).toHaveCount(publications.length);
  await page.fill('#pub-q', 'InsectNet');
  await expect(page.locator('li.pub:visible')).toHaveCount(1);
  await page.fill('#pub-q', '');
  await page.click('button[data-tab="preprints"]');
  await expect(page.locator('li.pub:visible')).toHaveCount(publications.filter((p) => p.category === 'preprints').length);
});

test('mobile menu opens', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile only');
  await page.goto('/');
  await expect(page.locator('#site-nav a[href="/alumni/"]')).toBeHidden();
  await page.click('#nav-toggle');
  await expect(page.locator('#site-nav a[href="/alumni/"]')).toBeVisible();
});

test('CV page and PDF are published', async ({ page, request }) => {
  const res = await page.goto('/cv/');
  expect(res?.status()).toBe(200);
  await expect(page.locator('h1')).toContainText('Soumik Sarkar');
  const pdf = await request.get('/cv/Soumik_Sarkar_CV.pdf');
  expect(pdf.status()).toBe(200);
  expect((await pdf.body()).subarray(0, 5).toString()).toBe('%PDF-');
});

test('no external runtime resources (site is self-contained)', async ({ page }) => {
  const external: string[] = [];
  page.on('request', (r) => { const u = new URL(r.url()); if (!['localhost', '127.0.0.1'].includes(u.hostname) && !u.protocol.startsWith('data')) external.push(r.url()); });
  for (const p of ['/', '/people/', '/principal-investigator/', '/publications/', '/news/', '/contribute/', '/cv/']) await page.goto(p, { waitUntil: 'networkidle' });
  expect(external).toEqual([]);
});

test('contribute form hands off to a prefilled GitHub issue form', async ({ page }) => {
  await page.goto('/contribute/');
  await page.evaluate(() => { (window as any).__opened = ''; window.open = ((u: string) => { (window as any).__opened = u; return null; }) as any; });
  await page.selectOption('[data-panel=photos] [name=kind]', 'Graduation or thesis defense');
  await page.fill('[data-panel=photos] [name=_who]', 'Jane Doe');
  await page.fill('[data-panel=photos] [name=event]', 'ISU commencement');
  await expect(page.locator('[data-panel=photos] [name=caption]')).toHaveValue(/Jane Doe — ph\.d\. graduation, ISU commencement\./i);
  await page.click('[data-panel=photos] button');
  const url = new URL(await page.evaluate(() => (window as any).__opened));
  expect(url.pathname).toMatch(/\/issues\/new$/);
  expect(url.searchParams.get('template')).toBe('gallery-photo.yml');
  expect(url.searchParams.get('kind')).toBe('Graduation or thesis defense');
  expect(url.searchParams.get('title')).toMatch(/^\[Photo\] Jane Doe/);
});

test('contribute: profile pre-fills known details and new-member detects existing people', async ({ page }) => {
  await page.goto('/contribute/');
  await page.click('button[data-tab=profile]');
  await page.fill('[data-panel=profile] [name=person]', 'Zahid Hasan');
  await expect(page.locator('[data-panel=profile] [name=github]')).toHaveValue(/github\.com\/zahid-isu/);
  await expect(page.locator('[data-panel=profile] [data-hint=person]')).toContainText('Found');
  await page.click('button[data-tab=member]');
  await page.fill('[data-panel=member] [name=name]', 'Nitesh Subedi');
  await expect(page.locator('[data-panel=member] [data-hint=name]')).toContainText('already on the website');
  await page.click('button[data-tab=milestone]');
  await page.fill('[data-panel=milestone] [name=who]', 'Shreyan Ganguly');
  await expect(page.locator('[data-panel=milestone] [data-hint=who]')).toContainText('Graduate Alumni');
});

test('token form: connect key, submit photos, commit lands in submissions/inbox, result shown (GitHub API mocked)', async ({ page }) => {
  const blobs: string[] = []; let treePaths: string[] = [];
  await page.route('https://api.github.com/**', async (route) => {
    const url = route.request().url(); const method = route.request().method();
    const json = (b: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) });
    if (url.endsWith('/user')) return json({ login: 'tester' });
    if (/\/repos\/[^/]+\/[^/]+$/.test(url)) return json({ permissions: { push: true } });
    if (url.includes('/git/ref/heads/main')) return json({ object: { sha: 'head1' } });
    if (url.includes('/git/commits/head1')) return json({ tree: { sha: 'tree0' } });
    if (url.endsWith('/git/blobs') && method === 'POST') { blobs.push(JSON.parse(route.request().postData()!).content); return json({ sha: `b${blobs.length}` }); }
    if (url.endsWith('/git/trees')) { treePaths = JSON.parse(route.request().postData()!).tree.map((t: any) => t.path); return json({ sha: 't1' }); }
    if (url.endsWith('/git/commits') && method === 'POST') return json({ sha: 'c1' });
    if (url.includes('/git/refs/heads/main')) return json({});
    if (url.includes('/contents/submissions/results/')) {
      const body = btoa(JSON.stringify({ ok: true, message: 'Added **1** photo(s) to the gallery.' }));
      return json({ content: body });
    }
    return json({ message: 'unexpected ' + url }, 404);
  });
  await page.goto('/contribute-token/');
  await page.fill('#token', 'github_pat_test');
  await page.click('#save-token');
  await expect(page.locator('#key-status')).toContainText('Connected as tester');
  // a tiny real PNG as the "phone photo"
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP4z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==', 'base64');
  await page.setInputFiles('[data-panel=photos] [name="__img_Photos"]', { name: 'IMG_0001.png', mimeType: 'image/png', buffer: png });
  await page.fill('[data-panel=photos] [name=event]', 'CVPR 2026');
  await page.fill('[data-panel=photos] [name=caption]', 'Poster at CVPR 2026.');
  await page.click('[data-panel=photos] button:has-text("Submit")');
  await expect(page.locator('[data-panel=photos] [data-status]')).toContainText('Added 1 photo(s) to the gallery', { timeout: 30000 });
  expect(treePaths.some((p) => /^submissions\/inbox\/[^/]+\/image-1\.jpg$/.test(p))).toBe(true);
  const sub = JSON.parse(Buffer.from(blobs[blobs.length - 1], 'base64').toString());
  expect(sub.kind).toBe('[Photo]');
  expect(sub.fields['Caption']).toBe('Poster at CVPR 2026.');
  expect(sub.fields['Event / conference / place']).toBe('CVPR 2026');
  expect(sub.images['Photos']).toEqual(['image-1.jpg']);
  expect(Buffer.from(blobs[0], 'base64').subarray(0, 3).toString('hex')).toBe('ffd8ff');   // re-encoded as JPEG (metadata stripped)
});
