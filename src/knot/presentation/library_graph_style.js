/* Complete render styles reset properties when the shared canvas changes mode. */
const LibraryGraphStyle = (() => {
  function frameNode(id, opacity, strength) {
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
  function edgeColor(opacity, highlighted) {
    return { color: '#42bb87', opacity: opacity * (highlighted ? 0.95 : 0.5) };
  }
  function nodeBase(n) {
    return {
      id: n.id,
      size: 14,
      fixed: false,
      chosen: true,
      opacity: 1,
      shadow: { enabled: false },
      widthConstraint: { maximum: 240 },
      margin: 10,
    };
  }
  function edgeBase(e) {
    return {
      id: e.id,
      from: e.from,
      to: e.to,
      label: e.label,
      arrows: { to: { enabled: true, scaleFactor: 1 } },
      chosen: true,
      dashes: e.navigation ? [6, 4] : e.origin === 'Inferred',
      smooth: { enabled: true, type: 'curvedCW', roundness: 0.12 },
    };
  }
  function create(palette) {
    const colors = palette.colors;
    return {
      manual: {
        node(n, selected) {
          const note = n.role === 'note';
          return {
            ...nodeBase(n),
            label: n.title + '\n' + (note ? 'Note' : n.entityTypes.join(' · ')),
            shape: note ? 'box' : 'dot',
            color: note ? colors.note : { background: colors.entity, border: colors.accent },
            font: {
              color: note ? colors['note-text'] : colors.text,
              face: palette.fonts.graph,
              size: 13,
            },
            borderWidth: n.id === selected ? 3 : 1,
          };
        },
        edge(e) {
          return {
            ...edgeBase(e),
            color: {
              color: e.navigation
                ? colors.navigation
                : e.status === 'Accepted'
                  ? colors.accepted
                  : colors.unreviewed,
              opacity: 1,
            },
            width: e.status === 'Accepted' ? 2 : 1,
            font: { color: colors['edge-text'], size: 10, strokeWidth: 0, align: 'middle' },
          };
        },
      },
      idle: {
        node(n, selected) {
          return {
            ...nodeBase(n),
            label: n.title,
            shape: 'dot',
            fixed: true,
            chosen: false,
            ...frameNode(n.id, n.opacity ?? 1, n.id === selected ? 1 : 0),
          };
        },
        edge(e, highlighted) {
          return {
            ...edgeBase(e),
            label: e.id === highlighted ? e.label : ' ',
            arrows: { to: { enabled: true, scaleFactor: 0.45 } },
            chosen: false,
            color: edgeColor(e.opacity ?? 1, e.id === highlighted),
            width: e.id === highlighted ? 1.8 : 0.8,
            font: { color: '#a1d9bd', size: 13, strokeWidth: 0, align: 'middle' },
            smooth: { enabled: false, type: 'curvedCW', roundness: 0.12 },
          };
        },
        frameNode,
        frameEdge(e, opacity, highlighted) {
          return {
            id: e.id,
            color: edgeColor(Math.min(opacity(e.from), opacity(e.to)), e.id === highlighted),
          };
        },
      },
    };
  }
  return { create };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = LibraryGraphStyle;
