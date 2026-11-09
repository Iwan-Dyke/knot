/* Layout geometry and motion own no knowledge or navigation state. */
const LibraryLayout = (() => {
  function scalePositions(positions, ratio, anchor) {
    const centre = positions[anchor] || { x: 0, y: 0 };
    return Object.fromEntries(
      Object.entries(positions).map(([id, point]) => [
        id,
        {
          x: centre.x + (point.x - centre.x) * ratio,
          y: centre.y + (point.y - centre.y) * ratio,
        },
      ]),
    );
  }
  function create(network) {
    let previous = '';
    return {
      update(enabled, spacing = 100, focused = false) {
        const key = `${enabled}:${spacing}:${focused}`;
        if (key === previous) return;
        previous = key;
        const scale = spacing / 100;
        network.setOptions({
          physics: {
            enabled,
            solver: 'barnesHut',
            stabilization: { enabled: false, fit: false },
            barnesHut: {
              springLength: 170 * scale,
              // A bounded neighbourhood needs room for labels around a highly
              // connected centre; full-network forces retain their existing scale.
              gravitationalConstant: (focused ? -50000 : -6000) * scale * scale,
              avoidOverlap: focused ? 1 : 0,
            },
          },
        });
        if (enabled) network.startSimulation();
        else network.stopSimulation();
      },
    };
  }
  return { create, scalePositions };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = LibraryLayout;
