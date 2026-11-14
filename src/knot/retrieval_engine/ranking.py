"""Pure lexical scoring shared by search and discovery."""

import math
import re
from collections import Counter

from knot.shared.vocabulary import local_name

STOP = set(
    'a an and are as at be been by can did do does for from had has have how i in is it me my of on or other others our rather s should than that the their these this to was were what when which who why with would strongest evidence recorded'.split()
)

NORMAL = {
    'dependencies': 'dependency',
    'outcomes': 'outcome',
    'output': 'outcome',
    'outputs': 'outcome',
    'results': 'outcome',
    'result': 'outcome',
    'risks': 'risk',
    'blockers': 'blocker',
    'blocked': 'blocker',
    'decisions': 'decision',
    'retries': 'retry',
    'plans': 'plan',
    'deployed': 'deploy',
    'deploying': 'deploy',
    'deployment': 'deploy',
    'approvers': 'approve',
    'approvals': 'approve',
    'approval': 'approve',
    'redesigned': 'redesign',
    'teams': 'team',
    'delivered': 'deliver',
    'delivering': 'deliver',
    'delivery': 'deliver',
    'independently': 'independent',
    'independence': 'independent',
    'developing': 'develop',
    'development': 'develop',
    'delegating': 'delegate',
    'delegation': 'delegate',
    'constraints': 'constraint',
    'gates': 'gate',
    'gated': 'gate',
    'reports': 'report',
    'reconciled': 'reconcile',
    'reconciliation': 'reconcile',
}

INTENTS = {
    'dependencies': (
        {'dependency', 'blocker', 'risk', 'unresolved', 'threaten', 'missing'},
        {'dependsOn': 8},
    ),
    'leadership': (
        {
            'leadership',
            'delegate',
            'coaching',
            'mentoring',
            'feedback',
            'develop',
            'independent',
            'ownership',
        },
        {'reportedOutcome': 6, 'madeDecision': 5, 'implemented': 4, 'mentored': 4, 'enabled': 3},
    ),
    'outcomes': ({'outcome', 'deliver', 'achievement'}, {'reportedOutcome': 6}),
    'measurement': (
        {'measurable', 'measured', 'measurement'},
        {'reportedOutcome': 6},
    ),
    'speed_comparison': ({'faster', 'slower', 'slowdown'}, {}),
    'cost_comparison': ({'cheaper', 'costlier'}, {}),
}

# Groups prevent repeated synonyms from inflating an intent signal. They describe
# sought evidence, not its truth or a judgement that an achievement was strongest.
CONCEPTS = {
    'leadership': (
        {'independent', 'autonomy', 'ownership', 'delegate'},
        {'deliver', 'outcome', 'support'},
        {'feedback', 'recognition', 'award', 'corroboration', 'corroborates'},
    ),
    'outcomes': (
        {'independent', 'autonomy', 'ownership'},
        {'deliver', 'achieved', 'improved', 'reduced'},
    ),
    'dependencies': (
        {'missing', 'blocker', 'gate', 'constraint', 'unresolved'},
        {'deadline', 'cutoff', 'lead', 'pending', 'outstanding'},
        {'source', 'extract', 'upstream', 'feed'},
    ),
    'measurement': (
        {'target', 'baseline', 'count', 'ratio', 'percent', 'percentage'},
        {'done', 'completed', 'achieved', 'exceeded', 'reduced', 'increased'},
    ),
    # Opposite directions seek the same measurement; they do not agree on its result.
    'speed_comparison': (
        {'faster', 'slower', 'slowdown', 'runtime', 'latency', 'duration', 'throughput'},
    ),
    'cost_comparison': ({'cheaper', 'costlier', 'cost', 'costs', 'billing', 'expense', 'price'},),
}


def tokens(text):
    return {NORMAL.get(word, word) for word in re.findall(r'\w+', text.casefold())} - STOP


def _explicit_subjects(question):
    # Only explicit syntax constrains search; capitalised prose alone is not an identity.
    project = re.compile(r'\b[Pp]roject\s+(?:"([^"\n]+)"|“([^”\n]+)”|([A-Z][\w-]*))')
    names = {
        value.strip().casefold()
        for match in project.findall(question)
        for value in match
        if value.strip()
    }
    identifiers = re.findall(
        r'\b[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+\b', project.sub('', question)
    )
    names.update(value.casefold() for value in identifiers if any(c.isdigit() for c in value))
    return sorted(names)


class _Question:
    def __init__(self, question, aliases, *, constrain_subject=False):
        self.terms = tokens(question) - tokens(' '.join(aliases))
        self.intents = sorted(name for name, (words, _) in INTENTS.items() if self.terms & words)
        self.weights = {}
        self.subjects = _explicit_subjects(question) if constrain_subject else []

    def matches_subject(self, text):
        return any(
            re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', text, re.I)
            for name in self.subjects
        )

    def fit(self, texts):
        documents = [tokens(text) for text in texts]
        frequency = Counter(term for document in documents for term in document)
        self.weights = {
            term: 1 + math.log((len(documents) + 1) / (frequency[term] + 1)) for term in self.terms
        }

    def score(self, text, *, labels='', predicate=''):
        matched = sorted(self.terms & tokens(text))
        label_terms = sorted(self.terms & tokens(labels))
        bonus = max(
            (INTENTS[name][1].get(local_name(predicate), 0) for name in self.intents), default=0
        )
        word_count = len(re.findall(r'\w+', text))
        # Saturation avoids punishing a complete qualification merely for being long.
        length_factor = math.sqrt(1 + min(word_count, 160) / 80)
        terms = tokens(re.sub(r'^(?:[*#].*|:[A-Z_]+:.*)$', '', text, flags=re.M))
        concepts = sorted(
            {
                '/'.join(sorted(group))
                for intent in self.intents
                for group in CONCEPTS[intent]
                if terms & group
            }
        )
        lexical = 4 * sum(self.weights.get(term, 1) for term in matched)
        heading = 0.5 * sum(self.weights.get(term, 1) for term in label_terms)
        return {
            **(
                {'subject_match': self.matches_subject(text + ' ' + labels)}
                if self.subjects
                else {}
            ),
            'score': round((lexical + heading) / length_factor + bonus + 4 * len(concepts), 6),
            'matched': matched,
            'label_terms': label_terms,
            'length_factor': round(length_factor, 6),
            'predicate_bonus': bonus,
            'intents': self.intents,
            'concepts': concepts,
        }
