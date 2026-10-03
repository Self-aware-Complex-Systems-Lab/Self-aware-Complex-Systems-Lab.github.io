import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: 'tests',
  reporter: [['list']],
  use: { baseURL: process.env.SITE_URL ?? 'http://localhost:4321' },
  webServer: process.env.SITE_URL ? undefined : { command: 'npx astro preview --port 4321', port: 4321, reuseExistingServer: true },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
});
