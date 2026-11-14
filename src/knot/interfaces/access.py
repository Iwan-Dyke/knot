"""Explicit source-revision grants for local assistant access."""

import copy
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pyoxigraph import Literal, NamedNode, Quad, Store

from knot.graph.rdf import DERIVED, LABEL, META, RDF_TYPE, VOCAB, one, values


@dataclass(frozen=True)
class AccessScope:
    revisions: tuple = ()
    whole_dataset: bool = False

    def __post_init__(self):
        if type(self.whole_dataset) is not bool or (self.whole_dataset and self.revisions):
            raise ValueError('Choose revision pins or an explicit whole-dataset grant')
        if (
            not isinstance(self.revisions, tuple)
            or any(not isinstance(pair, tuple) or len(pair) != 2 for pair in self.revisions)
            or len(dict(self.revisions)) != len(self.revisions)
        ):
            raise ValueError('Revision pins must be unique immutable pairs')
        for revision, sha in self.revisions:
            NamedNode(revision)
            if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
                raise ValueError('Source pins require SHA-256 hashes')

    @classmethod
    def all(cls):
        return cls(whole_dataset=True)

    @classmethod
    def from_file(cls, path):
        data = json.loads(Path(path).read_text())
        if (
            not isinstance(data, dict)
            or set(data) != {'revisions'}
            or not isinstance(data['revisions'], dict)
        ):
            raise ValueError('Scope file must contain only a revisions object')
        return cls(revisions=tuple(sorted(data['revisions'].items())))

    def apply(self, store, original, records, labels, *, include_framework_stubs=True):
        if self.whole_dataset:
            return store, original, records, labels
        allowed = dict(self.revisions)
        for revision, expected in allowed.items():
            if revision.startswith('urn:knot:note-revision:'):
                # Native pins are verified against their immutable manifest after
                # this ordinary-source projection, before any native text scan.
                registered = values(store, revision, VOCAB + 'sha256')
                if registered and (len(registered) != 1 or registered[0].value != expected):
                    raise ValueError('Source grant no longer matches the dataset')
                continue
            if one(store, revision, VOCAB + 'sha256').value != expected:
                raise ValueError('Source grant no longer matches the dataset')
        projected, historical = Store(), Store()

        def add(quad):
            projected.add(quad)
            historical.add(quad)

        def metadata(subject, predicates):
            for quad in store.quads_for_pattern(NamedNode(subject), None, None, META):
                if quad.predicate.value in predicates:
                    add(quad)

        def evidence_ids(aid):
            return sorted(e.value for e in values(store, aid, DERIVED))

        def eligible(aid):
            eids = evidence_ids(aid)
            return bool(eids) and all(
                one(store, eid, VOCAB + 'revision').value in allowed for eid in eids
            )

        assertion_fields = {RDF_TYPE, DERIVED} | {
            VOCAB + key
            for key in (
                'authorClassification',
                'subjectLabel',
                'objectLabel',
                'reviewStatus',
                'origin',
                'lifecycle',
                'rationale',
                'recordKind',
            )
        }
        evidence_fields = {
            VOCAB + key
            for key in (
                'quote',
                'revision',
                'locatorKind',
                'locator',
                'characterOffset',
                'startLine',
            )
        }
        revision_fields = {RDF_TYPE} | {
            VOCAB + key
            for key in (
                'snapshotPath',
                'sha256',
                'textPath',
                'transcriptionPath',
                'transcriptionSha256',
                'warning',
                'sourceWeek',
                'mediaType',
            )
        }
        occurrence_fields = {
            VOCAB + key for key in ('archive', 'archive_sha256', 'member', 'member_index')
        }
        mapping_fields = {
            VOCAB + key
            for key in ('sourceEntity', 'entity', 'reviewStatus', 'reviewer', 'time', 'rationale')
        }
        visible, scoped_labels, source_entities = [], defaultdict(set), set()
        for record in records:
            aid = record['id']
            if not eligible(aid):
                continue
            # Kind/review belong to this record; theme labels are never access grants.
            clean = {
                key: copy.deepcopy(record[key])
                for key in (
                    'id',
                    'subject',
                    'predicate',
                    'object',
                    'status',
                    'origin',
                    'rationale',
                    'framework',
                    'evidence',
                    'kind',
                    'classification',
                )
            }
            clean['classification'] = {'status': record['classification']['status']}
            visible.append(clean)
            metadata(aid, assertion_fields)
            for eid in evidence_ids(aid):
                metadata(eid, evidence_fields)
            for quad in store.quads_for_pattern(None, None, None, NamedNode(aid)):
                projected.add(quad)
            for quad in original.quads_for_pattern(None, None, None, NamedNode(aid)):
                historical.add(quad)
                source_entities.add(quad.subject)
                if not isinstance(quad.object, Literal):
                    source_entities.add(quad.object)
            for end in ('subject', 'object'):
                entity = record[end]
                if not entity.get('literal'):
                    scoped_labels[entity['id']].add(entity['label'])
                    add(
                        Quad(
                            NamedNode(entity['id']),
                            NamedNode(LABEL),
                            Literal(entity['label']),
                            META,
                        )
                    )

        # Sources with no assertions remain searchable if explicitly granted. Only
        # permitted revision links participate in document/revision context grouping.
        for revision in allowed:
            metadata(revision, revision_fields)
            for quad in store.quads_for_pattern(
                None, NamedNode(VOCAB + 'revision'), NamedNode(revision), META
            ):
                if NamedNode(VOCAB + 'Document') in values(store, quad.subject.value, RDF_TYPE):
                    add(quad)
                    add(
                        Quad(quad.subject, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Document'), META)
                    )
                if any(values(store, quad.subject.value, key) for key in occurrence_fields):
                    add(quad)
                    metadata(quad.subject.value, occurrence_fields)

        # Keep the framework exclusion policy even for rejected definitions; these
        # metadata stubs do not restore their domain triples or review history.
        for quad in store.quads_for_pattern(
            None, NamedNode(VOCAB + 'recordKind'), NamedNode(VOCAB + 'FrameworkDefinition'), META
        ):
            if not include_framework_stubs:
                break
            aid = quad.subject.value
            if eligible(aid):
                metadata(aid, {VOCAB + 'recordKind', DERIVED})
                for eid in evidence_ids(aid):
                    metadata(eid, {VOCAB + 'revision'})

        for source in source_entities:
            for quad in store.quads_for_pattern(
                None, NamedNode(VOCAB + 'sourceEntity'), source, META
            ):
                if (
                    one(store, quad.subject.value, VOCAB + 'reviewStatus').value
                    == VOCAB + 'Accepted'
                ):
                    metadata(quad.subject.value, mapping_fields)
        return projected, historical, visible, dict(scoped_labels)
