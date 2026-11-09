"""Shared structural rules and fallible semantic diagnostics for authored claims."""

import re

from pyoxigraph import Literal, NamedNode

from knot.graph.rdf import VOCAB

# A domain triple is not arbitrary ontology metadata or a navigation annotation.
# New relations require an ontology decision and an explicit addition here.
DOMAIN_PREDICATES = frozenset(
    'workedOn contributedTo resultedIn supports demonstrates dependsOn relatedTo '
    'documentedIn occurredOn reportedOutcome produced selected madeDecision decisionAbout '
    'proposed implemented enabled developed mentored hasMember eventCount used '
    'attributedByAuthorTo hasCompetency hasCriterion requires'.split()
)
ACTOR_TYPES = {VOCAB + 'Person', VOCAB + 'Group', 'http://www.w3.org/ns/prov#Agent'}
SPECIFIC_TYPES = {
    VOCAB + kind
    for kind in (
        'Person Group Project Document Book Event Decision Action Outcome Concept Capability '
        'Competency MasteryCriterion Framework RoleGrade Tool Note'
    ).split()
}


def validate_relationship(subject, predicate, obj):
    """Reject unsupported structure/vocabulary, never missing or uncertain domain types."""
    if not isinstance(subject, NamedNode) or not isinstance(predicate, NamedNode):
        raise ValueError('Assertion subject and predicate must be named IRIs')
    if predicate.value not in {VOCAB + name for name in DOMAIN_PREDICATES} | {
        'http://www.w3.org/2004/02/skos/core#definition'
    }:
        raise ValueError(f'Unsupported assertion predicate: {predicate.value}')
    if not isinstance(obj, (NamedNode, Literal)):
        raise ValueError('Assertion object must be a named IRI or an RDF literal')
    if isinstance(obj, Literal):
        patterns = {
            'http://www.w3.org/2001/XMLSchema#integer': r'[+-]?[0-9]+',
            'http://www.w3.org/2001/XMLSchema#decimal': r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)',
            'http://www.w3.org/2001/XMLSchema#boolean': r'(?:true|false|0|1)',
        }
        pattern = patterns.get(obj.datatype.value)
        if pattern and not re.fullmatch(pattern, obj.value.strip(' \t\r\n')):
            raise ValueError(f'Invalid lexical value for {obj.datatype.value}')


def qualification_issue(predicate, quotes, object_label):
    """A narrow plan/result heuristic; an exact quotation does not establish truth."""
    text = '\n'.join(quotes)
    proposal = re.search(
        r'(?im)^\s*(?:[-*]\s*)?(?:(?:I|we)\s+)?(?:proposed|planned(?:\s+to)?)\b', text
    )
    if predicate == 'madeDecision':
        return bool(proposal and not re.search(r'\b(chose|decided|agreed|approved)\b', text, re.I))
    if predicate == 'implemented':
        return bool(
            proposal
            and not re.search(r'\b(implemented|deployed|completed|delivered)\b', text, re.I)
        )
    if predicate == 'reportedOutcome':
        pending = r'\b(undecided|pending|proposed|proposals?|planned)\b'
        return bool(re.search(pending, object_label, re.I) and re.search(pending, text, re.I))
    return False


def relationship_warnings(
    predicate,
    subject_types,
    *,
    object_types=(),
    quotes=(),
    object_label='',
    subject=None,
    object=None,
):
    """Review prompts based on known types/context, without making open-world inferences."""
    name = predicate.removeprefix(VOCAB)
    kinds, objects = set(subject_types), set(object_types)
    warnings = []

    def warn(code, detail):
        warnings.append({'code': code, 'detail': detail, 'predicate': predicate})

    if isinstance(object, Literal) and name in {
        'workedOn',
        'contributedTo',
        'hasCompetency',
        'hasCriterion',
        'requires',
        'madeDecision',
        'implemented',
    }:
        warn(
            'literal_entity_relation',
            'Relationship usually identifies a referent; inspect whether this '
            'literal should be an attribute or an explicitly identified entity',
        )
        warnings[-1]['value'] = object.value

    if name in {'madeDecision', 'selected', 'proposed'} and kinds & SPECIFIC_TYPES:
        if not kinds & ACTOR_TYPES:
            warn(
                'decision_subject_needs_review'
                if name == 'madeDecision'
                else 'actor_subject_needs_review',
                'Known subject type does not identify a deciding/proposing actor; inspect attribution without assigning a person by default',
            )
    if name == 'decisionAbout' and kinds & SPECIFIC_TYPES and VOCAB + 'Decision' not in kinds:
        warn(
            'decision_about_subject_needs_review',
            'decisionAbout should start from a recorded decision, not its actor or context',
        )
    expected_objects = {
        'madeDecision': {'Decision'},
        'documentedIn': {'Document', 'Book', 'Note'},
        'hasCompetency': {'Competency', 'Capability'},
        'hasCriterion': {'MasteryCriterion'},
    }.get(name)
    if expected_objects and objects & SPECIFIC_TYPES:
        if not objects & {VOCAB + kind for kind in expected_objects}:
            warn(
                'relationship_object_type_needs_review',
                'Known object types may not fit this relationship; inspect the referent and source, without automatically retyping it',
            )
    if subject is not None and subject == object:
        warn(
            'self_relationship_needs_review',
            'Accepted identity projection makes this relationship reflexive; inspect whether it still expresses useful knowledge',
        )
    if qualification_issue(name, quotes, object_label):
        warn(
            'claim_qualification_needs_review',
            'Source/object wording describes a proposal, plan or unresolved matter; inspect whether this predicate overstates a decision or achieved result',
        )
    return warnings
