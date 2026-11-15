"""Read-only curation prompts from frozen labels and captured retrieval responses."""

import argparse
import json
from pathlib import Path

from knot.diagnostics.benchmark import _assess, _unique_judgements, _validate_labels
from knot.retrieval_engine.context import _prepare
from knot.retrieval_engine.evidence import _Evidence
from knot.shared.datasets import cli_data_root
from knot.shared.storage import digest
from knot.writing.notes import list_notes


def _key(label):
    return label['path'], label['sha256'], label['character_offset'], label['quote']


def diagnose(root, manifest, responses):
    """Owner-local only: no writes, semantic approval, ranking changes or scoped fallback."""
    root = Path(root)
    _validate_labels(root, manifest)
    questions = {q['id']: q for q in manifest['questions']}
    ids = [row['id'] for row in responses]
    if len(ids) != len(set(ids)) or set(ids) != set(questions):
        raise ValueError('Supply exactly one captured response per frozen question')
    store = _prepare(root)[0]
    spans = {}
    for row in sorted(responses, key=lambda r: r['id']):
        question = questions[row['id']]
        score = _assess(root, store, row['result'], question)
        for index, label in _unique_judgements(question).items():
            if label['judgement'] != 'Relevant':
                continue
            item = spans.setdefault(
                _key(label),
                {'evidence': dict(label), 'delivered_questions': [], 'missed_questions': []},
            )
            item['evidence']['qualification'] = item['evidence'].get(
                'qualification', False
            ) or label.get('qualification', False)
            outcome = (
                'delivered_questions'
                if index in score['relevant_retrieved']
                else 'missed_questions'
            )
            item[outcome].append(row['id'])

    notes, reader = list_notes(root), _Evidence(root, store)
    # Index current direct derivations only. A historical or transitive ancestor
    # is not evidence of a useful current description of this particular span.
    descriptions = []
    for note in notes:
        for pin in (note.get('derivation') or {}).get('sources', []):
            _, citation = reader.revision(pin['revision'])
            if not any(
                key[:2] == (citation['text_path'], citation['text_sha256']) for key in spans
            ):
                continue
            reader.revision(note['revision'])
            descriptions.append((note, pin, citation))

    recommendations = []
    for key, item in sorted(spans.items()):
        if not item['missed_questions']:
            continue
        path, sha, start, quote = key
        end = start + len(quote)
        native = [n for n in notes if (n['body_path'], n['body_sha256']) == (path, sha)]
        covering, partial = {}, {}
        # A labelled curated body is already a description; missing retrieval
        # does not justify creating another layer of derived knowledge.
        for note in native:
            if note.get('derivation'):
                reader.revision(note['revision'])
                covering[note['note']] = note
        for note, pin, citation in descriptions:
            if (citation['text_path'], citation['text_sha256']) != (path, sha):
                continue
            left, right = pin['character_offset'], pin['character_offset'] + len(pin['quote'])
            if left <= start and right >= end:
                covering[note['note']] = note
            elif left < end and right > start:
                partial[note['note']] = note
        signals = []
        generic = [
            n
            for n in native
            if (n.get('title') or '').strip().casefold()
            in {'', 'notes', 'note', 'untitled', 'summary', 'update', 'meeting notes'}
        ]
        if generic:
            signals.append('generic_title')
        if not covering:
            signals.append('no_covering_curated_span')
        if not covering and partial and item['evidence'].get('qualification'):
            signals.append('partial_qualified_context')
        if len(item['missed_questions']) > 1:
            signals.append('repeated_failure')
        if item['delivered_questions']:
            signals.append('wording_sensitivity')
        if not signals:
            signals.append('existing_description_review')
        correction = (
            'Review the existing title against the source; name its subject and relevant limitation.'
            if generic
            else 'Review the existing curated note and its title before adding anything; retain its source history.'
            if covering or partial
            else 'Inspect the source context; consider one focused, qualified description only if independently useful.'
        )
        related = {n['note']: n for n in [*native, *covering.values(), *partial.values()]}
        recommendations.append(
            {
                **item,
                'signals': signals,
                'current_notes': [
                    {'note': n['note'], 'revision': n['revision'], 'title': n.get('title')}
                    for _, n in sorted(related.items())
                ],
                'deficiency': 'The exact labelled context was not delivered for the listed questions; signals identify places to inspect.',
                'why_retrieval_may_improve': 'A faithful description may expose relevant context without requiring the original wording. Test with unchanged budgets before adopting it.',
                'smallest_proposed_correction': correction,
                'human_review_required': True,
                'review_reason': 'Meaning, usefulness, qualifications and identity require source review; this diagnostic cannot approve knowledge.',
                'limitations': 'Pins establish coverage, not description quality. A partial pin does not establish a misleading paraphrase. Wording sensitivity is an observed difference, not proof of exact-match dependence. Inspect budgets before blaming curation.',
            }
        )
    return {
        'version': 1,
        'scope': 'Owner-local, source-labelled review prompts; no automatic changes or approvals.',
        'questions_sha256': digest(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
        ),
        'responses_sha256': digest(
            json.dumps(responses, sort_keys=True, ensure_ascii=False).encode()
        ),
        'evidence_accounting_version': 2,
        'recommendations': recommendations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--questions', type=Path, required=True)
    parser.add_argument('--responses', type=Path, required=True)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = cli_data_root(parser, args.data_root).resolve()
    try:
        output = args.output.resolve()
        if output.is_relative_to(root) or output in {
            args.questions.resolve(),
            args.responses.resolve(),
        }:
            raise ValueError('Keep the report outside the dataset and distinct from its inputs')
        report = diagnose(
            root, json.loads(args.questions.read_text()), json.loads(args.responses.read_text())
        )
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
