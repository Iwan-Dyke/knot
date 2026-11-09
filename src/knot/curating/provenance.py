"""Exact, revision-pinned inputs for curated notes and entity presentation."""

import re
from pathlib import Path

from pyoxigraph import NamedNode

from knot.graph.rdf import VOCAB, values

PIN_FIELDS = {'revision', 'sha256', 'text_sha256', 'quote', 'character_offset', 'start_line'}
MAX_DERIVATION_DEPTH = 32


def _validate_pins(sources):
    if not isinstance(sources, list) or not sources:
        raise ValueError('Provenance requires a nonempty list of source pins')
    for pin in sources:
        if not isinstance(pin, dict) or set(pin) != PIN_FIELDS:
            raise ValueError('Invalid provenance source fields')
        if not isinstance(pin['revision'], str):
            raise ValueError('Provenance requires a source revision IRI')
        NamedNode(pin['revision'])
        for field in ('sha256', 'text_sha256'):
            if not isinstance(pin[field], str) or not re.fullmatch('[0-9a-f]{64}', pin[field]):
                raise ValueError('Provenance requires snapshot and evidence-text SHA-256 hashes')
        if not isinstance(pin['quote'], str) or not pin['quote']:
            raise ValueError('Provenance requires an exact nonempty quotation')
        for field, minimum in (('character_offset', 0), ('start_line', 1)):
            if type(pin[field]) is not int or pin[field] < minimum:
                raise ValueError('Provenance requires Unicode offsets and one-based lines')


def validate_derivation(value):
    """Validate metadata shape without reading sources or changing free-form writing."""
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {'method', 'qualification', 'sources'}:
        raise ValueError('Invalid derivation metadata')
    if value['method'] not in ('faithful_restatement', 'synthesis'):
        raise ValueError('Unknown derivation method')
    if not isinstance(value['qualification'], str) or not value['qualification'].strip():
        raise ValueError('Derivation requires an explicit qualification')
    _validate_pins(value['sources'])


class _Sources:
    def __init__(self, root, store, reader=None):
        from knot.graph.query import load_store
        from knot.retrieval_engine.evidence import _Evidence

        self.root = Path(root).resolve()
        self.owner = store is None and reader is None
        if reader is not None:
            if store is not None and store is not reader.store:
                raise ValueError('Provenance reader must use the supplied eligible store')
            store = reader.store
        self.store = (
            load_store(self.root / 'graph', history=True, include_notes=False, allow_empty=True)
            if self.owner
            else store
        )
        # This validator owns transitive checks; the evidence reader must not call
        # back into it for every native revision and lose cycle detection.
        self.evidence = reader or _Evidence(self.root, self.store, verify_derivation=False)
        self.accounts = {}
        self.depths = {}

    def read(self, revision):
        from knot.writing.notes import REVISION
        from knot.writing.sources import add_note_sources

        if revision.startswith(REVISION):
            if self.owner:
                add_note_sources(self.root, self.store, self.store, {}, note_revision=revision)
            elif not values(self.store, revision, VOCAB + 'noteMetadata'):
                # A supplied store is already an eligible view. Never widen it
                # using the owner registry, even for a valid immutable revision.
                raise ValueError('Unavailable native provenance source')
        return self.evidence.revision(revision, verify_derivation=False)

    def verify(self, pin, visiting):
        revision = pin['revision']
        if revision in visiting:
            raise ValueError('Cyclic derivation provenance')
        if len(visiting) >= MAX_DERIVATION_DEPTH:
            raise ValueError('Derivation provenance exceeds the maximum depth of 32')
        text, source = self.read(revision)
        if any(pin[key] != source[key] for key in ('sha256', 'text_sha256')):
            raise ValueError('Provenance source hash mismatch')
        offset, quote = pin['character_offset'], pin['quote']
        if text[offset : offset + len(quote)] != quote:
            raise ValueError('Provenance quotation does not match its exact source offset')
        if text[:offset].count('\n') + 1 != pin['start_line']:
            raise ValueError('Provenance quotation line does not match its source')
        if revision not in self.accounts:
            derivation = source.get('native_note', {}).get('derivation')
            validate_derivation(derivation)
            if derivation is not None:
                accounts = set()
                depth = 1
                for parent in derivation['sources']:
                    accounts.update(self.verify(parent, visiting | {revision}))
                    depth = max(depth, 1 + self.depths[parent['revision']])
            else:
                accounts = {source['sha256']}
                depth = 1
            self.accounts[revision] = accounts
            self.depths[revision] = depth
        # Cached ancestors must pay their complete subtree depth too. Otherwise
        # validating leaves first could admit arbitrarily deep provenance chains.
        if len(visiting) + self.depths[revision] > MAX_DERIVATION_DEPTH:
            raise ValueError('Derivation provenance exceeds the maximum depth of 32')
        return self.accounts[revision]


def validate_sources(root, sources, *, store=None, reader=None):
    """Verify exact sources, including nested derivations, without writing files.

    Omit store for owner-local authoring. A supplied store must already contain
    every permitted source, including native adapter metadata; it is never widened.
    Retrieval supplies its reader to share its source budget and verified cache.
    Returns leaf snapshot hashes as overlap groups, not identity or corroboration.
    """
    _validate_pins(sources)
    verifier = _Sources(root, store, reader)
    accounts = set()
    for pin in sources:
        accounts.update(verifier.verify(pin, set()))
    return sorted(accounts)


def source_pin(root, revision, quote, character_offset, *, store=None):
    """Construct a pin from verified original text, never from a rewritten paraphrase."""
    # Validate caller input before paths or metadata are inspected.
    pin = {
        'revision': revision,
        'sha256': '0' * 64,
        'text_sha256': '0' * 64,
        'quote': quote,
        'character_offset': character_offset,
        'start_line': 1,
    }
    _validate_pins([pin])
    reader = _Sources(root, store)
    text, source = reader.read(revision)
    pin.update(
        sha256=source['sha256'],
        text_sha256=source['text_sha256'],
        start_line=text[:character_offset].count('\n') + 1,
    )
    reader.verify(pin, set())
    return pin
