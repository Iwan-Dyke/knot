/* Optional draft navigation uses the shared note index and literal DOM helpers. */
const LibraryOrganisation = (() => {
  function create(index, request) {
    const $ = (id) => document.getElementById(id),
      { element, button, paged } = LibraryDOM;
    let noteId,
      navigation = { links: [], themes: [] },
      catalogue = null,
      generation = 0;
    const title = (id) => index.byId.get(id)?.title || id;

    function search() {
      const parent = $('editor-link-results');
      parent.replaceChildren();
      const matches = index
        .search($('editor-link-search').value, { role: 'note' })
        .filter(
          ({ record }) =>
            record.id !== noteId && !navigation.links.some((l) => l.note === record.id),
        );
      paged(
        parent,
        matches,
        ({ record, excerpt }) => {
          const row = element('article', undefined, 'editor-choice');
          row.append(
            button('Link ' + record.title, () => {
              navigation.links.push({ note: record.id, reason: '' });
              links();
              search();
              $('editor-links').lastElementChild.querySelector('input').focus();
            }),
            element(
              'p',
              `${record.author || 'Unknown author'} · ${record.kind || 'Unclassified'}`,
              'metadata',
            ),
            element(
              'p',
              excerpt || index.model.bodies[record.body]?.text.slice(0, 165) || 'Empty note.',
            ),
          );
          return row;
        },
        {
          size: 8,
          empty: 'No other matching notes. Refresh Library to include notes saved elsewhere.',
        },
      );
    }

    function links() {
      const parent = $('editor-links');
      parent.replaceChildren();
      for (const link of navigation.links) {
        const row = element('article', undefined, 'editor-choice'),
          label = element('label', `Why connect to ${title(link.note)}?`),
          reason = element('input');
        reason.type = 'text';
        reason.required = true;
        reason.value = link.reason;
        reason.addEventListener('input', () => {
          link.reason = reason.value;
          reason.setCustomValidity('');
        });
        label.append(reason);
        row.append(
          label,
          button('Remove link to ' + title(link.note), () => {
            navigation.links = navigation.links.filter((l) => l !== link);
            links();
            search();
            $('editor-link-search').focus();
          }),
        );
        parent.append(row);
      }
    }

    function themes() {
      const parent = $('editor-themes');
      parent.replaceChildren();
      // Saved labels are evidence of the selection at that revision, not catalogue edits.
      const choices = [...navigation.themes];
      for (const theme of catalogue || [])
        if (!choices.some((t) => t.id === theme.id))
          choices.push({ id: theme.id, label: theme.label });
      for (const theme of choices) {
        const label = element('label', undefined, 'editor-theme'),
          checkbox = element('input'),
          current = catalogue?.find((t) => t.id === theme.id),
          selected = navigation.themes.some((t) => t.id === theme.id);
        checkbox.type = 'checkbox';
        checkbox.checked = selected;
        checkbox.addEventListener('change', () => {
          if (checkbox.checked) navigation.themes.push({ id: theme.id, label: theme.label });
          else navigation.themes = navigation.themes.filter((t) => t.id !== theme.id);
          themes();
          Array.from(parent.querySelectorAll('input'))
            .find((input) => input.value === theme.id)
            ?.focus();
        });
        checkbox.value = theme.id;
        label.append(checkbox, element('span', theme.label));
        parent.append(label);
        if (selected && catalogue !== null && current?.label !== theme.label)
          parent.append(
            element(
              'p',
              current
                ? `Saved as “${theme.label}”; now named “${current.label}”. Remove and reselect to use the current name.`
                : `“${theme.label}” is no longer in the catalogue. Its saved membership is retained.`,
              'metadata',
            ),
          );
      }
      if (catalogue !== null && !choices.length)
        parent.append(element('p', 'No themes in this catalogue.', 'muted'));
    }

    async function loadThemes() {
      const sequence = ++generation;
      $('editor-theme-status').textContent = 'Loading theme choices…';
      $('editor-theme-retry').hidden = true;
      try {
        const result = await request('themes');
        if (sequence !== generation) return;
        catalogue = result.themes;
        themes();
        $('editor-theme-status').textContent = '';
      } catch (error) {
        if (sequence !== generation) return;
        $('editor-theme-status').textContent =
          'Theme choices unavailable. Saved memberships are retained. ' + error.message;
        $('editor-theme-retry').hidden = false;
      }
    }

    function reset(note) {
      noteId = note.note;
      navigation = JSON.parse(
        JSON.stringify({
          links: note.navigation?.links || [],
          themes: note.navigation?.themes || [],
        }),
      );
      catalogue = null;
      $('editor-organisation').open = false;
      $('editor-link-search').value = '';
      links();
      search();
      themes();
      void loadThemes();
    }

    function valid() {
      const inputs = $('editor-links').querySelectorAll('input');
      for (let i = 0; i < navigation.links.length; i++) {
        if (!navigation.links[i].reason.trim()) {
          $('editor-organisation').open = true;
          inputs[i].setCustomValidity('Explain why these notes are connected.');
          inputs[i].reportValidity();
          inputs[i].focus();
          return false;
        }
      }
      return true;
    }

    function comparison(value) {
      const parent = $('editor-current-navigation');
      parent.replaceChildren(element('h4', 'Saved connections and themes'));
      for (const link of value?.links || [])
        parent.append(element('p', `${title(link.note)}: ${link.reason}`));
      parent.append(
        element('p', 'Themes: ' + (value?.themes || []).map((t) => t.label).join(', ')),
      );
    }

    $('editor-link-search').addEventListener('input', search);
    $('editor-theme-retry').addEventListener('click', loadThemes);
    return {
      reset,
      valid,
      comparison,
      value: () => navigation,
      lock: (locked) => {
        $('editor-organisation-fields').disabled = locked;
      },
    };
  }
  return { create };
})();
