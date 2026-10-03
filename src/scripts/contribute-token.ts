// Browser helper for /contribute-token/: a lab member's OWN fine-grained GitHub token (kept only in their browser)
// commits a submission folder to submissions/inbox/ in ONE commit; .github/workflows/submissions.yml then applies it
// with the same processor as the issue forms and writes submissions/results/<id>.json, which this page polls.

const OWNER = 'Self-aware-Complex-Systems-Lab';
const REPO = 'Self-aware-Complex-Systems-Lab.github.io';
const BRANCH = 'main';
const API = 'https://api.github.com';
const TOKEN_KEY = 'scslab-contribute-token';
const MAX_SIDE = 2000;

export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY) ?? ''; } catch { return ''; } };
export const setToken = (t: string) => { try { if (t) localStorage.setItem(TOKEN_KEY, t.trim()); else localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ } };

async function gh<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, { ...init, headers: { Authorization: `Bearer ${getToken()}`, Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28', ...(init.headers ?? {}) } });
  if (!res.ok) { const e = new Error(`GitHub ${res.status}: ${(await res.text()).slice(0, 160)}`) as Error & { status: number }; e.status = res.status; throw e; }
  return res.json();
}

/** Who owns the key, and may it write to the website repository? */
export async function checkKey(): Promise<{ login: string; canWrite: boolean }> {
  const user = await gh<{ login: string }>('/user');
  const repo = await gh<{ permissions?: { push?: boolean } }>(`/repos/${OWNER}/${REPO}`);
  return { login: user.login, canWrite: !!repo.permissions?.push };
}

/** Apply EXIF rotation, downscale, re-encode as JPEG (re-encoding drops all metadata, including GPS). */
export async function prepareImage(file: File): Promise<Blob> {
  let src: ImageBitmap | HTMLImageElement;
  try { src = await createImageBitmap(file, { imageOrientation: 'from-image' }); }
  catch { src = await new Promise<HTMLImageElement>((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = bad; i.src = URL.createObjectURL(file); }); }
  const w0 = 'naturalWidth' in src ? src.naturalWidth : src.width, h0 = 'naturalHeight' in src ? src.naturalHeight : src.height;
  const k = Math.min(1, MAX_SIDE / Math.max(w0, h0)); const c = document.createElement('canvas');
  c.width = Math.round(w0 * k); c.height = Math.round(h0 * k); c.getContext('2d')!.drawImage(src, 0, 0, c.width, c.height);
  return new Promise((ok, bad) => c.toBlob((b) => (b ? ok(b) : bad(new Error('Could not encode image'))), 'image/jpeg', 0.85));
}

const b64 = async (blob: Blob) => { const u = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); return btoa(s); };
const textB64 = (t: string) => b64(new Blob([t]));

export type Submission = { kind: string; title: string; fields: Record<string, string>; images: Record<string, File[]> };

/** Commit the submission (JSON + prepared images) to submissions/inbox/<id>/ in a single commit. Returns the id. */
export async function submit(sub: Submission, onStep: (s: string) => void): Promise<string> {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const dir = `submissions/inbox/${id}`;
  const files: { path: string; content: string }[] = [];
  const imageNames: Record<string, string[]> = {};
  let n = 0; const total = Object.values(sub.images).reduce((a, l) => a + l.length, 0);
  for (const [label, list] of Object.entries(sub.images)) {
    imageNames[label] = [];
    for (const f of list) {
      onStep(`Preparing photo ${++n} of ${total}…`);
      const name = `image-${n}.jpg`;
      files.push({ path: `${dir}/${name}`, content: await b64(await prepareImage(f)) });
      imageNames[label].push(name);
    }
  }
  files.push({ path: `${dir}/submission.json`, content: await textB64(JSON.stringify({ kind: sub.kind, title: sub.title, fields: sub.fields, images: imageNames }, null, 1)) });
  onStep('Uploading…');
  for (let attempt = 0; attempt < 3; attempt++) {
    const head = (await gh<{ object: { sha: string } }>(`/repos/${OWNER}/${REPO}/git/ref/heads/${BRANCH}`)).object.sha;
    const baseTree = (await gh<{ tree: { sha: string } }>(`/repos/${OWNER}/${REPO}/git/commits/${head}`)).tree.sha;
    const tree = [];
    for (const f of files) {
      const blob = await gh<{ sha: string }>(`/repos/${OWNER}/${REPO}/git/blobs`, { method: 'POST', body: JSON.stringify({ content: f.content, encoding: 'base64' }) });
      tree.push({ path: f.path, mode: '100644', type: 'blob', sha: blob.sha });
    }
    const t = await gh<{ sha: string }>(`/repos/${OWNER}/${REPO}/git/trees`, { method: 'POST', body: JSON.stringify({ base_tree: baseTree, tree }) });
    const c = await gh<{ sha: string }>(`/repos/${OWNER}/${REPO}/git/commits`, { method: 'POST',
      body: JSON.stringify({ message: `Website submission ${sub.kind} ${sub.title}`.slice(0, 120), tree: t.sha, parents: [head] }) });
    try { await gh(`/repos/${OWNER}/${REPO}/git/refs/heads/${BRANCH}`, { method: 'PATCH', body: JSON.stringify({ sha: c.sha }) }); return id; }
    catch (e: any) { if (e.status !== 422 || attempt === 2) throw e; }   // someone pushed meanwhile: retry on the new tip
  }
  throw new Error('Could not upload');
}

/** Poll for the processor's result (usually 20–60 s). */
export async function waitForResult(id: string, timeoutMs = 240000): Promise<{ ok: boolean; message: string } | null> {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    await new Promise((r) => setTimeout(r, 8000));
    try {
      const f = await gh<{ content: string }>(`/repos/${OWNER}/${REPO}/contents/submissions/results/${id}.json?ref=${BRANCH}`);
      return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(f.content.replace(/\n/g, '')), (c) => c.charCodeAt(0))));
    } catch (e: any) { if (e.status !== 404) throw e; }
  }
  return null;
}
