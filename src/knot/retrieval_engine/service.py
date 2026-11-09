"""Read-only, bounded retrieval of existing source-backed assertion paths."""

import json

from pyoxigraph import NamedNode

from knot.graph.rdf import META, VOCAB, one
from knot.retrieval_engine.context import _labels as _labels
from knot.retrieval_engine.context import _prepare as _prepare
from knot.retrieval_engine.context import lookup as lookup
from knot.retrieval_engine.evidence import _Evidence as _Evidence
from knot.retrieval_engine.graph import _include_assertion as _include_assertion
from knot.retrieval_engine.graph import _iri as _iri
from knot.retrieval_engine.graph import _retrieve as _retrieve
from knot.retrieval_engine.policy import DOMAIN as DOMAIN
from knot.retrieval_engine.policy import FRAMEWORK as FRAMEWORK
from knot.retrieval_engine.policy import GENERIC as GENERIC
from knot.retrieval_engine.policy import Policy as Policy
from knot.retrieval_engine.response import _coalesce as _coalesce
from knot.retrieval_engine.response import _envelope as _envelope
from knot.retrieval_engine.response import _measure as _measure
from knot.retrieval_engine.response import _prune as _prune
from knot.retrieval_engine.response import _quotation as _quotation
from knot.retrieval_engine.response import _resize as _resize
from knot.retrieval_engine.response import serialise as serialise


def retrieve(
    root,
    seed=None,
    policy=None,
    *,
    question=None,
    mode='graph',
    limits=None,
    scope=None,
    note_revision=None,
    definition_order=False,
):
    """Return a fresh evidence package; no files or reviews are written."""
    if mode not in ('graph', 'text', 'hybrid'):
        raise ValueError('Select graph, text or hybrid mode')
    if type(definition_order) is not bool or (
        definition_order and (seed is not None or not question or note_revision is not None)
    ):
        raise ValueError('Definition ordering requires question-only retrieval')
    if question is not None:
        from knot.retrieval_engine.search import retrieve_ranked

        return retrieve_ranked(
            root,
            seed,
            question,
            policy or Policy(),
            mode='hybrid' if seed is None and mode == 'graph' else mode,
            limits=limits,
            scope=scope,
            note_revision=note_revision,
            definition_order=definition_order,
        )
    prepared = _prepare(root, scope=scope, note_revision=note_revision)
    native = [
        q.subject.value
        for q in prepared[0].quads_for_pattern(None, NamedNode(VOCAB + 'nativeNote'), None, META)
        if seed is None or q.object.value == seed
    ]
    associated = (
        seed is not None
        and mode == 'text'
        and any(
            seed in json.loads(q.object.value)['navigation_entities']
            for q in prepared[0].quads_for_pattern(
                None, NamedNode(VOCAB + 'noteMetadata'), None, META
            )
        )
    )
    if (native and (seed is not None or note_revision is not None)) or associated:
        from knot.retrieval_engine.search import Limits, _retrieve_ranked

        if seed is None:
            seed = one(prepared[0], note_revision or native[0], VOCAB + 'nativeNote').value
        return _retrieve_ranked(
            root, seed, '', policy or Policy(), 'text', limits or Limits(), prepared
        )
    if mode != 'graph' or limits is not None:
        raise ValueError('Text/hybrid retrieval and source limits require a question')
    return _retrieve(root, seed, policy or Policy(), *prepared)


def main():
    from knot.retrieval_engine.cli import main as run

    return run()


if __name__ == '__main__':
    main()
