/* Ambient presentation shares the graph canvas; manual navigation stays in the shell. */
const LibraryIdle = (() => {
  function create(index, graph, { exit, read }) {
    const $ = (id) => document.getElementById(id),
      panel = $('idle-panel'),
      canvas = $('graph-canvas');
    const home = document.createComment('Graph canvas home');
    canvas.before(home);
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    let active = false,
      policy = null,
      filters = {},
      seed = null,
      committed = null;
    let phase = 'ready',
      target = null,
      scene = null,
      cameraPoint = null,
      cooldown = null,
      tourSeed = 1,
      leftFullscreenAt = -Infinity;
    const geography = LibraryIdleScene.geography(),
      positions = geography.positions,
      { ease, merge } = LibraryIdleScene,
      filterInputs = new Map();
    for (const [key, source] of [
      ['status', 'claim-status'],
      ['origin', 'claim-origin'],
      ['theme', 'claim-theme'],
      ['kind', 'claim-kind'],
      ['type', 'graph-type'],
    ]) {
      const label = document.createElement('label'),
        select = $(source).cloneNode(true);
      select.id = 'idle-' + key;
      label.append(document.createTextNode(key[0].toUpperCase() + key.slice(1) + ' '), select);
      $('idle-filter-controls').append(label);
      filterInputs.set(key, select);
      select.addEventListener('change', () => {
        filters[key] = select.value;
        reconfigure();
      });
    }
    const noteLabel = document.createElement('label'),
      noteToggle = document.createElement('input');
    noteToggle.type = 'checkbox';
    noteToggle.id = 'idle-notes';
    noteLabel.append(noteToggle, document.createTextNode(' Associated notes'));
    $('idle-filter-controls').append(noteLabel);
    noteToggle.addEventListener('change', () => {
      filters.showNotes = noteToggle.checked;
      reconfigure();
    });

    const session = LibraryIdleModel.playback({
      changed: controls,
      failed: (error) => controls('Exploration paused: ' + error.message),
    });
    const duration = (id) => Number($(id).value) * 1000;
    const animated = (ms) => (reduced.matches ? 0 : ms);
    function stage(name, ms, paint, done, moving = true) {
      phase = name;
      panel.dataset.phase = name;
      session.play(ms, paint, done, moving);
      controls();
    }
    function panelOpacity(value) {
      const card = $('idle-card');
      card.hidden = !committed?.card;
      card.style.opacity = String(value);
      card.style.visibility = value > 0 ? 'visible' : 'hidden';
      card.inert = value === 0;
    }
    function controls(message) {
      $('idle-toggle').textContent = session.running
        ? 'Pause'
        : policy?.current
          ? 'Resume'
          : 'Start';
      $('idle-toggle').setAttribute('aria-pressed', String(session.running));
      $('idle-state').textContent =
        message ||
        (session.suspended && session.running
          ? 'Paused while hidden'
          : session.running
            ? {
                focus: 'Observing',
                reading: 'Reading',
                travel: 'Following a connection',
                region: 'New starting point',
                reveal: 'Revealing knowledge',
                farewell: 'Continuing',
              }[phase] || 'Exploring'
            : policy?.current
              ? 'Paused'
              : 'Ready');
      noteToggle.disabled = filters.status === 'Accepted';
      $('idle-read').disabled = !committed?.card;
      $('idle-toggle').disabled = phase === 'waiting';
    }
    function textFor(note) {
      const body = index.model.bodies[note.body],
        html = body?.html?.[note.format];
      if (!html) return body?.text;
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const block = doc.body.querySelector('p, blockquote, ul, ol, pre, table');
      block?.querySelectorAll('br').forEach((br) => br.replaceWith('\n'));
      return block?.textContent?.trim() || body.text;
    }
    function build() {
      policy = LibraryIdleModel.create(index, { filters: { ...filters }, seed: tourSeed, textFor });
    }
    function updateWindow() {
      const url = new URL(location.href);
      url.hash = new URLSearchParams({ view: 'idle', filters: JSON.stringify(filters) });
      $('idle-window').href = url.href;
    }
    function reconfigure() {
      const running = session.running,
        preferred = policy?.current || seed;
      session.stop();
      cooldown = null;
      updateWindow();
      if (!policy) {
        controls();
        return;
      }
      build();
      const step = policy.choose(preferred);
      if (step) {
        settle(sceneFor(step));
        beginFocus();
        session.hidden(document.hidden);
        if (running) session.start();
      } else empty();
    }
    function empty() {
      committed = null;
      scene = null;
      canvas.hidden = true;
      $('idle-card').hidden = true;
      $('idle-welcome').hidden = false;
      $('idle-welcome').querySelector('h2').textContent = 'No records match these filters';
      $('idle-welcome').querySelector('p').textContent =
        'Try another theme or relationship filter. Your notes are still available in Library.';
      $('idle-connection').textContent = '';
      $('idle-counts').textContent = '';
      controls('No matching content · waiting');
    }
    function card(view) {
      const c = view.card || { label: '', text: '', qualification: '', sources: [] },
        node = index.byId.get(view.id);
      $('idle-welcome').hidden = true;
      $('idle-card').hidden = !view.card;
      $('idle-title').textContent = node.title;
      $('idle-card-kind').textContent = c.label;
      $('idle-excerpt').textContent = c.text;
      $('idle-qualification').textContent = c.qualification;
      $('idle-attribution').textContent = view.card
        ? `${c.title} · ${c.curated ? 'Curator' : 'Author'}: ${c.author}`
        : '';
      const authors = [
        ...new Set(
          c.sources
            .map((pin) => pin.author || index.model.sources?.[pin.revision]?.author)
            .filter(Boolean),
        ),
      ];
      $('idle-sources').textContent =
        c.curated && authors.length ? 'Original sources: ' + authors.join(', ') : '';
      const edge = view.edge;
      $('idle-connection').textContent = edge
        ? `${index.byId.get(edge.from).title} → ${edge.label} → ${index.byId.get(edge.to).title} · ${edge.navigation ? 'Saved navigation' : `${edge.status} · ${edge.origin}`}`
        : {
            start: 'A starting point',
            region: 'New region · no connecting step',
            restart: 'New starting point · restarting sequence',
          }[view.kind];
      if (c.relationship)
        $('idle-qualification').textContent = [c.relationship, c.qualification]
          .filter(Boolean)
          .join('\n');
      $('idle-counts').textContent =
        `${view.scene.nodes.length} records · ${view.scene.edges.length} connections` +
        (view.scene.omitted || view.scene.hiddenEdges
          ? ` · ${view.scene.omitted} neighbours and ${view.scene.hiddenEdges} connections omitted`
          : '');
    }
    function sceneFor(step) {
      const previous = step.edge ? policy.current : null;
      const neighbourhood = index.neighbourhood(
        {
          seed: step.id,
          hops: Number($('idle-depth').value),
          filters,
          preferred: previous ? [previous] : [],
        },
        { nodes: 20, edges: 40 },
      );
      if (step.edge && !neighbourhood.edges.some((e) => e.id === step.edge.id)) {
        if (neighbourhood.edges.length >= 40) {
          neighbourhood.edges.pop();
          neighbourhood.hiddenEdges++;
        }
        neighbourhood.edges.unshift(step.edge);
      }
      return {
        ...step,
        scene: neighbourhood,
        layout: geography.place(neighbourhood, step.id),
        card: policy.cards.get(step.id),
      };
    }
    function camera(point) {
      cameraPoint = point;
      const bounds = $('idle-stage').getBoundingClientRect();
      graph.network.moveTo({
        position: point,
        scale: bounds.width > 700 ? 0.95 : 0.75,
        offset: {
          x: bounds.width > 700 ? Math.min(220, bounds.width * 0.15) : 0,
          y: bounds.width > 700 ? -30 : -bounds.height * 0.22,
        },
        animation: false,
      });
    }
    function render(view, selected = view.id, edge = view.edge?.id) {
      scene = view.scene;
      graph.showIdle(scene, view.layout, selected, edge);
    }
    function settle(view) {
      canvas.style.opacity = '1';
      committed = view;
      target = null;
      policy.commit(view);
      render(view);
      camera(view.layout[view.id]);
      card(view);
      panelOpacity(0);
    }
    function beginFocus() {
      target = null;
      const brighten = animated(Math.min(1400, duration('idle-focus')));
      stage(
        'focus',
        brighten,
        (p) => {
          graph.idleFrame(
            scene,
            () => 1,
            (id) => (id === committed.id ? 0.35 + 0.65 * ease(p) : 0),
          );
        },
        () =>
          stage('focus', Math.max(0, duration('idle-focus') - brighten), () => {}, reveal, false),
      );
    }
    function reveal() {
      if (!committed.card) {
        chooseNext();
        return;
      }
      stage(
        'reveal',
        animated(800),
        (p) => panelOpacity(ease(p)),
        () => stage('reading', duration('idle-reading'), () => panelOpacity(1), chooseNext, false),
      );
    }
    function chooseNext() {
      const step = policy.choose(undefined, new Set(scene.nodes.map((n) => n.id)));
      if (!step) {
        phase = 'waiting';
        panel.dataset.phase = phase;
        session.pause();
        controls('Exploration complete · staying here');
        return;
      }
      const key = `${policy.current}:${step.id}`;
      if (step.cooldown && cooldown !== key) {
        cooldown = key;
        stage('reading', duration('idle-focus'), () => {}, chooseNext, false);
        return;
      }
      target = step.id;
      const next = sceneFor(step);
      stage(
        'farewell',
        animated(committed.card ? 800 : 0),
        (p) => panelOpacity(1 - ease(p)),
        () => {
          if (step.edge) travel(next);
          else changeRegion(next);
        },
      );
    }
    function travel(next) {
      const old = committed;
      // If a cap omitted the chosen neighbour, reveal its actual edge before moving.
      const missing = !old.scene.nodes.some((n) => n.id === next.id);
      const departure = missing
        ? merge(old.scene, {
            ...old.scene,
            nodes: [index.byId.get(next.id)],
            edges: [next.edge],
          })
        : old.scene;
      const departureLayout = { ...old.layout, [next.id]: next.layout[next.id] };
      const start = () => {
        const union = merge(departure, next.scene);
        const oldIDs = new Set(departure.nodes.map((n) => n.id));
        const nextIDs = new Set(next.scene.nodes.map((n) => n.id));
        const initial = {
          ...union,
          nodes: union.nodes.map((n) => ({ ...n, opacity: oldIDs.has(n.id) ? 1 : 0 })),
          edges: union.edges.map((e) => ({
            ...e,
            opacity: oldIDs.has(e.from) && oldIDs.has(e.to) ? 1 : 0,
          })),
        };
        render({ ...next, scene: initial, layout: { ...departureLayout, ...next.layout } }, old.id);
        const from = positions.get(old.id),
          to = positions.get(next.id);
        card({ ...old, scene: union, edge: next.edge });
        panelOpacity(0);
        stage(
          'travel',
          animated(duration('idle-travel')),
          (p) => {
            const t = ease(p),
              entering = ease((p - 0.45) / 0.55),
              leaving = 1 - ease((p - 0.3) / 0.7);
            const opacity = (id) => {
              if (id === old.id || id === next.id || (oldIDs.has(id) && nextIDs.has(id))) return 1;
              return oldIDs.has(id) ? leaving : entering;
            };
            graph.idleFrame(
              union,
              opacity,
              (id) => (id === old.id ? 1 - t : id === next.id ? 0.35 * t : 0),
              next.edge.id,
            );
            camera({ x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t });
          },
          () => {
            cooldown = null;
            settle(next);
            beginFocus();
          },
        );
      };
      if (!missing) {
        start();
        return;
      }
      render(
        {
          ...old,
          scene: {
            ...departure,
            nodes: departure.nodes.map((n) => ({ ...n, opacity: n.id === next.id ? 0 : 1 })),
            edges: departure.edges.map((e) => ({ ...e, opacity: e.id === next.edge.id ? 0 : 1 })),
          },
          layout: departureLayout,
        },
        old.id,
        next.edge.id,
      );
      stage(
        'reveal',
        animated(1800),
        (p) =>
          graph.idleFrame(
            departure,
            (id) => (id === next.id ? ease(p) : 1),
            (id) => (id === old.id ? 1 : 0),
            next.edge.id,
          ),
        start,
      );
    }
    function changeRegion(next) {
      let replaced = false;
      stage(
        'region',
        animated(4000),
        (p) => {
          canvas.style.opacity = String(p < 0.5 ? 1 - ease(p * 2) : ease((p - 0.5) * 2));
          if (p >= 0.5 && !replaced) {
            render(next, next.id, null);
            camera(next.layout[next.id]);
            card(next);
            panelOpacity(0);
            replaced = true;
          }
        },
        () => {
          canvas.style.opacity = '1';
          cooldown = null;
          settle(next);
          beginFocus();
        },
      );
    }
    function toggle() {
      if (!active) return;
      if (session.running) {
        session.pause();
        return;
      }
      try {
        if (!policy) build();
        if (!policy.current) {
          const step = policy.choose(seed);
          if (!step) {
            empty();
            return;
          }
          settle(sceneFor(step));
          beginFocus();
        }
        session.start();
      } catch (error) {
        session.pause();
        controls('Exploration paused: ' + error.message);
      }
    }
    function enter(options) {
      active = true;
      tourSeed = crypto.getRandomValues(new Uint32Array(1))[0];
      seed = options.seed;
      filters = { ...options.filters };
      for (const [key, select] of filterInputs)
        select.value = filters[key] || (['status', 'origin'].includes(key) ? 'all' : '');
      noteToggle.checked = filters.showNotes !== false;
      graph.setActive(false);
      $('idle-stage').prepend(canvas);
      canvas.hidden = true;
      $('idle-card').hidden = true;
      $('idle-welcome').hidden = false;
      $('idle-welcome').querySelector('h2').textContent = 'Let your knowledge reveal itself';
      $('idle-welcome').querySelector('p').textContent =
        'Follow your existing connections at an unhurried pace. Choose Start when you’re ready.';
      $('idle-connection').textContent = '';
      $('idle-counts').textContent = '';
      $('idle-snapshot').textContent =
        $('snapshot-time').textContent + ' · Existing knowledge only · Space to pause';
      updateWindow();
      session.hidden(document.hidden);
      controls();
    }
    function leave() {
      session.stop();
      active = false;
      home.after(canvas);
      canvas.style.opacity = '1';
      graph.leaveIdle();
      geography.clear();
      scene = null;
      cameraPoint = null;
      phase = 'ready';
      target = null;
      policy = null;
      committed = null;
      cooldown = null;
      if (document.fullscreenElement === panel) document.exitFullscreen().catch(() => {});
    }
    $('idle-toggle').addEventListener('click', toggle);
    $('idle-exit').addEventListener('click', exit);
    $('idle-depth').addEventListener('change', reconfigure);
    $('idle-read').addEventListener('click', () => {
      session.pause();
      if (committed?.card) read(committed.card);
    });
    $('idle-card').addEventListener('focusin', () => {
      if (session.running) session.pause();
    });
    $('idle-fullscreen').addEventListener('click', async () => {
      try {
        if (document.fullscreenElement === panel) await document.exitFullscreen();
        else if (panel.requestFullscreen) await panel.requestFullscreen();
        else controls('Full screen is unavailable; use this window instead');
      } catch {
        controls('Full screen was not allowed; use this window instead');
      }
    });
    document.addEventListener('fullscreenchange', () => {
      if (!document.fullscreenElement) leftFullscreenAt = performance.now();
      $('idle-fullscreen').textContent =
        document.fullscreenElement === panel ? 'Leave full screen' : 'Full screen';
    });
    new ResizeObserver(() => {
      if (active && cameraPoint && !canvas.hidden) camera(cameraPoint);
    }).observe($('idle-stage'));
    document.addEventListener('visibilitychange', () => {
      if (active) session.hidden(document.hidden);
    });
    window.addEventListener('pagehide', () => {
      if (active) session.hidden(true);
    });
    window.addEventListener('pageshow', () => {
      if (active) session.hidden(document.hidden);
    });
    reduced.addEventListener('change', () => {
      if (active) {
        if (reduced.matches) session.snap();
      }
    });
    panel.addEventListener('keydown', (event) => {
      if (
        event.key === 'Escape' &&
        !document.fullscreenElement &&
        performance.now() - leftFullscreenAt > 250
      ) {
        event.preventDefault();
        exit();
      }
      if (event.code === 'Space' && !event.target.closest('button, input, select, a, summary')) {
        event.preventDefault();
        toggle();
      }
    });
    return {
      enter,
      leave,
      pause: () => session.pause(),
      get active() {
        return active;
      },
      get state() {
        return {
          current: policy?.current || null,
          running: session.running,
          suspended: session.suspended,
          pending: session.pending,
          animating: session.animating,
          phase,
          progress: session.progress,
          target,
          cachedPositions: positions.size,
          visible: scene?.nodes.length || 0,
          edges: scene?.edges.length || 0,
        };
      },
    };
  }
  return { create };
})();
