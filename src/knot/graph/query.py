"""Run a local SELECT query against the authoritative RDF files."""

import argparse
import json
from pathlib import Path

from pyoxigraph import NamedNode, Quad, RdfFormat, Store

from knot.graph.rdf import LABEL, META, RDF_TYPE, VOCAB, one
from knot.reviewing.state import apply_reviews
from knot.shared.datasets import cli_data_root
from knot.shared.storage import managed_path


def assertion_query(*, frameworks=False, all_knowledge=False):
    """Select source-backed assertions for the requested record view."""
    existence = 'EXISTS' if frameworks else 'NOT EXISTS'
    record_filter = (
        ''
        if all_knowledge
        else f'FILTER {existence} {{ ?assertion k:recordKind k:FrameworkDefinition }}'
    )
    return f"""
PREFIX k: <urn:knot:vocab:>
PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?assertion ?s ?p ?o ?subject ?object ?status ?origin ?quote ?snapshot ?rationale
WHERE {{
 GRAPH <urn:knot:metadata> {{
  ?assertion a k:Assertion ; k:subjectLabel ?subject ; k:objectLabel ?object ;
   k:reviewStatus ?status ; k:origin ?origin ; k:lifecycle k:Active ;
   prov:wasDerivedFrom ?evidence ; k:rationale ?rationale .
  {record_filter}
  VALUES ?status {{ k:Accepted k:Unreviewed }}
  ?evidence k:quote ?quote ; k:revision ?revision .
  ?revision k:snapshotPath ?snapshot .
 }}
 GRAPH ?assertion {{ ?s ?p ?o }}
}} ORDER BY ?assertion
"""


def identity_bindings(store):
    """Return only accepted bindings, with the same conflict policy for all views."""
    bindings = {}
    for quad in store.quads_for_pattern(None, NamedNode(VOCAB + 'sourceEntity'), None, META):
        proposal = quad.subject.value
        if one(store, proposal, VOCAB + 'reviewStatus').value != VOCAB + 'Accepted':
            continue
        target = one(store, proposal, VOCAB + 'entity')
        if quad.object in bindings and bindings[quad.object] != target:
            raise ValueError(f'Conflicting accepted identity: {quad.object}')
        bindings[quad.object] = target
    return bindings


def apply_identities(store):
    bindings = identity_bindings(store)
    for source, target in bindings.items():
        for quad in list(store.quads_for_pattern(source, NamedNode(LABEL), None, META)):
            store.add(Quad(target, quad.predicate, quad.object, META))
    assertions = list(
        store.quads_for_pattern(None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META)
    )
    for assertion in assertions:
        for quad in list(store.quads_for_pattern(None, None, None, assertion.subject)):
            subject = bindings.get(quad.subject, quad.subject)
            obj = bindings.get(quad.object, quad.object)
            if subject != quad.subject or obj != quad.object:
                store.remove(quad)
                store.add(Quad(subject, quad.predicate, obj, quad.graph_name))
    return store


def load_store(path, *, history=False, include_notes=True, allow_empty=False):
    path = Path(path).absolute()
    directory = path.is_dir() or (not path.exists() and path.name == 'graph')
    root = path.parent if directory else path.parent.parent
    path = managed_path(root, path.relative_to(root))
    root = root.resolve()
    files = sorted(path.glob('*.trig')) if directory else [path]
    if not files and not (
        allow_empty or (include_notes and (root / 'notes/registry.json').exists())
    ):
        raise ValueError(f'No RDF files found in {path}')
    store = Store()
    for file in files:
        store.load(path=managed_path(root, file.relative_to(root)), format=RdfFormat.TRIG)
    apply_reviews(store, root, history=history)
    # Review history uses original endpoints for content fingerprints and corrections.
    if not history:
        apply_identities(store)
    if include_notes:
        from knot.writing.notes import build_note_projection

        projection = build_note_projection(root, store)
        if projection:
            store.load(input=projection, format=RdfFormat.TRIG)
        elif not files and not allow_empty:
            raise ValueError(f'No RDF files found in {path}')
    return store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query', type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--graph', type=Path)
    group.add_argument('--data-root', type=Path)
    args = parser.parse_args()
    if args.graph is None:
        args.graph = cli_data_root(parser, args.data_root) / 'graph'
    store = load_store(args.graph)
    results = store.query(args.query.read_text())
    names = [variable.value for variable in results.variables]
    for row in results:
        print(
            json.dumps(
                {key: row[key].value if row[key] is not None else None for key in names},
                ensure_ascii=False,
            )
        )


if __name__ == '__main__':
    main()
