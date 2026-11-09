/* Read-only tour policy and a cancellable phase clock, independent of the DOM. */
const LibraryIdleModel = (() => {
  function excerpt(text, qualification = '') {
    const blocks = (text || '').trim().split(/\n\s*\n/);
    const first = blocks.find(
      (p) => p.trim() && !/^(?:#{1,6}\s|\*+\s|#\+|```|~~~|:PROPERTIES:)/.test(p),
    );
    if (!first || first.length + qualification.length > 1200) return null;
    return first.trim();
  }
  function create(
    index,
    { filters = {}, seed = 1, textFor = (n) => index.model.bodies[n.body]?.text } = {},
  ) {
    const { model } = index,
      eligible = index.eligible(filters);
    const allowed = new Set(eligible.nodes.map((n) => n.id));
    const claimIDs = new Set([...eligible.connections, ...eligible.attributes].map((c) => c.id));
    const cards = new Map(),
      components = new Map(),
      visits = new Map(),
      lastVisit = new Map();
    let current = null,
      recent = [],
      chain = new Set(),
      serial = 0;
    const noteCard = (note) => {
      if (filters.theme && !note.navigation.themes.some((t) => t.id === filters.theme)) return null;
      if (filters.kind && (note.kind || 'Unspecified') !== filters.kind) return null;
      const qualification = note.qualification || '',
        text = excerpt(textFor(note), qualification);
      if (!text) return null;
      return {
        text,
        qualification,
        title: note.title,
        author: note.author || 'Unknown',
        sourceId: note.id,
        revision: note.revision,
        curated: !!note.method,
        label: note.method
          ? `Curated excerpt · ${note.method.replaceAll('_', ' ')}`
          : 'Authored excerpt · not claim acceptance',
        sources: note.sources || [],
      };
    };
    const noteCards = new Map(Object.values(model.notes).map((n) => [n.id, noteCard(n)]));
    for (const node of eligible.nodes) {
      let card = node.role === 'note' ? noteCards.get(node.id) : null;
      if (node.role !== 'note') {
        const candidates = (index.associated.get(node.id) || [])
          .map((id) => noteCards.get(id))
          .filter(Boolean);
        candidates.sort(
          (a, b) => Number(b.curated) - Number(a.curated) || a.sourceId.localeCompare(b.sourceId),
        );
        card = candidates[0];
      }
      if (!card) {
        for (const claim of index.claimIndex.get(node.id) || []) {
          if (!claimIDs.has(claim.id)) continue;
          const qualification = (claim.evidence_accounts || [])
            .map((q) => JSON.stringify(q))
            .join('\n');
          for (const pin of claim.evidence || []) {
            if (!pin.quote?.trim() || pin.quote.length + qualification.length > 1200) continue;
            const source = model.sources?.[pin.revision];
            if (!source) continue;
            card = {
              text: pin.quote,
              qualification,
              title: source.title,
              author: source.author || 'Unknown',
              sourceId: source.note || pin.revision,
              revision: pin.revision,
              curated: false,
              label: `Claim evidence · ${claim.status} · ${claim.origin}`,
              relationship: `${claim.subject.label} → ${claim.predicate?.split(/[#/]/).pop() || 'relationship'} → ${claim.object.label}`,
              sources: [pin],
            };
            break;
          }
          if (card) break;
        }
      }
      if (card) cards.set(node.id, card);
    }
    // Components are navigation indexes over the filtered graph, never new relationships.
    for (const id of allowed) {
      if (components.has(id)) continue;
      const queue = [id];
      components.set(id, id);
      for (let i = 0; i < queue.length; i++) {
        for (const edge of eligible.adjacent.get(queue[i]) || []) {
          const next = edge.from === queue[i] ? edge.to : edge.from;
          if (!components.has(next)) {
            components.set(next, id);
            queue.push(next);
          }
        }
      }
    }
    const degree = (id) => (eligible.adjacent.get(id) || []).length;
    const tie = (id) => {
      let h = seed >>> 0;
      for (const c of id) h = Math.imul(h ^ c.codePointAt(0), 16777619) >>> 0;
      return h;
    };
    const rank = (a, b) =>
      Number(!!cards.get(b)?.curated) - Number(!!cards.get(a)?.curated) ||
      Number(cards.has(b)) - Number(cards.has(a)) ||
      (visits.get(a) || 0) - (visits.get(b) || 0) ||
      degree(a) - degree(b) ||
      tie(a) - tie(b) ||
      a.localeCompare(b);
    const kinds = new Map(model.relations.map((r) => [r.id, r.kind]));
    const tier = (e) =>
      e.navigation
        ? kinds.get(e.id) === 'link'
          ? 0
          : 1
        : e.status === 'Accepted' && e.origin === 'Explicit'
          ? 0
          : 2;
    const tiers = new Map(eligible.connections.map((e) => [e.id, tier(e)]));
    function choose(preferred, visible) {
      const ids = [...allowed];
      if (!current) {
        const linked = ids.filter((id) =>
          (eligible.adjacent.get(id) || []).some(
            (e) => allowed.has(e.from === id ? e.to : e.from) && e.from !== e.to,
          ),
        );
        const id = allowed.has(preferred)
          ? preferred
          : (linked.length ? linked : ids).sort(rank)[0];
        return id ? { id, kind: 'start', edge: null } : null;
      }
      const choices = new Map();
      for (const edge of eligible.adjacent.get(current) || []) {
        const id = edge.from === current ? edge.to : edge.from;
        if (!allowed.has(id) || chain.has(id)) continue;
        if (!choices.has(id) || tiers.get(edge.id) < tiers.get(choices.get(id).edge.id))
          choices.set(id, { id, edge, kind: 'follow' });
      }
      // Recency prefers another branch; only this chain's visited set ends a path.
      const best = [...choices.values()].sort(
        (a, b) =>
          Number(!!visible && !visible.has(a.id)) - Number(!!visible && !visible.has(b.id)) ||
          tiers.get(a.edge.id) - tiers.get(b.edge.id) ||
          Number(recent.includes(a.id)) - Number(recent.includes(b.id)) ||
          rank(a.id, b.id),
      )[0];
      if (best) return best;
      const others = ids.filter((id) => id !== current);
      if (!others.length) return null;
      const fresh = others.filter((id) => !recent.includes(id));
      const different = fresh.filter((id) => components.get(id) !== components.get(current));
      const starts = different.length ? different : fresh;
      if (starts.length) {
        starts.sort(rank);
        return { id: starts[0], kind: different.length ? 'region' : 'restart', edge: null };
      }
      others.sort((a, b) => (lastVisit.get(a) || 0) - (lastVisit.get(b) || 0) || rank(a, b));
      return { id: others[0], kind: 'restart', edge: null, cooldown: true };
    }
    function commit(step) {
      if (!step || !allowed.has(step.id)) return;
      if (step.kind !== 'follow') chain.clear();
      chain.add(step.id);
      current = step.id;
      recent = [...recent, current].slice(-12);
      visits.set(current, (visits.get(current) || 0) + 1);
      lastVisit.set(current, ++serial);
    }
    return {
      cards,
      choose,
      commit,
      filters,
      get current() {
        return current;
      },
      get recent() {
        return [...recent];
      },
      get chain() {
        return [...chain];
      },
    };
  }
  // One phase clock freezes elapsed time and the rendered frame together on pause.
  function playback({
    changed = () => {},
    failed = () => {},
    clock = {
      now: () => performance.now(),
      frame: (fn) => requestAnimationFrame(fn),
      cancelFrame: (id) => cancelAnimationFrame(id),
      wait: (fn, ms) => setTimeout(fn, ms),
      cancelWait: (id) => clearTimeout(id),
    },
  } = {}) {
    let phase = null,
      handle = null,
      anchor = null,
      running = false,
      suspended = false,
      generation = 0;
    function cancel() {
      generation++;
      if (handle !== null) (phase?.animated ? clock.cancelFrame : clock.cancelWait)(handle);
      handle = null;
      anchor = null;
    }
    function progress() {
      return Math.min(1, phase.elapsed / phase.duration);
    }
    function sample() {
      if (!phase || anchor === null) return;
      const now = clock.now();
      // A delayed animation frame must not teleport after machine sleep or a busy tab.
      phase.elapsed += Math.min(now - anchor, phase.animated ? 100 : Infinity);
      anchor = now;
      phase.paint(progress());
    }
    function freeze() {
      sample();
      cancel();
    }
    function finish() {
      if (!phase) return;
      const done = phase.done;
      cancel();
      phase.paint(1);
      phase = null;
      done();
    }
    function tick() {
      handle = null;
      if (!running || suspended || !phase) return;
      try {
        sample();
        if (phase.elapsed >= phase.duration) finish();
        else schedule();
      } catch (error) {
        cancel();
        running = false;
        failed(error);
      }
    }
    function schedule() {
      if (!running || suspended || !phase || handle !== null) return;
      anchor ??= clock.now();
      const token = generation;
      const callback = () => {
        if (token === generation) tick();
      };
      handle = phase.animated
        ? clock.frame(callback)
        : clock.wait(callback, Math.max(0, phase.duration - phase.elapsed));
    }
    return {
      play(duration, paint, done, animated = true) {
        cancel();
        phase = { duration, elapsed: 0, paint, done, animated };
        if (!duration) finish();
        else {
          paint(0);
          schedule();
        }
      },
      start() {
        running = !!phase;
        schedule();
        changed();
      },
      pause() {
        freeze();
        running = false;
        changed();
      },
      hidden(value) {
        freeze();
        suspended = value;
        schedule();
        changed();
      },
      stop() {
        cancel();
        phase = null;
        running = false;
        suspended = false;
        changed();
      },
      snap() {
        if (phase?.animated) finish();
      },
      get running() {
        return running;
      },
      get suspended() {
        return suspended;
      },
      get pending() {
        return handle !== null;
      },
      get animating() {
        return handle !== null && phase?.animated;
      },
      get progress() {
        return phase ? progress() : 0;
      },
    };
  }
  return { create, excerpt, playback };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = LibraryIdleModel;
