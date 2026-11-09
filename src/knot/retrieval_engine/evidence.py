"""Verified source reading, citations and per-request source budgets."""

import json
from pathlib import Path

from pyoxigraph import NamedNode

from knot.graph.rdf import META, RDF_TYPE, VOCAB, one, values
from knot.shared.storage import digest, managed_path


class _Evidence:
    def __init__(self, root, store, *, max_revisions=None, verify_derivation=True):
        self.root, self.store = Path(root).resolve(), store
        ledger = managed_path(self.root, 'migration/conversion.json')
        self.hashes = json.loads(ledger.read_text()).get('outputs', {}) if ledger.exists() else {}
        self.cache = {}
        self.attempted = set()
        self.failures = {}
        self.max_revisions = max_revisions
        self.verify_derivation = verify_derivation
        self.derivations_checked = set()

    def read(self, path, expected):
        try:
            resolved = managed_path(self.root, path)
        except ValueError as error:
            raise ValueError('UnsafePath') from error
        try:
            data = resolved.read_bytes()
        except OSError as error:
            raise ValueError('MissingFile') from error
        if not expected:
            raise ValueError('MissingHash')
        if digest(data) != expected:
            raise ValueError('ChangedFile')
        return data

    def preview(self, revision, max_bytes):
        """Read bounded routing hints; only revision() can provide verified evidence."""
        snapshot = one(self.store, revision, VOCAB + 'snapshotPath').value
        paths = values(self.store, revision, VOCAB + 'transcriptionPath') or values(
            self.store, revision, VOCAB + 'textPath'
        )
        path = paths[0].value if paths else snapshot
        try:
            resolved = managed_path(self.root, path)
        except ValueError as error:
            raise ValueError('UnsafePath') from error
        try:
            size = resolved.stat().st_size
            windows = min(4, max_bytes)
            width = max_bytes // windows
            offsets = sorted(
                {int(i * max(0, size - width) / max(1, windows - 1)) for i in range(windows)}
            )
            if size <= max_bytes:
                offsets, width = [0], max_bytes
            pieces = []
            with resolved.open('rb') as stream:
                for offset in offsets:
                    stream.seek(offset)
                    pieces.append(stream.read(width))
        except OSError as error:
            raise ValueError('MissingFile') from error
        return '\n'.join(p.decode('utf-8', errors='ignore') for p in pieces), sum(map(len, pieces))

    def revision(self, revision, *, verify_derivation=None):
        if revision in self.failures:
            raise self.failures[revision]
        if revision not in self.attempted:
            if self.max_revisions is not None and len(self.attempted) >= self.max_revisions:
                raise ValueError('SourceRevisionBudget')
            self.attempted.add(revision)
        try:
            text, source = self._revision(revision)
            verify = self.verify_derivation if verify_derivation is None else verify_derivation
            derivation = source.get('native_note', {}).get('derivation')
            if verify and derivation and revision not in self.derivations_checked:
                from knot.curating.provenance import validate_sources

                source['source_accounts'] = validate_sources(
                    self.root, derivation['sources'], reader=self
                )
                self.derivations_checked.add(revision)
            return text, source
        except (ValueError, UnicodeError) as error:
            self.failures[revision] = error
            raise

    def _revision(self, revision):
        store = self.store
        snapshot = one(store, revision, VOCAB + 'snapshotPath').value
        sha = one(store, revision, VOCAB + 'sha256').value
        if revision not in self.cache:
            native = values(store, revision, VOCAB + 'noteMetadata')
            if native:
                from knot.writing.notes import _path

                _path(self.root, snapshot)
                _path(self.root, one(store, revision, VOCAB + 'manifestPath').value)
            raw = self.read(snapshot, sha)
            transcription = values(store, revision, VOCAB + 'transcriptionPath')
            extracted = values(store, revision, VOCAB + 'textPath')
            if native:
                self.read(
                    one(store, revision, VOCAB + 'manifestPath').value,
                    one(store, revision, VOCAB + 'manifestSha256').value,
                )
                path, expected, method = snapshot, sha, 'NativeNote'
            elif transcription:
                path = transcription[0].value
                expected = one(store, revision, VOCAB + 'transcriptionSha256').value
                raw = self.read(path, expected)
                method = 'StoredTranscription'
            elif Path(snapshot).suffix.lower() in ('.org', '.md', '.txt'):
                path, expected, method = snapshot, sha, 'SourceText'
            elif extracted:
                path = extracted[0].value
                expected = self.hashes.get(path)
                raw = self.read(path, expected)
                method = 'ExtractedText'
            else:
                raise ValueError('UnavailableText')
            text = raw.decode('utf-8' if native else 'utf-8-sig')
            native_header = json.loads(native[0].value) if native else None
            derivation = native_header.get('derivation') if native_header else None
            documents, occurrences = [], []
            references = (
                ()
                if native
                else store.quads_for_pattern(
                    None, NamedNode(VOCAB + 'revision'), NamedNode(revision), META
                )
            )
            for quad in references:
                subject = quad.subject.value
                if NamedNode(VOCAB + 'Document') in values(store, subject, RDF_TYPE):
                    documents.append(subject)
                occurrence = {}
                for key in ('archive', 'archive_sha256', 'member', 'member_index'):
                    found = values(store, subject, VOCAB + key)
                    if found:
                        occurrence[key] = found[0].value
                if occurrence:
                    occurrences.append({'id': subject, **occurrence})
            if native:
                # A native grant authorizes its manifest, not other documents or
                # occurrences that happen to reference its body in factual RDF.
                documents = [native_header['id']]
            self.cache[revision] = (
                text,
                {
                    'revision': revision,
                    'snapshot': snapshot,
                    'sha256': sha,
                    'text_path': path,
                    'text_sha256': expected,
                    'verification': method,
                    'documents': sorted(documents),
                    'occurrences': sorted(occurrences, key=lambda o: o['id']),
                    'warnings': []
                    if native
                    else sorted(v.value for v in values(store, revision, VOCAB + 'warning')),
                    'overlap_group': sorted(
                        v.value for v in values(store, revision, VOCAB + 'sourceWeek')
                    )
                    if transcription and not native
                    else [],
                    'independence': 'Unknown',
                    'citation_status': 'Verified',
                },
            )
            if native:
                self.cache[revision][1].update(
                    native_note=native_header,
                    manifest_sha256=one(store, revision, VOCAB + 'manifestSha256').value,
                    manifest_path=one(store, revision, VOCAB + 'manifestPath').value,
                )
                if derivation:
                    self.cache[revision][1].update(
                        representation='CuratedKnowledge',
                        independence='DerivedAccount',
                        source_accounts=sorted({p['sha256'] for p in derivation['sources']}),
                    )
        return self.cache[revision]

    def citation(self, eid):
        store = self.store
        revision = one(store, eid, VOCAB + 'revision').value
        text, source = self.revision(revision)
        quote = one(store, eid, VOCAB + 'quote').value
        offsets = values(store, eid, VOCAB + 'characterOffset')
        if not quote or quote not in text:
            raise ValueError('MissingQuotation')
        if offsets:
            offset = int(offsets[0].value)
            if offset < 0 or text[offset : offset + len(quote)] != quote:
                raise ValueError('ChangedLocator')
        else:
            offset = text.index(quote)
        start_lines = values(store, eid, VOCAB + 'startLine')
        if start_lines and int(start_lines[0].value) != text[:offset].count('\n') + 1:
            raise ValueError('ChangedLocator')
        locator = {}
        for key in ('locatorKind', 'locator', 'characterOffset', 'startLine'):
            found = values(store, eid, VOCAB + key)
            if found:
                locator[key] = found[0].value
        return quote, {**source, 'locator': locator}
