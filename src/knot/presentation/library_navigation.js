/* Route decisions are pure; this controller owns history and view lifecycle effects. */
const LibraryNavigation = (() => {
  function transition(current, route, manual = null) {
    if (route.view === 'idle' && current.view === 'idle')
      return { kind: 'stay', selection: { ...current } };
    if (current.view === 'idle' && route.view && route.view !== 'idle')
      return {
        kind: 'leave',
        history: 'replace',
        selection: {
          view: route.view,
          id: route.id ?? manual?.id ?? null,
          revision: route.revision ?? (route.view === 'library' ? manual?.revision : null) ?? null,
        },
      };
    return {
      kind: route.view === 'idle' ? 'enter' : 'navigate',
      history: 'push',
      selection: {
        view: route.view || current.view,
        id: route.id ?? null,
        revision: route.revision || null,
      },
    };
  }
  function create(index, graph, { idle, capture, apply, render, resetReader, resetScroll, visit }) {
    const $ = (id) => document.getElementById(id),
      model = index.model,
      sessions = new Map(),
      currentRoute = () => LibraryModel.route(location.hash, model.initial_record);
    let selection = currentRoute(),
      idleReturn = null,
      idleFocus = null,
      serial = 0,
      restoring = false;

    function save() {
      if (restoring || selection.view === 'idle') return;
      const key = history.state?.knotKey;
      if (key !== undefined) sessions.set(key, structuredClone(capture()));
    }
    function applyState(saved) {
      selection = { ...saved.selection };
      apply(structuredClone(saved));
    }
    function leaveIdle() {
      if (!idle().active) return false;
      idle().leave();
      if (idleReturn) applyState(idleReturn);
      idleReturn = null;
      return true;
    }
    function restoreFocus() {
      (idleFocus?.isConnected ? idleFocus : $('main-panel')).focus({ preventScroll: true });
    }
    function paint() {
      if (selection.view !== 'idle') visit(selection.id);
      render();
      if (selection.view !== 'idle' || idle().active) return;
      let filters = idleReturn?.graph.filters || {};
      const encoded = new URLSearchParams(location.hash.slice(1)).get('filters');
      if (encoded) {
        try {
          const supplied = JSON.parse(encoded);
          filters = Object.fromEntries(
            ['status', 'origin', 'theme', 'kind', 'type', 'showNotes']
              .filter(
                (key) => typeof supplied?.[key] === (key === 'showNotes' ? 'boolean' : 'string'),
              )
              .map((key) => [key, supplied[key]]),
          );
        } catch {
          /* Invalid display settings cannot change the dataset or its scope. */
        }
      }
      idle().enter({ seed: idleReturn?.selection.id, filters });
    }
    function navigate(route, { focus = false } = {}) {
      const plan = transition(selection, route, idleReturn?.selection);
      if (plan.kind === 'stay') return;
      const previous = selection;
      if (plan.kind === 'leave') leaveIdle();
      else save();
      if (plan.kind === 'enter') {
        idleReturn = structuredClone(capture(true));
        idleFocus = document.activeElement;
      }
      const returnKey = plan.kind === 'enter' ? history.state?.knotKey : undefined;
      selection = plan.selection;
      history[plan.history + 'State'](
        { knotKey: ++serial, fingerprint: model.manifest.fingerprint, idleReturnKey: returnKey },
        '',
        LibraryModel.hash(selection),
      );
      if (plan.kind === 'leave') {
        resetReader();
        paint();
        save();
        restoreFocus();
        return;
      }
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
      if (previous.id !== selection.id) resetScroll(selection.view);
      paint();
      save();
      const target = selection.view === 'idle' ? $('idle-toggle') : $('selection-title');
      target.tabIndex = selection.view === 'idle' ? 0 : -1;
      target.focus({ preventScroll: true });
    }
    function exitIdle() {
      if (!idle().active) return;
      if (history.state?.idleReturnKey !== undefined && sessions.has(history.state.idleReturnKey))
        history.back();
      else navigate(idleReturn?.selection || { view: 'graph' });
    }
    function restore() {
      const leavingIdle = leaveIdle();
      restoring = true;
      const saved =
        history.state?.fingerprint === model.manifest.fingerprint
          ? sessions.get(history.state?.knotKey)
          : null;
      selection = currentRoute();
      if (selection.view === 'idle') {
        idleReturn = structuredClone(
          sessions.get(history.state?.idleReturnKey) || {
            ...capture(true),
            selection: { view: 'graph', id: null, revision: null },
          },
        );
        paint();
        restoring = false;
        return;
      }
      if (saved) applyState(saved);
      else {
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
      resetReader();
      paint();
      restoring = false;
      save();
      if (leavingIdle) restoreFocus();
    }
    window.addEventListener('popstate', restore);
    window.addEventListener('hashchange', () => {
      if (JSON.stringify(currentRoute()) !== JSON.stringify(selection)) restore();
    });
    return {
      navigate,
      save,
      restore,
      exitIdle,
      switchView(view) {
        const manual = selection.view === 'idle' ? idleReturn?.selection : selection;
        navigate({ view, id: manual?.id, revision: view === 'library' ? manual?.revision : null });
      },
      get selection() {
        return { ...selection };
      },
    };
  }
  return { create, transition };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = LibraryNavigation;
