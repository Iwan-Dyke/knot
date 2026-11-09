/* Reading, provenance and context renderers consume the shared snapshot only. */
const LibraryReader = (() => {
  const { element, button, details, section, field, badge, local, date, link, paged } = LibraryDOM;
  function create(index, navigate, onCollection) {
    const model = index.model;
    const recordLink = (id, view = 'library') =>
      link(index.byId.get(id) || { id, title: 'Not included: ' + id }, view, navigate);
    function citation(pin) {
      const source = model.sources[pin.revision],
        card = details(source?.title || pin.revision);
      card.className = 'evidence-card';
      card.append(element('blockquote', pin.quote));
      if (source) {
        field(card, 'Original author', source.author);
        field(card, 'Revision', pin.revision);
        field(card, 'Snapshot SHA-256', source.sha256);
        field(card, 'Text SHA-256', source.text_sha256);
        field(card, 'Source path', source.snapshot);
        field(card, 'Evidence text path', source.text_path);
        const locator = pin.locator || {
          characterOffset: pin.character_offset,
          startLine: pin.start_line,
        };
        field(card, 'Locator', JSON.stringify(locator));
        card.append(
          button('Open pinned source', () =>
            navigate({ view: 'library', id: source.note || pin.revision, revision: pin.revision }),
          ),
        );
        if (source.snapshot !== source.text_path)
          card.append(
            element(
              'p',
              'Text is a transcription/extraction; the original binary is not embedded.',
              'metadata',
            ),
          );
      }
      return card;
    }
    function claimCard(claim) {
      const card = details(
        `${claim.subject.label} → ${local(claim.predicate)} → ${claim.object.label}`,
      );
      card.className = 'evidence-card';
      card.firstElementChild.append(
        element('br'),
        badge(claim.status),
        badge(claim.origin),
        badge(claim.lifecycle || 'Active'),
      );
      card.append(element('p', claim.rationale));
      card.append(recordLink(claim.subject.id));
      if (!claim.object.literal) {
        card.append(document.createTextNode(' → '), recordLink(claim.object.id));
      } else {
        field(card, 'Value', claim.object.value ?? claim.object.id);
        field(card, 'Datatype', claim.object.datatype);
        field(card, 'Language', claim.object.language);
      }
      field(card, 'Assertion', claim.id);
      if (claim.classification)
        field(
          card,
          'Kind/type classification',
          `${claim.kind}: ${claim.classification.status} · ${claim.classification.rationale}`,
        );
      for (const theme of claim.themes || [])
        field(
          card,
          'Theme membership',
          `${theme.label} · ${theme.status || 'Author declared'} (separate from claim review)`,
        );
      for (const account of claim.evidence_accounts || [])
        field(card, 'Evidence qualification', JSON.stringify(account));
      for (const pin of claim.evidence || []) card.append(citation(pin));
      const events = model.reviews.filter(
        (e) => e.target === claim.id || e.replacement_id === claim.id,
      );
      for (const event of events) {
        const trail = details('Review: ' + event.action);
        field(trail, 'Reviewer', event.reviewer);
        field(trail, 'When', event.time);
        field(trail, 'Reason', event.reason);
        const previous = model.historical_claims[event.target];
        if (previous) {
          field(
            trail,
            'Historical claim',
            `${previous.subject_label} → ${local(previous.predicate)} → ${previous.object_label}`,
          );
          field(trail, 'State', `${local(previous.status)} · ${local(previous.lifecycle)}`);
          field(trail, 'Rationale', previous.rationale);
          previous.evidence.forEach((p) => trail.append(citation(p)));
        }
        if (event.replacement_id) field(trail, 'Replacement', event.replacement_id);
        card.append(trail);
      }
      return card;
    }
    function renderContext(parent, id, filters = {}, revision = null) {
      parent.replaceChildren();
      const record = index.byId.get(id);
      if (!record) {
        parent.append(element('p', 'Select a note or entity to inspect its context.', 'muted'));
        return;
      }
      if (revision && record.revision !== revision)
        parent.append(
          element(
            'p',
            'Connections below describe the current snapshot. The reader shows the explicitly selected historical revision.',
            'notice',
          ),
        );
      field(parent, 'Canonical ID', id);
      if (record.role === 'entity') {
        field(parent, 'Types', record.entityTypes.join(', '));
        for (const typing of record.typing || [])
          field(
            parent,
            'Typing qualification',
            `${typing.origin || 'Unknown'} · ${typing.status} ${typing.rationale || ''}`,
          );
        if (record.aliases?.length) field(parent, 'Aliases', record.aliases.join(' · '));
      }
      const groups = [
        [
          'Outgoing note links',
          (index.outgoing.get(id) || []).filter((e) => e.kind === 'link'),
          (e) => e.to,
        ],
        [
          'Backlinks',
          (index.incoming.get(id) || []).filter((e) => e.kind === 'link'),
          (e) => e.from,
        ],
        [
          'Related entities',
          (index.outgoing.get(id) || []).filter((e) => e.kind === 'association'),
          (e) => e.to,
        ],
        [
          'Associated notes',
          (index.incoming.get(id) || []).filter((e) => e.kind === 'association'),
          (e) => e.from,
        ],
      ];
      for (const [title, items, target] of groups)
        if (items.length) {
          const group = section(parent, title);
          paged(group, items, (e) => {
            const row = element('div', undefined, 'history-row');
            row.append(recordLink(target(e)), element('p', e.reason, 'metadata'));
            return row;
          });
        }
      const memberships = record.navigation?.themes || record.themes || [];
      if (memberships.length) {
        const group = section(parent, 'Other locations');
        for (const theme of memberships) {
          group.append(
            button(theme.label, () => onCollection('theme', theme.id, theme.label)),
            element('p', theme.status || 'Author declared navigation', 'metadata'),
          );
        }
      }
      if (record.sources?.length) {
        const group = section(parent, 'Sources of this curated note');
        record.sources.forEach((p) => group.append(citation(p)));
      }
      const all = index.claimIndex.get(id) || [],
        claims = all.filter(
          (c) =>
            (!filters.status || filters.status === 'all' || c.status === filters.status) &&
            (!filters.origin || filters.origin === 'all' || c.origin === filters.origin) &&
            (!filters.theme || c.themes.some((t) => t.id === filters.theme)) &&
            (!filters.kind || c.kind === filters.kind),
        );
      const group = section(parent, 'Source-backed relationships');
      if (all.length !== claims.length)
        group.append(
          element(
            'p',
            `${all.length - claims.length} relationships hidden by review/origin filters.`,
            'metadata',
          ),
        );
      paged(group, claims, claimCard);
      const inactive = Object.values(model.historical_claims).filter(
        (c) =>
          !model.claims[c.id] &&
          ((c.display_subject || c.subject) === id || (c.display_object || c.object) === id),
      );
      if (inactive.length) {
        const history = section(parent, 'Historical relationships');
        for (const c of inactive) {
          const card = details(`${c.subject_label} → ${local(c.predicate)} → ${c.object_label}`);
          card.append(badge(local(c.status)), badge(local(c.lifecycle)), element('p', c.rationale));
          c.evidence.forEach((p) => card.append(citation(p)));
          history.append(card);
        }
      }
    }
    function content(parent, source, format) {
      const body = model.bodies[source.body];
      if (!body) {
        parent.append(
          element('p', 'This historical body is not included in this snapshot.', 'notice'),
        );
        return;
      }
      const toolbar = element('div', undefined, 'button-row'),
        article = element('div', undefined, 'reader-content');
      const draw = (raw = false) => {
        article.replaceChildren();
        if (raw || !body.html[format]) article.append(element('pre', body.text, 'source-text'));
        else article.innerHTML = body.html[format];
      };
      toolbar.append(
        button('Formatted', () => draw()),
        button('Exact source', () => draw(true)),
      );
      const smaller = button('A−', () => {
        article.style.fontSize =
          Math.max(0.85, (parseFloat(article.style.fontSize) || 1.1) - 0.1) + 'rem';
      });
      const larger = button('A+', () => {
        article.style.fontSize =
          Math.min(2, (parseFloat(article.style.fontSize) || 1.1) + 0.1) + 'rem';
      });
      smaller.setAttribute('aria-label', 'Decrease reading text size');
      larger.setAttribute('aria-label', 'Increase reading text size');
      toolbar.append(smaller, larger);
      parent.append(toolbar, article);
      draw();
      article.addEventListener('click', (event) => {
        const a = event.target.closest('a');
        if (!a) return;
        if (a.dataset.record) {
          event.preventDefault();
          navigate({ view: 'library', id: a.dataset.record });
        }
        if (a.dataset.anchor) {
          event.preventDefault();
          document.getElementById(a.dataset.anchor)?.scrollIntoView();
        }
      });
    }
    function render(parent, id, revision) {
      if (!revision && model.sources[id] && !index.byId.has(id)) revision = id;
      parent.replaceChildren();
      const record = index.byId.get(id),
        source = revision ? model.sources[revision] : null;
      if (!id) {
        parent.append(
          element('h2', 'Your knowledge, ready to read'),
          element(
            'p',
            'Choose a note, entity or topic on the left. Unclassified and standalone notes are included.',
          ),
        );
        return;
      }
      if (revision) {
        const valid =
          record?.role === 'note'
            ? record.history.some((r) => r.revision === revision)
            : id === revision;
        if (!valid) {
          parent.append(
            element('p', 'This revision is not part of the selected record.', 'notice'),
          );
          return;
        }
        if (!source) {
          parent.append(
            element(
              'p',
              'Revision metadata is available, but this historical body is not included. It remains preserved in the dataset.',
              'notice',
            ),
            element('pre', `knot show ${id} --revision ${revision}`),
          );
          return;
        }
        parent.append(element('p', 'Pinned source revision · ' + revision, 'notice'));
        field(parent, 'Author', source.author);
        field(parent, 'Snapshot SHA-256', source.sha256);
        field(parent, 'Text SHA-256', source.text_sha256);
        if (record?.role === 'note' && record.revision !== revision)
          parent.append(button('Read current note', () => navigate({ view: 'library', id })));
        content(parent, source, source.format);
        for (const pin of source.derivation?.sources || []) parent.append(citation(pin));
        return;
      }
      if (!record) {
        parent.append(
          element(
            'p',
            'Not included in this snapshot. No record was substituted by name.',
            'notice',
          ),
        );
        return;
      }
      if (record.role === 'note') {
        parent.append(badge(record.kind || 'Unspecified kind'), badge(record.format));
        field(parent, record.method ? 'Curated author' : 'Author', record.author);
        field(parent, 'Modified', date(record.modified_at));
        field(parent, 'Current revision as of export', record.revision);
        if (record.qualification)
          parent.append(element('p', record.qualification, 'qualification'));
        content(parent, record, record.format);
        if (record.sources.length) {
          const group = section(parent, 'Evidence and original authors');
          record.sources.forEach((p) => group.append(citation(p)));
        }
        const timeline = details(`Revision history (${record.history.length})`);
        paged(timeline, [...record.history].reverse(), (r) => {
          const row = element('div', undefined, 'history-row');
          field(row, 'When', date(r.modified_at));
          field(row, 'Author', r.author);
          field(row, 'Saved by', r.agent);
          field(row, 'Reason', r.reason);
          field(row, 'Revision', r.revision);
          field(row, 'Body SHA-256', r.body_sha256);
          if (model.sources[r.revision])
            row.append(
              button(
                r.revision === record.revision ? 'Read current revision' : 'Read this revision',
                () => navigate({ view: 'library', id, revision: r.revision }),
              ),
            );
          else
            row.append(
              element(
                'p',
                'Body not included in this snapshot; preserved in the dataset.',
                'muted',
              ),
            );
          return row;
        });
        parent.append(timeline);
      } else {
        parent.append(element('p', 'Entity overview', 'eyebrow'));
        field(parent, 'Types', record.entityTypes.join(', '));
        field(parent, 'Aliases', record.aliases.join(' · ') || 'None recorded');
        const group = section(parent, 'Associated notes');
        paged(group, index.associated.get(id) || [], (note) => recordLink(note));
        const attributes = (index.claimIndex.get(id) || []).filter((c) => c.object.literal);
        if (attributes.length) {
          const values = section(parent, 'Attributes');
          attributes.forEach((c) => values.append(claimCard(c)));
        }
      }
    }
    return { render, renderContext, citation, claimCard };
  }
  return { create };
})();
