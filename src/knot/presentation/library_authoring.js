/* Optional local editor. Only the serving process supplies a session capability. */
const LibraryAuthoring = (() => {
  function create(index, { selection, refresh }) {
    const $ = (id) => document.getElementById(id),
      config = index.model.authoring,
      dialog = $('note-editor');
    let draft = null,
      baseline = '',
      busy = false,
      committed = null,
      uncertain = false,
      previewSequence = 0;

    async function request(route, payload) {
      let response;
      try {
        response = await fetch(config.base + route, {
          method: payload === undefined ? 'GET' : 'POST',
          headers: {
            'X-Knot-Session': config.token,
            ...(payload === undefined ? {} : { 'Content-Type': 'application/json' }),
          },
          ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
          cache: 'no-store',
          credentials: 'omit',
        });
      } catch {
        throw new Error(
          'Cannot reach the local session. Your draft is still here; retry when connected.',
        );
      }
      const result = await response.json();
      if (!response.ok)
        throw Object.assign(new Error(result.error || 'The request failed.'), {
          status: response.status,
          current: result.current,
        });
      return result;
    }
    const values = () =>
      JSON.stringify([
        $('editor-title').value,
        $('editor-body').value,
        $('editor-author').value,
        $('editor-format').value,
      ]);
    const dirty = () => dialog.open && values() !== baseline;
    function lock(value) {
      busy = value;
      for (const id of [
        'editor-save',
        'editor-cancel',
        'editor-reload',
        'editor-preview-toggle',
        'editor-title',
        'editor-body',
        'editor-author',
        'editor-format',
      ])
        $(id).disabled = value;
    }
    function populate(note, creating = false) {
      lock(false);
      draft = { ...note, creating };
      committed = null;
      uncertain = false;
      previewSequence++;
      $('editor-title').value = note.title || '';
      $('editor-body').value = note.body;
      $('editor-author').value = note.author || '';
      $('editor-format').value = note.format;
      $('editor-new-fields').hidden = !creating;
      $('editor-heading').textContent = creating ? 'New note' : 'Edit note';
      $('editor-attribution').textContent = creating
        ? 'Write freely. A title and author are optional.'
        : `Author: ${note.author || 'Unknown'} · ${note.format === 'org' ? 'Org' : 'Markdown'} · Earlier revisions are preserved.`;
      $('editor-status').textContent = '';
      $('editor-conflict').hidden = true;
      $('editor-preview').hidden = true;
      $('editor-preview-toggle').setAttribute('aria-expanded', 'false');
      $('editor-save').textContent = 'Save note';
      baseline = values();
      if (!dialog.open) dialog.showModal();
      $('editor-title').focus();
    }
    function body() {
      const entered = $('editor-body').value;
      // Textareas normalise CRLF. Preserve unchanged bytes and an existing CRLF convention.
      if (entered === draft.body.replace(/\r\n?/g, '\n')) return draft.body;
      return draft.body.includes('\r\n') && !/(^|[^\r])\n/.test(draft.body)
        ? entered.replace(/\n/g, '\r\n')
        : entered;
    }
    async function openExisting() {
      if (dialog.open) return;
      const id = selection().id;
      $('authoring-status').textContent = 'Opening current version…';
      try {
        const note = await request('note?' + new URLSearchParams({ note: id }));
        if (dialog.open || selection().id !== id) return;
        populate(note);
        $('authoring-status').textContent = '';
      } catch (error) {
        $('authoring-status').textContent = error.message;
      }
    }
    async function refreshed(note = null) {
      const snapshot = await request('snapshot');
      refresh(snapshot, note);
    }
    async function save() {
      if (busy) return;
      previewSequence++;
      lock(true);
      $('editor-status').textContent = committed ? 'Refreshing Library…' : 'Saving…';
      try {
        if (!committed) {
          const payload = {
            note: draft.note,
            title: $('editor-title').value || null,
            body: body(),
            ...(draft.creating
              ? { author: $('editor-author').value || null, format: $('editor-format').value }
              : { expected: draft.revision }),
          };
          uncertain = true;
          committed = await request(draft.creating ? 'create' : 'save', payload);
          uncertain = false;
        }
        await refreshed(committed.note);
        dialog.close();
        $('authoring-status').textContent = 'Saved.';
      } catch (error) {
        if (committed) {
          $('editor-status').textContent =
            'Your note is saved. Library could not refresh. Retry refresh to display it.';
          $('editor-save').textContent = 'Retry refresh';
        } else {
          if (error.status && error.status < 500) uncertain = false;
          $('editor-status').textContent = error.message;
          if (error.current) {
            $('editor-current-title').textContent = error.current.title || 'Untitled note';
            $('editor-current-body').textContent = error.current.body;
            $('editor-conflict').hidden = false;
          }
        }
      } finally {
        lock(false);
        if (committed && dialog.open) {
          for (const id of ['editor-title', 'editor-body', 'editor-author', 'editor-format'])
            $(id).disabled = true;
        }
      }
    }
    function cancel() {
      if (busy) return;
      const question = uncertain
        ? 'The last save could not be confirmed. Close the editor and check the Library before creating another note?'
        : !committed && dirty()
          ? 'Discard this unsaved draft?'
          : null;
      if (question && !confirm(question)) return;
      uncertain = false;
      previewSequence++;
      dialog.close();
    }
    async function preview() {
      const sequence = ++previewSequence;
      $('editor-status').textContent = 'Preparing preview…';
      try {
        const result = await request('preview', {
          body: body(),
          format: draft.creating ? $('editor-format').value : draft.format,
        });
        if (sequence !== previewSequence || !dialog.open) return;
        $('editor-preview').innerHTML = result.html;
        $('editor-preview').hidden = false;
        $('editor-preview-toggle').setAttribute('aria-expanded', 'true');
        $('editor-status').textContent = 'Preview of your current writing.';
      } catch (error) {
        if (sequence === previewSequence && dialog.open)
          $('editor-status').textContent = error.message;
      }
    }
    function update() {
      const route = selection(),
        note = index.model.notes[route.id];
      $('authoring-controls').hidden = route.view === 'idle';
      $('edit-note').hidden =
        route.view !== 'library' || Boolean(route.revision) || !note || Boolean(note.method);
    }
    $('authoring-controls').hidden = false;
    $('interface-mode').textContent = 'LOCAL LIBRARY · NOTE EDITING ENABLED';
    $('snapshot-help').textContent =
      'Saves refresh this Library. Use Refresh for changes made elsewhere. Keep the local session URL private.';
    $('new-note').addEventListener('click', () => {
      lock(false);
      populate(
        {
          note: 'urn:knot:note:' + crypto.randomUUID(),
          title: null,
          body: '',
          author: null,
          format: 'markdown',
        },
        true,
      );
    });
    $('edit-note').addEventListener('click', openExisting);
    $('editor-save').addEventListener('click', save);
    $('editor-preview-toggle').addEventListener('click', preview);
    $('editor-cancel').addEventListener('click', cancel);
    dialog.addEventListener('cancel', (event) => {
      event.preventDefault();
      cancel();
    });
    $('editor-reload').addEventListener('click', async () => {
      if (busy || !confirm('Discard your draft and load the latest saved version?')) return;
      lock(true);
      try {
        populate(await request('note?' + new URLSearchParams({ note: draft.note })));
      } catch (error) {
        $('editor-status').textContent = error.message;
      } finally {
        lock(false);
      }
    });
    for (const id of ['editor-body', 'editor-format'])
      $(id).addEventListener('input', () => {
        previewSequence++;
        $('editor-preview').hidden = true;
        $('editor-preview-toggle').setAttribute('aria-expanded', 'false');
      });
    $('refresh-library').addEventListener('click', async () => {
      $('refresh-library').disabled = true;
      $('authoring-status').textContent = 'Refreshing…';
      try {
        await refreshed();
        $('authoring-status').textContent = 'Library refreshed.';
      } catch (error) {
        $('authoring-status').textContent = error.message;
      } finally {
        $('refresh-library').disabled = false;
      }
    });
    window.addEventListener('beforeunload', (event) => {
      if (busy || uncertain || (!committed && dirty())) {
        event.preventDefault();
        event.returnValue = '';
      }
    });
    return { update };
  }
  return { create };
})();
