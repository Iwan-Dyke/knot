"""Terminal prompts shared by owner-local interactive commands."""

import json
import sys

from knot.shared.vocabulary import KINDS


def _ask(prompt, *, end='\n'):
    print(prompt, file=sys.stderr, flush=True, end=end)
    line = sys.stdin.readline()
    if not line:
        raise ValueError('Capture cancelled: input ended before saving')
    return line.rstrip('\r\n')


def _wizard(metadata, *, confirm=True, curated=False):
    if metadata.get('format', 'markdown') != 'markdown' or (
        'derivation' in metadata and not curated
    ):
        raise ValueError('Guided capture uses Markdown; use a file for Org or curated notes')
    print('Section 1: Note details (optional)', file=sys.stderr)
    for field, prompt in (
        ('title', 'Title (optional):'),
        ('author', 'Your name / author (optional; left unknown if skipped):'),
        ('kind', f'Kind (optional: {", ".join(sorted(KINDS))}):'),
    ):
        if field not in metadata:
            while True:
                value = _ask(prompt).strip()
                if field != 'kind' or not value or value in KINDS:
                    metadata[field] = value or None
                    break
                print(
                    'Choose a listed kind or press Enter to leave it unclassified.', file=sys.stderr
                )
    print(
        '\nSection 2: Your note\n'
        'Write one continuous note in your own words. Things to consider:\n'
        '  • What prompted this? Include context or a source where useful.\n'
        '  • What do you think, and why? What matters to you here?\n'
        '  • What does it connect to? What is uncertain or has changed your mind?\n'
        '  • Is there anything you want to try or revisit?\n'
        'These are prompts to think about, not separate answers to fill in.\n'
        'Enter keeps writing; blank lines keep paragraph breaks.\n'
        'Type /done on its own line to finish, or /cancel to cancel.\n'
        'No headings or guidance will be added to your note.',
        file=sys.stderr,
    )
    lines = []
    while True:
        line = _ask('note> ', end='')
        if line == '/cancel':
            raise ValueError('Capture cancelled: nothing saved')
        if line == '/done':
            break
        lines.append(line)
    if not any(line.strip() for line in lines):
        raise ValueError('Capture cancelled: no note text entered')
    body = '\n'.join(lines) + '\n'
    print('\nPreview', file=sys.stderr)
    print(json.dumps(metadata, ensure_ascii=False, indent=2), file=sys.stderr)
    print(body, file=sys.stderr)
    if confirm and _ask('Save this note? [y/N]').strip().lower() not in ('y', 'yes'):
        raise ValueError('Capture cancelled: nothing saved')
    return body


def _choose(prompt, choices, *, multiple=False):
    if not choices:
        print('No choices available; skipping this step.', file=sys.stderr)
        return [] if multiple else None
    for index, (label, _) in enumerate(choices, 1):
        print(f'{index}. {label}', file=sys.stderr)
    while True:
        answer = _ask(prompt + ' (Enter to skip):').strip()
        if not answer:
            return [] if multiple else None
        try:
            indexes = [int(n) - 1 for n in answer.split(',')]
            if (not multiple and len(indexes) != 1) or any(
                i < 0 or i >= len(choices) for i in indexes
            ):
                raise ValueError
            selected = [choices[i][1] for i in dict.fromkeys(indexes)]
            return selected if multiple else selected[0]
        except ValueError:
            print('Use the displayed number(s), separated by commas.', file=sys.stderr)


def _required(prompt):
    while True:
        value = _ask(prompt).strip()
        if value:
            return value


def _evidence(body, *, name='note'):
    while True:
        quote = _ask(f'Paste an exact supporting passage from the {name} (Enter to cancel):')
        if not quote:
            return None
        positions = [i for i in range(len(body)) if body.startswith(quote, i)]
        if not positions:
            print(
                f'That passage is not in the {name}. Preserve its exact wording.', file=sys.stderr
            )
            continue
        offset = (
            positions[0]
            if len(positions) == 1
            else _choose(
                'Which occurrence?',
                [
                    (f'Character {i}: {body[max(0, i - 40) : i + len(quote) + 40]!r}', i)
                    for i in positions
                ],
            )
        )
        if offset is not None:
            return quote, offset
