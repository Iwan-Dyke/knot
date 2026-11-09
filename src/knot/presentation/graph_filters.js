/* The exported snapshot stays immutable; filters only change visibility. */
function entitySearchText(node) {
  return [node.label, node.id, ...(node.aliases || []), ...(node.entityTypes || [])]
    .join(' ').toLocaleLowerCase();
}

function matchesSearch(text, query) {
  return query.trim().toLocaleLowerCase().split(/\s+/).every(word => text.includes(word));
}

function initialFilters(nodes, edges, attributes = []) {
  const claims = [...edges.filter(e => !e.organisation && !e.navigation), ...attributes];
  const context = [...claims, ...edges.filter(e => e.navigation), ...nodes.filter(n => n.role === 'note')];
  const statuses = new Set(claims.map(e => e.status));
  // Keep the initial mixed view distinct from an explicit accepted-only selection.
  if (nodes.some(n => n.role === 'note') && statuses.has('Accepted')) statuses.add('Unreviewed');
  return {
    themes: new Set(context.flatMap(e => e.themeIds?.length ? e.themeIds : ['__unthemed__'])),
    types: new Set(nodes.filter(n => n.role !== 'theme').flatMap(n => n.entityTypes || ['Entity'])),
    statuses,
    origins: new Set(claims.map(e => e.origin)),
    hiddenEntities: new Set(), kind: '', focus: null, focusHops: 1, showThemes: true, showNotes: true,
  };
}

function filterGraph(nodes, edges, filters, attributes = []) {
  const eligible = new Set(nodes.filter(n => n.role !== 'theme'
    && !filters.hiddenEntities.has(n.id)
    && (n.entityTypes || ['Entity']).some(t => filters.types.has(t))).map(n => n.id));
  const matches = e => eligible.has(e.from)
    && filters.statuses.has(e.status) && filters.origins.has(e.origin)
    && (!filters.kind || e.kind === filters.kind)
    && (e.themeIds?.length ? e.themeIds : ['__unthemed__']).some(t => filters.themes.has(t));
  let claims = edges.filter(e => !e.organisation && !e.navigation && eligible.has(e.to) && matches(e));
  let shownAttributes = attributes.filter(matches);
  const acceptedOnly = filters.statuses.size === 1 && filters.statuses.has('Accepted');
  const noteMatches = item => (!filters.kind || item.kind === filters.kind)
    && (item.themeIds?.length ? item.themeIds : ['__unthemed__']).some(t => filters.themes.has(t));
  let navigation = filters.showNotes && !acceptedOnly ? edges.filter(e => e.navigation
    && eligible.has(e.from) && eligible.has(e.to) && noteMatches(e)) : [];
  let reached = null, canExpand = false;
  if (filters.focus) {
    reached = new Set([filters.focus]);
    const connections = [...claims, ...navigation], selected = new Set();
    // Expand only through filtered relationship edges. Theme hubs and literal
    // attributes provide context, never shortcuts between unrelated subjects.
    for (let hop = 0; hop < (filters.focusHops ?? 1); hop++) {
      const next = connections.filter(e => !selected.has(e.id)
        && (reached.has(e.from) || reached.has(e.to)));
      if (!next.length) break;
      next.forEach(e => {selected.add(e.id); reached.add(e.from); reached.add(e.to);});
    }
    canExpand = connections.some(e => !selected.has(e.id)
      && (reached.has(e.from) || reached.has(e.to)));
    claims = claims.filter(e => selected.has(e.id));
    navigation = navigation.filter(e => selected.has(e.id));
    shownAttributes = shownAttributes.filter(e => reached.has(e.from));
  }
  const visible = new Set([...claims.flatMap(e => [e.from, e.to]), ...shownAttributes.map(e => e.from)]);
  navigation.forEach(e => {visible.add(e.from); visible.add(e.to);});
  if (filters.showNotes && !acceptedOnly) nodes.filter(n => n.role === 'note' && eligible.has(n.id)
    && noteMatches(n) && (!reached || reached.has(n.id))).forEach(n => visible.add(n.id));
  const claimIds = new Set([...claims, ...shownAttributes].map(e => e.id));
  nodes.filter(n => n.role === 'note' && visible.has(n.id)).forEach(n => claimIds.add(n.id));
  const themeIds = new Map(nodes.filter(n => n.role === 'theme').map(n => [n.id, n.themeId]));
  const themeLinks = filters.showThemes && !acceptedOnly ? edges.filter(e => e.organisation
    && filters.themes.has(themeIds.get(e.from)) && visible.has(e.to)
    && Object.keys(e.memberships || {}).some(id => claimIds.has(id))) : [];
  themeLinks.forEach(e => visible.add(e.from));
  return {nodes: nodes.filter(n => visible.has(n.id)), claims, navigation, attributes:shownAttributes, themeLinks, canExpand};
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {filterGraph, initialFilters, entitySearchText, matchesSearch};
}
