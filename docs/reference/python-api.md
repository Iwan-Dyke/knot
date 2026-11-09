# Native note and retrieval Python APIs

Run these examples from the checkout with `PYTHONPATH=src .venv/bin/python`.
Replace `ENTITY_IRI` with a resolved entity from your own dataset.

Core APIs take an explicit dataset path. Use the shared resolver when you want the
same selection as the CLI, or pass `Path('/path/to/dataset')` yourself:

```python
from knot.shared.datasets import resolve_data_root
from knot.writing.notes import create_note, note_history, read_note, save_note

root = resolve_data_root()
first = create_note(root, 'A hypothesis I want to revisit.\n')
latest = save_note(
    root,
    first['note'],
    'A revised hypothesis, with its uncertainty preserved.\n',
    expected=first['revision'],
    title='Reflection',
)
read_note(root, first['note'])  # Current committed version
read_note(root, first['note'], revision=first['revision'])  # Original version
note_history(root, first['note'])  # Verified versions, oldest first
```

`create_note` accepts optional `format='markdown'|'org'`, `title`, `author`, `agent`,
`reason`, `entities`, `kind`, `navigation` and `derivation`. Bodies may be strings or UTF-8 bytes; whitespace and line endings are
preserved. Notes need no title, entity or classification. Keep the returned `note`
ID for later operations. Saves require the last observed `revision` as `expected`;
reload after a conflicting save. Omitted format/title/author/entities/kind retain their values;
explicit `None` clears title/author/kind, and `entities=[]` removes all associations.
Unchanged body and note metadata create no
revision. Agent/reason describe actual commits and do not force audit-only saves.
`derivation` accepts the [curated-note provenance object](../curation.md#curated-knowledge-notes) on creation or a curated
revision; curated metadata and source-integrity requirements apply equally to the
API and CLI. Save the curated text under its own note ID rather than revising its source.

Associate a note with zero, one or multiple existing entity IRIs. Select an existing
canonical entity with `just retrieval lookup` first:

```python
linked = save_note(
    root, latest['note'], latest['body'], expected=latest['revision'],
    entities=['ENTITY_IRI'], kind='Thought',
)
```

Add further existing IRIs to `entities` to connect the same text to other projects,
books or concepts. Accepted identity bindings resolve explicit source IRIs to their
canonical targets; matching labels and unreviewed identity proposals do not merge
entities. Unknown entity IRIs are rejected. Association order and duplicates do not
create extra revisions. `kind` uses the existing knowledge kinds, such as `Thought`,
`Observation`, `Hypothesis` or `Question`; its default `None` leaves a note unclassified.

Ordinary revisions use schema version 2, curated revisions version 3, and revisions
with navigation version 4. Earlier manifests stay readable with no
associations/classification and are never rewritten. A real edit creates a new
revision; association/classification edits share the unchanged body snapshot.

Relative to `root`, the registry is `notes/registry.json`; immutable revision manifests
are under `notes/revisions/`. Exact body bytes share content-addressed snapshots under
`sources/revisions/<sha256>/note.txt`. Back up both the registry and preserved
revisions/snapshots. Do not edit those immutable files. Save/revert through the API;
missing or corrupt evidence fails verification.

The normal query loader rebuilds note RDF in the same dataset from one committed
registry snapshot. `urn:knot:notes` contains current navigation; `urn:knot:note-history`
contains immutable revision metadata, original associations and exact source hashes.
Current navigation follows accepted identity bindings without rewriting manifests.
Bodies remain in their original snapshots; they are not duplicated as RDF literals.
For example, the existing `just query <file.rq>` can run:

```sparql
PREFIX k: <urn:knot:vocab:>
SELECT ?entity ?note ?revision ?source ?sha256 WHERE {
  GRAPH <urn:knot:notes> {
    ?note a k:Note; k:associatedEntity ?entity; k:currentRevision ?revision .
  }
  GRAPH <urn:knot:note-history> {
    ?revision k:snapshotPath ?source; k:sha256 ?sha256 .
  }
} ORDER BY ?entity ?note
```

Associations are navigation, with no assertion review status or causal meaning.
No generated note graph files need rebuilding: owner queries reverify committed
manifests and source bytes each time, failing explicitly on corruption. This costs
work proportional to the saved note history. Retrieval builds a separate *eligible
view of the same dataset*, adding only current/permitted source revisions before
source ranking. Assertion review remains independent. No assertions are extracted
or accepted. The CLI supports resumable drafts; a general external-editor working-copy workflow
is not implemented. Drafts are not committed note revisions.

`navigation` records themes, explained note links and source-backed entity
declarations; see the [navigation contract](../notes.md#guided-capture). Omitting it
on save retains the existing navigation. To clear a category, supply its empty list
alongside the other categories you want to retain. These connections never accept
claims or resolve identities by matching labels.

Native notes use the existing bounded retrieval API:

```python
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.service import retrieve

budget = Policy(max_chars=12000)
retrieve(root, linked['note'], budget)  # Complete current note, or an explicit budget omission
retrieve(root, policy=budget, question='What changed my understanding?', mode='text')
retrieve(root, 'ENTITY_IRI', budget, mode='text')  # Associated notes
retrieve(
    root, linked['note'], budget,
    note_revision=first['revision'],  # Exact historical version
)
```

With an entity and question, `mode='hybrid'` combines native passages, existing source
text and graph paths under the same limits and selector. Question-only queries search
all eligible source text without inventing a graph seed. A note seed reads that note;
without a question it returns a complete note unit, and with a question it selects
complete relevant sections. Historical requests select the specified native revision.

Native citations include `native_note` metadata (ID, author, title, kind, format,
creation/save times and declared navigation), body/manifest hashes and exact source
locators. `verification='NativeNote'` verifies text and provenance, not the truth of
the writing. Its source context has `claim_review=null`. Recognised qualifications
within a unit remain intact; cross-section/cross-note qualifications and logical
contradictions are not automatically established.
Curated-note provenance identifies the restatement or synthesis and its input pins
separately from the exact quoted evidence. The curated author is not the original
source author, and source-only curation still has no assertion acceptance status.

The mutable note registry now uses schema version 2: committed heads plus ordered
committed revision membership. A save publishes both atomically. Older registries
remain readable; a real save upgrades their verified index. Before granting native
revisions from an older registry without editing a note, run the owner-local API:

```python
from knot.writing.notes import index_note_revisions
index_note_revisions(root)
```

This verifies the old committed ancestry and replaces only the registry. Immutable
bodies/manifests and assertion reviews are unchanged. MCP never runs this write.
