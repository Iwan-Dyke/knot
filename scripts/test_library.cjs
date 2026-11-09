const assert = require('node:assert/strict');
const { create, route, hash } = require('../src/knot/presentation/library_model.js');
const notes = {
  n: {
    id: 'n',
    title: 'Same label',
    body: 'body',
    kind: null,
    entities: [],
    history: [],
    navigation: { themes: [{ id: 'x' }, { id: 'y' }], links: [] },
  },
  isolated: {
    id: 'isolated',
    title: 'Isolated',
    navigation: { themes: [], links: [] },
    entities: [],
  },
};
const entities = Object.fromEntries(
  ['a', 'b', 'c', 'd'].map((id) => [
    id,
    { id, title: 'Same label', types: ['Project'], aliases: [], themes: [] },
  ]),
);
const claims = Object.fromEntries(
  [
    ['ab', 'a', 'b'],
    ['ac', 'a', 'c'],
    ['bd', 'b', 'd'],
    ['cd', 'c', 'd'],
  ].map(([id, from, to]) => [
    id,
    {
      id,
      subject: { id: from },
      object: { id: to },
      status: 'Unreviewed',
      origin: 'Explicit',
      kind: 'Idea',
      themes: [],
    },
  ]),
);
const relations = Object.values(claims).map((c) => ({
  id: c.id,
  from: c.subject.id,
  to: c.object.id,
  kind: 'claim',
  label: 'relatedTo',
  status: c.status,
  origin: c.origin,
  themes: [],
  knowledge_kind: 'Idea',
}));
relations.push({ id: 'link', from: 'n', to: 'a', kind: 'association', label: 'about' });
const model = {
  notes,
  entities,
  claims,
  relations,
  bodies: { body: { text: 'A body-only needle', html: {} } },
};
const index = create(model);
assert.equal(route('', 'a').id, 'a', 'A demo can open on a connected record');
assert.equal(route('#view=library', 'a').id, null, 'Explicit routes override the demo start');
assert.equal(route(hash({ view: 'graph', id: 'n' }), 'a').id, 'n');
assert.equal(
  index.search('needle').length,
  1,
  'Body search finds a note without matching its title',
);
assert.equal(index.search('Same label').length, 5, 'Duplicate labels retain distinct identities');
for (const theme of ['x', 'y'])
  assert.equal(index.search('', { collection: { type: 'theme', id: theme } })[0].record.id, 'n');
assert.deepEqual(
  index.search('', { collection: { type: 'standalone' } }).map((x) => x.record.id),
  ['isolated'],
);
assert.deepEqual(
  index.neighbourhood({ seed: 'isolated', filters: {} }).nodes.map((n) => n.id),
  ['isolated'],
);
let result = index.neighbourhood({
  seed: 'a',
  hops: 1,
  expanded: ['b', 'c'],
  collapsed: ['b'],
  filters: {},
});
assert.ok(
  result.nodes.some((n) => n.id === 'd'),
  'Collapsing one branch retains another route to shared neighbour',
);
result = index.neighbourhood({
  seed: 'a',
  hops: 1,
  expanded: ['b', 'c'],
  collapsed: ['b', 'c'],
  filters: {},
});
assert.ok(!result.nodes.some((n) => n.id === 'd'));
result = index.neighbourhood({ seed: 'a', hops: 2, filters: {} }, { nodes: 2, edges: 1 });
assert.equal(result.nodes.length, 2);
assert.ok(result.omitted > 0);
result = index.neighbourhood({ seed: 'a', hops: 1, filters: { status: 'Accepted' } });
assert.equal(result.edges.length, 0);
assert.equal(result.nodes[0].id, 'a');
result = index.neighbourhood({ seed: 'a', full: true, filters: { status: 'Accepted' } });
assert.equal(result.edges.length, 0);
assert.deepEqual(
  result.nodes.map((n) => n.id),
  ['a'],
  'Full graph retains accepted-only semantics and selected root',
);
const target = { view: 'library', id: 'urn:knot:note:one', revision: 'urn:knot:note-revision:old' };
assert.deepEqual(route(hash(target)), target);

