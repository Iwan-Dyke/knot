/* Browser-only synthetic performance measurements. No private dataset access. */
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');

async function offlineContext(browser, report, label) {
  const context = await browser.newContext({
    viewport: { width: 1500, height: 1000 }, serviceWorkers: 'block',
  });
  await context.route(/https?:\/\//, (route) => {
    report.blocked_requests.push({ context: label, url: route.request().url() });
    return route.abort();
  });
  return context;
}

async function main() {
  const playwright = require('playwright');
  const root = path.resolve(__dirname, '..'),
    folder = await fs.mkdtemp(path.join(os.tmpdir(), 'knot-library-scale-'));
  const browserName = process.argv[2] || 'chromium',
    browser = await playwright[browserName].launch({ headless: true });
  const report = {
    browser: browserName,
    version: browser.version(),
    platform: os.platform(),
    release: os.release(),
    cpu: os.cpus()[0].model,
    memoryBytes: os.totalmem(),
    cpuThrottling: 'none',
    coldDefinition: 'new browser context per open; OS file cache not cleared',
    blocked_requests: [],
    profiles: {},
  };
  try {
    for (const profile of ['M', 'L']) {
      const file = path.join(folder, profile + '.html');
      execFileSync(
        path.join(root, '.venv/bin/python'),
        [path.join(root, 'tests/library_scale_fixture.py'), profile, file],
        {
          cwd: root,
          env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: path.join(root, 'src') },
        },
      );
      const runs = {
        startup: [],
        metadata: [],
        body: [],
        reader: [],
        graph: [],
        switchView: [],
        heapBytes: [],
      };
      for (let i = 0; i < 20; i++) {
        const context = await offlineContext(browser, report, profile + ':cold:' + i),
          page = await context.newPage();
        const errors = [];
        page.on('pageerror', (e) => errors.push(e.message));
        await page.goto(pathToFileURL(file).href);
        await page.waitForFunction(() => window.knotLibrary);
        runs.startup.push(
          await page.evaluate(
            () => performance.getEntriesByName('knot-library-ready')[0].startTime,
          ),
        );
        assert.equal(await page.evaluate(() => knotLibrary.graph.network), null);
        assert.deepEqual(errors, []);
        await context.close();
        assert.deepEqual(report.blocked_requests, [], 'Benchmark attempted network requests');
      }
      const context = await offlineContext(browser, report, profile + ':warm'),
        page = await context.newPage();
      await page.goto(pathToFileURL(file).href);
      await page.waitForFunction(() => window.knotLibrary);
      const warm = await page.evaluate(async () => {
        const values = {
          metadata: [],
          body: [],
          reader: [],
          graph: [],
          switchView: [],
          heapBytes: [],
        };
        const painted = () =>
          new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        for (let i = 0; i < 50; i++) {
          let start = performance.now();
          knotLibrary.index.search('Historic ' + i);
          values.metadata.push(performance.now() - start);
          start = performance.now();
          knotLibrary.index.search('needle' + i);
          values.body.push(performance.now() - start);
          start = performance.now();
          knotLibrary.navigate({ view: 'library', id: 'urn:example:note:' + i });
          await painted();
          values.reader.push(performance.now() - start);
          start = performance.now();
          knotLibrary.navigate({ view: 'graph', id: 'urn:example:entity:' + i }, { focus: true });
          await painted();
          values.graph.push(performance.now() - start);
          if (
            knotLibrary.graph.visible.nodes.length > 100 ||
            knotLibrary.graph.visible.edges.length > 300
          )
            throw Error('Graph bounds exceeded');
          start = performance.now();
          document.getElementById('view-library').click();
          await painted();
          values.switchView.push(performance.now() - start);
          if (performance.memory) values.heapBytes.push(performance.memory.usedJSHeapSize);
        }
        return values;
      });
      Object.assign(runs, warm);
      await context.close();
      assert.deepEqual(report.blocked_requests, [], 'Benchmark attempted network requests');
      const p95 = (values) =>
        [...values].sort((a, b) => a - b)[Math.ceil(values.length * 0.95) - 1] ?? null;
      report.profiles[profile] = {
        bytes: (await fs.stat(file)).size,
        runs,
        p95: Object.fromEntries(Object.entries(runs).map(([k, v]) => [k, p95(v)])),
      };
      console.log(browserName + ' ' + profile + ' ' + JSON.stringify(report.profiles[profile].p95));
    }
  } finally {
    await browser.close();
    await fs.writeFile(path.join(folder, 'results.json'), JSON.stringify(report, null, 2));
    console.log('Raw measurements: ' + folder);
  }
}
module.exports = { offlineContext };
if (require.main === module) {
  main().catch((e) => {
    console.error(e);
    process.exitCode = 1;
  });
}
