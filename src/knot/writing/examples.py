"""Generate a public synthetic dataset through KNOT's existing authoring APIs."""

import argparse
import sysconfig
from pathlib import Path

from knot.curating.candidates import publish_candidate
from knot.curating.provenance import source_pin
from knot.graph.knowledge import rebuild
from knot.graph.rdf import VOCAB
from knot.reviewing.writer import decide
from knot.writing.notes import create_note, save_note
from knot.writing.themes import add_themes

EXAMPLES = Path(__file__).resolve().parents[3] / 'data-examples'
PROJECT = 'urn:knot:entity:00000000-0000-4000-8000-000000000101'
CONCEPT = 'urn:knot:entity:00000000-0000-4000-8000-000000000102'
TRIAL = 'urn:knot:entity:00000000-0000-4000-8000-000000000201'
TANK = 'urn:knot:entity:00000000-0000-4000-8000-000000000202'
VOLUNTEERS = 'urn:knot:entity:00000000-0000-4000-8000-000000000203'
DECISION = 'urn:knot:entity:00000000-0000-4000-8000-000000000204'


def _declaration(body, identifier, label, kind):
    return {
        'id': identifier,
        'label': label,
        'type': kind,
        'quote': label,
        'offset': body.decode('utf-8').index(label),
    }


def _connected_examples(root, texts, themes, garden, reading):
    trial = create_note(
        root,
        texts['trial'],
        title='Rainwater trial',
        author='Example author',
        agent='Example generator',
        kind='Hypothesis',
        entities=[PROJECT, CONCEPT],
        navigation={
            'themes': themes,
            'links': [
                {'note': garden['note'], 'reason': 'Develops the project proposal.'},
                {'note': reading['note'], 'reason': 'Defines the concept the trial explores.'},
            ],
            'declarations': [
                _declaration(texts['trial'], TRIAL, 'Rainwater trial', 'Action'),
                _declaration(texts['trial'], TANK, 'Rainwater tank', 'Tool'),
            ],
        },
    )
    decision = create_note(
        root,
        texts['decision'],
        title='Wait for the tank',
        author='Example author',
        agent='Example generator',
        kind='Statement',
        entities=[PROJECT, TRIAL, TANK],
        navigation={
            'themes': themes[1:],
            'links': [
                {'note': trial['note'], 'reason': 'Records the decision governing the trial.'}
            ],
            'declarations': [
                _declaration(texts['decision'], VOLUNTEERS, 'Garden volunteers', 'Group'),
                _declaration(texts['decision'], DECISION, 'Trial timing decision', 'Decision'),
            ],
        },
    )
    observation = create_note(
        root,
        texts['observation'],
        title='Trial readiness check',
        author='Example author',
        agent='Example generator',
        kind='Observation',
        entities=[PROJECT, TRIAL, TANK],
        navigation={
            'themes': themes,
            'links': [
                {'note': trial['note'], 'reason': 'Qualifies the proposal with current readiness.'},
                {
                    'note': decision['note'],
                    'reason': 'Explains why the decision to wait still matters.',
                },
            ],
            'declarations': [],
        },
    )
    synthesis = create_note(
        root,
        '# Why the trial is still a proposal\n\n'
        'The fictional garden trial depends on a tank. The volunteers decided to wait, '
        'and the readiness check records that the tank is not yet available. '
        'No completed trial or water-saving result is established.\n',
        title='Why the trial is still a proposal',
        author='Example curator',
        agent='Example generator',
        kind='Assessment',
        entities=[PROJECT, TRIAL, TANK],
        derivation={
            'method': 'synthesis',
            'qualification': 'Several notes from one fictional scenario, not independent corroboration.',
            'sources': [
                source_pin(root, note['revision'], quote, note['body'].index(quote))
                for note, quote in [
                    (
                        trial,
                        'The Rainwater trial depends on a Rainwater tank being available before it can start.',
                    ),
                    (
                        decision,
                        'Garden volunteers made the Trial timing decision: wait until the tank is available.',
                    ),
                    (
                        observation,
                        'The Rainwater tank is not yet available. No trial run or water-saving result has\nbeen recorded for the community garden project.',
                    ),
                ]
            ],
        },
    )
    endpoints = {
        PROJECT: 'Community garden project',
        CONCEPT: 'Water conservation',
        TRIAL: 'Rainwater trial',
        TANK: 'Rainwater tank',
        VOLUNTEERS: 'Garden volunteers',
        DECISION: 'Trial timing decision',
    }
    for name, source, subject, predicate, target, quote in [
        (
            'project-trial',
            trial,
            PROJECT,
            'relatedTo',
            TRIAL,
            'The community garden project includes a proposed Rainwater trial.',
        ),
        (
            'trial-tank',
            trial,
            TRIAL,
            'dependsOn',
            TANK,
            'The Rainwater trial depends on a Rainwater tank being available before it can start.',
        ),
        (
            'project-tank',
            trial,
            PROJECT,
            'dependsOn',
            TANK,
            'The community garden project also depends on that Rainwater tank being available.',
        ),
        (
            'trial-concept',
            trial,
            TRIAL,
            'relatedTo',
            CONCEPT,
            'The Rainwater trial explores Water conservation; no reduction has been measured.',
        ),
        (
            'volunteers-project',
            decision,
            VOLUNTEERS,
            'workedOn',
            PROJECT,
            'Garden volunteers are working on the community garden project.',
        ),
        (
            'volunteers-decision',
            decision,
            VOLUNTEERS,
            'madeDecision',
            DECISION,
            'Garden volunteers made the Trial timing decision: wait until the tank is available.',
        ),
        (
            'decision-trial',
            decision,
            DECISION,
            'decisionAbout',
            TRIAL,
            'The Trial timing decision concerns the Rainwater trial.',
        ),
    ]:
        publish_candidate(
            root,
            {
                'id': 'urn:knot:assertion:example-' + name,
                'subject': {'id': subject, 'label': endpoints[subject]},
                'predicate': VOCAB + predicate,
                'object': {'id': target, 'label': endpoints[target]},
                'origin': 'Explicit',
                'rationale': 'A relationship in the fictional planning scenario; no completed trial is established.',
                'agent': 'urn:knot:agent:example-generator',
                'generated_at': '2026-01-01T12:00:00Z',
                'sources': [
                    source_pin(root, source['revision'], quote, source['body'].index(quote))
                ],
            },
        )
    return {
        'trial_note': trial['note'],
        'decision_note': decision['note'],
        'observation': observation['note'],
        'synthesis': synthesis['note'],
        'trial': TRIAL,
        'tank': TANK,
        'volunteers': VOLUNTEERS,
        'decision': DECISION,
    }


