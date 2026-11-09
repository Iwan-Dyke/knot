/* Canonical read model and bounded exploration; no DOM or storage dependencies. */
const LibraryModel = (() => {
  const graph =
    typeof module !== 'undefined' && module.exports
      ? require('./graph_filters.js')
      : { filterGraph, initialFilters, entitySearchText, matchesSearch };
  function create(model) {
    const records = [
      ...Object.values(model.notes).map((n) => ({
        ...n,
        role: 'note',
        label: n.title,
        entityTypes: ['Note'],
      })),
      ...Object.values(model.entities).map((n) => ({
        ...n,
        role: 'entity',
        label: n.title,
        entityTypes: n.types,
      })),
    ].sort((a, b) => a.title.localeCompare(b.title) || a.id.localeCompare(b.id));
    const byId = new Map(records.map((n) => [n.id, n]));
    const nodes = records.map((n) => ({
      ...n,
      kind: n.kind || 'Unspecified',
      themeIds: (n.navigation?.themes || n.themes || []).map((t) => t.id),
    }));
    const edges = model.relations
      .filter((e) => byId.has(e.from) && byId.has(e.to))
      .map((e) => ({
        ...e,
        navigation: e.kind !== 'claim',
        kind: e.kind === 'claim' ? e.knowledge_kind : byId.get(e.from)?.kind || 'Unspecified',
        themeIds: (e.themes || byId.get(e.from)?.navigation?.themes || []).map((t) => t.id),
      }));
    const attributes = Object.values(model.claims)
      .filter((c) => c.object.literal)
      .map((c) => ({
        id: c.id,
        from: c.subject.id,
        status: c.status,
        origin: c.origin,
        kind: c.kind,
        themeIds: c.themes.map((t) => t.id),
      }));
    const incoming = new Map(),
      outgoing = new Map(),
      associated = new Map(),
      claimIndex = new Map();
    const add = (map, key, value) => {
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(value);
    };
    for (const e of model.relations) {
      add(outgoing, e.from, e);
      add(incoming, e.to, e);
      if (e.kind === 'association') add(associated, e.to, e.from);
    }
    for (const c of Object.values(model.claims)) {
      add(claimIndex, c.subject.id, c);
      if (!c.object.literal && c.object.id !== c.subject.id) add(claimIndex, c.object.id, c);
    }
    const metadata = new Map(records.map((n) => [n.id, graph.entitySearchText(n)]));
    const bodyText = new Map(
      Object.entries(model.bodies).map(([id, b]) => [id, b.text.toLocaleLowerCase()]),
    );
    const memberships = new Map(
      records.map((n) => [
        n.id,
        new Set((n.navigation?.themes || n.themes || []).map((t) => t.id)),
      ]),
    );
    for (const n of Object.values(model.notes))
      for (const eid of n.entities) {
        if (model.entities[eid])
          for (const t of n.navigation.themes) memberships.get(eid)?.add(t.id);
      }
    const search = (query = '', { role = 'all', kind = '', collection = { type: 'all' } } = {}) => {
      const matched = [],
        words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      for (const n of records) {
        if ((role !== 'all' && n.role !== role) || (kind && (n.kind || 'Unspecified') !== kind))
          continue;
        if (collection.type === 'notes' && n.role !== 'note') continue;
        if (collection.type === 'entities' && n.role !== 'entity') continue;
        if (collection.type === 'theme' && !memberships.get(n.id)?.has(collection.id)) continue;
        if (collection.entityType && !n.entityTypes.includes(collection.entityType)) continue;
        if (collection.type === 'type' && !n.entityTypes.includes(collection.id)) continue;
        if (
          collection.type === 'unclassified' &&
          (n.role !== 'note' || memberships.get(n.id)?.size)
        )
          continue;
        if (
          collection.type === 'standalone' &&
          (n.role !== 'note' || incoming.has(n.id) || outgoing.has(n.id) || claimIndex.has(n.id))
        )
          continue;
        if (
          collection.type === 'associated' &&
          !(associated.get(collection.id) || []).includes(n.id)
        )
          continue;
        if (['created', 'modified'].includes(collection.type) && n.role !== 'note') continue;
        const meta = metadata.get(n.id),
          body = bodyText.get(n.body) || '';
        if (words.every((w) => meta.includes(w) || body.includes(w)))
          matched.push({
            record: n,
            rank: words.every((w) => meta.includes(w)) ? 0 : 1,
            excerpt:
              words.length && words.some((w) => body.includes(w))
                ? model.bodies[n.body].text.slice(
                    Math.max(0, body.indexOf(words.find((w) => body.includes(w))) - 35),
                    body.indexOf(words.find((w) => body.includes(w))) + 130,
                  )
                : '',
          });
      }
      matched.sort(
        (a, b) =>
          a.rank - b.rank ||
          (['created', 'modified'].includes(collection.type)
            ? (b.record[collection.type + '_at'] || '').localeCompare(
                a.record[collection.type + '_at'] || '',
              )
            : 0),
      );
      return matched;
    };
    let cacheKey = '',
      cached;
    function eligible(selection = {}) {
      const key = JSON.stringify(selection);
      if (cached && key === cacheKey) return cached;
      const filters = graph.initialFilters(nodes, edges, attributes);
      if (selection.status && selection.status !== 'all')
        filters.statuses = new Set([selection.status]);
      if (selection.origin && selection.origin !== 'all')
        filters.origins = new Set([selection.origin]);
      if (selection.theme) filters.themes = new Set([selection.theme]);
      if (selection.type) filters.types = new Set([selection.type]);
      filters.kind = selection.kind || '';
      filters.showThemes = false;
      filters.showNotes = selection.showNotes !== false;
      const filtered = graph.filterGraph(nodes, edges, filters, attributes);
      const connections = [...filtered.claims, ...filtered.navigation].sort((a, b) =>
        a.id.localeCompare(b.id),
      );
      const adjacent = new Map();
      for (const e of connections) {
        add(adjacent, e.from, e);
        if (e.to !== e.from) add(adjacent, e.to, e);
      }
      cached = { connections, adjacent, attributes: filtered.attributes, nodes: filtered.nodes };
      cacheKey = key;
      return cached;
    }
    function neighbourhood(state, limits = { nodes: 100, edges: 300 }) {
      const filtered = eligible(state.filters);
      const { connections, adjacent } = filtered;
      if (state.full)
        return {
          nodes:
            byId.has(state.seed) && !filtered.nodes.some((n) => n.id === state.seed)
              ? [byId.get(state.seed), ...filtered.nodes]
              : filtered.nodes,
          edges: connections,
          omitted: 0,
          hiddenEdges: 0,
          tree: new Set(),
          depth: new Map(),
        };
      if (!byId.has(state.seed))
        return {
          nodes: [],
          edges: [],
          omitted: 0,
          hiddenEdges: 0,
          tree: new Set(),
          depth: new Map(),
        };
      const reached = new Map([[state.seed, 0]]),
        queue = [state.seed],
        tree = new Set(),
        expanded = new Set(state.expanded || []),
        collapsed = new Set(state.collapsed || []);
      const omitted = new Set(),
        priorities = new Set(state.preferred || []);
      for (let i = 0; i < queue.length; i++) {
        const id = queue[i],
          depth = reached.get(id);
        if (collapsed.has(id) || !(depth < (state.hops ?? 1) || expanded.has(id))) continue;
        const neighbours = [...(adjacent.get(id) || [])].sort((a, b) => {
          const an = a.from === id ? a.to : a.from,
            bn = b.from === id ? b.to : b.from;
          return (
            Number(priorities.has(bn)) - Number(priorities.has(an)) ||
            an.localeCompare(bn) ||
            a.id.localeCompare(b.id)
          );
        });
        for (const e of neighbours) {
          const other = e.from === id ? e.to : e.from;
          if (reached.has(other)) continue;
          if (reached.size >= limits.nodes) {
            omitted.add(other);
            continue;
          }
          reached.set(other, depth + 1);
          queue.push(other);
          tree.add(e.id);
        }
      }
      const all = connections.filter((e) => reached.has(e.from) && reached.has(e.to));
      all.sort(
        (a, b) => Number(tree.has(b.id)) - Number(tree.has(a.id)) || a.id.localeCompare(b.id),
      );
      return {
        nodes: [...reached.keys()].map((id) => byId.get(id)),
        edges: all.slice(0, limits.edges),
        omitted: omitted.size,
        hiddenEdges: Math.max(0, all.length - limits.edges),
        tree,
        depth: reached,
      };
    }
    return {
      model,
      records,
      byId,
      nodes,
      edges,
      search,
      eligible,
      neighbourhood,
      incoming,
      outgoing,
      associated,
      claimIndex,
      memberships,
    };
  }
  function route(hash, initialRecord = null) {
    const params = new URLSearchParams(hash.replace(/^#/, ''));
    return {
      view: params.get('view') === 'library' ? 'library' : 'graph',
      id: hash ? params.get('id') : initialRecord,
      revision: params.get('revision'),
    };
  }
  function hash(selection) {
    const params = new URLSearchParams({ view: selection.view });
    if (selection.id) params.set('id', selection.id);
    if (selection.revision) params.set('revision', selection.revision);
    return '#' + params;
  }
  return { create, route, hash };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = LibraryModel;
