/* Offline shell: shared selection, fragment routes and session-only navigation state. */
(() => {
  const $ = (id) => document.getElementById(id),
    { element, button, details, link } = LibraryDOM;
  const model = JSON.parse($('library-data').textContent),
    index = LibraryModel.create(model);
  $('knowledge-search').value = model.initial_search || '';
  const sessions = new Map();
  const currentRoute = () => LibraryModel.route(location.hash, model.initial_record);
  let selection = currentRoute(),
    recent = [],
    page = 0,
    collection = { type: 'all' },
    collectionTitle = 'All knowledge';
  let serial = 0,
    restoring = false,
    queryTimer,
    readerKey = '',
    scrolls = { library: 0, graph: 0 };
  const reader = LibraryReader.create(index, navigate, setCollection);
  const graph = LibraryGraph.create(index, {
    navigate,
    selected: () => selection.id,
    changed: () => {
      save();
      reader.renderContext($('context-content'), selection.id, graph.filters, selection.revision);
    },
  });
  function state() {
    return {
      selection: { ...selection },
      graph: graph.getState(),
      query: $('knowledge-search').value,
      role: $('record-filter').value,
      kind: $('note-kind').value,
      collection,
      collectionTitle,
      page,
      branches: [...$('library-tree').querySelectorAll('details[open]')].map(
        (d) => d.dataset.branch,
      ),
      scrolls: { ...scrolls, [selection.view]: $('main-panel').scrollTop },
    };
  }
  function save() {
    if (restoring) return;
    const key = history.state?.knotKey;
    if (key !== undefined) sessions.set(key, state());
  }
  function navigate(route, { focus = false } = {}) {
    save();
    const previous = selection;
    selection = {
      view: route.view || selection.view,
      id: route.id ?? null,
      revision: route.revision || null,
    };
    history.pushState(
      { knotKey: ++serial, fingerprint: model.manifest.fingerprint },
      '',
      LibraryModel.hash(selection),
    );
    if (selection.view === 'graph' && selection.id && !index.byId.has(selection.id)) {
      graph.setState({ seed: null, full: false, positions: {}, camera: null });
    } else if (
      focus ||
      (selection.view === 'graph' &&
        selection.id &&
        ((!graph.seed && !graph.full) ||
          (previous.view === 'library' &&
            !graph.visible?.nodes.some((n) => n.id === selection.id))))
    ) {
      graph.setState({
        seed: selection.id,
        hops: 1,
        expanded: [],
        collapsed: [],
        preferred: [],
        full: false,
        positions: {},
        camera: null,
      });
    }
    if (previous.id !== selection.id) scrolls[selection.view] = 0;
    render();
    save();
    $('selection-title').tabIndex = -1;
    $('selection-title').focus({ preventScroll: true });
  }
  function restore() {
    restoring = true;
    const saved =
      history.state?.fingerprint === model.manifest.fingerprint
        ? sessions.get(history.state?.knotKey)
        : null;
    selection = currentRoute();
    if (saved) {
      selection = saved.selection;
      graph.setState(saved.graph);
      $('knowledge-search').value = saved.query;
      $('record-filter').value = saved.role;
      $('note-kind').value = saved.kind;
      collection = saved.collection;
      collectionTitle = saved.collectionTitle;
      page = saved.page;
      scrolls = saved.scrolls;
      for (const d of $('library-tree').querySelectorAll('details'))
        d.open = saved.branches.includes(d.dataset.branch);
    } else {
      history.replaceState(
        { knotKey: ++serial, fingerprint: model.manifest.fingerprint },
        '',
        location.hash || LibraryModel.hash(selection),
      );
      graph.setState({
        seed: selection.id,
        full: false,
        positions: {},
        expanded: [],
        collapsed: [],
        preferred: [],
        hops: 1,
      });
    }
    readerKey = '';
    render();
    restoring = false;
    save();
  }
  window.addEventListener('popstate', restore);
  // Native links and pasted fragments also participate without persisting session state.
  window.addEventListener('hashchange', () => {
    const route = currentRoute();
    if (JSON.stringify(route) !== JSON.stringify(selection)) restore();
  });
  function choose(record) {
    navigate(
      { view: selection.view, id: record.id },
      { focus: selection.view === 'graph' && !graph.full },
    );
    if (innerWidth < 700) $('navigation-panel').classList.remove('drawer-open');
  }
  function renderResults() {
    const results = index.search($('knowledge-search').value, {
      role: $('record-filter').value,
      kind: $('note-kind').value,
      collection,
    });
    const size = 100;
    page = Math.min(page, Math.max(0, Math.ceil(results.length / size) - 1));
    $('collection-title').textContent = collectionTitle;
    $('result-count').textContent = `${results.length} records`;
    $('search-results').replaceChildren();
    $('result-pages').replaceChildren();
    for (const item of results.slice(page * size, (page + 1) * size)) {
      const { record, excerpt } = item,
        row = element('a', undefined, 'record-choice');
      row.href = LibraryModel.hash({ view: selection.view, id: record.id });
      row.setAttribute('aria-current', String(record.id === selection.id));
      row.dataset.record = record.id;
      row.append(
        element('span', record.title, 'record-title'),
        element(
          'small',
          record.role === 'note'
            ? `Note · ${record.kind || 'Unspecified'}`
            : record.entityTypes.join(' · '),
        ),
      );
      if (excerpt) row.append(element('small', excerpt));
      row.addEventListener('click', (event) => {
        if (!event.ctrlKey && !event.metaKey && !event.shiftKey) {
          event.preventDefault();
          choose(record);
        }
      });
      $('search-results').append(row);
    }
    if (!results.length)
      $('search-results').append(
        element('p', 'No matching records. Try another collection or search.', 'muted'),
      );
    if (results.length > size) {
      const prev = button('Previous', () => {
          page--;
          renderResults();
          save();
        }),
        next = button('Next', () => {
          page++;
          renderResults();
          save();
        });
      prev.disabled = page === 0;
      next.disabled = (page + 1) * size >= results.length;
      $('result-pages').append(
        prev,
        element('span', `${page + 1} / ${Math.ceil(results.length / size)}`),
        next,
      );
    }
  }
  function setCollection(type, id, title, options = {}) {
    collection = { type, id, entityType: options.entityType };
    $('record-filter').value =
      options.role ||
      (['notes', 'unclassified', 'standalone', 'created', 'modified'].includes(type)
        ? 'note'
        : type === 'entities'
          ? 'entity'
          : 'all');
    collectionTitle = title;
    page = 0;
    renderResults();
    save();
  }
  function tree() {
    const parent = $('library-tree');
    for (const [title, type] of [
      ['All knowledge', 'all'],
      ['All notes', 'notes'],
      ['All entities', 'entities'],
      ['Unclassified notes', 'unclassified'],
      ['Standalone notes', 'standalone'],
      ['Recently created', 'created'],
      ['Recently modified', 'modified'],
    ])
      parent.append(button(title, () => setCollection(type, null, title)));
    const themes = details('Themes');
    themes.dataset.branch = 'themes';
    const themeList = element('ul');
    themes.append(themeList);
    themes.addEventListener('toggle', () => {
      if (themes.open && !themeList.childElementCount) {
        for (const theme of model.themes) {
          const item = element('li'),
            branch = details(theme.label);
          branch.dataset.branch = 'theme:' + theme.id;
          branch.append(button('All records', () => setCollection('theme', theme.id, theme.label)));
          branch.append(
            button('Notes', () => {
              setCollection('theme', theme.id, theme.label + ' · Notes', { role: 'note' });
            }),
          );
          branch.append(
            button('Entities', () => {
              setCollection('theme', theme.id, theme.label + ' · Entities', { role: 'entity' });
            }),
          );
          const subtopics = details('Entity types');
          subtopics.dataset.branch = 'theme-types:' + theme.id;
          subtopics.addEventListener('toggle', () => {
            if (subtopics.open && subtopics.childElementCount === 1) {
              const types = new Set(
                index.records
                  .filter(
                    (record) =>
                      index.memberships.get(record.id)?.has(theme.id) && record.role === 'entity',
                  )
                  .flatMap((record) => record.entityTypes),
              );
              for (const type of [...types].sort())
                subtopics.append(
                  button(type, () =>
                    setCollection('theme', theme.id, `${theme.label} · ${type}`, {
                      role: 'entity',
                      entityType: type,
                    }),
                  ),
                );
            }
            save();
          });
          branch.append(subtopics);
          item.append(branch);
          themeList.append(item);
        }
      }
      save();
    });
    parent.append(themes);
    const types = details('Entity types');
    types.dataset.branch = 'types';
    const typeList = element('ul');
    types.append(typeList);
    types.addEventListener('toggle', () => {
      if (types.open && !typeList.childElementCount)
        for (const type of [...new Set(index.nodes.flatMap((n) => n.entityTypes))].sort()) {
          const row = element('li');
          row.append(button(type, () => setCollection('type', type, type)));
          typeList.append(row);
        }
      save();
    });
    parent.append(types);
  }
  function renderRecents() {
    $('recent-list').replaceChildren();
    for (const id of recent) {
      const record = index.byId.get(id);
      if (record) {
        const row = element('div');
        row.append(link(record, selection.view, navigate));
        $('recent-list').append(row);
      }
    }
  }
  function render() {
    const record = index.byId.get(selection.id),
      source = model.sources[selection.revision || selection.id];
    $('view-graph').setAttribute('aria-pressed', String(selection.view === 'graph'));
    $('view-library').setAttribute('aria-pressed', String(selection.view === 'library'));
    $('graph-panel').hidden = selection.view !== 'graph';
    $('reader-panel').hidden = selection.view !== 'library';
    graph.setActive(selection.view === 'graph');
    $('selection-title').textContent =
      source?.title ||
      record?.title ||
      (selection.id
        ? 'Not included in this snapshot'
        : selection.view === 'graph'
          ? 'Explore your knowledge'
          : 'Knowledge Library');
    $('selection-type').textContent = source
      ? 'Pinned evidence'
      : record
        ? record.role === 'note'
          ? 'Note'
          : record.entityTypes.join(' · ')
        : 'One knowledge system · two views';
    $('read-selection').hidden = selection.view !== 'graph' || !record;
    $('explore-selection').hidden = selection.view !== 'library' || !record;
    if (record) {
      recent = [record.id, ...recent.filter((id) => id !== record.id)].slice(0, 20);
    }
    renderRecents();
    renderResults();
    reader.renderContext($('context-content'), selection.id, graph.filters, selection.revision);
    if (selection.view === 'library') {
      const key = JSON.stringify(selection);
      if (readerKey !== key) {
        reader.render($('reader-panel'), selection.id, selection.revision);
        readerKey = key;
      }
    } else graph.draw();
    $('main-panel').scrollTop = scrolls[selection.view] || 0;
    performance.mark('knot-view-ready');
  }
  for (const view of ['graph', 'library'])
    $('view-' + view).addEventListener('click', () => {
      save();
      navigate({
        view,
        id: selection.id,
        revision: view === 'library' ? selection.revision : null,
      });
    });
  $('read-selection').addEventListener('click', () =>
    navigate({ view: 'library', id: selection.id }),
  );
  $('explore-selection').addEventListener('click', () =>
    navigate({ view: 'graph', id: selection.id }, { focus: true }),
  );
  $('start-library').addEventListener('click', () => navigate({ view: 'library' }));
  document.querySelector('.skip').addEventListener('click', (event) => {
    event.preventDefault();
    $('main-panel').focus();
  });
  $('clear-recents').addEventListener('click', () => {
    recent = [];
    renderRecents();
  });
  $('knowledge-search').addEventListener('input', () => {
    clearTimeout(queryTimer);
    queryTimer = setTimeout(() => {
      page = 0;
      renderResults();
      save();
      performance.mark('knot-search-ready');
    }, 120);
  });
  for (const id of ['record-filter', 'note-kind'])
    $(id).addEventListener('change', () => {
      page = 0;
      renderResults();
      save();
    });
  for (const [id, panel] of [
    ['toggle-navigation', 'navigation-panel'],
    ['toggle-context', 'context-panel'],
  ])
    $(id).addEventListener('click', () => {
      $(panel).classList.toggle('drawer-open');
      $(id).setAttribute('aria-expanded', String($(panel).classList.contains('drawer-open')));
    });
  $('main-panel').addEventListener(
    'scroll',
    () => {
      scrolls[selection.view] = $('main-panel').scrollTop;
      save();
    },
    { passive: true },
  );
  const option = (select, value, title) => {
    const o = element('option', title || value);
    o.value = value;
    $(select).append(o);
  };
  for (const kind of [
    ...new Set(Object.values(model.notes).map((n) => n.kind || 'Unspecified')),
  ].sort())
    option('note-kind', kind);
  for (const kind of [...new Set(Object.values(model.claims).map((c) => c.kind))].sort())
    option('claim-kind', kind);
  for (const theme of model.themes) option('claim-theme', theme.id, theme.label);
  for (const type of [...new Set(index.nodes.flatMap((n) => n.entityTypes))].sort())
    option('graph-type', type);
  $('snapshot-time').textContent =
    'Snapshot · ' + new Date(model.manifest.generated_at).toLocaleString();
  $('snapshot-info').textContent =
    `${model.manifest.history} Snapshot ${model.manifest.fingerprint.slice(0, 16)}.`;
  $('collection-counts').textContent =
    `${model.manifest.counts.notes} NOTES · ${model.manifest.counts.entities} ENTITIES · ${model.manifest.counts.claims} CLAIMS`;
  tree();
  restore();
  performance.mark('knot-library-ready');
  window.knotLibrary = {
    index,
    graph,
    navigate,
    get selection() {
      return { ...selection };
    },
    get recents() {
      return [...recent];
    },
  };
})();