def build_examples(destination):
    root = Path(destination).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError('Example destination must be empty; existing data is never overwritten')
    examples = (
        EXAMPLES
        if EXAMPLES.is_dir()
        else Path(sysconfig.get_path('data')) / 'share/knot/data-examples'
    )
    # Read all packaged inputs before creating a dataset. The checkout and wheel
    # use the same example files, without a second embedded copy of their text.
    garden_text = (examples / 'garden.md').read_bytes()
    reading_text = (examples / 'reading.org').read_bytes()
    question_text = (examples / 'question.md').read_bytes()
    connected_texts = {
        name: (examples / (name + '.md')).read_bytes()
        for name in ('trial', 'decision', 'observation')
    }
    add_themes(
        root,
        [{'id': name, 'label': name.title(), 'keywords': []} for name in ('learning', 'projects')],
    )
    themes = [{'id': name, 'label': name.title()} for name in ('learning', 'projects')]
    garden = create_note(
        root,
        garden_text,
        title='Community garden plan',
        author='Example author',
        agent='Example generator',
        kind='Idea',
        navigation={
            'themes': themes,
            'links': [],
            'declarations': [
                {
                    'id': PROJECT,
                    'label': 'Community garden project',
                    'type': 'Project',
                    'quote': 'community garden project',
                    'offset': garden_text.decode().index('community garden project'),
                }
            ],
        },
    )
    reading = create_note(
        root,
        reading_text,
        format='org',
        title='Water conservation',
        author='Example author',
        agent='Example generator',
        kind='Definition',
        navigation={
            'themes': themes[:1],
            'links': [
                {'note': garden['note'], 'reason': 'Provides context for the proposed trial.'}
            ],
            'declarations': [
                {
                    'id': CONCEPT,
                    'label': 'Water conservation',
                    'type': 'Concept',
                    'quote': 'Water conservation',
                    'offset': 2,
                }
            ],
        },
    )
    isolated = create_note(
        root,
        question_text,
        title='An independent question',
        kind='Question',
    )
    quote = 'The community garden project explores water conservation.'
    pin = source_pin(root, garden['revision'], quote, garden['body'].index(quote))
    curated = create_note(
        root,
        '# Garden and conservation\n\nThe fictional project explores water conservation. '
        'The source describes a proposal, not a completed outcome.\n',
        title='Garden and conservation',
        author='Example curator',
        agent='Example generator',
        entities=[PROJECT, CONCEPT],
        kind='Statement',
        derivation={
            'method': 'faithful_restatement',
            'qualification': 'One fictional account; no measured outcome.',
            'sources': [pin],
        },
    )
    for suffix, predicate, origin in [
        ('connection', 'relatedTo', 'Explicit'),
        ('suggestion', 'relatedTo', 'Inferred'),
    ]:
        candidate = {
            'id': 'urn:knot:assertion:example-' + suffix,
            'subject': {'id': PROJECT, 'label': 'Community garden project'},
            'predicate': VOCAB + predicate,
            'object': {'id': CONCEPT, 'label': 'Water conservation'},
            'origin': origin,
            'rationale': 'The example records an interest, not a measured result.',
            'agent': 'urn:knot:agent:example-generator',
            'generated_at': '2026-01-01T12:00:00Z',
            'sources': [pin],
        }
        publish_candidate(root, candidate)
    decide(
        root,
        'urn:knot:assertion:example-connection',
        'accept',
        reviewer='Example reviewer',
        reason='Synthetic review demonstrating an accepted association.',
    )
    decide(
        root,
        'urn:knot:assertion:example-suggestion',
        'correct',
        reviewer='Example reviewer',
        reason='Synthetic correction clarifying the qualification.',
        replacement={
            'subject': PROJECT,
            'predicate': VOCAB + 'relatedTo',
            'object': CONCEPT,
            'subject_label': 'Community garden project',
            'object_label': 'Water conservation',
            'rationale': 'A possible reading connection; no successful outcome is established.',
        },
    )
    save_note(
        root,
        garden['note'],
        garden['body'] + '\nThe proposal is still under discussion.\n',
        expected=garden['revision'],
        agent='Example generator',
        reason='Demonstrate current versus cited text.',
    )
    connected = _connected_examples(root, connected_texts, themes, garden, reading)
    rebuild(root)
    return {
        'garden': garden['note'],
        'reading': reading['note'],
        'isolated': isolated['note'],
        'curated': curated['note'],
        'project': PROJECT,
        'concept': CONCEPT,
        'cited_revision': garden['revision'],
        **connected,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        build_examples(args.destination)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f'Example dataset created at {args.destination.resolve()}')


if __name__ == '__main__':
    main()
