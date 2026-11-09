/* Shared filter semantics are also used by the Library graph. */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = require('./graph_filters.js');
}

if (typeof document !== 'undefined') (() => {
  const sourceNodes = nodes.get(), sourceEdges = edges.get();
  const sourceAttributes = sourceNodes.flatMap(n => (n.attributes || []).map(a => ({...a, attribute:true})));
  const sourceClaims = [...sourceEdges.filter(e => !e.organisation && !e.navigation), ...sourceAttributes];
  const noteData = JSON.parse(document.getElementById('curated-notes')?.textContent
    || '{"notes":{},"entities":{}}');
  const byNode = new Map(sourceNodes.map(n => [n.id, n]));
  const byEdge = new Map([...sourceEdges, ...sourceAttributes].map(e => [e.id, e]));
  const entities = sourceNodes.filter(n => n.role !== 'theme')
    .sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id));
  const searchText = new Map(entities.map(n => [n.id, entitySearchText(n)]));
  const entityRows = new Map();
  let listedEntities = [];
  const themeEdges = sourceEdges.filter(e => e.organisation);
  let detailedThemes = true, themeFrame;
  let filters = initialFilters(sourceNodes, sourceEdges, sourceAttributes);
  let visible, visibleClaimIds, selection = null, arranging = true;
  let layoutTimer, fitAfterLayout = true;
  const $ = id => document.getElementById(id);
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const action = (text, callback) => {
    const button = element('button', text);
    button.type = 'button'; button.addEventListener('click', callback);
    return button;
  };
  const field = (parent, title, text) => {
    parent.append(element('h4', title), element('div', text ?? 'Not recorded', 'evidence-text'));
  };
  const checkboxes = [];
  const facet = (id, key, labels = new Map()) => {
    const container = $(id), values = [...filters[key]].sort((a, b) =>
      (labels.get(a) || a).localeCompare(labels.get(b) || b));
    const buttons = element('div', undefined, 'button-row');
    for (const [title, enabled] of [['All', true], ['None', false]]) {
      buttons.append(action(title, () => {
        filters[key] = new Set(enabled ? values : []); syncControls(); apply();
      }));
    }
    container.append(buttons);
    for (const value of values) {
      const label = element('label', undefined, 'choice');
      const input = element('input'); input.type = 'checkbox'; input.checked = true;
      input.dataset.facet = key; input.value = value;
      input.addEventListener('change', () => {
        input.checked ? filters[key].add(value) : filters[key].delete(value); apply();
      });
      label.append(input, element('span', labels.get(value) || value));
      container.append(label); checkboxes.push({input, key, value});
    }
  };
  const themeNames = new Map([['__unthemed__', 'No assigned theme']]);
  [...sourceClaims, ...sourceEdges.filter(e => e.navigation), ...sourceNodes].forEach(e =>
    (e.themeDetails || []).forEach(t => themeNames.set(t.id, t.label)));
  sourceNodes.filter(n => n.role === 'theme').forEach(n =>
    themeNames.set(n.themeId, n.label.replace(/^THEME · /, '')));
  facet('theme-filters', 'themes', themeNames);
  facet('type-filters', 'types'); facet('status-filters', 'statuses'); facet('origin-filters', 'origins');
  [...new Set([...sourceClaims, ...sourceNodes.filter(n => n.role === 'note')].map(e => e.kind))].sort().forEach(kind => {
    const option = element('option', kind); option.value = kind; $('kind-filter').append(option);
  });

  function matchingEntities() {
    const query = $('entity-search').value.trim().toLocaleLowerCase();
    return entities.filter(n => matchesSearch(searchText.get(n.id), query));
  }
  function renderEntities() {
    const matches = matchingEntities(), shown = new Set(visible.nodes.map(n => n.id));
    for (const node of matches) {
      if (!entityRows.has(node.id)) {
        const row = element('div', undefined, 'entity-choice');
        const check = element('input'); check.type = 'checkbox';
        check.setAttribute('aria-label', 'Show ' + node.label + ' (' + node.id + ')');
        check.dataset.entity = node.id;
        check.addEventListener('change', () => {
          check.checked ? filters.hiddenEntities.delete(node.id) : filters.hiddenEntities.add(node.id);
          apply();
        });
        const button = action(node.label, () => inspectNode(node.id, true));
        button.title = node.id; button.className = 'entity-name';
        button.dataset.entity = node.id;
        const description = element('span', undefined, 'hint');
        row.append(check, button, description);
        entityRows.set(node.id, {row, check, description});
      }
      const {check, description} = entityRows.get(node.id);
      check.checked = !filters.hiddenEntities.has(node.id);
      const text = (node.entityTypes || ['Entity']).join(', ')
        + (shown.has(node.id) ? '' : ' · outside current view');
      if (description.textContent !== text) description.textContent = text;
    }
    // Ordinary filter changes preserve DOM identity, keyboard focus and scroll.
    if (matches.length !== listedEntities.length || matches.some((n,i) => n !== listedEntities[i])) {
      $('entity-list').replaceChildren(...matches.map(n => entityRows.get(n.id).row));
      listedEntities = matches;
    }
    $('entity-matches').textContent = `${matches.length} of ${entities.length} notes and entities listed`;
  }

  function syncControls() {
    checkboxes.forEach(({input, key, value}) => {input.checked = filters[key].has(value);});
    $('kind-filter').value = filters.kind;
    $('theme-links').checked = filters.showThemes;
    $('note-links').checked = filters.showNotes;
  }
  function stopLayout() {
    clearTimeout(layoutTimer); fitAfterLayout = false;
    if (arranging) network.setOptions({physics: {enabled: false}});
    arranging = false;
    $('animate-layout').checked = false;
    $('layout-state').textContent = 'Layout paused'; $('pause-layout').disabled = true;
  }
  function startLayout() {
    clearTimeout(layoutTimer); fitAfterLayout = false;
    const live = $('animate-layout').checked;
    arranging = visible.nodes.length > 0;
    $('layout-state').textContent = live ? 'Live layout' : arranging ? 'Arranging…' : 'Layout paused';
    $('pause-layout').disabled = !live && !arranging;
    const spacing = Number($('node-spacing').value) / 100;
    network.setOptions({physics:{
      enabled:arranging,
      // Animate visible frames instead of running hidden stabilization. Keep the
      // camera still: fitting after spacing changes would shrink the labels again.
      stabilization:{enabled:false, fit:false},
      barnesHut:{springLength:170 * spacing, gravitationalConstant:-6000 * spacing * spacing},
    }});
    if (!arranging) return;
    network.startSimulation();
    if (!live) layoutTimer = setTimeout(stopLayout, 4000);
  }
  function finishLayout() {
    if (arranging && !$('animate-layout').checked) {
      const shouldFit = fitAfterLayout;
      stopLayout();
      if (shouldFit) fit();
    }
  }
  function membershipText(edge) {
    const counts = new Map();
    Object.entries(edge.memberships || {}).filter(([id]) => visibleClaimIds.has(id)).forEach(([, status]) =>
      counts.set(status, (counts.get(status) || 0) + 1));
    return [...counts].sort().map(([status, count]) => `${status} (${count})`).join(', ');
  }
  function apply(pause = true) {
    // Preserve positions unless the user has opted into a live simulation.
    if (pause && !$('animate-layout').checked) stopLayout();
    visible = filterGraph(sourceNodes, sourceEdges, filters, sourceAttributes);
    visibleClaimIds = new Set([...visible.claims, ...visible.attributes, ...visible.nodes.filter(n => n.role === 'note')].map(e => e.id));
    const nodeIds = new Set(visible.nodes.map(n => n.id));
    const edgeIds = new Set([...visible.claims, ...visible.navigation, ...visible.themeLinks].map(e => e.id));
    const nodeUpdates = sourceNodes.filter(n => !!nodes.get(n.id).hidden === nodeIds.has(n.id))
      .map(n => ({id:n.id, hidden:!nodeIds.has(n.id), physics:nodeIds.has(n.id)}));
    const edgeUpdates = sourceEdges.map(e => ({
      id:e.id, hidden:!edgeIds.has(e.id), physics:!e.organisation && edgeIds.has(e.id),
      label:$('edge-labels').checked ? e.label : '',
      ...(e.organisation ? {title:'Theme membership: ' + membershipText(e)
        + '; navigation only, separate from claim review'} : {}),
    })).filter(update => {
      const previous = edges.get(update.id);
      return Object.entries(update).some(([key, value]) => previous[key] !== value);
    });
    if (nodeUpdates.length) nodes.update(nodeUpdates);
    if (edgeUpdates.length) edges.update(edgeUpdates);
    const entityCount = visible.nodes.filter(n => n.role !== 'theme').length;
    $('graph-counts').textContent = `${entityCount} / ${entities.length} notes and entities · `
      + `${visible.claims.length} claims · ${visible.navigation.length} note connections · `
      + `${visible.attributes.length} / ${sourceAttributes.length} attributes · `
      + `${visible.nodes.length - entityCount} theme hubs`;
    $('empty-graph').hidden = visible.nodes.length > 0;
    $('clear-focus').hidden = !filters.focus;
    $('expand-focus').hidden = !filters.focus;
    $('contract-focus').hidden = !filters.focus;
    $('contract-focus').disabled = filters.focusHops <= 1;
    $('expand-focus').disabled = !visible.canExpand;
    $('expand-focus').title = visible.canExpand
      ? 'Reveal the next connections of every visible note and entity.'
      : 'No further connections match the current filters in this snapshot.';
    $('reset-hops').hidden = !filters.focus || filters.focusHops === 1;
    $('focus-state').hidden = !filters.focus;
    $('focus-state').textContent = filters.focus
      ? `Focus: ${byNode.get(filters.focus).label} · ${filters.focusHops} hop${filters.focusHops === 1 ? '' : 's'}` : '';
    const acceptedOnly = filters.statuses.size === 1 && filters.statuses.has('Accepted');
    $('note-links').checked = filters.showNotes;
    $('theme-links').disabled = acceptedOnly || !sourceEdges.some(e => e.organisation);
    $('theme-links').checked = !$('theme-links').disabled && filters.showThemes;
    $('theme-links').parentElement.title = acceptedOnly ? 'Theme navigation is excluded from accepted-only views.' : '';
    network.unselectAll();
    if (selection?.edge && !visibleClaimIds.has(selection.edge) && !edgeIds.has(selection.edge)) selection = null;
    renderEntities(); renderSelection();
    if (pause && $('animate-layout').checked) startLayout();
  }

  function inspectNode(id, pan = false) {
    selection = {node:id};
    if (visible.nodes.some(n => n.id === id)) {
      network.selectNodes([id]);
      if (pan) network.focus(id, {scale:Math.max(network.getScale(), 0.8), animation:false});
    }
    renderSelection();
    document.querySelector('.inspector').scrollTop = 0;
  }
  function inspectEdge(id) {
    selection = {edge:id};
    if (byEdge.get(id).attribute) network.selectNodes([byEdge.get(id).from]);
    else network.selectEdges([id]);
    renderSelection();
    document.querySelector('.inspector').scrollTop = 0;
  }
  function renderNotes(panel, entity, previous) {
    const ids = [...new Set([...(noteData.notes[entity] ? [entity] : []), ...(noteData.entities[entity] || [])])];
    const section = element('section', undefined, 'curated-notes');
    const readingNote = !!noteData.notes[entity];
    section.append(element('h4', readingNote ? 'Note text' : `Associated notes (${ids.length})`));
    if (!ids.length) {
      section.append(element('p', 'No note is associated with this subject yet.', 'hint'));
    } else {
      section.append(element('p', readingNote
        ? 'Saved writing. Select a claim connection to see the evidence cited for that claim.'
        : 'Reading associated with this subject. This list is independent of claim filters; these notes do not necessarily support the visible claims.', 'hint'));
    }
    ids.forEach((id, index) => {
      const note = noteData.notes[id];
      const card = element('details', undefined, 'curated-note');
      card.dataset.note = id;
      card.open = previous.has(id) ? previous.get(id).open : index === 0;
      card.append(element('summary', note.title));
      card.append(element('p', `${note.method ? 'Curated by' : 'Author:'} ${note.author || 'Unknown'}${note.kind ? ' · ' + note.kind : ''}`, 'hint'));
      card.append(element('div', note.body, 'note-body'));
      const sources = element('details', undefined, 'note-sources');
      sources.open = previous.get(id)?.sourcesOpen || false;
      sources.append(element('summary', 'Sources & qualifications'));
      if (note.method) {
        field(sources, 'Scope', note.qualification);
        field(sources, 'Curation', note.method === 'faithful_restatement' ? 'Faithful restatement' : 'Synthesis');
      }
      for (const source of note.sources) {
        field(sources, 'Source', source.title + (source.author ? ' · ' + source.author : ''));
        field(sources, 'Original quotation', source.quote);
        field(sources, 'Location', `${source.text_path} · line ${source.start_line}`);
        field(sources, 'Source revision', source.revision);
      }
      field(sources, 'Note identifier', note.id);
      field(sources, 'Note revision', note.revision);
      card.append(sources); section.append(card);
    });
    panel.append(section);
  }
  function renderSelection() {
    const panel = $('selection-detail');
    const previous = new Map();
    if (selection?.node && panel.dataset.entity === selection.node) {
      panel.querySelectorAll('.curated-note').forEach(card => previous.set(card.dataset.note,
        {open:card.open, sourcesOpen:card.querySelector('.note-sources').open}));
    }
    panel.dataset.entity = selection?.node || '';
    panel.replaceChildren();
    if (!selection) {panel.append(element('p', 'Nothing selected.', 'hint')); return;}
    if (selection.node) {
      const node = byNode.get(selection.node);
      panel.append(element('h3', node.label));
      if (node.role === 'theme') {
        field(panel, 'Identifier', node.id);
        panel.append(element('p', 'An overlapping navigation category. Membership review does not accept its claims.'));
        return;
      }
      panel.append(element('p', (node.entityTypes || ['Entity']).join(' · '), 'hint'));
      if (!visible.nodes.some(n => n.id === node.id)) {
        panel.append(element('p', 'Outside the current graph filters. You can still read this record here.', 'hint'));
      }
      panel.append(action(node.role === 'note' ? 'Focus on this note' : 'Focus on this entity', () => {
        filters.focus = node.id; filters.focusHops = 1; apply(); fit(); $('clear-focus').focus();
      }));
      renderNotes(panel, node.id, previous);
      const attributes = visible.attributes.filter(a => a.from === node.id);
      if (attributes.length) panel.append(element('h4', `${attributes.length} visible attributes`));
      for (const attribute of attributes) {
        const words = attribute.label.replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();
        const name = words.charAt(0).toUpperCase() + words.slice(1);
        const value = attribute.detail.literal_value;
        const text = name + (value.length <= 100 ? ': ' + value : ' (text value)');
        const button = action(text, () => inspectEdge(attribute.id));
        button.className = 'attribute';
        button.append(element('small', `${attribute.status} · ${attribute.origin} · ${attribute.kind}`));
        panel.append(button);
      }
      const connected = [...visible.claims, ...visible.navigation].filter(e => e.from === node.id || e.to === node.id);
      panel.append(element('h4', `${connected.length} visible connections`));
      if (!connected.length) {
        const hasConnections = sourceEdges.some(e => !e.organisation && (e.from === node.id || e.to === node.id));
        panel.append(element('p', hasConnections
          ? 'Current filters hide these connections. Reset filters to widen the view.'
          : 'No saved connections yet.', 'hint'));
      }
      for (const edge of connected) {
        const text = `${byNode.get(edge.from).label} → ${edge.label} → ${byNode.get(edge.to).label}`;
        const button = action(text, () => inspectEdge(edge.id)); button.className = 'connection';
        button.append(element('small', edge.navigation ? 'Note link · navigation' : `Claim · ${edge.status} · ${edge.origin} · ${edge.kind}`));
        panel.append(button);
      }
      const identifiers = element('details');
      identifiers.append(element('summary', node.role === 'note' ? 'Note details' : 'Entity details'));
      field(identifiers, 'Identifier', node.id);
      if (node.aliases?.length) field(identifiers, 'Historical names and aliases', node.aliases.join('\n'));
      panel.append(identifiers);
    } else {
      const edge = byEdge.get(selection.edge);
      if (edge.organisation) {
        panel.append(element('h3', 'Theme membership'));
        field(panel, 'Theme', byNode.get(edge.from).label);
        field(panel, 'Entity', byNode.get(edge.to).label);
        field(panel, 'Visible supporting memberships', membershipText(edge));
        panel.append(element('p', 'Navigation only. Membership review is independent of claim review.'));
        return;
      }
      const detail = edge.detail;
      if (edge.navigation) {
        panel.append(element('h3', `${byNode.get(edge.from).label} → ${edge.label} → ${byNode.get(edge.to).label}`));
        field(panel, 'Connection explanation', detail.rationale);
        panel.append(element('p', 'A saved note connection. It does not imply agreement, causation or claim acceptance.', 'hint'));
        panel.append(action('Read source note', () => inspectNode(detail.note, true)));
        panel.append(action('Explore linked subject', () => inspectNode(edge.to, true)));
        field(panel, 'Saved in note revision', detail.revision);
        return;
      }
      panel.append(element('h3', edge.attribute ? `${detail.subject} · ${detail.relation}`
        : `${detail.subject} → ${detail.relation} → ${detail.object}`));
      if (edge.attribute) {
        field(panel, 'Value (literal)', detail.literal_value);
        field(panel, 'Datatype', detail.object_datatype);
        if (detail.object_language) field(panel, 'Language', detail.object_language);
      }
      field(panel, 'Claim', `${edge.status} · ${edge.origin} · ${edge.kind}`);
      field(panel, 'Rationale', detail.rationale);
      for (const account of detail.evidence_accounts || []) {
        field(panel, account.relationship === 'RepeatedAccount' ? 'Repeated source account' : 'Unresolved source overlap', account.qualification);
        field(panel, 'Account qualification by', account.reviewer);
      }
      if (detail.themes) field(panel, 'Themes (separate review)', detail.themes);
      panel.append(element('h4', 'Evidence cited by this claim'));
      for (const evidence of detail.evidence) {
        field(panel, 'Source snapshot', evidence.snapshot);
        field(panel, 'Exact quotation', evidence.quote);
      }
      field(panel, 'Assertion identifier', edge.id);
      if (detail.kind_type_review) {
        const extra = element('details');
        extra.append(element('summary', 'Classification details'));
        field(extra, 'Classification review', detail.kind_type_review); panel.append(extra);
      }
    }
  }
  function fit() {
    // Distant theme hubs must not make a small focused neighbourhood unreadable.
    const framed = visible.nodes.filter(n => !filters.focus || n.role !== 'theme');
    if (framed.length) network.fit({nodes:framed.map(n => n.id), animation:false});
  }
  function themeDetail() {
    // Tiny dots are expensive to rasterise and indistinct at overview scale.
    // Hysteresis prevents repeated dataset updates near the zoom boundary.
    const scale = network.getScale();
    const detailed = detailedThemes ? scale >= 0.25 : scale > 0.35;
    if (detailed === detailedThemes || themeFrame || !themeEdges.length) return;
    themeFrame = requestAnimationFrame(() => {
      themeFrame = null;
      const scale = network.getScale();
      const detailed = detailedThemes ? scale >= 0.25 : scale > 0.35;
      if (detailed === detailedThemes) return;
      detailedThemes = detailed;
      edges.update(themeEdges.map(e => ({id:e.id, dashes:detailed ? e.dashes : false})));
    });
  }
  $('entity-search').addEventListener('input', renderEntities);
  $('show-entities').addEventListener('click', () => {
    matchingEntities().forEach(n => filters.hiddenEntities.delete(n.id));
    apply();
  });
  $('hide-entities').addEventListener('click', () => {
    const matches = new Set(matchingEntities().map(n => n.id));
    filters.hiddenEntities = new Set(entities.filter(n => !matches.has(n.id)).map(n => n.id));
    apply();
  });
  $('kind-filter').addEventListener('change', () => {filters.kind = $('kind-filter').value; apply();});
  $('theme-links').addEventListener('change', () => {filters.showThemes = $('theme-links').checked; apply();});
  $('note-links').addEventListener('change', () => {filters.showNotes = $('note-links').checked; apply();});
  $('edge-labels').addEventListener('change', apply);
  $('expand-focus').addEventListener('click', () => {
    if (!filters.focus || !visible.canExpand) return;
    filters.focusHops++; apply(); fit();
  });
  $('reset-hops').addEventListener('click', () => {filters.focusHops = 1; apply(); fit();});
  $('contract-focus').addEventListener('click', () => {
    if (!filters.focus || filters.focusHops <= 1) return;
    filters.focusHops--; apply(); fit();
  });
  $('clear-focus').addEventListener('click', () => {
    filters.focus = null; filters.focusHops = 1; apply(); fit();
  });
  $('reset-filters').addEventListener('click', () => {
    filters = initialFilters(sourceNodes, sourceEdges, sourceAttributes); selection = null;
    $('entity-search').value = ''; $('edge-labels').checked = true;
    syncControls(); apply(); fit();
  });
  $('fit-graph').addEventListener('click', fit);
  $('pause-layout').addEventListener('click', stopLayout);
  $('layout-graph').addEventListener('click', startLayout);
  $('animate-layout').addEventListener('change', () => {
    $('animate-layout').checked ? startLayout() : stopLayout();
  });
  $('node-spacing').addEventListener('input', () => {
    $('spacing-value').textContent = (Number($('node-spacing').value) / 100) + '×';
    startLayout();
  });
  network.on('click', params => {
    if (params.nodes.length) inspectNode(params.nodes[0]);
    else if (params.edges.length) inspectEdge(params.edges[0]);
    else {selection = null; renderSelection();}
  });
  network.on('stabilizationIterationsDone', finishLayout);
  network.on('stabilized', finishLayout);
  // Covers wheel zoom, fit, focus and animated/programmatic camera changes.
  network.on('beforeDrawing', themeDetail);
  $('mynetwork').setAttribute('aria-label', 'Knowledge graph; use the entity list to explore with a keyboard.');
  apply(false);
  // Used by the local viewer benchmark; no writes to the knowledge graph.
  window.knotViewer = {inspectNode};
})();
