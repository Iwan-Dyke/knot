/* Actual local HTTP/browser workflow; all notes are synthetic and temporary. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawn } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const playwright = require('playwright');

async function main() {
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'knot-library-authoring-'));
  const root = path.join(folder, 'dataset');
  const env = { ...process.env, PYTHONPATH: path.resolve('src'), PYTHONDONTWRITEBYTECODE: '1' };
  const python = (code, ...args) =>
    execFileSync(path.resolve('.venv/bin/python'), ['-c', code, root, ...args], {
      env,
      encoding: 'utf8',
    });
  const ids = JSON.parse(
    python(`
import json, sys
from pathlib import Path
from knot.writing.notes import create_note
from knot.curating.provenance import source_pin
from knot.writing.themes import add_themes
root = Path(sys.argv[1])
add_themes(root, [{'id': 'gardens', 'label': 'Gardens'}, {'id': 'ideas', 'label': 'Ideas'}])
plain = create_note(root, 'First paragraph.\\r\\n\\r\\nCafé 🌿', author='Example writer')
org = create_note(root, '* Heading\\n\\nAn Org observation.', title='Org account', format='org')
curated = create_note(root, 'A qualified restatement.', title='Curated account', author='Example curator', agent='Test', derivation={'method': 'faithful_restatement', 'qualification': 'One account.', 'sources': [source_pin(root, plain['revision'], 'First paragraph.', 0)]})
print(json.dumps({'plain': plain['note'], 'revision': plain['revision'], 'org': org['note'], 'curated': curated['note']}))
`),
  );
  const server = spawn(
    path.resolve('.venv/bin/python'),
    ['-m', 'knot.interfaces.note_cli', 'serve', '--data-root', root, '--no-open'],
    { env },
  );
  let errors = '',
    output = '';
  server.stderr.on('data', (chunk) => {
    errors += chunk;
  });
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error('Local server did not start: ' + errors)),
        30000,
      );
      server.once('exit', () => {
        clearTimeout(timer);
        reject(new Error('Local server exited: ' + errors));
      });
      server.stdout.on('data', (chunk) => {
        output += chunk;
        const found = output.match(/http:\/\/127\.0\.0\.1:\d+\/[^\s]+/);
        if (found) {
          clearTimeout(timer);
          resolve(found[0]);
        }
      });
    });
    browser = await playwright[process.argv[2] || 'chromium'].launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 1450, height: 1000 },
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));
    const notes = () =>
      JSON.parse(
        python(
          'import json, sys; from knot.writing.notes import list_notes; print(json.dumps(list_notes(sys.argv[1])))',
        ),
      );
    const history = (id) =>
      JSON.parse(
        python(
          'import json, sys; from knot.writing.notes import note_history; print(json.dumps(note_history(sys.argv[1], sys.argv[2])))',
          id,
        ),
      );
    const choose = async (tab, id, revision = null) => {
      await tab.evaluate(
        ({ id, revision }) => knotLibrary.navigate({ view: 'library', id, revision }),
        { id, revision },
      );
    };
    const saved = async (tab) => {
      await tab.locator('#editor-save').click();
      await tab.waitForFunction(() => !document.getElementById('note-editor').open);
      assert.equal(await tab.locator('#authoring-status').innerText(), 'Saved.');
    };
    const organise = async (tab) => {
      await tab.locator('#editor-organisation > summary').click();
      await tab.getByLabel('Gardens', { exact: true }).waitFor();
    };
    const connect = async (tab, query, title, reason) => {
      await tab.locator('#editor-link-search').fill(query);
      await tab.getByRole('button', { name: 'Link ' + title, exact: true }).click();
      await tab.getByLabel('Why connect to ' + title + '?', { exact: true }).fill(reason);
    };
    await page.goto(url);
    assert.equal(await page.locator('#new-note').isVisible(), true);
    await choose(page, ids.plain);
    await page.locator('#edit-note').click();
    await page.waitForFunction(() => document.getElementById('note-editor').open);
    assert.equal(await page.locator('#editor-body').inputValue(), 'First paragraph.\n\nCafé 🌿');
    await saved(page);
    assert.equal(
      history(ids.plain).length,
      1,
      'An untouched CRLF note is not normalised into a new revision',
    );

    await page.locator('#new-note').click();
    await page.locator('#editor-title').fill('An emerging idea');
    await page.locator('#editor-author').fill('Example writer');
    const original =
      '## Observation\n\nCafé 🌿 — a first paragraph.\n\nA second paragraph.\n\n<script>window.injected = true</script>\n\n![external](https://invalid.example/track.png)';
    await page.locator('#editor-body').fill(original);
    await organise(page);
    await connect(page, 'Org observation', 'Org account', 'A related observation.');
    await page.getByLabel('Why connect to Org account?', { exact: true }).fill('   ');
    await page.locator('#editor-save').click();
    assert.equal(notes().length, 3, 'A connection needs a nonblank explanation');
    await page
      .getByLabel('Why connect to Org account?', { exact: true })
      .fill('A related observation.');
    await page.getByLabel('Gardens', { exact: true }).check();
    await page.getByLabel('Ideas', { exact: true }).check();
    await page.locator('#editor-preview-toggle').click();
    await page.locator('#editor-preview h2').waitFor();
    assert.equal(await page.locator('#editor-preview script, #editor-preview img').count(), 0);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.screenshot({ path: path.join(folder, 'editor-preview.png') });
    await saved(page);
    const created = await page.evaluate(() => knotLibrary.selection.id);
    assert.equal(await page.locator('#selection-title').innerText(), 'An emerging idea');
    assert.ok((await page.locator('#reader-panel').innerText()).includes('A second paragraph.'));
    assert.equal(history(created)[0].body, original);
    assert.deepEqual(history(created)[0].navigation.links, [
      { note: ids.org, reason: 'A related observation.' },
    ]);
    assert.equal(history(created)[0].navigation.themes.length, 2);
    assert.equal(history(ids.org).length, 1, 'Linking never rewrites the target');
    await choose(page, ids.org);
    assert.ok((await page.locator('#context-content').innerText()).includes('An emerging idea'));
    await choose(page, created);
    await page.locator('#knowledge-search').fill('emerging idea');
    await page.waitForFunction(() =>
      document.getElementById('search-results').innerText.includes('An emerging idea'),
    );
    await page.locator('#edit-note').click();
    await page.locator('#editor-title').fill('A developed idea');
    await organise(page);
    await page.locator('#editor-link-search').fill('emerging idea');
    assert.equal(
      await page.locator('#editor-link-results button').count(),
      0,
      'Exclude the current note',
    );
    assert.equal(await page.getByLabel('Ideas', { exact: true }).isChecked(), true);
    await page.getByLabel('Why connect to Org account?', { exact: true }).fill('Expanded context.');
    await page.locator('#editor-body').fill('## Development\n\nStill a qualified observation.');
    await saved(page);
    assert.equal(await page.locator('#selection-title').innerText(), 'A developed idea');
    assert.equal(history(created).length, 2);
    assert.equal(history(created)[0].body, original);
    assert.equal(history(created).at(-1).navigation.links[0].reason, 'Expanded context.');
    await page.locator('#explore-selection').click();
    assert.equal(
      await page.evaluate(
        (id) => knotLibrary.graph.visible.nodes.find((n) => n.id === id).title,
        created,
      ),
      'A developed idea',
    );
    await page.locator('#view-idle').click();
    await page.locator('#idle-exit').click();
    await page.waitForFunction(() => knotLibrary.selection.view === 'graph');
    assert.equal(await page.evaluate(() => knotLibrary.selection.id), created);
    await page.locator('#read-selection').click();

    const second = await context.newPage();
    await second.goto(url);
    await choose(second, created);
    await page.locator('#edit-note').click();
    await second.locator('#edit-note').click();
    await organise(page);
    await organise(second);
    await page.getByLabel('Why connect to Org account?', { exact: true }).fill('First connection.');
    await second
      .getByLabel('Why connect to Org account?', { exact: true })
      .fill('Draft connection.');
    await page.locator('#editor-body').fill('First writer wins.');
    await second.locator('#editor-body').fill('Second writer keeps this draft.');
    let releasePreview, previewReceived;
    const previewReady = new Promise((resolve) => {
      previewReceived = resolve;
    });
    const delayed = new Promise((resolve) => {
      releasePreview = resolve;
    });
    await second.route('**/api/preview', async (route) => {
      const response = await route.fetch();
      previewReceived();
      await delayed;
      await route.fulfill({ response });
    });
    await second.locator('#editor-preview-toggle').click();
    await previewReady;
    await saved(page);
    await second.locator('#editor-save').click();
    await second.locator('#editor-conflict').waitFor();
    const deliveredPreview = second.waitForResponse((response) =>
      response.url().endsWith('/api/preview'),
    );
    releasePreview();
    await (await deliveredPreview).finished();
    await second.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
    );
    assert.ok(
      (await second.locator('#editor-status').innerText()).includes('changed'),
      'A late preview must not replace the conflict message',
    );
    assert.equal(await second.locator('#editor-preview').isVisible(), false);
    await second.unroute('**/api/preview');
    assert.equal(
      await second.locator('#editor-body').inputValue(),
      'Second writer keeps this draft.',
    );
    assert.equal(await second.locator('#editor-current-body').innerText(), 'First writer wins.');
    assert.ok(
      (await second.locator('#editor-current-navigation').innerText()).includes(
        'First connection.',
      ),
    );
    assert.equal(
      await second.getByLabel('Why connect to Org account?', { exact: true }).inputValue(),
      'Draft connection.',
    );
    assert.equal(history(created).at(-1).body, 'First writer wins.');
    second.once('dialog', (dialog) => dialog.dismiss());
    await second.locator('#editor-cancel').click();
    assert.equal(await second.locator('#note-editor').isVisible(), true);
    second.once('dialog', (dialog) => dialog.accept());
    await second.locator('#editor-reload').click();
    await second.waitForFunction(
      () => document.getElementById('editor-body').value === 'First writer wins.',
    );
    await second.locator('#editor-body').fill('Both observations reconciled explicitly.');
    await organise(second);
    assert.equal(
      await second.getByLabel('Why connect to Org account?', { exact: true }).inputValue(),
      'First connection.',
    );
    await second.getByRole('button', { name: 'Remove link to Org account', exact: true }).click();
    await second.getByLabel('Gardens', { exact: true }).uncheck();
    await second.getByLabel('Ideas', { exact: true }).uncheck();
    await saved(second);
    assert.equal(history(created).at(-1).body, 'Both observations reconciled explicitly.');
    assert.deepEqual(history(created).at(-1).navigation.links, []);
    assert.deepEqual(history(created).at(-1).navigation.themes, []);
    await second.close();

    await page.locator('#edit-note').click();
    await organise(page);
    await page.getByLabel('Gardens', { exact: true }).check();
    page.once('dialog', (dialog) => dialog.dismiss());
    await page.locator('#editor-cancel').click();
    assert.equal(
      await page.locator('#note-editor').isVisible(),
      true,
      'Organisation alone makes a dirty draft',
    );
    const beforeOrganisation = history(created).length;
    await saved(page);
    assert.equal(history(created).length, beforeOrganisation + 1);
    assert.equal(history(created).at(-1).body, 'Both observations reconciled explicitly.');
    await page.locator('#edit-note').click();
    await saved(page);
    assert.equal(
      history(created).length,
      beforeOrganisation + 1,
      'Opening organisation does not add a revision',
    );

    const beforeRetry = notes().length;
    await page.locator('#new-note').click();
    await page.locator('#editor-title').fill('Retry safely');
    await page.locator('#editor-body').fill('A response can be lost after saving.');
    await organise(page);
    await connect(page, 'Org observation', 'Org account', 'Retry this connection too.');
    await page.getByLabel('Ideas', { exact: true }).check();
    await page.route('**/api/create', async (route) => {
      await route.fetch();
      await route.abort('failed');
    });
    await page.locator('#editor-save').click();
    await page.waitForFunction(() =>
      document.getElementById('editor-status').textContent.includes('Cannot reach'),
    );
    assert.equal(notes().length, beforeRetry + 1, 'The lost response happened after the commit');
    assert.equal(
      await page.locator('#editor-body').inputValue(),
      'A response can be lost after saving.',
    );
    await page.unroute('**/api/create');
    python(`
import json, sys
from pathlib import Path
path = Path(sys.argv[1]) / 'organisation/catalogue.json'
catalogue = json.loads(path.read_text())
catalogue['themes'] = [t for t in catalogue['themes'] if t['id'] != 'ideas']
path.write_text(json.dumps(catalogue))
`);
    await saved(page);
    assert.equal(notes().length, beforeRetry + 1, 'Retry did not duplicate the note');
    const retried = await page.evaluate(() => knotLibrary.selection.id);
    await page.locator('#edit-note').click();
    await organise(page);
    assert.ok(
      (await page.locator('#editor-themes').innerText()).includes('no longer in the catalogue'),
    );
    assert.equal(await page.getByLabel('Ideas', { exact: true }).isChecked(), true);
    await page.locator('#editor-body').fill('Retain this older membership.');
    await saved(page);
    assert.deepEqual(history(retried).at(-1).navigation.themes, [{ id: 'ideas', label: 'Ideas' }]);
    await page.route('**/api/themes', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Synthetic catalogue failure' }),
      }),
    );
    await page.locator('#edit-note').click();
    await page.locator('#editor-organisation > summary').click();
    await page.locator('#editor-theme-retry').waitFor();
    assert.equal(await page.getByLabel('Ideas', { exact: true }).isChecked(), true);
    await page.unroute('**/api/themes');
    await page.locator('#editor-theme-retry').click();
    await page.getByLabel('Gardens', { exact: true }).waitFor();
    await saved(page);
    assert.equal(history(retried).length, 2);

    const beforeRefresh = notes().length;
    await page.locator('#new-note').click();
    await page.locator('#editor-title').fill('Refresh independently');
    await page.locator('#editor-body').fill('Already saved.');
    await page.route('**/api/snapshot', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Synthetic refresh failure' }),
      }),
    );
    await page.locator('#editor-save').click();
    await page.waitForFunction(
      () => document.getElementById('editor-save').textContent === 'Retry refresh',
    );
    assert.equal(notes().length, beforeRefresh + 1);
    assert.equal(await page.locator('#editor-body').isDisabled(), true);
    assert.equal(await page.locator('#editor-link-search').isDisabled(), true);
    await page.unroute('**/api/snapshot');
    await saved(page);
    assert.equal(notes().length, beforeRefresh + 1);

    await choose(page, ids.org);
    await page.locator('#edit-note').click();
    await page.locator('#editor-body').fill('* Heading\n\nUpdated Org writing.');
    await page.locator('#editor-preview-toggle').click();
    await page.waitForFunction(() =>
      document.getElementById('editor-preview').innerText.includes('Updated Org writing.'),
    );
    await saved(page);
    assert.equal(history(ids.org).at(-1).format, 'org');

    python(`
import sys
from knot.writing.notes import create_note
create_note(sys.argv[1], 'Garden project is a proposal.', title='External project', navigation={'themes': [], 'links': [], 'declarations': [{'id': 'urn:knot:entity:00000000-0000-4000-8000-000000000302', 'label': 'Garden project', 'type': 'Project', 'quote': 'Garden project', 'offset': 0}]})
`);
    await page.locator('#refresh-library').click();
    await page.waitForFunction(
      () => document.getElementById('authoring-status').textContent === 'Library refreshed.',
    );
    assert.equal(await page.locator('#graph-type option[value="Project"]').count(), 1);
    await page.locator('#view-idle').click();
    assert.equal(
      await page.locator('#idle-type option[value="Project"]').count(),
      1,
      'Idle must offer classifications introduced by a refreshed snapshot',
    );
    await page.locator('#idle-exit').click();
    await page.waitForFunction(() => knotLibrary.selection.view === 'library');
    await choose(page, ids.org);
    await page.locator('#edit-note').click();
    await organise(page);
    await page.locator('#editor-link-search').fill('Garden project is a proposal');
    assert.equal(
      await page.getByRole('button', { name: 'Link External project', exact: true }).count(),
      1,
    );
    await page.locator('#editor-cancel').click();
    await choose(page, ids.curated);
    assert.equal(await page.locator('#edit-note').isVisible(), false);
    await choose(page, ids.plain, ids.revision);
    assert.equal(await page.locator('#edit-note').isVisible(), false);

    const count = notes().length;
    await page.locator('#new-note').click();
    await page.locator('#editor-body').fill('A disposable draft.');
    page.once('dialog', (dialog) => dialog.accept());
    await page.locator('#editor-cancel').click();
    assert.equal(notes().length, count);
    await page.setViewportSize({ width: 600, height: 800 });
    await page.locator('#new-note').click();
    await page.locator('#editor-body').fill('Readable on a narrow screen.');
    assert.equal(await page.locator('#editor-save').isVisible(), true);
    assert.equal(
      await page.evaluate(
        () =>
          document.getElementById('note-editor').scrollWidth <=
          document.getElementById('note-editor').clientWidth,
      ),
      true,
    );
    await page.screenshot({ path: path.join(folder, 'editor-narrow.png') });
    page.once('dialog', (dialog) => dialog.accept());
    await page.locator('#editor-cancel').click();

    python(
      'import sys; from pathlib import Path; from knot.presentation.library import export_library; export_library(Path(sys.argv[1]), Path(sys.argv[2]))',
      path.join(folder, 'offline.html'),
    );
    await page.goto(pathToFileURL(path.join(folder, 'offline.html')).href);
    assert.equal(await page.locator('#new-note').isVisible(), false);
    assert.equal(await page.evaluate(() => knotLibrary.index.model.authoring), undefined);
    assert.equal(await page.evaluate(() => typeof LibraryOrganisation), 'undefined');
    assert.equal(pageErrors.length, 0, pageErrors.join('\n'));
    console.log(
      'Local Library create/read/edit/save, conflicts, retries, preview, Org, navigation and offline boundaries passed. Artifacts: ' +
        folder,
    );
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
