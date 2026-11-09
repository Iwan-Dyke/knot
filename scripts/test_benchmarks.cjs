const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { prepareBenchmark } = require('./benchmark_viewer.cjs');
const { offlineContext } = require('./benchmark_library.cjs');

async function main() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'knot-benchmark-check-'));
  let generated;
  try {
    const input = path.join(root, 'synthetic.html');
    await fs.writeFile(input, '<p>Synthetic snapshot</p>');
    await assert.rejects(prepareBenchmark([]), /input\.html/);
    await assert.rejects(prepareBenchmark([path.join(root, 'missing.html')]), /ENOENT/);
    await assert.rejects(prepareBenchmark([input, path.join(root, 'invalid'), '0']), /positive integer/);
    assert.deepEqual(await fs.readdir(root), ['synthetic.html']);

    const defaults = await prepareBenchmark([input]);
    generated = defaults.output;
    assert.equal(defaults.input, input);
    assert.equal(defaults.html, '<p>Synthetic snapshot</p>');
    assert.equal(defaults.repeats, 3);
    assert.equal(path.dirname(generated), path.resolve(os.tmpdir()));
    assert.ok(path.basename(generated).startsWith('knot-viewer-benchmark-'));
    if (process.platform !== 'win32') {
      assert.equal((await fs.stat(generated)).mode & 0o077, 0, 'Temporary evidence stays private');
    }
    assert.deepEqual(await fs.readdir(root), ['synthetic.html']);

    const output = path.join(root, 'explicit output');
    const explicit = await prepareBenchmark([input, output, '2']);
    assert.equal(explicit.output, output);
    assert.equal(explicit.repeats, 2);
    assert.ok((await fs.stat(output)).isDirectory());

    const report = { blocked_requests: [] }, contexts = [];
    const browser = {
      async newContext(options) {
        assert.equal(options.serviceWorkers, 'block');
        const context = {
          async route(pattern, handler) { this.pattern = pattern; this.handler = handler; },
        };
        contexts.push(context);
        return context;
      },
    };
    for (const phase of ['M:cold:0', 'M:warm']) {
      const context = await offlineContext(browser, report, phase);
      const url = 'https://example.invalid/pixel?phase=' + phase;
      assert.ok(context.pattern.test(url));
      let aborted = false;
      await context.handler({
        request: () => ({ url: () => url }),
        abort: async () => { aborted = true; },
      });
      assert.ok(aborted, phase + ' aborts network requests');
      assert.deepEqual(report.blocked_requests.at(-1), { context: phase, url });
    }
    assert.equal(contexts.length, 2);
    assert.equal(report.blocked_requests.length, 2);
  } finally {
    if (generated) await fs.rm(generated, { recursive: true, force: true });
    await fs.rm(root, { recursive: true, force: true });
  }
  console.log('Benchmark input, output and offline-context checks passed');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
