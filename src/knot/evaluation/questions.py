"""Finite question templates, exact visible names and fixed coverage answers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pyoxigraph import NamedNode

from knot.evaluation.access import ScopedSnapshot
from knot.evaluation.engine import DEFINITION, evaluate
from knot.evaluation.request import CoverageRequest
from knot.evaluation.snapshot import canonical_hash
from knot.graph.rdf import DERIVED, VOCAB, one, values
from knot.interfaces.access import AccessScope
from knot.retrieval_engine.context import _labels

TEMPLATE = 'Does project "PROJECT" have reviewed support for criterion "CRITERION"?'
CONTRACT = 'reviewed-support-question/1'
QUOTED = r'"(?:[^"\\\n]|\\.)+"'
DECISION_PATTERN = rf'Why was decision (?P<decision>{QUOTED}) chosen\?'
SUFFIX = (
    rf'(?: in framework (?P<framework>{QUOTED})'
    rf'(?: at revision (?P<revision>{QUOTED}))?)?\?'
)
PATTERNS = (
    rf'Does project (?P<subject>{QUOTED}) have reviewed support for criterion '
    rf'(?P<criterion>{QUOTED}){SUFFIX}',
    rf'What reviewed support does project (?P<subject>{QUOTED}) have for criterion '
    rf'(?P<criterion>{QUOTED}){SUFFIX}',
)


def _parse(question: str) -> dict[str, str] | None:
    if not isinstance(question, str) or not 1 <= len(question) <= 2000:
        raise ValueError('Supply a question of 1–2000 characters')
    for pattern in PATTERNS:
        match = re.fullmatch(pattern, question.strip(), re.I)
        if match:
            try:
                parsed = {
                    key: json.loads(value) for key, value in match.groupdict().items() if value
                }
            except ValueError:
                return None
            if all(value.strip() for value in parsed.values()):
                return parsed
    return None


def _iri(value: str) -> bool:
    try:
        NamedNode(value)
        return True
    except ValueError:
        return False


def _matches(value: str, labels: dict[str, set[str]]) -> list[str]:
    # Caller-supplied IRIs identify the request, not proof that an entity exists.
    if _iri(value):
        return [value]
    return sorted(
        iri
        for iri, names in labels.items()
        if value.casefold() in {name.casefold() for name in names}
    )


def evaluation_answer(question: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """Render only the returned rule outcome; never interpret its source quotations."""
    (row,) = receipt['criteria']
    wording = {
        'support_found': (
            'A qualifying reviewed direct support mapping was found. '
            'This is an attributed assessment, not proof of capability or whole-criterion attainment.'
        ),
        'no_qualifying_support': (
            'No qualifying reviewed direct support mapping was found in the evaluated scope. '
            'This does not establish lack of capability or absence outside that scope.'
        ),
        'unknown': 'The result is unknown; no support or absence conclusion is established.',
    }
    return _question_receipt(
        {
            'question_contract': CONTRACT,
            'question': question,
            'status': 'evaluated',
            'request': receipt['request'],
            'answer': wording[row['outcome']],
            'evaluation': receipt,
        }
    )


def _question_receipt(result: dict[str, Any]) -> dict[str, Any]:
    result['answer_sha256'] = canonical_hash(result)
    return result


def answer_question(
    root: Path, question: str, *, scope: AccessScope | None = None
) -> dict[str, Any]:
    """Resolve one supported question or return choices without executing a broader request."""
    result = {'question_contract': CONTRACT, 'question': question, 'request': None}
    parsed = _parse(question)
    if parsed is None or any(
        not _iri(parsed[key]) for key in ('framework', 'revision') if key in parsed
    ):
        return _question_receipt(
            {
                **result,
                'status': 'unsupported_question',
                'supported_question': TEMPLATE,
                'answer': 'This question is outside the supported contract. No evaluation was performed.',
            }
        )
    if scope is not None and not isinstance(scope, AccessScope):
        raise TypeError('Supply an AccessScope')
    snapshot = ScopedSnapshot(Path(root), scope if scope is not None else AccessScope.all())
    store, records = snapshot.view.store, snapshot.view.records
    labels = _labels(store, records)
    subjects = _matches(parsed['subject'], labels)
    criteria = _matches(parsed['criterion'], labels)

    def choices(values: dict[str, list]) -> dict[str, Any]:
        snapshot.verify()
        return _question_receipt(
            {
                **result,
                'status': 'needs_selection',
                'choices': {key: rows[:10] for key, rows in values.items()},
                'choices_truncated': any(len(rows) > 10 for rows in values.values()),
                'answer': (
                    'No evaluation was performed. Use exact identifiers to resolve missing or '
                    'ambiguous selections; missing visible choices do not establish absence.'
                ),
            }
        )

    if len(subjects) != 1 or len(criteria) != 1:
        return choices({'subject': subjects, 'criterion': criteria})
    if 'framework' in parsed and 'revision' in parsed:
        pairs = {(parsed['framework'], parsed['revision'])}
    else:
        pairs = set()
        for record in records:
            if not (
                record['subject']['id'] == criteria[0]
                and record['framework']
                and record['predicate'] == DEFINITION
                and record['status'] == 'Accepted'
                and one(store, record['id'], VOCAB + 'lifecycle').value == VOCAB + 'Active'
            ):
                continue
            framework = one(store, record['id'], VOCAB + 'framework').value
            if parsed.get('framework', framework) != framework:
                continue
            revisions = {
                one(store, eid.value, VOCAB + 'revision').value
                for eid in values(store, record['id'], DERIVED)
            }
            if len(revisions) == 1:
                pairs.add((framework, next(iter(revisions))))
    if len(pairs) != 1:
        return choices(
            {
                'framework_revision': [
                    {'framework': framework, 'framework_revision': revision}
                    for framework, revision in sorted(pairs)
                ]
            }
        )
    framework, revision = next(iter(pairs))
    request = CoverageRequest(subjects[0], framework, revision, (criteria[0],))
    receipt = evaluate(root, request, scope=scope)
    # Resolution must remain valid through execution, including newly ambiguous labels.
    snapshot.verify()
    return evaluation_answer(question, receipt)
