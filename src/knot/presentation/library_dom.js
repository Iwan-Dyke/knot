/* DOM primitives keep evidence and record labels literal. */
const LibraryDOM = (() => {
  const element = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  const button = (text, action) => {
    const el = element('button', text);
    el.type = 'button';
    el.addEventListener('click', action);
    return el;
  };
  const details = (title, open = false) => {
    const el = element('details');
    el.open = open;
    el.append(element('summary', title));
    return el;
  };
  const section = (parent, title) => {
    const el = element('section', undefined, 'context-section');
    el.append(element('h3', title));
    parent.append(el);
    return el;
  };
  const field = (parent, name, value) => {
    parent.append(element('div', name + ': ' + (value ?? 'Not recorded'), 'metadata'));
  };
  const badge = (text) => element('span', text, 'badge');
  const local = (value) =>
    String(value || '')
      .split(':')
      .at(-1);
  const date = (value) => (value ? new Date(value).toLocaleString() : 'Not recorded');
  function link(record, view, navigate, revision = null) {
    const el = element('a', record.title || record.id);
    const route = { view, id: record.id, revision };
    el.href = LibraryModel.hash(route);
    el.addEventListener('click', (event) => {
      if (!event.ctrlKey && !event.metaKey && !event.shiftKey) {
        event.preventDefault();
        navigate(route);
      }
    });
    return el;
  }
  function paged(parent, items, render, { size = 100, empty = 'None recorded.' } = {}) {
    const content = element('div'),
      controls = element('div', undefined, 'button-row');
    let page = 0;
    parent.append(content, controls);
    const draw = () => {
      content.replaceChildren();
      controls.replaceChildren();
      if (!items.length) content.append(element('p', empty, 'muted'));
      items.slice(page * size, (page + 1) * size).forEach((item) => content.append(render(item)));
      if (items.length > size) {
        const prev = button('Previous', () => {
            page--;
            draw();
          }),
          next = button('Next', () => {
            page++;
            draw();
          });
        prev.disabled = page === 0;
        next.disabled = (page + 1) * size >= items.length;
        controls.append(
          prev,
          element(
            'span',
            `${page * size + 1}–${Math.min(items.length, (page + 1) * size)} of ${items.length}`,
          ),
          next,
        );
      }
    };
    draw();
  }
  return { element, button, details, section, field, badge, local, date, link, paged };
})();
