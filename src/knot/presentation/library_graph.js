/* A single lazy graph instance; all relationship meaning comes from the model. */
const LibraryGraph = (() => {
  const { element, button, link, paged } = LibraryDOM;
  function create(index, { navigate, changed, selected }) {
    const $ = (id) => document.getElementById(id),
      colors = index.model.palette.colors,
      reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    let network = null,
      motion,
      active = false,
      ambient = false,
      manualScene = true,
      layouts = {},
      nodeSet,
      edgeSet,
      state = {
        seed: null,
        hops: 1,
        expanded: [],
        collapsed: [],
        preferred: [],
        filters: {},
        cross: true,
        full: false,
        live: !reducedMotion.matches,
        focusedLive: false,
        spacing: 100,
      },
      positions = {},
      lastSeed = null,
      visible = null,
      restoredPositions = false;
    const liveLayout = () => (state.full ? state.live : state.focusedLive);
    const savePositions = () => {
      if (network && !ambient && manualScene) Object.assign(positions, network.getPositions());
    };
    function rememberLayout() {
      savePositions();
      layouts[state.full ? 'live' : 'focused'] = {
        seed: state.seed,
        spacing: state.spacing,
        positions: structuredClone(positions),
        camera:
          network && manualScene
            ? { position: network.getViewPosition(), scale: network.getScale() }
            : state.camera || null,
      };
    }
    function getState() {
      rememberLayout();
      return {
        ...structuredClone(state),
        layouts: structuredClone(layouts),
        positions: { ...positions },
        camera:
          network && manualScene
            ? { position: network.getViewPosition(), scale: network.getScale() }
            : state.camera || null,
      };
    }
    function setState(next) {
      if (next.full !== undefined && next.full !== state.full) rememberLayout();
      state = { ...state, ...next };
      if (next.layouts) layouts = structuredClone(next.layouts);
      positions = next.positions || {};
      lastSeed = state.seed;
      restoredPositions = true;
      sync();
    }
    function sync() {
      $('claim-status').value = state.filters.status || 'all';
      $('claim-origin').value = state.filters.origin || 'all';
      $('claim-theme').value = state.filters.theme || '';
      $('claim-kind').value = state.filters.kind || '';
      $('graph-type').value = state.filters.type || '';
      $('cross-links').checked = state.cross;
      $('note-links').checked = state.filters.showNotes !== false;
      $('note-links').disabled = state.filters.status === 'Accepted';
      $('node-spacing').value = state.spacing;
      syncMotion();
    }
    function syncMotion() {
      const enabled =
        active && !ambient && !document.hidden && liveLayout() && visible?.nodes.length > 1;
      motion?.update(!!enabled, state.spacing, !state.full);
      $('node-spacing-value').textContent = `${state.spacing}%`;
      $('node-spacing').setAttribute('aria-valuetext', `${state.spacing}%`);
      $('layout-toggle').textContent = liveLayout()
        ? 'Pause layout'
        : state.full
          ? 'Resume layout'
          : 'Live layout';
      $('layout-toggle').disabled = !(visible?.nodes.length > 1);
    }
    function setActive(value) {
      active = value;
      syncMotion();
    }
    function draw() {
      const camera = network
        ? { position: network.getViewPosition(), scale: network.getScale() }
        : null;
      const refocus =
        lastSeed !== state.seed || (restoredPositions && !Object.keys(positions).length);
      if (!restoredPositions) savePositions();
      restoredPositions = false;
      if (lastSeed !== state.seed) {
        positions = {};
        lastSeed = state.seed;
      }
      visible = index.neighbourhood(state);
      $('graph-empty').hidden = !!visible.nodes.length;
      $('graph-canvas').hidden = !visible.nodes.length;
      $('hop-count').textContent = state.full
        ? 'Full graph'
        : `${state.hops} hop${state.hops === 1 ? '' : 's'}`;
      $('hop-less').disabled = state.full || state.hops === 0;
      $('hop-more').disabled = state.full || !state.seed;
      $('graph-reset').disabled = state.full;
      $('cross-links').disabled = state.full;
      $('full-graph').setAttribute('aria-pressed', String(state.full));
      $('focused-graph').setAttribute('aria-pressed', String(!state.full));
      const allEdges = visible.edges.filter(
        (e) => state.cross || state.full || visible.tree.has(e.id),
      );
      $('graph-status').textContent = visible.nodes.length
        ? `${visible.nodes.length} records · ${allEdges.length} connections shown` +
          (visible.omitted
            ? ` · ${visible.omitted} neighbours outside the 100-record limit; use the list to choose them.`
            : '') +
          (visible.hiddenEdges
            ? ` · ${visible.hiddenEdges} additional connections outside the 300-connection limit.`
            : '') +
          (!state.full && !state.cross
            ? ` · ${visible.edges.length - allEdges.length} cross-links hidden.`
            : '') +
          (visible.nodes.length === 1
            ? ' No matching connections; the selected record remains visible.'
            : '')
        : 'Search or choose a record to start. No graph layout is running.';
      if (visible.nodes.length) {
        const levels = new Map();
        for (const n of visible.nodes) {
          const depth = visible.depth.get(n.id) || 0;
          if (!levels.has(depth)) levels.set(depth, []);
          levels.get(depth).push(n.id);
        }
        for (const [depth, ids] of levels) {
          ids.sort();
          ids.forEach((id, i) => {
            if (!positions[id]) {
              if (state.full) {
                const columns = Math.ceil(Math.sqrt(ids.length));
                positions[id] = {
                  x: (((i % columns) - (columns - 1) / 2) * 220 * state.spacing) / 100,
                  y: ((Math.floor(i / columns) - (columns - 1) / 2) * 220 * state.spacing) / 100,
                };
              } else {
                const angle = (2 * Math.PI * i) / ids.length - Math.PI / 2;
                const centre = positions[state.seed] || { x: 0, y: 0 };
                const radius = (depth * 270 * state.spacing) / 100;
                positions[id] = {
                  x: centre.x + Math.cos(angle) * radius,
                  y: centre.y + Math.sin(angle) * radius,
                };
              }
            }
          });
        }
        renderNetwork({ ...visible, edges: allEdges }, positions, selected());
        if (state.camera) network.moveTo({ ...state.camera, animation: false });
        else if (camera && !refocus) network.moveTo({ ...camera, animation: false });
        else network.fit({ animation: false });
        state.camera = null;
      }
      if (!visible.nodes.length && network && !manualScene) {
        nodeSet.clear();
        edgeSet.clear();
      }
      manualScene = true;
      sync();
      connections();
    }
    function renderNetwork(scene, layout, id, highlighted = null) {
      const visualNodes = scene.nodes.map((n) => ({
        id: n.id,
        label: ambient
          ? n.title
          : n.title + '\n' + (n.role === 'note' ? 'Note' : n.entityTypes.join(' · ')),
        shape: ambient ? 'dot' : n.role === 'note' ? 'box' : 'dot',
        size: 14,
        fixed: ambient,
        chosen: !ambient,
        opacity: 1,
        shadow: { enabled: false },
        ...layout[n.id],
        color:
          n.role === 'note' ? colors.note : { background: colors.entity, border: colors.accent },
        font: {
          color: n.role === 'note' ? colors['note-text'] : colors.text,
          face: index.model.palette.fonts.graph,
          size: ambient ? 19 : 13,
        },
        widthConstraint: { maximum: 240 },
        margin: 10,
        borderWidth: n.id === id ? (ambient ? 5 : 3) : 1,
        ...(ambient ? idleNode(n.id, n.opacity ?? 1, n.id === id ? 1 : 0) : {}),
      }));
      const visualEdges = scene.edges.map((e) => ({
        id: e.id,
        from: e.from,
        to: e.to,
        label: ambient && e.id !== highlighted ? ' ' : e.label,
        arrows: { to: { enabled: true, scaleFactor: ambient ? 0.45 : 1 } },
        chosen: !ambient,
        color: {
          color: ambient
            ? '#42bb87'
            : e.navigation
              ? colors.navigation
              : e.status === 'Accepted'
                ? colors.accepted
                : colors.unreviewed,
          opacity: ambient ? (e.opacity ?? 1) * (e.id === highlighted ? 0.95 : 0.5) : 1,
        },
        dashes: e.navigation ? [6, 4] : e.origin === 'Inferred',
        width: ambient ? (e.id === highlighted ? 1.8 : 0.8) : e.status === 'Accepted' ? 2 : 1,
        font: {
          color: ambient ? '#a1d9bd' : colors['edge-text'],
          size: ambient ? 13 : 10,
          strokeWidth: 0,
          align: 'middle',
        },
        smooth: { enabled: !ambient, type: 'curvedCW', roundness: 0.12 },
      }));
      if (!network) {
        nodeSet = new vis.DataSet();
        edgeSet = new vis.DataSet();
        network = new vis.Network(
          $('graph-canvas'),
          { nodes: nodeSet, edges: edgeSet },
          {
            physics: false,
            layout: { improvedLayout: false },
            interaction: {
              hover: false,
              keyboard: { enabled: true, bindToWindow: false },
              navigationButtons: true,
            },
            nodes: { chosen: true },
            edges: { selectionWidth: 2 },
          },
        );
        motion = LibraryLayout.create(network);
        network.on('click', (params) => {
          if (!ambient && params.nodes.length) navigate({ view: 'graph', id: params.nodes[0] });
        });
        network.on('doubleClick', (params) => {
          if (!ambient && params.nodes.length) focus(params.nodes[0]);
        });
        network.on('dragEnd', () => {
          if (ambient) return;
          savePositions();
          changed();
        });
        network.on('zoom', () => {
          if (!ambient) changed();
        });
      }
      const wanted = new Set(visualNodes.map((n) => n.id));
      nodeSet.remove(nodeSet.getIds().filter((id) => !wanted.has(id)));
      nodeSet.update(visualNodes);
      const wantedEdges = new Set(visualEdges.map((e) => e.id));
      edgeSet.remove(edgeSet.getIds().filter((id) => !wantedEdges.has(id)));
      edgeSet.update(visualEdges);
      if (ambient) network.unselectAll();
      else if (id && wanted.has(id)) network.selectNodes([id], false);
    }
    function idleNode(id, opacity, strength) {
      return {
        id,
        opacity,
        size: 6 + strength * 4,
        borderWidth: 1 + strength,
        color: {
          background: `rgb(${Math.round(32 + strength * 124)},${Math.round(89 + strength * 154)},${Math.round(63 + strength * 136)})`,
          border: '#69dca2',
        },
        font: {
          color: `rgba(206,233,219,${opacity})`,
          face: 'system-ui, sans-serif',
          size: 17 + strength * 2,
          strokeWidth: 0,
        },
        shadow: {
          enabled: true,
          color: `rgba(66,225,151,${(0.18 + strength * 0.25) * opacity})`,
          size: 12 + strength * 16,
          x: 0,
          y: 0,
        },
      };
    }
    function idleFrame(scene, opacity, focus, highlighted = null) {
      nodeSet.update(scene.nodes.map((n) => idleNode(n.id, opacity(n.id), focus(n.id))));
      edgeSet.update(
        scene.edges.map((e) => ({
          id: e.id,
          color: {
            color: '#42bb87',
            opacity: Math.min(opacity(e.from), opacity(e.to)) * (e.id === highlighted ? 0.95 : 0.5),
          },
        })),
      );
    }
    function showIdle(scene, layout, id, highlighted) {
      ambient = true;
      // Returning to Library need not redraw Graph yet; never save these as manual coordinates.
      manualScene = false;
      setActive(false);
      $('graph-canvas').hidden = false;
      renderNetwork(scene, layout, id, highlighted);
      motion.update(false);
      network.setOptions({
        interaction: {
          dragNodes: false,
          dragView: false,
          zoomView: false,
          keyboard: { enabled: false },
          navigationButtons: false,
        },
      });
      network.redraw();
      return network;
    }
    function leaveIdle() {
      ambient = false;
      if (network)
        network.setOptions({
          interaction: {
            dragNodes: true,
            dragView: true,
            zoomView: true,
            keyboard: { enabled: true, bindToWindow: false },
            navigationButtons: true,
          },
        });
    }
    function connections() {
      const parent = $('connection-list');
      parent.replaceChildren();
      const id = selected() || state.seed,
        edges = index.eligible(state.filters).adjacent.get(id) || [];
      const visibleIDs = new Set(visible?.nodes.map((n) => n.id));
      paged(
        parent,
        edges,
        (e) => {
          const target = e.from === id ? e.to : e.from,
            record = index.byId.get(target),
            row = element('div', undefined, 'connection');
          row.append(
            element('span', e.from === id ? `→ ${e.label}` : `← ${e.label}`),
            link(record, 'graph', navigate),
          );
          row.append(
            element('small', e.navigation ? 'Saved navigation' : `${e.status} · ${e.origin}`),
          );
          row.append(button('Focus', () => focus(target)));
          const expanded =
            !state.collapsed.includes(target) &&
            (state.expanded.includes(target) || visible.depth.get(target) < state.hops);
          if (!state.full && visibleIDs.has(target))
            row.append(
              button(expanded ? 'Collapse' : 'Expand', () => {
                if (expanded) {
                  state.expanded = state.expanded.filter((n) => n !== target);
                  state.collapsed.push(target);
                } else {
                  state.expanded.push(target);
                  state.collapsed = state.collapsed.filter((n) => n !== target);
                }
                draw();
                changed();
              }),
            );
          else if (!state.full)
            row.append(
              button('Include', () => {
                state.preferred = [target, ...state.preferred.filter((n) => n !== target)];
                if (!state.expanded.includes(id)) state.expanded.push(id);
                draw();
                changed();
              }),
            );
          return row;
        },
        {
          size: 100,
          empty:
            'No connections match these filters. Saved source notes remain available in the Library.',
        },
      );
    }
    function focus(id) {
      navigate({ view: 'graph', id }, { focus: true });
    }
    for (const [id, key] of [
      ['claim-status', 'status'],
      ['claim-origin', 'origin'],
      ['claim-theme', 'theme'],
      ['claim-kind', 'kind'],
      ['graph-type', 'type'],
    ]) {
      $(id).addEventListener('change', () => {
        state.filters[key] = $(id).value;
        draw();
        changed();
      });
    }
    $('note-links').addEventListener('change', () => {
      state.filters.showNotes = $('note-links').checked;
      draw();
      changed();
    });
    for (const [id, delta] of [
      ['hop-less', -1],
      ['hop-more', 1],
    ])
      $(id).addEventListener('click', () => {
        state.hops = Math.max(0, state.hops + delta);
        draw();
        changed();
      });
    $('cross-links').addEventListener('change', () => {
      state.cross = $('cross-links').checked;
      draw();
      changed();
    });
    $('graph-reset').addEventListener('click', () => {
      setState({
        hops: 1,
        expanded: [],
        collapsed: [],
        preferred: [],
        full: false,
        positions: {},
        camera: null,
      });
      draw();
      changed();
    });
    $('graph-fit').addEventListener('click', () => {
      network?.fit({ animation: false });
      changed();
    });
    function changeMode(full) {
      if (full === state.full) return;
      if (
        full &&
        index.records.length > 100 &&
        !confirm(
          `Show all ${index.records.length} records? This may be slow. Focused exploration stays available.`,
        )
      )
        return;
      rememberLayout();
      const seed = full ? state.seed : selected() || state.seed;
      const cached = layouts[full ? 'live' : 'focused'];
      const reuse = cached && (full || cached.seed === seed);
      setState({
        full,
        seed,
        ...(seed !== state.seed ? { hops: 1, expanded: [], collapsed: [], preferred: [] } : {}),
        positions: reuse
          ? LibraryLayout.scalePositions(
              cached.positions,
              state.spacing / cached.spacing,
              full ? selected() || seed : seed,
            )
          : {},
        camera: reuse ? cached.camera : null,
      });
      draw();
      changed();
    }
    $('full-graph').addEventListener('click', () => changeMode(true));
    $('focused-graph').addEventListener('click', () => changeMode(false));
    $('layout-toggle').addEventListener('click', () => {
      if (state.full) state.live = !state.live;
      else state.focusedLive = !state.focusedLive;
      syncMotion();
      changed();
    });
    $('node-spacing').addEventListener('input', () => {
      const spacing = Number($('node-spacing').value);
      if (!liveLayout()) {
        savePositions();
        positions = LibraryLayout.scalePositions(
          positions,
          spacing / state.spacing,
          state.full ? selected() || state.seed : state.seed,
        );
        // Apply the scaled positions directly, retaining manual placements and the
        // camera. Reading old canvas positions or fitting here would undo the change.
        restoredPositions = true;
        state.spacing = spacing;
        draw();
      } else {
        state.spacing = spacing;
        syncMotion();
      }
      changed();
    });
    document.addEventListener('visibilitychange', syncMotion);
    reducedMotion.addEventListener('change', () => {
      if (reducedMotion.matches) state.live = state.focusedLive = false;
      syncMotion();
      changed();
    });
    return {
      draw,
      showIdle,
      idleFrame,
      leaveIdle,
      setActive,
      focus,
      getState,
      setState,
      get full() {
        return state.full;
      },
      get filters() {
        return state.filters;
      },
      get seed() {
        return state.seed;
      },
      get network() {
        return network;
      },
      get visible() {
        return visible;
      },
    };
  }
  return { create };
})();
