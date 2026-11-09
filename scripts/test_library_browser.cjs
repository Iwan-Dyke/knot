/* Use the optional external Playwright installation; all data stays in a temporary folder. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { execFileSync } = require('node:child_process');
const playwright = require('playwright');
const checkCinematicIdle = require('./test_idle_browser.cjs');

async function checkIdle(page, context, folder, ids) {
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.goto(pathToFileURL(path.join(folder, 'library.html')).href);
  await page.clock.install();
  await page.evaluate(
    (id) => knotLibrary.navigate({ view: 'graph', id }, { focus: true }),
    ids.project,
  );
  await page.locator('#node-spacing').fill('150');
  await page.locator('#node-spacing').dispatchEvent('input');
  await page.evaluate(() => {
    window.idleBefore = {
      model: JSON.stringify(knotLibrary.index.model),
      selection: knotLibrary.selection,
      positions: knotLibrary.graph.network.getPositions(),
      state: knotLibrary.graph.getState(),
      recents: knotLibrary.recents,
    };
    window.originalNetwork = knotLibrary.graph.network;
  });
  await page.locator('#view-idle').click();
  assert.equal(await page.locator('#idle-panel').isVisible(), true);
  assert.equal(await page.evaluate(() => knotLibrary.idle.state.running), false);
  const historyLength = await page.evaluate(() => history.length);
  await page.locator('#idle-toggle').click();
  assert.equal(
    await page.evaluate(() => knotLibrary.idle.state.running),
    true,
    await page.locator('#idle-state').innerText(),
  );
  const first = await page.evaluate(() => knotLibrary.idle.state.current);
  assert.ok(first);
  assert.equal(await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled), false);
  assert.equal(await page.locator('#idle-card').isVisible(), false, 'Focus precedes reading');
  await page.clock.runFor(50000);
  const second = await page.evaluate(() => knotLibrary.idle.state.current);
  assert.notEqual(
    first,
    second,
    'Idle automatically follows an existing connection: ' +
      JSON.stringify(
        await page.evaluate(() => ({
          state: knotLibrary.idle.state,
          status: document.getElementById('idle-state').textContent,
          connection: document.getElementById('idle-connection').textContent,
        })),
      ),
  );
  assert.ok((await page.locator('#idle-connection').innerText()).includes('→'));
  assert.ok(
    await page.evaluate(
      () => knotLibrary.idle.state.visible <= 40 && knotLibrary.idle.state.edges <= 80,
    ),
  );
  assert.equal(await page.evaluate(() => history.length), historyLength);
  assert.equal(
    await page.evaluate(() => knotLibrary.graph.network === window.originalNetwork),
    true,
  );
  assert.deepEqual(
    await page.evaluate(() => knotLibrary.recents),
    await page.evaluate(() => idleBefore.recents),
  );
  await page.screenshot({ path: path.join(folder, 'idle.png') });
  await page.locator('#idle-toggle').click();
  await page.clock.runFor(60000);
  assert.equal(await page.evaluate(() => knotLibrary.idle.state.current), second);
  assert.equal(await page.evaluate(() => knotLibrary.idle.state.pending), false);
  await page.locator('#idle-toggle').click();
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.clock.runFor(60000);
  assert.equal(await page.evaluate(() => knotLibrary.idle.state.current), second);
  assert.equal(await page.evaluate(() => knotLibrary.idle.state.pending), false);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('blur'));
  });
  assert.equal(
    await page.evaluate(() => knotLibrary.idle.state.running && knotLibrary.idle.state.pending),
    true,
  );
  await page.locator('#idle-toggle').click();
  await page.locator('#idle-exit').click();
  await page.waitForFunction(() => knotLibrary.selection.view === 'graph');
  assert.deepEqual(
    await page.evaluate(() => knotLibrary.selection),
    await page.evaluate(() => idleBefore.selection),
  );
  assert.deepEqual(
    await page.evaluate(() => knotLibrary.graph.network.getPositions()),
    await page.evaluate(() => idleBefore.positions),
  );
  assert.equal(await page.locator('#node-spacing').inputValue(), '150');
  assert.equal(await page.evaluate(() => knotLibrary.idle.state.cachedPositions), 0);
  assert.equal(
    await page.evaluate(() => JSON.stringify(knotLibrary.index.model) === idleBefore.model),
    true,
  );
  await page.goForward();
  assert.equal(await page.evaluate(() => knotLibrary.selection.view), 'idle');
  assert.equal(
    await page.evaluate(() => knotLibrary.idle.state.running),
    false,
    'Forward never starts a tour',
  );
  await page.locator('#idle-toggle').click();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.clock.runFor(20100);
  assert.equal(await page.evaluate(() => knotLibrary.idle.state.animating), false);
  const idleHistory = await page.evaluate(() => history.length);
  for (let i = 0; i < 80; i++) await page.clock.runFor(20100);
  assert.equal(await page.evaluate(() => history.length), idleHistory);
  assert.ok(
    await page.evaluate(
      () => knotLibrary.idle.state.cachedPositions <= knotLibrary.index.records.length,
    ),
  );
  assert.ok(
    await page.evaluate(
      () => knotLibrary.idle.state.visible <= 40 && knotLibrary.idle.state.edges <= 80,
    ),
  );
  for (
    let i = 0;
    i < 50 && (await page.evaluate(() => knotLibrary.idle.state.phase)) !== 'reading';
    i++
  )
    await page.clock.runFor(500);
  await page.locator('#idle-read').click();
  assert.equal(await page.evaluate(() => knotLibrary.selection.view), 'library');
  assert.ok(await page.evaluate(() => knotLibrary.selection.revision));
  const libraryReturn = await page.evaluate(() => ({
    selection: knotLibrary.selection,
    graph: knotLibrary.graph.getState(),
    recents: knotLibrary.recents,
  }));
  await page.locator('#view-idle').click();
  await page.locator('#idle-filters').evaluate((e) => (e.open = true));
  await page.locator('#idle-status').selectOption('Accepted');
  const popupPromise = context.waitForEvent('page');
  await page.locator('#idle-window').click();
  const popup = await popupPromise;
  await popup.waitForFunction(() => window.knotLibrary);
  assert.equal(await popup.evaluate(() => knotLibrary.selection.view), 'idle');
  assert.equal(await popup.evaluate(() => knotLibrary.idle.state.running), false);
  assert.equal(await popup.locator('#idle-status').inputValue(), 'Accepted');
  assert.equal(await popup.evaluate(() => window.opener), null);
  await popup.close();
  await page.locator('#idle-fullscreen').click();
  if (await page.evaluate(() => !!document.fullscreenElement)) {
    await page.keyboard.press('Escape');
    // Some headless window managers do not implement the browser's Escape exit.
    if (await page.evaluate(() => !!document.fullscreenElement))
      await page.locator('#idle-fullscreen').click();
    await page.waitForFunction(() => !document.fullscreenElement);
    assert.equal(await page.evaluate(() => knotLibrary.selection.view), 'idle');
  } else assert.ok((await page.locator('#idle-state').innerText()).includes('window'));
  await page.locator('#idle-exit').click();
  await page.waitForFunction(() => knotLibrary.selection.view === 'library');
  assert.deepEqual(await page.evaluate(() => knotLibrary.selection), libraryReturn.selection);
  assert.deepEqual(
    await page.evaluate(() => knotLibrary.graph.getState().positions),
    libraryReturn.graph.positions,
  );
  assert.deepEqual(await page.evaluate(() => knotLibrary.recents), libraryReturn.recents);
  await page.clock.resume();
  console.log('Idle browser traversal, pause, visibility, provenance and navigation checks passed');
}

async function checkIdleFixtures(page, folder) {
  // Browser-only projection fixtures: these are never saved through knowledge authoring APIs.
  const base = await page.evaluate(() => structuredClone(knotLibrary.index.model));
  const template = await fs.readFile(path.join(folder, 'library.html'), 'utf8');
  await page.clock.install();
  for (const size of [0, 1, 70]) {
    const fixture = {
      ...base,
      notes: {},
      entities: {},
      claims: {},
      relations: [],
      sources: {},
      reviews: [],
      historical_claims: {},
      themes: [],
      bodies: {
        example: {
          text: 'A complete synthetic reading passage.',
          html: { markdown: '<p>A complete synthetic reading passage.</p>' },
        },
      },
    };
    delete fixture.initial_record;
    fixture.manifest = {
      ...base.manifest,
      fingerprint: 'synthetic-idle-' + size,
      counts: { notes: size, entities: 0, claims: 0 },
    };
    for (let i = 0; i < size; i++) {
      const id = 'urn:example:idle:note:' + i;
      fixture.notes[id] = {
        id,
        title: 'Example note ' + i,
        revision: 'urn:example:idle:revision:' + i,
        body: 'example',
        format: 'markdown',
        author: 'Example writer',
        entities: [],
        sources: [],
        history: [],
        navigation: { links: [], themes: [], declarations: [] },
      };
      if (i)
        fixture.relations.push({
          id: 'edge-' + i,
          from: 'urn:example:idle:note:0',
          to: id,
          kind: 'link',
          label: 'links to',
        });
    }
    const output = path.join(folder, 'idle-' + size + '.html');
    await fs.writeFile(
      output,
      template.replace(
        /(<script id="library-data" type="application\/json">)[\s\S]*?(<\/script>)/,
        (_, start, end) => start + JSON.stringify(fixture).replace(/</g, '\\u003c') + end,
      ),
    );
    await page.goto(pathToFileURL(output).href + '#view=idle');
    await page.locator('#idle-depth').selectOption('2');
    await page.locator('#idle-toggle').click();
    if (size === 1) await page.clock.runFor(22000);
    const state = await page.evaluate(() => knotLibrary.idle.state);
    assert.ok(state.visible <= 40 && state.edges <= 80);
    if (size < 2) {
      assert.equal(state.pending, false);
      assert.equal(state.running, false);
      assert.equal(state.visible, size);
    } else {
      assert.equal(state.running, true);
      assert.ok((await page.locator('#idle-counts').innerText()).includes('omitted'));
      await page.locator('#idle-toggle').click();
      await page.setViewportSize({ width: 360, height: 800 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: path.join(folder, 'idle-narrow.png') });
      await page.setViewportSize({ width: 1500, height: 1000 });
    }
    await page.locator('#idle-exit').click();
    assert.equal(await page.evaluate(() => knotLibrary.selection.view), 'graph');
  }
  console.log('Idle empty, singleton, dense and narrow-screen checks passed');
  await page.clock.resume();
}

async function checkDenseFocus(page, folder) {
  // A browser-only projection fixture, never an authoritative knowledge dataset.
  const model = await page.evaluate(() => structuredClone(knotLibrary.index.model));
  delete model.initial_record;
  const entity = Object.values(model.entities)[0],
    claim = Object.values(model.claims)[0];
  model.notes = {};
  model.entities = {};
  model.claims = {};
  model.relations = [];
  model.sources = {};
  model.bodies = {};
  model.historical_claims = {};
  model.reviews = [];
  model.themes = [];
  model.manifest.counts = { notes: 0, entities: 121, claims: 120 };
  model.manifest.fingerprint = 'synthetic-dense-focused-layout';
  model.manifest.history = 'Synthetic layout fixture';
  model.manifest.boundary = 'Browser test projection; not an authoritative knowledge dataset';
  const root = 'urn:example:dense:0';
  for (let i = 0; i <= 120; i++) {
    const id = `urn:example:dense:${i}`,
      title = `Synthetic connected project ${i}`;
    model.entities[id] = { ...entity, id, title, aliases: [], themes: [], typing: [] };
    if (!i) continue;
    const relation = `urn:example:dense:claim:${i}`;
    model.claims[relation] = {
      ...claim,
      id: relation,
      subject: { id: root, label: 'Synthetic connected project 0' },
      object: { id, label: title, literal: false },
      evidence: [],
      evidence_accounts: [],
      themes: [],
    };
    model.relations.push({
      id: relation,
      from: root,
      to: id,
      kind: 'claim',
      label: 'relatedTo',
      status: claim.status,
      origin: claim.origin,
      knowledge_kind: claim.kind,
      themes: [],
    });
  }
  const html = await fs.readFile(path.join(folder, 'library.html'), 'utf8');
  const output = path.join(folder, 'dense.html');
  await fs.writeFile(
    output,
    html.replace(
      /(<script id="library-data" type="application\/json">)[\s\S]*?(<\/script>)/,
      (_, start, end) => start + JSON.stringify(model).replace(/</g, '\\u003c') + end,
    ),
  );
  await page.goto(pathToFileURL(output).href);
  await page.evaluate((id) => knotLibrary.navigate({ view: 'graph', id }, { focus: true }), root);
  assert.equal(await page.evaluate(() => knotLibrary.graph.visible.nodes.length), 100);
  assert.ok(await page.evaluate(() => knotLibrary.graph.visible.omitted > 0));
  await page.evaluate(() => {
    window.overlaps = () => {
      const network = knotLibrary.graph.network;
      const boxes = knotLibrary.graph.visible.nodes.map((n) => network.getBoundingBox(n.id));
      return boxes.reduce(
        (count, a, i) =>
          count +
          boxes
            .slice(i + 1)
            .filter(
              (b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom,
            ).length,
        0,
      );
    };
  });
  const before = await page.evaluate(() => overlaps());
  assert.ok(before > 0, 'The dense radial fixture reproduces overlapping labels');
  await page.evaluate(() => {
    window.layoutSettled = false;
    knotLibrary.graph.network.once('stabilized', () => (window.layoutSettled = true));
  });
  await page.locator('#layout-toggle').click();
  await page.waitForFunction(() => window.layoutSettled);
  await page.locator('#layout-toggle').click();
  assert.ok(
    (await page.evaluate(() => overlaps())) < before / 5,
    'Settled focused forces leave room between the dense fixture labels',
  );
  assert.equal(await page.evaluate(() => knotLibrary.graph.visible.nodes.length), 100);
  assert.equal(await page.locator('#focused-graph').getAttribute('aria-pressed'), 'true');
  await page.locator('#graph-fit').click();
  await page.screenshot({ path: path.join(folder, 'focused-live-dense.png') });
  console.log(
    `Dense focused layout: ${before} overlapping label pairs -> ${await page.evaluate(() => overlaps())}`,
  );
}

async function main() {
  const root = path.resolve(__dirname, '..'),
    folder = await fs.mkdtemp(path.join(os.tmpdir(), 'knot-library-browser-'));
  execFileSync(
    path.join(root, '.venv/bin/python'),
    [
      '-c',
      'import json,sys\nfrom pathlib import Path\nfrom example_data import build_examples\nfrom knot.presentation.library import export_library\np=Path(sys.argv[1])\nids=build_examples(p/"data")\nexport_library(p/"data",p/"library.html",visual_theme="paper")\nexport_library(p/"data",p/"demo.html",visual_theme="paper",initial_record=ids["project"])\n(p/"ids.json").write_text(json.dumps(ids))',
      folder,
    ],
    {
      cwd: root,
      env: {
        ...process.env,
        PYTHONDONTWRITEBYTECODE: '1',
        PYTHONPATH: [path.join(root, 'src'), path.join(root, 'scripts')].join(path.delimiter),
      },
    },
  );
  const ids = JSON.parse(await fs.readFile(path.join(folder, 'ids.json'), 'utf8'));
  const browser = await playwright[process.argv[2] || 'chromium'].launch({ headless: true }),
    context = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  const requests = [],
    errors = [];
  await context.route(/https?:\/\//, (r) => {
    requests.push(r.request().url());
    return r.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  try {
    if (process.argv.includes('--idle-only')) {
      await checkIdle(page, context, folder, ids);
      await checkIdleFixtures(page, folder);
      await checkCinematicIdle(page, folder);
      assert.deepEqual(errors, []);
      assert.deepEqual(requests, []);
      console.log('Offline Idle checks passed. Artifacts: ' + folder);
      return;
    }
    await page.goto(pathToFileURL(path.join(folder, 'library.html')).href);
    await page.waitForFunction(() => window.knotLibrary);
    assert.equal(await page.locator('#view-graph').getAttribute('aria-pressed'), 'true');
    assert.equal(
      await page.locator('#node-spacing').isVisible(),
      true,
      'Spacing is available in Focused mode before choosing a record',
    );
    assert.equal(await page.locator('#layout-toggle').isVisible(), true);
    assert.equal(await page.locator('#layout-toggle').isDisabled(), true);
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network),
      null,
      'No network starts before a selection',
    );
    await page.locator('#view-library').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network),
      null,
      'Library needs no graph instance',
    );
    await page.locator('#view-graph').click();
    await page.locator('#full-graph').click();
    assert.equal(await page.locator('#full-graph').getAttribute('aria-pressed'), 'true');
    assert.equal(await page.evaluate(() => knotLibrary.graph.visible.nodes.length), 14);
    assert.equal(
      await page
        .locator('#graph-layout-controls')
        .innerText()
        .then((s) => s.includes('Live layout moves nodes')),
      false,
    );
    await page.locator('#note-links').uncheck();
    assert.deepEqual(
      await page.evaluate(() => knotLibrary.graph.visible.nodes.map((n) => n.id).sort()),
      [ids.project, ids.concept, ids.trial, ids.tank, ids.volunteers, ids.decision].sort(),
    );
    assert.equal(await page.evaluate(() => knotLibrary.graph.visible.edges.length), 9);
    assert.ok(
      await page.evaluate(() => knotLibrary.graph.visible.edges.every((e) => !e.navigation)),
    );
    await page.locator('#view-library').click();
    await page.evaluate((id) => knotLibrary.navigate({ view: 'library', id }), ids.curated);
    assert.ok(
      (await page.locator('#reader-panel').innerText()).includes('Example curator'),
      'Hidden note nodes remain readable in Library',
    );
    await page.evaluate(() => knotLibrary.navigate({ view: 'graph', id: null }));
    assert.equal(await page.locator('#note-links').isChecked(), false);
    assert.equal(await page.evaluate(() => knotLibrary.graph.visible.nodes.length), 6);
    await page.locator('#note-links').check();
    assert.equal(await page.evaluate(() => knotLibrary.graph.visible.nodes.length), 14);
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    await page.evaluate(() => (window.firstNetwork = knotLibrary.graph.network));
    await page.locator('.graph-filters > summary').click();
    await page.locator('#claim-status').selectOption('Accepted');
    assert.equal(await page.locator('#note-links').isDisabled(), true);
    assert.equal(await page.evaluate(() => knotLibrary.graph.visible.edges.length), 1);
    assert.equal(await page.evaluate(() => knotLibrary.graph.visible.nodes.length), 2);
    await page.locator('#claim-status').selectOption('all');
    await page.locator('.graph-filters > summary').click();
    await page.locator('#node-spacing').focus();
    await page.locator('#node-spacing').press('ArrowRight');
    assert.equal(
      await page.evaluate(() =>
        Math.round(knotLibrary.graph.network.physics.options.barnesHut.springLength),
      ),
      187,
    );
    await page.locator('#layout-toggle').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
    );
    await page.evaluate((id) => knotLibrary.navigate({ view: 'graph', id }), ids.project);
    assert.equal(await page.locator('#full-graph').getAttribute('aria-pressed'), 'true');
    assert.equal(await page.evaluate(() => knotLibrary.graph.visible.nodes.length), 14);
    await page.locator('#layout-toggle').click();
    await page.locator('#view-library').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
    );
    assert.equal(await page.locator('#selection-title').innerText(), 'Community garden project');
    await page.locator('#view-graph').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network === window.firstNetwork),
      true,
    );
    assert.equal(context.pages().length, 1, 'Graph modes and Library use the same browser tab');
    await page.goBack();
    assert.equal(await page.locator('#view-library').getAttribute('aria-pressed'), 'true');
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
    );
    await page.goForward();
    assert.equal(await page.locator('#full-graph').getAttribute('aria-pressed'), 'true');
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    await page.locator('#layout-toggle').click();
    await page.screenshot({ path: path.join(folder, 'live-network.png') });
    await page.locator('#focused-graph').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
    );
    assert.equal(await page.evaluate(() => knotLibrary.graph.seed), ids.project);
    await page.locator('#note-links').uncheck();
    assert.deepEqual(
      await page.evaluate(() => knotLibrary.graph.visible.nodes.map((n) => n.id).sort()),
      [ids.project, ids.concept, ids.trial, ids.tank, ids.volunteers].sort(),
      'The same note filter applies in Focused mode',
    );
    await page.locator('#note-links').check();
    await page.evaluate((id) => knotLibrary.graph.network.moveNode(id, 45, -35), ids.project);
    const beforeSpacing = await page.evaluate(() => knotLibrary.graph.network.getPositions());
    const beforeCamera = await page.evaluate(() => ({
      scale: knotLibrary.graph.network.getScale(),
      position: knotLibrary.graph.network.getViewPosition(),
    }));
    const previousSpacing = Number(await page.locator('#node-spacing').inputValue());
    await page.locator('#node-spacing').focus();
    await page.locator('#node-spacing').press('ArrowRight');
    const nextSpacing = Number(await page.locator('#node-spacing').inputValue());
    const fixedPositions = await page.evaluate(() => knotLibrary.graph.network.getPositions());
    assert.deepEqual(
      fixedPositions[ids.project],
      beforeSpacing[ids.project],
      'The centre stays in place',
    );
    for (const [id, point] of Object.entries(beforeSpacing)) {
      if (id === ids.project) continue;
      const centre = beforeSpacing[ids.project];
      const before = Math.hypot(point.x - centre.x, point.y - centre.y);
      const after = Math.hypot(fixedPositions[id].x - centre.x, fixedPositions[id].y - centre.y);
      assert.ok(
        Math.abs(after / before - nextSpacing / previousSpacing) < 0.01,
        'Spacing changes actual node distances around the centre',
      );
    }
    assert.deepEqual(
      await page.evaluate(() => ({
        scale: knotLibrary.graph.network.getScale(),
        position: knotLibrary.graph.network.getViewPosition(),
      })),
      beforeCamera,
      'Changing spacing preserves zoom and camera position',
    );
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
    );
    assert.equal(await page.locator('#node-spacing-value').innerText(), `${nextSpacing}%`);
    await page.locator('#full-graph').click();
    await page.locator('#focused-graph').click();
    assert.deepEqual(
      await page.evaluate(() => knotLibrary.graph.network.getPositions()),
      fixedPositions,
    );
    await page.locator('#full-graph').click();
    const pausedPositions = await page.evaluate(() => knotLibrary.graph.network.getPositions());
    await page.locator('#node-spacing').focus();
    await page.locator('#node-spacing').press('ArrowRight');
    assert.notDeepEqual(
      await page.evaluate(() => knotLibrary.graph.network.getPositions()),
      pausedPositions,
      'Spacing also adjusts a paused Live network immediately',
    );
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
    );
    await page.locator('#focused-graph').click();
    assert.equal(Number(await page.locator('#node-spacing').inputValue()), nextSpacing + 10);
    const restored = await page.evaluate(() => knotLibrary.graph.network.getPositions());
    const centre = fixedPositions[ids.project];
    const neighbour = Object.keys(fixedPositions).find((id) => id !== ids.project);
    const priorDistance = Math.hypot(
      fixedPositions[neighbour].x - centre.x,
      fixedPositions[neighbour].y - centre.y,
    );
    const restoredDistance = Math.hypot(
      restored[neighbour].x - centre.x,
      restored[neighbour].y - centre.y,
    );
    assert.ok(
      Math.abs(restoredDistance / priorDistance - (nextSpacing + 10) / nextSpacing) < 0.01,
      'A cached Focused layout adopts the spacing changed in Live network',
    );
    await page.screenshot({ path: path.join(folder, 'focused-spacing.png') });
    assert.equal(await page.locator('#layout-toggle').innerText(), 'Live layout');
    const focusedIDs = await page.evaluate(() => knotLibrary.graph.visible.nodes.map((n) => n.id));
    await page.locator('#layout-toggle').click();
    assert.equal(await page.locator('#layout-toggle').innerText(), 'Pause layout');
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    assert.deepEqual(
      await page.evaluate(() => knotLibrary.graph.visible.nodes.map((n) => n.id)),
      focusedIDs,
      'Animating Focused mode does not load the full network',
    );
    await page.waitForFunction(
      (before) =>
        Object.entries(knotLibrary.graph.network.getPositions()).some(
          ([id, point]) => Math.hypot(point.x - before[id].x, point.y - before[id].y) > 10,
        ),
      restored,
    );
    await page.locator('#node-spacing').focus();
    await page.locator('#node-spacing').press('ArrowRight');
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    await page.locator('#hop-more').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    await page.locator('#hop-less').click();
    await page.locator('#note-links').uncheck();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    await page.locator('#note-links').check();
    await page.locator('#view-library').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
    );
    await page.goBack();
    assert.equal(await page.locator('#focused-graph').getAttribute('aria-pressed'), 'true');
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    await page.locator('#full-graph').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
      'Full network retains its own paused setting',
    );
    await page.locator('#focused-graph').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
    );
    await page.locator('#layout-toggle').click();
    const arranged = await page.evaluate(() => knotLibrary.graph.network.getPositions());
    await page.waitForTimeout(200);
    assert.deepEqual(await page.evaluate(() => knotLibrary.graph.network.getPositions()), arranged);
    await page.locator('#full-graph').click();
    await page.locator('#focused-graph').click();
    const afterModeChange = await page.evaluate(() => knotLibrary.graph.network.getPositions());
    assert.deepEqual(
      afterModeChange,
      arranged,
      'Pausing keeps the new arrangement across mode changes: ' +
        JSON.stringify(
          Object.keys(arranged)
            .filter((id) => JSON.stringify(arranged[id]) !== JSON.stringify(afterModeChange[id]))
            .map((id) => ({ id, before: arranged[id], after: afterModeChange[id] })),
        ),
    );
    await page.locator('#view-library').click();
    await page.locator('#knowledge-search').fill('independent question');
    await page.waitForTimeout(170);
    await page.locator('#search-results .record-choice').first().click();
    assert.equal(await page.locator('#reader-panel h1').innerText(), 'An independent question');
    await page.locator('#explore-selection').click();
    assert.equal(await page.evaluate(() => knotLibrary.graph.visible.nodes.length), 1);
    assert.equal(await page.locator('#layout-toggle').isDisabled(), true);
    assert.equal(
      await page.evaluate(
        (id) => Math.round(knotLibrary.graph.network.getPosition(id).x),
        ids.isolated,
      ),
      0,
    );
    await page.screenshot({ path: path.join(folder, 'isolated-graph.png') });
    await page.evaluate((id) => knotLibrary.navigate({ view: 'library', id }), ids.garden);
    assert.ok((await page.locator('#reader-panel').innerText()).includes('still under discussion'));
    assert.ok((await page.locator('#context-content').innerText()).includes('Backlinks'));
    await page.evaluate((id) => knotLibrary.navigate({ view: 'library', id }), ids.reading);
    assert.equal(await page.locator('#reader-panel h1').innerText(), 'Water conservation');
    assert.equal(await page.locator('#reader-panel pre').count(), 1);
    await page.goBack();
    assert.equal(await page.evaluate(() => knotLibrary.selection.id), ids.garden);
    await page.goForward();
    assert.equal(await page.evaluate(() => knotLibrary.selection.id), ids.reading);
    await page.evaluate((id) => knotLibrary.navigate({ view: 'library', id }), ids.curated);
    assert.ok((await page.locator('#reader-panel').innerText()).includes('Example curator'));
    await page.locator('#reader-panel .evidence-card').first().locator('summary').click();
    await page
      .locator('#reader-panel')
      .getByRole('button', { name: 'Open pinned source' })
      .first()
      .click();
    assert.equal(await page.evaluate(() => knotLibrary.selection.revision), ids.cited_revision);
    assert.ok(
      !(await page.locator('.reader-content').innerText()).includes('still under discussion'),
    );
    await page.evaluate(
      (id) => knotLibrary.navigate({ view: 'graph', id }, { focus: true }),
      ids.project,
    );
    await page.locator('.graph-filters > summary').click();
    await page.locator('#claim-status').selectOption('Accepted');
    assert.ok(
      await page.evaluate(() =>
        knotLibrary.graph.visible.edges.every((e) => e.status === 'Accepted'),
      ),
    );
    await page.locator('#claim-status').selectOption('all');
    const seedBefore = await page.evaluate(() => knotLibrary.graph.seed);
    await page
      .locator('#connection-list')
      .getByRole('button', { name: 'Focus', exact: true })
      .first()
      .click();
    assert.notEqual(await page.evaluate(() => knotLibrary.graph.seed), seedBefore);
    await page.goBack();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.seed),
      seedBefore,
      'Back restores the prior graph root',
    );
    assert.ok(
      (await page.locator('#context-content').innerText()).includes('Historical relationships'),
    );
    await page.screenshot({ path: path.join(folder, 'graph.png') });
    await page.locator('#view-library').click();
    await page.evaluate((id) => knotLibrary.navigate({ view: 'library', id }), ids.garden);
    await page.screenshot({ path: path.join(folder, 'library.png') });
    assert.equal(await page.evaluate(() => localStorage.length), 0);
    await page.locator('#record-filter').selectOption('note');
    await page.locator('#knowledge-search').fill('');
    await page.waitForTimeout(170);
    assert.equal(await page.locator('#search-results .record-choice').count(), 8);
    await page.locator('#main-panel').evaluate((node) => (node.scrollTop = 150));
    const readerScroll = await page.locator('#main-panel').evaluate((node) => node.scrollTop);
    await page.locator('#view-graph').click();
    await page.locator('#view-library').click();
    assert.equal(
      await page.locator('#main-panel').evaluate((node) => node.scrollTop),
      readerScroll,
      'View switches preserve reader scroll',
    );
    await page.evaluate(() => knotLibrary.navigate({ view: 'graph', id: 'urn:example:missing' }));
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.visible.nodes.length),
      0,
      'An absent record does not show a different graph root',
    );
    assert.ok((await page.locator('#selection-title').innerText()).includes('Not included'));
    await page.goto(pathToFileURL(path.join(folder, 'demo.html')).href);
    assert.equal(await page.evaluate(() => knotLibrary.graph.seed), ids.project);
    assert.ok(await page.evaluate(() => knotLibrary.graph.visible.nodes.length >= 8));
    assert.ok(await page.evaluate(() => knotLibrary.graph.visible.edges.length >= 8));
    await page.screenshot({ path: path.join(folder, 'example-start.png') });
    await page.reload();
    assert.equal(await page.evaluate(() => knotLibrary.graph.seed), ids.project);
    await page.locator('#hop-more').click();
    assert.ok(
      await page.evaluate(
        (id) => knotLibrary.graph.visible.nodes.some((n) => n.id === id),
        ids.decision,
      ),
    );
    assert.equal(await page.evaluate(() => knotLibrary.graph.full), false);
    const direct = await context.newPage();
    direct.on('pageerror', (e) => errors.push(e.message));
    await direct.goto(
      pathToFileURL(path.join(folder, 'demo.html')).href +
        '#view=library&id=' +
        encodeURIComponent(ids.isolated),
    );
    assert.equal(
      await direct.evaluate(() => knotLibrary.graph.network),
      null,
      'Explicit Library routes override the demo start without constructing a graph',
    );
    assert.equal(await direct.locator('#reader-panel h1').innerText(), 'An independent question');
    await direct.close();
    await checkIdle(page, context, folder, ids);
    await checkIdleFixtures(page, folder);
    await checkCinematicIdle(page, folder);
    await checkDenseFocus(page, folder);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(pathToFileURL(path.join(folder, 'library.html')).href);
    assert.equal(await page.evaluate(() => knotLibrary.recents.length), 0);
    await page.locator('#full-graph').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
      'Reduced motion keeps the live network paused until explicitly requested',
    );
    await page.evaluate(
      (id) => knotLibrary.navigate({ view: 'graph', id }, { focus: true }),
      ids.project,
    );
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      false,
    );
    await page.locator('#layout-toggle').click();
    assert.equal(
      await page.evaluate(() => knotLibrary.graph.network.physics.options.enabled),
      true,
      'Reduced motion allows an explicit request to animate the focused graph',
    );
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.waitForFunction(() => !matchMedia('(prefers-reduced-motion: reduce)').matches);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.waitForFunction(() => !knotLibrary.graph.network.physics.options.enabled);
    await page.setViewportSize({ width: 360, height: 800 });
    await page.locator('#toggle-navigation').click();
    assert.equal(await page.locator('#navigation-panel').isVisible(), true);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(folder, 'narrow.png') });
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    console.log('Offline Graph/Library browser checks passed. Artifacts: ' + folder);
  } finally {
    await browser.close();
  }
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
