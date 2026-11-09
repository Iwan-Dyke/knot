"""Shared knowledge kinds, entity types and IRI names."""

KINDS = {
    'Unspecified',
    'Statement',
    'Observation',
    'Thought',
    'Idea',
    'Hypothesis',
    'Question',
    'Assessment',
    'Definition',
}

TYPES = {
    'Entity',
    'Person',
    'Project',
    'Document',
    'Event',
    'Decision',
    'Action',
    'Outcome',
    'Concept',
    'Capability',
    'Book',
    'Framework',
    'RoleGrade',
    'Group',
    'Tool',
}


def local_name(iri):
    return iri.rsplit('#', 1)[-1].rsplit('/', 1)[-1].rsplit(':', 1)[-1]