const originalModel = JSON.stringify(model);
const withoutNotes = index.neighbourhood({ seed: 'a', full: true, filters: { showNotes: false } });
assert.deepEqual(withoutNotes.nodes.map((n) => n.id).sort(), ['a', 'b', 'c', 'd']);
assert.ok(withoutNotes.edges.every((e) => !e.navigation));
assert.ok(
  !index
    .neighbourhood({ seed: 'a', hops: 3, filters: { showNotes: false } })
    .nodes.some((n) => n.id === 'n'),
);
assert.deepEqual(
  index.neighbourhood({ seed: 'isolated', filters: { showNotes: false } }).nodes.map((n) => n.id),
  ['isolated'],
  'An explicitly focused note remains readable',
);
assert.equal(index.search('needle').length, 1, 'Graph visibility does not filter the Library');

const noteClaim = {
  id: 'documentation',
  subject: { id: 'b' },
  object: { id: 'n' },
  status: 'Accepted',
  origin: 'Explicit',
  kind: 'Idea',
  themes: [],
};
const noteValue = {
  ...noteClaim,
  id: 'note-value',
  subject: { id: 'isolated' },
  object: { id: 'value', literal: true },
};
const endpointModel = create({
  ...model,
  claims: { ...claims, documentation: noteClaim, 'note-value': noteValue },
  relations: [
    ...relations,
    {
      id: 'documentation',
      from: 'b',
      to: 'n',
      kind: 'claim',
      knowledge_kind: 'Idea',
      status: 'Accepted',
      origin: 'Explicit',
      themes: [],
    },
  ],
});
const endpoints = endpointModel.neighbourhood({ full: true, filters: { showNotes: false } });
assert.ok(
  endpoints.nodes.some((n) => n.id === 'n'),
  'A note used as a claim endpoint stays visible',
);
assert.ok(
  endpoints.nodes.some((n) => n.id === 'isolated'),
  'A note with a literal claim stays visible',
);
assert.ok(endpoints.edges.some((e) => e.id === 'documentation'));
assert.ok(endpoints.edges.every((e) => !e.navigation));
const acceptedNotes = endpointModel.neighbourhood({
  full: true,
  filters: { showNotes: false, status: 'Accepted' },
});
assert.deepEqual(acceptedNotes.nodes.map((n) => n.id).sort(), ['b', 'isolated', 'n']);
assert.equal(JSON.stringify(model), originalModel, 'Toggling notes never removes stored knowledge');
console.log('Library search, identity, routes and bounded graph checks passed');

const { create: layout, scalePositions } = require('../src/knot/presentation/library_layout.js');
const placed = { root: { x: 20, y: -10 }, neighbour: { x: 70, y: 90 }, hidden: { x: -30, y: 40 } };
assert.deepEqual(scalePositions(placed, 2, 'root'), {
  root: { x: 20, y: -10 },
  neighbour: { x: 120, y: 190 },
  hidden: { x: -80, y: 90 },
});
assert.deepEqual(placed.neighbour, { x: 70, y: 90 }, 'Spacing preserves the saved input layout');
assert.deepEqual(scalePositions({}, 2, 'missing'), {});
const updates = [];
let starts = 0,
  stops = 0;
const motion = layout({
  setOptions: (options) => updates.push(options),
  startSimulation: () => starts++,
  stopSimulation: () => stops++,
});
motion.update(true);
motion.update(true);
assert.equal(starts, 1, 'Reading/selection does not restart an unchanged live layout');
motion.update(false);
motion.update(false, 150);
assert.equal(starts, 1, 'Changing spacing while paused does not start motion');
assert.equal(updates.at(-1).physics.enabled, false);
assert.equal(updates.at(-1).physics.stabilization.enabled, false);
assert.ok(stops > 0, 'Leaving an active graph stops simulation');
motion.update(true, 150);
assert.equal(starts, 2, 'Motion can resume with the new spacing');
const fullRepulsion = updates.at(-1).physics.barnesHut.gravitationalConstant;
motion.update(true, 150, true);
assert.equal(starts, 3, 'Changing graph mode applies its forces even when motion is already on');
assert.ok(
  Math.abs(updates.at(-1).physics.barnesHut.gravitationalConstant) > Math.abs(fullRepulsion),
);
motion.update(true, 150, true);
assert.equal(starts, 3, 'An unchanged focused layout is not restarted');
motion.update(true, 150, false);
assert.equal(updates.at(-1).physics.barnesHut.gravitationalConstant, fullRepulsion);
console.log('Live layout pause/resume and unchanged-update checks passed');

