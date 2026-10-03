// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// Organization Pages repo (Self-aware-Complex-Systems-Lab.github.io) is served from the domain root,
// so no `base` is needed. If this is ever moved to a project repo, set `base: '/<repo>'`.
export default defineConfig({
  site: 'https://self-aware-complex-systems-lab.github.io',
  trailingSlash: 'ignore',
  build: { format: 'directory' },
  vite: { plugins: [tailwindcss()] },
});
