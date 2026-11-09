"""Immutable graph traversal policy and supported routing predicates."""

from dataclasses import asdict, dataclass

DOMAIN = (
    'madeDecision',
    'decisionAbout',
    'proposed',
    'dependsOn',
    'reportedOutcome',
    'implemented',
    'produced',
    'developed',
    'enabled',
    'selected',
    'mentored',
    'workedOn',
    'contributedTo',
    'resultedIn',
    'supports',
    'demonstrates',
    'documentedIn',
    'occurredOn',
    'hasMember',
    'eventCount',
    'used',
    'attributedByAuthorTo',
    'relatedTo',
)

FRAMEWORK = (
    'hasCompetency',
    'hasCriterion',
    'requires',
    'http://www.w3.org/2004/02/skos/core#definition',
)

GENERIC = {'Person', 'Theme', 'Framework', 'RoleGrade'}


@dataclass(frozen=True)
class Policy:
    max_depth: int = 2
    max_assertions: int = 10
    max_passages: int = 4
    max_chars: int = 12000
    max_expanded: int = 16
    max_frontier: int = 16
    max_degree: int = 12
    hub_degree: int = 24
    seed_hub_degree: int = 4
    accepted_only: bool = False
    include_frameworks: bool = False
    outgoing: tuple = DOMAIN
    incoming: tuple = ('relatedTo', 'decisionAbout')

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key.startswith('max_') or key in ('hub_degree', 'seed_hub_degree'):
                if type(value) is not int or value < 1:
                    raise ValueError(f'{key} must be a positive integer')
        for direction in (self.outgoing, self.incoming):
            if not isinstance(direction, tuple) or len(set(direction)) != len(direction):
                raise ValueError('Predicate policies must be tuples without duplicates')
            if set(direction) - set(DOMAIN + FRAMEWORK):
                raise ValueError('Only substantive and framework predicates may route retrieval')
