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