const Idle = require('../src/knot/presentation/library_idle_model.js');
assert.equal(route('#view=idle').view, 'idle');
const tourModel = {
  notes: Object.fromEntries(
    ['one', 'two', 'three', 'alone'].map((id) => [
      id,
      {
        id,
        title: id,
        revision: 'revision-' + id,
        body: id,
        author: 'Example author',
        entities: [],
        sources: [],
        navigation: { themes: [], links: [] },
      },
    ]),
  ),
  entities: {},
  claims: {},
  bodies: Object.fromEntries(
    ['one', 'two', 'three', 'alone'].map((id) => [
      id,
      {
        text: '# Heading\n\nA complete paragraph about ' + id + '.',
        html: {},
      },
    ]),
  ),
  relations: [
    { id: '12', from: 'one', to: 'two', kind: 'link', label: 'links to' },
    { id: '23', from: 'two', to: 'three', kind: 'link', label: 'links to' },
    { id: '31', from: 'three', to: 'one', kind: 'link', label: 'links to' },
    { id: 'self', from: 'one', to: 'one', kind: 'link', label: 'links to' },
  ],
};
const tourBytes = JSON.stringify(tourModel),
  tourIndex = create(tourModel);
const tour = Idle.create(tourIndex, { seed: 7 });
assert.equal(tour.cards.size, 4);
assert.equal(tour.cards.get('one').text, 'A complete paragraph about one.');
assert.equal(tour.cards.get('one').revision, 'revision-one');
let step = tour.choose('one');
assert.equal(step.id, 'one');
tour.commit(step);
const seen = new Set(['one']);
for (let i = 0; i < 2; i++) {
  step = tour.choose();
  assert.equal(step.kind, 'follow');
  assert.ok(!seen.has(step.id));
  assert.ok([step.edge.from, step.edge.to].includes(tour.current));
  assert.ok([step.edge.from, step.edge.to].includes(step.id));
  seen.add(step.id);
  tour.commit(step);
}
step = tour.choose();
assert.equal(step.id, 'alone');
assert.equal(step.kind, 'region');
assert.equal(step.edge, null, 'Disconnected changes never invent an edge');
tour.commit(step);
assert.equal(tour.choose().cooldown, true, 'Exhausted recency adds a dwell before repeating');
for (let i = 0; i < 10000; i++) tour.commit(tour.choose());
assert.ok(tour.recent.length <= 12 && tour.chain.length <= tour.cards.size);
assert.equal(JSON.stringify(tourModel), tourBytes, 'Tour never mutates its input');

