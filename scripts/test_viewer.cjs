/* Pure filter semantics; no browser or npm packages required. */
const assert = require('node:assert/strict');
const { filterGraph, initialFilters, entitySearchText, matchesSearch } = require('../src/knot/presentation/viewer.js');

const nodes = [
  {id:'a', label:'Alex', entityTypes:['Person']},
  {id:'b', label:'Shared name', entityTypes:['Project']},
  {id:'c', label:'Shared name', entityTypes:['Project', 'Concept']},
  {id:'d', label:'Untyped', entityTypes:['Entity']},
  {id:'theme:t', role:'theme', themeId:'t'},
  {id:'theme:u', role:'theme', themeId:'u'},
];
const claim = (id, from, to, themes, status='Accepted', origin='Explicit') =>
  ({id, from, to, themeIds:themes, status, origin, kind:'Observation'});
const theme = (id, from, to, support) =>
  ({id, from, to, organisation:true, memberships:support});
const edges = [
  claim('ab','a','b',['t']),
  claim('bc','b','c',['u'],'Unreviewed','Inferred'),
  claim('ac','a','c',[]),
  {...claim('cd','c','d',['t','u']), kind:'Question'},
  theme('ta','theme:t','a',{ab:'Accepted'}),
  theme('tb','theme:t','b',{ab:'Unreviewed'}),
  theme('ub','theme:u','b',{bc:'Accepted'}),
  theme('uc','theme:u','c',{bc:'Accepted',cd:'Unreviewed'}),
  theme('tc','theme:t','c',{cd:'Unreviewed'}),
  theme('td','theme:t','d',{cd:'Unreviewed'}),
];
const ids = rows => rows.map(r=>r.id).sort();
const run = changes => filterGraph(nodes, edges, {...initialFilters(nodes, edges), ...changes});
const original = JSON.stringify({nodes,edges});
assert.deepEqual(ids(run({}).claims), ['ab','ac','bc','cd']);
// Membership belongs to each claim, not every claim incident to a themed entity.
assert.deepEqual(ids(run({themes:new Set(['t'])}).claims), ['ab','cd']);
assert.deepEqual(ids(run({themes:new Set(['u'])}).claims), ['bc','cd']);
assert.deepEqual(ids(run({themes:new Set(['__unthemed__'])}).claims), ['ac']);
assert.deepEqual(run({themes:new Set()}).nodes, []);
assert.deepEqual(ids(run({hiddenEntities:new Set(['c'])}).claims), ['ab']);
assert.deepEqual(ids(run({hiddenEntities:new Set(['c'])}).themeLinks), ['ta','tb']);
assert.deepEqual(ids(run({types:new Set(['Project','Concept'])}).claims), ['bc']);
assert.deepEqual(ids(run({types:new Set(['Person','Concept'])}).claims), ['ac']);
assert.deepEqual(run({types:new Set()}).nodes, []);
assert.deepEqual(ids(run({focus:'b'}).claims), ['ab','bc']);
assert.deepEqual(ids(run({focus:'b',themes:new Set(['t'])}).claims), ['ab']);
assert.deepEqual(run({focus:'b',hiddenEntities:new Set(['b'])}).nodes, []);
assert.deepEqual(ids(run({statuses:new Set(['Accepted'])}).claims), ['ab','ac','cd']);
// Claim acceptance never promotes theme navigation into accepted evidence.
assert.deepEqual(run({statuses:new Set(['Accepted'])}).themeLinks, []);
assert.deepEqual(ids(run({origins:new Set(['Explicit'])}).claims), ['ab','ac','cd']);
assert.deepEqual(ids(run({kind:'Question'}).claims), ['cd']);
assert.deepEqual(run({statuses:new Set()}).nodes, []);
assert.deepEqual(run({showThemes:false}).themeLinks, []);
assert.equal(run({}).nodes.filter(n=>n.label==='Shared name').length, 2);
assert.equal(JSON.stringify({nodes,edges}), original, 'Filtering must not mutate source data');
const attribute = {...claim('count','b',null,['t']), detail:{literal_value:'18'}};
const attrFilters = initialFilters(nodes, [], [attribute]);
const attrView = changes => filterGraph(nodes, [], {...attrFilters,...changes}, [attribute]);
assert.deepEqual(ids(attrView({}).nodes), ['b'], 'A subject with only attributes is still visible');
assert.deepEqual(ids(attrView({}).attributes), ['count']);
assert.deepEqual(attrView({statuses:new Set(['Unreviewed'])}).nodes, []);
assert.deepEqual(attrView({hiddenEntities:new Set(['b'])}).attributes, []);
assert.deepEqual(attrView({themes:new Set(['u'])}).attributes, []);
assert.deepEqual(attrView({focus:'a'}).attributes, []);
assert.deepEqual(attrView({types:new Set(['Person'])}).attributes, []);
assert.match(entitySearchText({label:'Current name',id:'urn:stable',aliases:['Historic spelling']}), /historic spelling/);
console.log('Viewer filter semantics passed');
assert.equal(matchesSearch('AI Coding and Development'.toLocaleLowerCase(), 'AI development'), true);
assert.equal(matchesSearch('AI Coding and Development'.toLocaleLowerCase(), ' development   AI '), true);
assert.equal(matchesSearch('AI Coding and Development'.toLocaleLowerCase(), 'AI recruitment'), false);
assert.equal(matchesSearch('AI Coding and Development'.toLocaleLowerCase(), ''), true);

