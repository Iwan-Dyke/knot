"""Shared RDF vocabulary, deterministic serialisation and metadata access."""

import tempfile
from collections import defaultdict
from pathlib import Path

from pyoxigraph import Literal, NamedNode

from knot.shared.storage import digest

BASE = 'urn:knot:'
VOCAB = 'urn:knot:vocab:'
RDF_TYPE = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type'
LABEL = 'http://www.w3.org/2000/01/rdf-schema#label'
DERIVED = 'http://www.w3.org/ns/prov#wasDerivedFrom'
ATTRIBUTED = 'http://www.w3.org/ns/prov#wasAttributedTo'


def identifier(kind, value):
    return BASE + kind + ':' + digest(value.encode('utf-8'))


def write_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        name = Path(temporary.name)
    try:
        name.replace(path)
    finally:
        name.unlink(missing_ok=True)


class Dataset:
    def __init__(self):
        self.graphs = defaultdict(set)

    def add(self, subject, predicate, obj, *, literal=False, graph=BASE + 'metadata'):
        term = Literal(obj) if literal else NamedNode(obj)
        self.graphs[graph].add(f'{NamedNode(subject)} {NamedNode(predicate)} {term} .')

    def text(self):
        return ''.join(
            f'{NamedNode(graph)} {{\n' + '\n'.join('  ' + line for line in sorted(lines)) + '\n}\n'
            for graph, lines in sorted(self.graphs.items())
        )


META = NamedNode(BASE + 'metadata')


def values(store, subject, predicate, graph=META):
    return [
        q.object
        for q in store.quads_for_pattern(NamedNode(subject), NamedNode(predicate), None, graph)
    ]


def one(store, subject, predicate, graph=META):
    found = values(store, subject, predicate, graph)
    if len(found) != 1:
        raise ValueError(f'Expected one {predicate} for {subject}, found {len(found)}')
    return found[0]
