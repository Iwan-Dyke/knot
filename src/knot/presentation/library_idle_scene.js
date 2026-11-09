/* Disposable map geography: coordinates survive every visit, never knowledge edits. */
const LibraryIdleScene = (() => {
  const ease = (t) => {
    t = Math.max(0, Math.min(1, t));
    return t * t * t * (t * (t * 6 - 15) + 10);
  };
  function geography() {
    const positions = new Map(),
      occupied = new Set();
    let regions = 0;
    function place(scene, seed) {
      const neighbours = new Map(scene.nodes.map((n) => [n.id, []]));
      for (const edge of scene.edges) {
        neighbours.get(edge.from)?.push(edge.to);
        neighbours.get(edge.to)?.push(edge.from);
      }
      for (const node of scene.nodes) {
        if (positions.has(node.id)) continue;
        const parent = (neighbours.get(node.id) || []).find((id) => positions.has(id));
        const origin = positions.get(parent) ||
          positions.get(seed) || { x: regions++ * 12800, y: 0 };
        let hash = 0;
        for (const c of node.id) hash = Math.imul(hash ^ c.codePointAt(0), 16777619) >>> 0;
        let point;
        // A sparse grid keeps new labels apart without ever moving existing nodes.
        for (let radius = 0; !point; radius++) {
          const slots = [];
          for (let x = -radius; x <= radius; x++)
            for (let y = -radius; y <= radius; y++)
              if (Math.max(Math.abs(x), Math.abs(y)) === radius) slots.push({ x, y });
          for (let i = 0; i < slots.length; i++) {
            const slot = slots[(i + hash) % slots.length];
            const candidate = { x: origin.x + slot.x * 320, y: origin.y + slot.y * 240 };
            const key = `${candidate.x},${candidate.y}`;
            if (!occupied.has(key)) {
              occupied.add(key);
              point = candidate;
              break;
            }
          }
        }
        positions.set(node.id, point);
      }
      return Object.fromEntries(scene.nodes.map((n) => [n.id, positions.get(n.id)]));
    }
    return {
      place,
      positions,
      clear() {
        positions.clear();
        occupied.clear();
        regions = 0;
      },
    };
  }
  function merge(old, next) {
    return {
      ...next,
      nodes: [...new Map([...old.nodes, ...next.nodes].map((n) => [n.id, n])).values()],
      edges: [...new Map([...old.edges, ...next.edges].map((e) => [e.id, e])).values()],
    };
  }
  return { ease, geography, merge };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = LibraryIdleScene;