const noteNodes = [
  {id:'n1', label:'AI reflection', role:'note', entityTypes:['Note'], kind:'Thought', themeIds:['t']},
  {id:'n2', label:'Foundations', role:'note', entityTypes:['Note'], kind:'Question', themeIds:[]},
  {id:'alone', label:'Unlinked', role:'note', entityTypes:['Note'], kind:'Thought', themeIds:[]},
];
const navigation = [
  {id:'link', from:'n1', to:'n2', navigation:true, kind:'Thought', themeIds:['t']},
  {id:'about', from:'n2', to:'b', navigation:true, kind:'Question', themeIds:[]},
];
const allNodes = [...nodes, ...noteNodes], allEdges = [...edges, ...navigation];
const noteView = changes => filterGraph(allNodes, allEdges,
  {...initialFilters(allNodes, allEdges), ...changes});
assert.deepEqual(ids(noteView({}).navigation), ['about','link']);
assert.ok(ids(noteView({}).nodes).includes('alone'), 'Unlinked notes must be visible');
assert.deepEqual(ids(noteView({focus:'b'}).navigation), ['about']);
assert.deepEqual(ids(noteView({focus:'n2'}).navigation), ['about','link']);
assert.deepEqual(ids(noteView({themes:new Set(['t'])}).navigation), ['link']);
assert.deepEqual(ids(noteView({kind:'Thought'}).navigation), ['link']);
assert.deepEqual(noteView({statuses:new Set(['Accepted'])}).navigation, []);
assert.ok(!ids(noteView({statuses:new Set(['Accepted'])}).nodes).includes('alone'));
assert.deepEqual(noteView({showNotes:false}).navigation, []);
assert.ok(!ids(noteView({showNotes:false}).nodes).includes('alone'));
assert.deepEqual(noteView({hiddenEntities:new Set(['n2'])}).navigation, []);
const noteOnly = filterGraph(noteNodes, [], initialFilters(noteNodes, []));
assert.deepEqual(ids(noteOnly.nodes), ['alone','n1','n2']);

// Hiding associated notes preserves notes that participate in claims.
const endpointEdges = [...allEdges,
  {...claim('documentation', 'b', 'n1', []), label:'documentedIn'},
  claim('note-claim', 'n2', 'c', [], 'Unreviewed'),
];
const endpointAttributes = [attribute, {...claim('note-value', 'n1', null, [])}];
const endpointView = changes => filterGraph(allNodes, endpointEdges,
  {...initialFilters(allNodes, endpointEdges, endpointAttributes), ...changes}, endpointAttributes);
const hiddenNotes = endpointView({showNotes:false});
assert.ok(hiddenNotes.nodes.some(n => n.id === 'n1'));
assert.ok(hiddenNotes.nodes.some(n => n.id === 'n2'));
assert.deepEqual(ids(hiddenNotes.claims), ['ab','ac','bc','cd','documentation','note-claim']);
assert.deepEqual(ids(hiddenNotes.attributes), ['count','note-value']);
assert.deepEqual(hiddenNotes.navigation, []);
assert.ok(endpointView({showNotes:true}).nodes.some(n => n.id === 'n1'));
assert.ok(endpointView({showNotes:true}).claims.some(e => e.id === 'documentation'));
assert.ok(endpointView({focus:'b', focusHops:3, showNotes:false}).nodes.some(n => n.id === 'n1'));
// Associated-note visibility does not change claim visibility or review state.
assert.ok(endpointView({statuses:new Set(['Accepted'])}).claims.some(e => e.id === 'documentation'));
assert.ok(endpointView({statuses:new Set(['Accepted']), showNotes:false}).claims.some(e => e.id === 'documentation'));
assert.equal(endpointEdges.find(e => e.id === 'documentation').status, 'Accepted');

// Each click expands from every visible subject, in both directions. Theme
// hubs must not create shortcuts into otherwise unrelated parts of the graph.
const oneHop = noteView({focus:'n1', focusHops:1});
assert.deepEqual(ids(oneHop.nodes), ['n1','n2']);
assert.equal(oneHop.canExpand, true);
const twoHops = noteView({focus:'n1', focusHops:2});
assert.deepEqual(ids(twoHops.nodes), ['b','n1','n2']);
assert.deepEqual(ids(twoHops.navigation), ['about','link']);
assert.deepEqual(ids(twoHops.claims), []);
const threeHops = noteView({focus:'n1', focusHops:3});
assert.deepEqual(ids(threeHops.claims), ['ab','bc']);
assert.ok(!ids(threeHops.nodes).includes('d'));
assert.ok(!ids(threeHops.nodes).includes('alone'));
assert.deepEqual(noteView({focus:'n1', focusHops:5, hiddenEntities:new Set(['n2'])}).navigation, []);
assert.deepEqual(ids(noteView({focus:'n1', focusHops:5, themes:new Set(['t'])}).navigation), ['link']);
assert.equal(noteView({focus:'n1', focusHops:5, themes:new Set(['t'])}).canExpand, false);
assert.deepEqual(noteView({focus:'n1', focusHops:5, statuses:new Set(['Accepted'])}).navigation, []);
assert.equal(noteView({focus:'alone', focusHops:1}).canExpand, false);
assert.equal(noteView({focus:'n1', focusHops:10}).canExpand, false);
assert.deepEqual(ids(noteView({focus:'n1', focusHops:1}).nodes), ids(oneHop.nodes));
