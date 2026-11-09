/* Visual continuity checks against the actual canvas renderer and offline projection. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

module.exports = async function checkCinematicIdle(page, folder) {
  const base = await page.evaluate(() => structuredClone(knotLibrary.index.model));
  const template = await fs.readFile(path.join(folder, 'library.html'), 'utf8');
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
      text: {
        text: 'Existing synthetic knowledge.\nA second line, with its qualification.',
        html: {
          markdown:
            '<p>Existing synthetic knowledge.<br>A second line, with its qualification.</p>',
        },
      },
      empty: { text: '', html: { markdown: '' } },
    },
  };
  delete fixture.initial_record;
  fixture.manifest = { ...base.manifest, fingerprint: 'cinematic-synthetic-projection' };
  const titles = {
    a: 'Aperture model',
    b: 'Bridge experiment',
    c: 'Calibration',
    d: 'Design review',
    x: 'Earlier question',
    island: 'Independent idea',
  };
  for (const [id, title] of Object.entries(titles))
    fixture.notes[id] = {
      id,
      title,
      revision: 'urn:example:revision:' + id,
      body: ['c', 'x'].includes(id) ? 'empty' : 'text',
      format: 'markdown',
      author: 'Example author',
      entities: [],
      sources: [],
      history: [],
      navigation: { links: [], themes: [], declarations: [] },
    };
  for (const [from, to, kind] of [
    ['a', 'b', 'link'],
    ['b', 'c', 'link'],
    ['c', 'd', 'link'],
    ['d', 'b', 'link'],
    ['a', 'x', 'association'],
  ])
    fixture.relations.push({
      id: from + to,
      from,
      to,
      kind,
      label: kind === 'link' ? 'links to' : 'about',
    });
  const output = path.join(folder, 'idle-cinematic.html');
  await fs.writeFile(
    output,
    template.replace(
      /(<script id="library-data" type="application\/json">)[\s\S]*?(<\/script>)/,
      (_, start, end) => start + JSON.stringify(fixture).replace(/</g, '\\u003c') + end,
    ),
  );
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') });
  await page.goto(pathToFileURL(output).href + '#view=graph&id=a');
  await page.clock.pauseAt(new Date('2026-01-01T00:00:10Z'));
  await page.locator('#view-idle').click();
  await page.locator('#idle-toggle').click();
  const capture = () =>
    page.evaluate(() => {
      const network = knotLibrary.graph.network;
      const positions = network.getPositions();
      const surface = document.querySelector('#graph-canvas canvas');
      const context = surface.getContext('2d');
      const ratio = surface.width / surface.getBoundingClientRect().width;
      const labelBrightness = {};
      for (const id of ['c', 'x']) {
        if (!positions[id]) continue;
        const point = network.canvasToDOM(positions[id]);
        const x = Math.max(0, Math.round((point.x - 90) * ratio));
        const y = Math.max(0, Math.round((point.y + 12) * ratio));
        const width = Math.min(Math.round(180 * ratio), surface.width - x);
        const height = Math.min(Math.round(35 * ratio), surface.height - y);
        if (width <= 0 || height <= 0) continue;
        const pixels = context.getImageData(x, y, width, height).data;
        let peak = 0;
        for (let i = 0; i < pixels.length; i += 4)
          peak = Math.max(peak, (pixels[i + 1] * pixels[i + 3]) / 255);
        labelBrightness[id] = peak;
      }
      return {
        state: knotLibrary.idle.state,
        positions,
        camera: network.getViewPosition(),
        scale: network.getScale(),
        nodes: Object.fromEntries(network.body.data.nodes.get().map((n) => [n.id, n.opacity])),
        edges: network.body.data.edges
          .get()
          .map((e) => ({ id: e.id, from: e.from, to: e.to, opacity: e.color.opacity })),
        screen: Object.fromEntries(
          Object.entries(positions).map(([id, p]) => [id, network.canvasToDOM(p)]),
        ),
        panel: Number(getComputedStyle(document.getElementById('idle-card')).opacity),
        canvas: Number(getComputedStyle(document.getElementById('graph-canvas')).opacity),
        labelBrightness,
      };
    });
  const initial = await capture();
  assert.equal(initial.state.current, 'a');
  assert.equal(initial.panel, 0);
  const modelBefore = await page.evaluate(() => JSON.stringify(knotLibrary.index.model));
  await page.clock.runFor(9900);
  assert.equal((await capture()).state.phase, 'focus');
  assert.equal(await page.locator('#idle-card').isVisible(), false);
  await page.screenshot({ path: path.join(folder, 'cinematic-focus.png') });
  await page.clock.runFor(1500);
  assert.equal((await capture()).state.phase, 'reading', JSON.stringify(await capture()));
  assert.equal((await capture()).panel, 1);
  assert.equal(await page.locator('#idle-excerpt').innerText(), fixture.bodies.text.text);
  await page.screenshot({ path: path.join(folder, 'cinematic-reading.png') });
  await page.clock.runFor(8000);
  assert.equal((await capture()).state.phase, 'reading', 'A full reading interval precedes motion');
  await page.clock.runFor(4000);
  const early = await capture();
  assert.equal(early.state.phase, 'travel');
  assert.equal(early.state.target, 'b');
  assert.equal(early.panel, 0);
  assert.equal(early.nodes.c, 0, 'New neighbours do not appear at departure');
  assert.equal(early.nodes.x, 1, 'The old neighbourhood is retained during departure');
  await page.clock.runFor(12000);
  const middle = await capture();
  assert.equal(middle.state.current, 'a', 'The destination is committed only on arrival');
  assert.ok(
    middle.nodes.c > 0 && middle.nodes.c < 1,
    'Destination neighbours emerge gradually: ' +
      JSON.stringify({ state: middle.state, nodes: middle.nodes }),
  );
  assert.ok(middle.nodes.x > 0 && middle.nodes.x < 1, 'Old neighbours fade gradually');
  assert.deepEqual(middle.positions.a, initial.positions.a);
  assert.deepEqual(middle.positions.b, initial.positions.b);
  assert.deepEqual(middle.positions.x, initial.positions.x);
  assert.equal(middle.scale, initial.scale, 'Travel does not zoom out to fit the graph');
  const vector = {
    x: initial.positions.b.x - initial.positions.a.x,
    y: initial.positions.b.y - initial.positions.a.y,
  };
  const delta = { x: middle.camera.x - initial.camera.x, y: middle.camera.y - initial.camera.y };
  const distanceSquared = vector.x ** 2 + vector.y ** 2;
  assert.ok(
    Math.abs(delta.x * vector.y - delta.y * vector.x) < 0.001,
    'The real camera follows the AB segment',
  );
  const fraction = (delta.x * vector.x + delta.y * vector.y) / distanceSquared;
  assert.ok(
    fraction > 0.3 && fraction < 0.7,
    'The camera occupies intermediate positions over the 24-second journey',
  );
  assert.notDeepEqual(
    middle.screen.a,
    initial.screen.a,
    'The canvas actually moves beneath the viewport',
  );
  assert.ok(middle.edges.some((e) => e.id === 'ab' && e.opacity > 0.9));
  await page.screenshot({ path: path.join(folder, 'cinematic-travel-middle.png') });

  await page.locator('#idle-toggle').click();
  await page.clock.runFor(32); // Let the renderer finish its already requested final draw.
  const paused = await capture();
  await page.clock.runFor(60000);
  assert.deepEqual(await capture(), paused, 'Pause freezes both camera and visual fades');
  await page.locator('#idle-toggle').click();
  await page.clock.runFor(6500);
  const late = await capture();
  assert.ok(late.nodes.c > middle.nodes.c);
  assert.ok(late.nodes.x < middle.nodes.x);
  assert.ok(
    late.labelBrightness.c > middle.labelBrightness.c,
    'Actual destination-label pixels fade in with the node',
  );
  assert.deepEqual(late.positions.b, initial.positions.b);
  await page.screenshot({ path: path.join(folder, 'cinematic-travel-arriving.png') });
  await page.clock.runFor(6000);
  const arrived = await capture();
  assert.equal(arrived.state.current, 'b');
  assert.equal(arrived.nodes.x, undefined, 'An old neighbour is removed only after its fade');
  assert.equal(arrived.nodes.c, 1);
  assert.deepEqual(arrived.positions.b, initial.positions.b);
  assert.ok(Math.abs(arrived.camera.x - initial.camera.x - vector.x) < 0.001);
  assert.ok(Math.abs(arrived.camera.y - initial.camera.y - vector.y) < 0.001);

  await page.locator('#idle-focus').selectOption('5');
  await page.locator('#idle-travel').selectOption('4');
  const visited = ['b'];
  let regionFade = false;
  for (let i = 0; i < 120 && visited.at(-1) !== 'island'; i++) {
    await page.clock.runFor(1000);
    const view = await capture();
    if (view.state.current !== visited.at(-1)) visited.push(view.state.current);
    if (view.state.current === 'c')
      assert.notEqual(
        view.state.phase,
        'reading',
        'A missing excerpt skips reading, not traversal',
      );
    if (view.state.phase === 'region' && view.canvas > 0 && view.canvas < 1) regionFade = true;
    for (const edge of view.edges)
      assert.ok(
        fixture.relations.some((e) => e.id === edge.id && e.from === edge.from && e.to === edge.to),
        'Every drawn edge exists in the snapshot',
      );
    assert.ok(view.state.visible <= 40 && view.state.edges <= 80);
    if (view.positions.b) assert.deepEqual(view.positions.b, initial.positions.b);
  }
  assert.equal(visited[0], 'b');
  assert.equal(visited.at(-1), 'island');
  assert.deepEqual(
    visited.slice(1, -1).sort(),
    ['c', 'd'],
    'Either branch traverses the cycle once',
  );
  assert.ok(regionFade, 'A disconnected region fades instead of pretending to follow an edge');
  assert.equal(await page.evaluate(() => JSON.stringify(knotLibrary.index.model)), modelBefore);
  await page.locator('#idle-exit').click();
  assert.equal(await page.evaluate(() => knotLibrary.idle.state.cachedPositions), 0);

  await checkIdleInterruptions(page, output);

  await page.goto(
    pathToFileURL(path.join(folder, 'idle-70.html')).href +
      '#view=graph&id=urn%3Aexample%3Aidle%3Anote%3A0',
  );
  await page.locator('#view-idle').click();
  await page.locator('#idle-depth').selectOption('2');
  await page.locator('#idle-focus').selectOption('5');
  await page.locator('#idle-travel').selectOption('4');
  await page.locator('#idle-toggle').click();
  for (let i = 0; i < 25; i++) {
    await page.clock.runFor(1000);
    const view = await capture();
    assert.ok(
      view.state.visible <= 40 && view.state.edges <= 80,
      'Dense transition unions stay bounded',
    );
  }
  await page.screenshot({ path: path.join(folder, 'cinematic-hub.png') });
  await page.locator('#idle-exit').click();
  await page.clock.resume();
  await page.goto(pathToFileURL(path.join(folder, 'library.html')).href);
  console.log(
    'Cinematic canvas movement, stable geography, progressive fades, chain/cycle and region checks passed',
  );
};

async function checkIdleInterruptions(page, output) {
  const view = () =>
    page.evaluate(() => ({
      ...knotLibrary.idle.state,
      positions: knotLibrary.graph.network.getPositions(),
      camera: knotLibrary.graph.network.getViewPosition(),
      opacity: Number(getComputedStyle(document.getElementById('graph-canvas')).opacity),
      nodes: knotLibrary.graph.network.body.data.nodes.get().map((n) => [n.id, n.opacity]),
      excerpt: document.getElementById('idle-excerpt').textContent,
      panelOpacity: Number(getComputedStyle(document.getElementById('idle-card')).opacity),
    }));
  async function enter(seed = 'a', motion = 'no-preference') {
    await page.emulateMedia({ reducedMotion: motion });
    await page.goto(pathToFileURL(output).href + '#view=graph&id=' + seed);
    await page.clock.runFor(32);
    await page.evaluate(() => {
      window.idleReturnCheck = {
        selection: knotLibrary.selection,
        positions: knotLibrary.graph.network.getPositions(),
        camera: knotLibrary.graph.network.getViewPosition(),
        scale: knotLibrary.graph.network.getScale(),
        recents: knotLibrary.recents,
      };
      window.idleNetworkCheck = knotLibrary.graph.network;
    });
    await page.locator('#view-idle').click();
    await page.locator('#idle-focus').selectOption('5');
    await page.locator('#idle-toggle').click();
  }
  async function reach(phase, progress = 0) {
    for (let i = 0; i < 100; i++) {
      const current = await view();
      if (current.phase === phase && current.progress >= progress) return current;
      assert.equal(current.running, true, await page.locator('#idle-state').innerText());
      await page.clock.runFor(500);
    }
    assert.fail('Did not reach ' + phase + ': ' + JSON.stringify(await view()));
  }
  async function hidden(value) {
    await page.evaluate((value) => {
      Object.defineProperty(document, 'hidden', { configurable: true, value });
      document.dispatchEvent(new Event('visibilitychange'));
    }, value);
  }
  async function assertRestored(context = 'exit') {
    await page.waitForURL(/#view=graph/);
    await page.clock.runFor(60000);
    const actual = await page.evaluate(() => ({
      selection: knotLibrary.selection,
      positions: knotLibrary.graph.network.getPositions(),
      camera: knotLibrary.graph.network.getViewPosition(),
      scale: knotLibrary.graph.network.getScale(),
      recents: knotLibrary.recents,
    }));
    const expected = await page.evaluate(() => idleReturnCheck);
    for (const axis of ['x', 'y'])
      assert.ok(
        Math.abs(actual.camera[axis] - expected.camera[axis]) < 1e-6,
        context +
          ': restored camera ' +
          JSON.stringify({ actual: actual.camera, expected: expected.camera }),
      );
    // Canvas transform round trips introduce sub-pixel floating-point noise.
    for (const key of Object.keys(expected).filter((key) => key !== 'camera'))
      assert.deepEqual(
        actual[key],
        expected[key],
        context +
          ': restored ' +
          key +
          ' ' +
          JSON.stringify({ actual: actual[key], expected: expected[key] }),
      );
    assert.equal(await page.evaluate(() => knotLibrary.idle.active), false);
    assert.equal((await view()).pending, false);
    assert.equal((await view()).cachedPositions, 0);
    assert.equal(await page.locator('#graph-canvas').count(), 1);
    assert.equal(
      await page.evaluate(() =>
        document.getElementById('idle-stage').contains(document.getElementById('graph-canvas')),
      ),
      false,
    );
  }

  // Reconfiguration must reset presentation opacity as well as cancelling its timer.
  await enter('island');
  const fading = await reach('region', 0.2);
  assert.ok(fading.opacity < 1 && fading.opacity > 0);
  await page.locator('#idle-toggle').click();
  await page.locator('#idle-depth').selectOption('2');
  const reconfigured = await view();
  assert.equal(
    reconfigured.opacity,
    1,
    'Changing depth during a region fade must not leave a dim scene',
  );
  assert.equal(reconfigured.current, 'island');
  assert.equal(reconfigured.running, false, 'Settings cannot override an explicit pause');
  await page.clock.runFor(60000);
  assert.deepEqual(await view(), reconfigured, 'The cancelled region must not arrive later');

  await enter();
  await reach('travel', 0.25);
  await hidden(true);
  await page.clock.runFor(32);
  const suspended = await view();
  assert.equal(suspended.pending, false);
  await page.clock.runFor(60 * 60 * 1000);
  assert.deepEqual(await view(), suspended, 'A hidden window freezes the actual journey and fades');
  await hidden(false);
  await page.clock.runFor(500);
  assert.notDeepEqual(
    (await view()).camera,
    suspended.camera,
    'Visibility resumes the saved journey',
  );
  await page.locator('#idle-toggle').click();
  await hidden(true);
  await hidden(false);
  assert.equal((await view()).running, false);
  const target = (await view()).target;
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.waitForFunction((id) => knotLibrary.idle.state.current === id, target, {
    polling: 50,
    timeout: 5000,
  });
  await page.clock.runFor(32);
  const reduced = await view();
  assert.equal(reduced.current, target, 'Reduced motion settles the real destination');
  assert.equal(
    reduced.running,
    false,
    'Changing accessibility preferences does not resume playback',
  );
  assert.equal(reduced.animating, false);
  await page.clock.runFor(60000);
  assert.deepEqual(await view(), reduced);

  await enter();
  await reach('travel', 0.2);
  await page.locator('#idle-filters').evaluate((e) => {
    e.open = true;
  });
  await page.locator('#idle-status').selectOption('Accepted');
  assert.equal(await page.locator('#graph-canvas').isVisible(), false);
  assert.equal(await page.locator('#idle-card').isVisible(), false);
  assert.equal((await view()).current, null);
  assert.equal((await view()).pending, false);
  await page.clock.runFor(60000);
  assert.equal(
    await page.locator('#graph-canvas').isVisible(),
    false,
    'An excluded destination cannot return on a stale callback',
  );
  await page.locator('#idle-status').selectOption('all');
  assert.equal((await view()).running, false);
  assert.equal((await view()).opacity, 1);
  await page.locator('#idle-toggle').click();
  await reach('reading');
  await page.locator('#idle-read').focus();
  const reading = await view();
  assert.equal(reading.running, false, 'Keyboard inspection pauses the excerpt');
  await page.clock.runFor(60000);
  assert.equal((await view()).excerpt, reading.excerpt);
  assert.equal((await view()).current, reading.current);
  await page.locator('#idle-panel').focus();
  await page.keyboard.press('Space');
  assert.equal((await view()).running, true, 'Space resumes when focus is on the presentation');
  await page.keyboard.press('Space');
  assert.equal((await view()).running, false);
  await page.evaluate(() => {
    document.getElementById('idle-panel').requestFullscreen = () =>
      Promise.reject(new Error('Synthetic full-screen denial'));
  });
  await page.locator('#idle-fullscreen').click();
  assert.ok((await page.locator('#idle-state').innerText()).includes('window'));
  assert.equal(
    await page.evaluate(() => knotLibrary.idle.active),
    true,
    'Full-screen denial keeps the ordinary view usable',
  );
  assert.equal((await view()).current, reading.current);
  await page.evaluate(() => {
    delete document.getElementById('idle-panel').requestFullscreen;
  });

  for (const phase of ['focus', 'reading', 'travel', 'region']) {
    await enter(phase === 'region' ? 'island' : 'a');
    await reach(phase, ['travel', 'region'].includes(phase) ? 0.2 : 0);
    if (phase === 'focus') await page.keyboard.press('Escape');
    else if (phase === 'reading') await page.locator('#view-graph').click();
    else if (phase === 'travel') await page.goBack();
    else await page.locator('#idle-exit').click();
    await assertRestored(phase);
  }

  // Reusing the same page catches accumulated controls, canvases and listeners.
  for (let i = 0; i < 8; i++) {
    await page.locator('#view-idle').click();
    await page.locator('#idle-toggle').click();
    assert.equal((await view()).running, true);
    await page.clock.runFor(400);
    await page.keyboard.press('Escape');
    await assertRestored();
    assert.equal(await page.evaluate(() => knotLibrary.graph.network === idleNetworkCheck), true);
  }

  await enter('a', 'reduce');
  await page.clock.runFor(20000);
  const baseline = await page.evaluate(() => ({
    history: history.length,
    recents: knotLibrary.recents,
    elements: document.querySelectorAll('*').length,
    records: knotLibrary.index.records.length,
    model: JSON.stringify(knotLibrary.index.model),
  }));
  await page.evaluate(() => {
    window.idleTitleChanges = 0;
    let previous = document.getElementById('idle-title').textContent;
    window.idleTitleObserver = new MutationObserver(() => {
      const next = document.getElementById('idle-title').textContent;
      if (previous !== next) idleTitleChanges++;
      previous = next;
    });
    idleTitleObserver.observe(document.getElementById('idle-title'), { childList: true });
  });
  const geography = new Map();
  for (let hour = 1; hour <= 8; hour++) {
    await page.clock.runFor(60 * 60 * 1000);
    const current = await view();
    assert.equal(current.running, true, 'The accelerated tour keeps running after hour ' + hour);
    assert.ok(current.visible <= 40 && current.edges <= 80);
    assert.ok(current.cachedPositions <= baseline.records);
    for (const [id, position] of Object.entries(current.positions)) {
      if (geography.has(id)) assert.deepEqual(position, geography.get(id));
      geography.set(id, position);
    }
    assert.equal(await page.evaluate(() => history.length), baseline.history);
    assert.deepEqual(await page.evaluate(() => knotLibrary.recents), baseline.recents);
    assert.equal(
      await page.evaluate(() => document.querySelectorAll('*').length),
      baseline.elements,
    );
  }
  assert.ok(
    await page.evaluate(() => idleTitleChanges > 500),
    'The soak exercises real displayed-note changes',
  );
  assert.equal(await page.evaluate(() => JSON.stringify(knotLibrary.index.model)), baseline.model);
  await page.evaluate(() => idleTitleObserver.disconnect());
  await page.locator('#idle-exit').click();
  await assertRestored();
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  console.log(
    'Idle interruptions, filter recovery, repeated entry and eight accelerated hours passed',
  );
}
