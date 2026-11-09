"""Source-backed display names, independent of identity and assertion history."""

import json

from pyoxigraph import NamedNode

from knot.shared.storage import managed_path


def _validate_sources(root, sources, store):
    from knot.curating.provenance import validate_sources

    validate_sources(root, sources, store=store)


def _profile(value):
    fields = {'entity', 'preferred_label', 'aliases', 'agent', 'reason', 'sources'}
    if set(value) != fields:
        raise ValueError('Entity label profiles require identity, names, attribution and sources')
    NamedNode(value['entity'])
    for key in ('preferred_label', 'agent', 'reason'):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f'Entity label profile requires a nonempty {key}')
    aliases = value['aliases']
    if (
        not isinstance(aliases, list)
        or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
        or len(set(aliases)) != len(aliases)
    ):
        raise ValueError('Entity label aliases must be unique nonempty names')
    if not isinstance(value['sources'], list) or not value['sources']:
        raise ValueError('Entity label profiles require source provenance')


def apply_entity_labels(root, store, records, labels, *, scope=None):
    """Copy display fields after access filtering; never infer or mutate identities."""
    from knot.graph.query import identity_bindings

    path = managed_path(root, 'curation/entity-labels.json')
    if not path.exists():
        return records, labels
    data = json.loads(path.read_text(encoding='utf-8'))
    if (
        not isinstance(data, dict)
        or set(data) != {'schema_version', 'profiles'}
        or type(data['schema_version']) is not int
        or data['schema_version'] != 1
        or not isinstance(data['profiles'], list)
    ):
        raise ValueError('Invalid entity label catalogue')
    grants = dict(scope.revisions) if scope is not None and not scope.whole_dataset else None
    bindings = {source.value: target.value for source, target in identity_bindings(store).items()}
    profiles = {}
    for profile in data['profiles']:
        if not isinstance(profile, dict):
            raise ValueError('Invalid entity label profile')
        entity = profile.get('entity')
        if not isinstance(entity, str) or bindings.get(entity, entity) not in labels:
            # A display overlay cannot create an entity or expose an unseen identity.
            continue
        sources = profile.get('sources')
        if grants is not None and (
            not isinstance(sources, list)
            or not sources
            or any(
                not isinstance(source, dict)
                or not isinstance(source.get('revision'), str)
                or source['revision'] not in grants
                or grants[source['revision']] != source.get('sha256')
                for source in sources
            )
        ):
            # Denied source pins must be checked before any source read or validation.
            continue
        _profile(profile)
        if entity in profiles:
            raise ValueError('Duplicate entity label profile')
        _validate_sources(root, sources, store)
        profiles[entity] = profile
    if not profiles:
        return records, labels
    names = {entity: set(values) for entity, values in labels.items()}
    for entity, profile in profiles.items():
        # A confirmed source identity contributes searchable history, not a competing
        # preferred name for the canonical referent. Its own source grants still apply.
        names[bindings.get(entity, entity)].update(
            [profile['preferred_label'], *profile['aliases']]
        )
    displayed = []
    for record in records:
        changed = dict(record)
        for end in ('subject', 'object'):
            entity = record[end]
            profile = profiles.get(entity['id'])
            if profile is not None and not entity.get('literal'):
                changed[end] = {
                    **entity,
                    'original_label': entity.get('original_label', entity['label']),
                    'label': profile['preferred_label'],
                }
        displayed.append(changed)
    return displayed, names