// A long chain ends at its actual end, even after the recent-history window expires.
const chainIds = Array.from({ length: 20 }, (_, i) => 'chain-' + i);
const chainModel = {
  ...tourModel,
  notes: Object.fromEntries(
    [...chainIds, 'alone'].map((id) => [id, { ...tourModel.notes.one, id, title: id }]),
  ),
  relations: chainIds.slice(1).map((id, i) => ({
    id: 'edge-' + i,
    from: chainIds[i],
    to: id,
    kind: 'link',
    label: 'links to',
  })),
};
for (const cycle of [false, true]) {
  const relations = [...chainModel.relations];
  if (cycle)
    relations.push({
      id: 'closing-edge',
      from: chainIds.at(-1),
      to: chainIds[0],
      kind: 'link',
      label: 'links to',
    });
  const longTour = Idle.create(create({ ...chainModel, relations }));
  longTour.commit(longTour.choose(chainIds[0]));
  for (let i = 1; i < chainIds.length; i++) {
    const next = longTour.choose();
    assert.equal(next.kind, 'follow', 'A connected chain must not restart at an arbitrary limit');
    assert.ok(!longTour.chain.includes(next.id), 'Even a long cycle cannot revisit its start');
    assert.ok([next.edge.from, next.edge.to].includes(longTour.current));
    longTour.commit(next);
  }
  assert.equal(longTour.chain.length, chainIds.length);
  assert.deepEqual(longTour.choose(), { id: 'alone', kind: 'region', edge: null });
}
assert.equal(Idle.create(tourIndex, { filters: { status: 'Accepted' } }).choose(), null);
assert.equal(Idle.create(tourIndex, { filters: { showNotes: false } }).choose('one'), null);
const lone = create({ ...tourModel, notes: { alone: tourModel.notes.alone }, relations: [] });
const single = Idle.create(lone);
single.commit(single.choose());
assert.equal(single.choose(), null, 'One readable record waits without repeated visits');
assert.equal(Idle.excerpt('X'.repeat(1300)), null, 'Long units are not cut mid-qualification');
assert.equal(Idle.excerpt('# Heading\n\nComplete text.', 'Q'.repeat(1200)), null);

const bridgeModel = structuredClone(tourModel);
bridgeModel.bodies.two.text = '';
bridgeModel.relations = bridgeModel.relations.slice(0, 2);
const bridgeTour = Idle.create(create(bridgeModel));
bridgeTour.commit(bridgeTour.choose('one'));
assert.equal(bridgeTour.cards.has('two'), false);
assert.equal(bridgeTour.choose().id, 'two', 'A node without an excerpt remains a real step');
bridgeTour.commit(bridgeTour.choose());
assert.equal(bridgeTour.choose().id, 'three', 'A missing excerpt must not break the chain');

// Different generated topologies exercise invariants without prescribing a route.
for (let seed = 1; seed <= 12; seed++) {
  let random = seed;
  const draw = (n) => (random = (Math.imul(random, 1664525) + 1013904223) >>> 0) % n;
  const ids = Array.from({ length: 24 }, (_, i) => 'generated-' + i);
  const generated = {
    ...tourModel,
    notes: Object.fromEntries(
      ids.map((id, i) => [
        id,
        {
          ...tourModel.notes.one,
          id,
          title: 'Repeated label',
          body: i % 3 ? 'one' : 'empty',
          navigation: { themes: [{ id: i % 2 ? 'left' : 'right' }], links: [] },
        },
      ]),
    ),
    bodies: { ...tourModel.bodies, empty: { text: '' } },
    relations: Array.from({ length: 70 }, (_, i) => ({
      id: 'generated-edge-' + i,
      from: ids[draw(ids.length)],
      to: ids[draw(ids.length)],
      kind: 'link',
      label: 'links to',
    })),
  };
  generated.relations.push({ ...generated.relations[0], id: 'parallel-edge' });
  generated.relations.push({ id: 'missing-endpoint', from: ids[0], to: 'absent', kind: 'link' });
  const original = JSON.stringify(generated),
    index = create(generated);
  const filters = seed % 3 ? { theme: seed % 2 ? 'left' : 'right' } : {};
  const eligible = index.eligible(filters),
    allowed = new Set(eligible.nodes.map((n) => n.id));
  const walk = Idle.create(index, { filters, seed }),
    replay = Idle.create(index, { filters, seed });
  for (let visit = 0; visit < 500; visit++) {
    const next = walk.choose('absent');
    assert.deepEqual(next, replay.choose('absent'), 'A seeded walk is reproducible');
    if (!allowed.size) {
      assert.equal(next, null);
      break;
    }
    assert.ok(allowed.has(next.id), 'Automatic selection never revives a filtered-out root');
    const continuations = (eligible.adjacent.get(walk.current) || []).filter(
      (e) => !walk.chain.includes(e.from === walk.current ? e.to : e.from),
    );
    if (walk.current && continuations.length) assert.equal(next.kind, 'follow');
    if (next.kind === 'follow') {
      assert.ok(!walk.chain.includes(next.id), 'No cycle repeats within a chain');
      assert.ok(
        eligible.connections.some(
          (e) =>
            e.id === next.edge.id &&
            ((e.from === walk.current && e.to === next.id) ||
              (e.to === walk.current && e.from === next.id)),
        ),
        'Each step is a real eligible adjacent edge, preserving its direction',
      );
    } else assert.equal(next.edge, null, 'A restart has no invented connecting edge');
    walk.commit(next);
    replay.commit(next);
    assert.ok(walk.recent.length <= 12 && walk.chain.length <= allowed.size);
  }
  assert.equal(JSON.stringify(generated), original, 'Exploration cannot mutate its source model');
}

