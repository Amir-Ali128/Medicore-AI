// Test-only Vite options. Each test file starts its own dev server and node:test
// runs files in parallel. Without these options every server also starts the
// background dependency scanner/optimizer and writes to the shared
// node_modules/.vite cache; concurrent writes occasionally collide and fail the
// whole file outside any assertion ("test at <file>:1:1 ... test failed").
// The tests only use ssrLoadModule, which never needs pre-bundled client deps.
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export function isolatedVite() {
  const cacheDir = mkdtempSync(join(tmpdir(), 'medicore-vite-test-'));
  process.once('exit', () => rmSync(cacheDir, { recursive: true, force: true }));
  return {
    cacheDir,
    optimizeDeps: { noDiscovery: true, include: [] },
  };
}
