"""Build source-backed competency assertions from a curated extraction catalogue."""

import re

from knot.graph.rdf import ATTRIBUTED, DERIVED, LABEL, RDF_TYPE, VOCAB, Dataset, identifier
from knot.shared.storage import digest, managed_path
from knot.shared.text import extract_text

SKOS = 'http://www.w3.org/2004/02/skos/core#'


def clean_text(text):
    # PDF page furniture can interrupt a criterion; retain it only in the exact quote.
    lines = [
        line
        for line in text.splitlines()
        if not re.match(r'^(\d{2}/\d{2}/\d{4}, \d{2}:\d{2}|Page \d+ of \d+https:)', line)
    ]
    return '\n'.join(lines).replace('\xa0', ' ').strip()


def build_frameworks(root, catalog):
    dataset = Dataset()
    keys = [f['key'] for f in catalog['frameworks']]
    if len(keys) != len(set(keys)) or catalog['active_framework'] not in keys:
        raise ValueError('Invalid framework selection or duplicate framework key')
    if catalog.get('authority_record'):
        dataset.add(
            'urn:knot:assessment-policy',
            VOCAB + 'authorityRecord',
            catalog['authority_record'],
            literal=True,
        )
    for framework in catalog['frameworks']:
        snapshot = managed_path(root, framework['snapshot'])
        if digest(snapshot.read_bytes()) != framework['sha256']:
            raise ValueError('Framework source hash mismatch or unsafe snapshot')
        text = extract_text(snapshot)['text']
        sha = framework['sha256']
        fid = 'urn:knot:framework:' + framework['key'] + ':' + sha
        revision = 'urn:knot:revision:' + sha
        dataset.add(revision, VOCAB + 'snapshotPath', framework['snapshot'], literal=True)
        dataset.add(revision, VOCAB + 'sha256', sha, literal=True)
        dataset.add(fid, RDF_TYPE, SKOS + 'ConceptScheme')
        dataset.add(fid, LABEL, framework['title'], literal=True)
        dataset.add(fid, DERIVED, revision)
        if framework['key'] == catalog['active_framework']:
            dataset.add('urn:knot:assessment-policy', VOCAB + 'currentFramework', fid)

        def assertion(subject, predicate, obj, quote, subject_label, object_label, literal=False):
            if not quote or quote not in text:
                raise ValueError(f'Framework quotation does not match source: {subject_label}')
            aid = identifier(
                'framework-assertion', '\0'.join((subject, predicate, obj, sha, quote))
            )
            evidence = identifier('framework-evidence', sha + '\0' + quote)
            dataset.add(subject, predicate, obj, literal=literal, graph=aid)
            for key, value in (
                ('reviewStatus', 'Unreviewed'),
                ('origin', 'Explicit'),
                ('lifecycle', 'Active'),
                ('recordKind', 'FrameworkDefinition'),
            ):
                dataset.add(aid, VOCAB + key, VOCAB + value)
            dataset.add(aid, RDF_TYPE, VOCAB + 'Assertion')
            dataset.add(aid, VOCAB + 'framework', fid)
            dataset.add(aid, VOCAB + 'subjectLabel', subject_label, literal=True)
            dataset.add(aid, VOCAB + 'objectLabel', object_label, literal=True)
            dataset.add(
                aid,
                VOCAB + 'rationale',
                'Explicit career-framework definition or requirement; source quotation checked. Personal achievement is assessed separately.',
                literal=True,
            )
            dataset.add(aid, ATTRIBUTED, 'urn:knot:agent:codex-curation')
            dataset.add(aid, DERIVED, evidence)
            dataset.add(evidence, VOCAB + 'revision', revision)
            dataset.add(evidence, VOCAB + 'quote', quote, literal=True)
            dataset.add(evidence, VOCAB + 'characterOffset', str(text.index(quote)), literal=True)
            dataset.add(
                evidence,
                VOCAB + 'locatorKind',
                'extracted_line' if snapshot.suffix.lower() == '.pdf' else 'source_line',
                literal=True,
            )
            dataset.add(
                evidence,
                VOCAB + 'startLine',
                str(text[: text.index(quote)].count('\n') + 1),
                literal=True,
            )

        seen = set()
        for skill in framework['skills']:
            if skill['name'] in seen:
                raise ValueError('Duplicate framework competency')
            seen.add(skill['name'])
            sid = identifier('competency', fid + '\0' + skill['name'])
            dataset.add(sid, RDF_TYPE, VOCAB + 'Competency')
            dataset.add(sid, RDF_TYPE, SKOS + 'Concept')
            dataset.add(sid, LABEL, skill['name'], literal=True)
            assertion(
                fid, VOCAB + 'hasCompetency', sid, skill['quote'], framework['title'], skill['name']
            )
            assertion(
                sid,
                SKOS + 'definition',
                clean_text(skill['quote']),
                skill['quote'],
                skill['name'],
                clean_text(skill['quote']),
                literal=True,
            )
            levels = {}
            for level, quote in skill['levels'].items():
                cid = identifier('criterion', sid + '\0' + level)
                levels[level] = cid
                label = skill['name'] + ' · ' + level + ' · ' + framework['key']
                dataset.add(cid, RDF_TYPE, VOCAB + 'MasteryCriterion')
                dataset.add(cid, LABEL, label, literal=True)
                dataset.add(cid, VOCAB + 'masteryLevel', level, literal=True)
                assertion(sid, VOCAB + 'hasCriterion', cid, quote, skill['name'], label)
                assertion(
                    cid,
                    SKOS + 'definition',
                    clean_text(quote),
                    quote,
                    label,
                    clean_text(quote),
                    literal=True,
                )
            for grade, level in skill['requirements'].items():
                if level.lower() == 'n/a':
                    continue
                if level not in levels:
                    raise ValueError(f'Missing {level} criterion for {skill["name"]}')
                gid = fid + ':grade:' + grade
                label = framework['title'] + ' · ' + grade
                dataset.add(gid, RDF_TYPE, VOCAB + 'RoleGrade')
                dataset.add(gid, LABEL, label, literal=True)
                dataset.add(gid, VOCAB + 'grade', grade, literal=True)
                assertion(
                    gid,
                    VOCAB + 'requires',
                    levels[level],
                    skill['requirements_quote'],
                    label,
                    skill['name'] + ' · ' + level + ' · ' + framework['key'],
                )
    return dataset.text().encode('utf-8')