const sourced = structuredClone(tourModel);
sourced.entities = Object.fromEntries(
  ['subject', 'object', 'unassociated'].map((id) => [
    id,
    { id, title: 'Same title', types: ['Concept'], themes: [] },
  ]),
);
sourced.notes.one.method = 'synthesis';
sourced.notes.one.qualification = 'This is a proposal, not a measured outcome.';
sourced.notes.one.entities = ['subject'];
sourced.relations.push(
  { id: 'about', from: 'one', to: 'subject', kind: 'association', label: 'about' },
  {
    id: 'claim',
    from: 'subject',
    to: 'object',
    kind: 'claim',
    status: 'Accepted',
    origin: 'Inferred',
    label: 'relatedTo',
    themes: [],
  },
);
sourced.claims.claim = {
  id: 'claim',
  subject: { id: 'subject', label: 'Subject' },
  object: { id: 'object', label: 'Object' },
  predicate: 'urn:example:relatedTo',
  status: 'Accepted',
  origin: 'Inferred',
  themes: [],
  evidence: [{ revision: 'source-revision', quote: 'A reported connection with qualifications.' }],
  evidence_accounts: [],
};
sourced.sources = {
  'source-revision': { title: 'Original account', author: 'Source author', note: 'one' },
};
const sourcedTour = Idle.create(create(sourced), { filters: { status: 'Accepted' } });
assert.equal(
  sourcedTour.cards.get('subject').curated,
  true,
  'Curated association is reading context even when navigation is hidden',
);
assert.equal(sourcedTour.cards.get('subject').qualification, sourced.notes.one.qualification);
assert.equal(sourcedTour.cards.get('object').label, 'Claim evidence · Accepted · Inferred');
assert.equal(sourcedTour.cards.has('unassociated'), false, 'Equal labels never attach a summary');
sourcedTour.commit(sourcedTour.choose('object'));
const reverse = sourcedTour.choose();
assert.equal(reverse.id, 'subject');
assert.equal(reverse.edge.from, 'subject');
assert.equal(
  reverse.edge.to,
  'object',
  'Reverse traversal preserves the actual predicate direction',
);
assert.equal(
  Idle.create(create(sourced), { filters: { origin: 'Explicit', showNotes: false } }).choose(),
  null,
);
const preferred = structuredClone(sourced);
preferred.claims.claim.origin = 'Explicit';
preferred.relations.find((e) => e.id === 'claim').origin = 'Explicit';
const priorityTour = Idle.create(create(preferred));
priorityTour.commit(priorityTour.choose('subject'));
assert.equal(
  priorityTour.choose().id,
  'object',
  'An explicit accepted connection precedes an association',
);
assert.equal(
  priorityTour.choose(undefined, new Set(['one'])).id,
  'one',
  'A visible real connection can be followed without replacing the scene',
);
assert.equal(
  priorityTour.choose(undefined, new Set()).id,
  'object',
  'Missing visible candidates still allow a real adjacent step',
);

const absentSource = structuredClone(sourced);
absentSource.sources = {};
assert.equal(
  Idle.create(create(absentSource)).cards.has('object'),
  false,
  'A quote without its included source must not become reading material',
);
const qualified = structuredClone(sourced);
qualified.claims.claim.evidence_accounts = [
  { qualification: 'An attributed account, not independent corroboration.' },
];
const qualifiedCard = Idle.create(create(qualified)).cards.get('object');
assert.equal(qualifiedCard.text, sourced.claims.claim.evidence[0].quote);
assert.ok(qualifiedCard.qualification.includes('not independent corroboration'));
qualified.claims.claim.evidence_accounts[0].qualification = 'Q'.repeat(1250);
assert.equal(
  Idle.create(create(qualified)).cards.has('object'),
  false,
  'An oversized qualification is never silently dropped to fit an excerpt',
);

const contextual = structuredClone(sourced);
contextual.notes.one.kind = 'Definition';
contextual.notes.one.navigation.themes = [{ id: 'other-topic' }];
contextual.claims.claim.kind = 'Idea';
contextual.claims.claim.themes = [{ id: 'selected-topic' }];
Object.assign(
  contextual.relations.find((e) => e.id === 'claim'),
  {
    knowledge_kind: 'Idea',
    themes: [{ id: 'selected-topic' }],
  },
);
delete contextual.sources['source-revision'].author;
const scopedCard = Idle.create(create(contextual), {
  filters: { kind: 'Idea', theme: 'selected-topic' },
}).cards.get('subject');
assert.equal(
  scopedCard.curated,
  false,
  'A note outside the content filters is not attached as a summary',
);
assert.equal(scopedCard.text, sourced.claims.claim.evidence[0].quote);
assert.equal(scopedCard.author, 'Unknown', 'Missing authorship is never attributed to the owner');
const pair = Idle.create(
  create({
    ...tourModel,
    notes: { one: tourModel.notes.one, two: tourModel.notes.two },
    relations: [tourModel.relations[0]],
  }),
);
pair.commit(pair.choose('one'));
pair.commit(pair.choose());
assert.equal(pair.choose().cooldown, true);
assert.equal(
  pair.choose().kind,
  'restart',
  'Two stops restart without inventing a new relationship',
);
pair.commit(pair.choose());
assert.equal(
  pair.choose().kind,
  'follow',
  'Session recency must not cut short a newly started chain',
);

const Scene = require('../src/knot/presentation/library_idle_scene.js');
const map = Scene.geography();
for (let i = 0; i < 250; i++) {
  const ids = i ? ['map-' + (i - 1), 'map-' + i] : ['map-0'];
  map.place(
    { nodes: ids.map((id) => ({ id })), edges: i ? [{ from: ids[0], to: ids[1] }] : [] },
    ids[0],
  );
}
const originalPosition = { ...map.positions.get('map-0') };
map.place({ nodes: [{ id: 'map-0' }], edges: [] }, 'map-0');
assert.deepEqual(
  map.positions.get('map-0'),
  originalPosition,
  'Revisiting after 200 nodes preserves geography',
);
assert.equal(new Set([...map.positions.values()].map((p) => `${p.x},${p.y}`)).size, 250);
map.clear();
assert.equal(map.positions.size, 0);

// Pause preserves the rendered progress as well as the remaining phase time.
let now = 0,
  serial = 0;
const timers = new Map(),
  frames = new Map(),
  emitted = [];
const clock = {
  now: () => now,
  frame: (fn) => {
    frames.set(++serial, fn);
    return serial;
  },
  cancelFrame: (id) => frames.delete(id),
  wait: (fn, ms) => {
    timers.set(++serial, { fn, ms });
    return serial;
  },
  cancelWait: (id) => timers.delete(id),
};
const playback = Idle.playback({ clock });
playback.play(
  1000,
  (p) => emitted.push(p),
  () => emitted.push('done'),
);
playback.start();
const stale = [...frames.values()][0];
now = 50;
playback.pause();
assert.equal(emitted.at(-1), 0.05);
stale();
assert.equal(emitted.at(-1), 0.05, 'Cancelled frames cannot alter the paused display');
now = 5000;
playback.start();
assert.equal(emitted.at(-1), 0.05, 'Resume does not rewind or jump');
playback.hidden(true);
assert.equal(frames.size, 0);
now = 9000;
playback.hidden(false);
assert.equal(frames.size, 1);
playback.pause();
playback.hidden(true);
playback.hidden(false);
assert.equal(frames.size, 0, 'Visibility never overrides explicit pause');
playback.stop();
playback.play(
  10000,
  () => {},
  () => emitted.push('read'),
  false,
);
playback.start();
now += 4000;
playback.pause();
playback.start();
assert.equal([...timers.values()][0].ms, 6000, 'Reading resumes for its remaining duration');
playback.stop();
function fireNext(ms) {
  assert.equal(frames.size + timers.size, 1, 'Only one phase callback may be pending');
  const queue = frames.size ? frames : timers;
  const [id, pending] = [...queue][0];
  queue.delete(id);
  now += ms;
  (typeof pending === 'function' ? pending : pending.fn)();
}
let completed = 0,
  position = 0,
  readingFinished = false;
playback.play(
  100,
  (p) => {
    position = p * 100;
  },
  () => {
    completed++;
    playback.play(
      1000,
      () => {},
      () => {
        readingFinished = true;
        playback.stop();
      },
      false,
    );
  },
);
playback.start();
playback.start();
const oldPhaseCallback = [...frames.values()][0];
fireNext(50);
assert.equal(position, 50);
fireNext(50);
assert.equal(position, 100);
assert.equal(completed, 1);
oldPhaseCallback();
assert.equal(completed, 1, 'A late animation callback cannot complete the new phase');
fireNext(1000);
assert.equal(readingFinished, true);
assert.equal(playback.pending, false);

let replaced = false;
playback.play(
  100,
  () => {},
  () => {
    replaced = true;
  },
);
playback.start();
const superseded = [...frames.values()][0];
playback.play(
  1000,
  () => {},
  () => playback.stop(),
  false,
);
superseded();
assert.equal(replaced, false, 'Changing settings cancels the old arrival');
const stopped = [...timers.values()][0].fn;
playback.stop();
stopped();
assert.equal(frames.size + timers.size, 0, 'Exit leaves no chain of callbacks behind');

let failedMessage = '',
  failedArrival = false;
const failing = Idle.playback({
  clock,
  failed: (e) => {
    failedMessage = e.message;
  },
});
failing.play(
  100,
  (p) => {
    if (p > 0) throw new Error('Synthetic render failure');
  },
  () => {
    failedArrival = true;
  },
);
failing.start();
fireNext(50);
assert.equal(failedMessage, 'Synthetic render failure');
assert.equal(failedArrival, false, 'Failed rendering must not commit an arrival');
assert.equal(failing.running, false);
assert.equal(
  frames.size + timers.size,
  0,
  'Rendering failures pause instead of retrying indefinitely',
);
failing.stop();

playback.play(
  1000,
  (p) => {
    if (p) now += 30;
  },
  () => {},
);
playback.start();
fireNext(50);
fireNext(20);
assert.equal(playback.progress, 0.1, 'Phase timing includes time spent drawing');
playback.stop();
playback.play(
  1000,
  (p) => {
    position = p * 100;
  },
  () => {
    completed++;
  },
);
playback.start();
fireNext(60 * 60 * 1000);
assert.equal(position, 10, 'A delayed frame cannot teleport through an entire journey');
playback.pause();
const completionsBeforeSnap = completed;
playback.snap();
assert.equal(position, 100);
assert.equal(completed, completionsBeforeSnap + 1);
assert.equal(playback.running, false, 'Reduced motion cannot resume an explicit pause');
playback.stop();
let instantComplete = 0;
playback.play(
  0,
  (p) => {
    position = p * 100;
  },
  () => {
    instantComplete++;
  },
);
assert.equal(position, 100);
assert.equal(instantComplete, 1);
assert.equal(
  frames.size + timers.size,
  0,
  'A reduced-motion phase settles without scheduling animation',
);
console.log('Idle traversal, geography, content and playback checks passed');
