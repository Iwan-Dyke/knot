"""Build a verifiable RDF dataset from preserved sources and curated candidates."""

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pyoxigraph import NamedNode, RdfFormat, Store

from knot.curating.rules import validate_relationship
from knot.graph.rdf import (
    ATTRIBUTED,
    BASE,
    DERIVED,
    LABEL,
    META,
    RDF_TYPE,
    VOCAB,
    Dataset,
    identifier,
    write_bytes,
)
from knot.ingestion.frameworks import build_frameworks
from knot.ingestion.inventory import verify_sources
from knot.shared.datasets import cli_data_root
from knot.shared.storage import atomic_json, digest, managed_path
from knot.shared.text import extract_text, segment_text


def migrate(root):
    root = Path(root).resolve()
    curation = managed_path(root, 'curation')
    legacy = managed_path(root, 'migration')
    if curation.exists():
        if not curation.is_dir():
            raise ValueError('Curation path must be a directory')
        # A partial move must not silently drop claims or identity decisions.
        if any(legacy.glob('curated-*.json')) or any(
            (legacy / name).exists() for name in ('entities.json', 'frameworks.json')
        ):
            raise ValueError('Curation inputs are split; move all inputs into curation/')
    else:
        curation = legacy
    inventory = json.loads(managed_path(root, 'migration/inventory.json').read_text())
    if inventory['summary']['errors']:
        raise ValueError('Resolve inventory errors before migration')
    verify_sources(root, inventory)
    previous_path = managed_path(root, 'migration/conversion.json')
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    generated_at = previous.get('generated_at', datetime.now(timezone.utc).isoformat())
    # A rerun must never erase manually reviewed or corrected graph content.
    for relative, expected in previous.get('outputs', {}).items():
        path = managed_path(root, relative)
        if not path.exists() or digest(path.read_bytes()) != expected:
            raise ValueError(
                f'Generated output changed or missing; reconcile before rebuilding: {relative}'
            )
    graph_path = managed_path(root, 'graph/knowledge.trig')
    if graph_path.exists() and not previous:
        raise ValueError('Existing graph has no conversion ledger; refusing overwrite')

    # File moves do not change where an existing assertion was first extracted.
    # Its original provenance is part of immutable review fingerprints.
    curation_files = {}
    if graph_path.exists():
        prior = Store()
        prior.load(path=graph_path, format=RdfFormat.TRIG)
        for quad in prior.quads_for_pattern(None, NamedNode(VOCAB + 'curationFile'), None, META):
            curation_files[quad.subject.value] = quad.object.value

    dataset = Dataset()
    bindings = {}
    binding_path = managed_path(root, curation.relative_to(root) / 'entities.json')
    if binding_path.exists():
        for binding in json.loads(binding_path.read_text())['bindings']:
            key = (binding['source_sha256'], binding['label'])
            if key in bindings and bindings[key] != binding['entity_id']:
                raise ValueError(f'Conflicting entity binding: {key}')
            status = binding.get('status', 'unreviewed').lower()
            if status not in ('accepted', 'unreviewed', 'rejected'):
                raise ValueError(f'Invalid identity review status: {status}')
            if status == 'accepted':
                bindings[key] = binding['entity_id']
            identity = identifier('identity-proposal', json.dumps(binding, sort_keys=True))
            dataset.add(identity, VOCAB + 'entity', binding['entity_id'])
            dataset.add(
                identity,
                VOCAB + 'sourceEntity',
                identifier('entity', binding['source_sha256'] + '\0' + binding['label']),
            )
            dataset.add(identity, VOCAB + 'sourceLabel', binding['label'], literal=True)
            dataset.add(identity, VOCAB + 'revision', BASE + 'revision:' + binding['source_sha256'])
            dataset.add(identity, VOCAB + 'rationale', binding['rationale'], literal=True)
            dataset.add(identity, VOCAB + 'reviewStatus', VOCAB + status.capitalize())
            for key in ('reviewer', 'time'):
                if key in binding:
                    if not isinstance(binding[key], str) or not binding[key].strip():
                        raise ValueError(f'Invalid identity review {key}')
                    dataset.add(identity, VOCAB + key, binding[key], literal=True)
    by_hash = defaultdict(list)
    for item in inventory['entries']:
        if item['status'] == 'verified':
            by_hash[item['sha256']].append(item)
    records, texts, outputs, extracted_texts = {}, {}, {}, {}
    for sha, occurrences in sorted(by_hash.items()):
        first = occurrences[0]
        snapshot = managed_path(root, first['snapshot'])
        if digest(snapshot.read_bytes()) != sha:
            raise ValueError(f'Snapshot hash mismatch: {snapshot}')
        result = extract_text(snapshot)
        text = result.pop('text')
        texts[sha] = text
        segments = segment_text(text, result['format'])
        assert ''.join(segment['text'] for segment in segments) == text
        relative_text = f'migration/text/{sha}.txt'
        extracted_texts[relative_text] = text.encode('utf-8')
        outputs[relative_text] = digest(text.encode('utf-8'))
        revision = BASE + 'revision:' + sha
        dataset.add(revision, RDF_TYPE, VOCAB + 'DocumentRevision')
        dataset.add(revision, VOCAB + 'sha256', sha, literal=True)
        dataset.add(revision, VOCAB + 'snapshotPath', first['snapshot'], literal=True)
        dataset.add(revision, VOCAB + 'textPath', relative_text, literal=True)
        for warning in result['warnings']:
            dataset.add(revision, VOCAB + 'warning', warning, literal=True)
        for occurrence in occurrences:
            document = identifier('document', occurrence['logical_path'])
            dataset.add(document, RDF_TYPE, VOCAB + 'Document')
            dataset.add(document, LABEL, occurrence['logical_path'], literal=True)
            dataset.add(document, VOCAB + 'revision', revision)
            source = BASE + 'occurrence:' + occurrence['occurrence_id']
            dataset.add(source, VOCAB + 'revision', revision)
            for key in ('archive', 'archive_sha256', 'member', 'member_index'):
                dataset.add(source, VOCAB + key, occurrence[key], literal=True)
        ids = Counter(segment['org_id'] for segment in segments if segment['org_id'])
        passages = []
        for segment in segments:
            passage = identifier('passage', sha + segment['key'])
            org_id = segment['org_id']
            if org_id and ids[org_id] == 1:
                heading_key = first['logical_path'] + '\0org:' + org_id
                identity = 'source_id'
            else:
                heading_key = first['logical_path'] + '\0content:' + segment['key']
                identity = 'generated_requires_review_after_edits'
                if org_id:
                    result['warnings'].append(
                        f'Conflicting Org ID {org_id}; heading not merged by ID'
                    )
            heading = identifier('heading', heading_key)
            dataset.add(heading, RDF_TYPE, VOCAB + 'Heading')
            dataset.add(heading, LABEL, segment['title'], literal=True)
            if org_id:
                dataset.add(heading, VOCAB + 'orgId', org_id, literal=True)
            dataset.add(passage, RDF_TYPE, VOCAB + 'Passage')
            dataset.add(passage, VOCAB + 'revision', revision)
            dataset.add(passage, VOCAB + 'heading', heading)
            for key in ('start_line', 'end_line', 'text'):
                dataset.add(passage, VOCAB + key, segment[key], literal=True)
            dataset.add(passage, VOCAB + 'locatorKind', result['locator_kind'], literal=True)
            passages.append(
                {
                    'id': passage,
                    'heading': heading,
                    'identity': identity,
                    'start_line': segment['start_line'],
                    'end_line': segment['end_line'],
                    'semantic_status': 'pending',
                    'assertions': [],
                }
            )
        records[sha] = {
            **result,
            'source_paths': sorted({o['logical_path'] for o in occurrences}),
            'snapshot': first['snapshot'],
            'text_path': relative_text,
            'text_sha256': outputs[relative_text],
            'text_status': 'extracted',
            'structure_status': 'complete',
            'semantic_status': 'pending',
            'passages': passages,
        }
        for warning in result['warnings']:
            dataset.add(revision, VOCAB + 'warning', warning, literal=True)

    count = 0
    seen = set()
    for path in sorted(curation.glob('curated-*.json')):
        path = managed_path(root, path.relative_to(root))
        if path.stem.endswith('-coverage'):
            continue
        claims = json.loads(path.read_text())
        for claim in claims:
            sha, quote = claim['source_sha256'], claim['quote']
            if sha not in texts or not quote or quote not in texts[sha]:
                raise ValueError(f'Claim quote does not match source: {path.name}, {sha}')
            if claim['origin'] not in ('explicit', 'inferred'):
                raise ValueError(f'Invalid candidate vocabulary: {claim}')
            signature = json.dumps(claim, sort_keys=True, ensure_ascii=False)
            assertion = identifier('assertion', signature)
            if assertion in seen:
                continue
            seen.add(assertion)
            count += 1
            # Identity resolution belongs to the query projection so approvals stay valid.
            subject = identifier('entity', sha + '\0' + claim['subject'])
            obj = identifier('entity', sha + '\0' + claim['object'])
            validate_relationship(
                NamedNode(subject), NamedNode(VOCAB + claim['predicate']), NamedNode(obj)
            )
            dataset.add(subject, VOCAB + claim['predicate'], obj, graph=assertion)
            for entity, label in ((subject, claim['subject']), (obj, claim['object'])):
                dataset.add(entity, LABEL, label, literal=True)
                dataset.add(entity, RDF_TYPE, VOCAB + 'CandidateEntity')
            dataset.add(assertion, RDF_TYPE, VOCAB + 'Assertion')
            dataset.add(assertion, VOCAB + 'subjectLabel', claim['subject'], literal=True)
            dataset.add(assertion, VOCAB + 'objectLabel', claim['object'], literal=True)
            dataset.add(assertion, VOCAB + 'reviewStatus', VOCAB + 'Unreviewed')
            dataset.add(assertion, VOCAB + 'origin', VOCAB + claim['origin'].capitalize())
            dataset.add(assertion, VOCAB + 'lifecycle', VOCAB + 'Active')
            dataset.add(assertion, VOCAB + 'rationale', claim['rationale'], literal=True)
            dataset.add(assertion, ATTRIBUTED, BASE + 'agent:codex-curation')
            dataset.add(assertion, VOCAB + 'generatedAt', generated_at, literal=True)
            dataset.add(
                assertion,
                VOCAB + 'curationFile',
                curation_files.get(assertion, path.relative_to(root).as_posix()),
                literal=True,
            )
            # Exact quote offsets remove ambiguity when a quote repeats in a source.
            offset = texts[sha].find(quote)
            if texts[sha].find(quote, offset + 1) != -1:
                records[sha]['warnings'].append(
                    'Repeated quote: candidate anchored to first occurrence; review needed'
                )
            prefix = texts[sha][:offset]
            line = len(prefix.splitlines()) + (not prefix or prefix.endswith(('\n', '\r', '\f')))
            line = max(1, line)
            evidence = identifier('evidence', sha + '\0' + str(offset) + '\0' + quote)
            dataset.add(evidence, VOCAB + 'revision', BASE + 'revision:' + sha)
            dataset.add(evidence, VOCAB + 'quote', quote, literal=True)
            dataset.add(evidence, VOCAB + 'characterOffset', offset, literal=True)
            dataset.add(evidence, VOCAB + 'locatorKind', records[sha]['locator_kind'], literal=True)
            dataset.add(assertion, DERIVED, evidence)
            for passage in records[sha]['passages']:
                if passage['start_line'] <= line <= passage['end_line']:
                    passage['assertions'].append(assertion)
                    passage['semantic_status'] = 'candidates_extracted_not_exhaustive'
                    dataset.add(evidence, VOCAB + 'passage', passage['id'])
                    break
    for path in sorted(curation.glob('curated-*-coverage.json')):
        path = managed_path(root, path.relative_to(root))
        coverage = json.loads(path.read_text())
        for sha, review in coverage.items():
            if sha not in records:
                raise ValueError(f'Unknown coverage revision {sha}')
            records[sha]['curation_review'] = review
            records[sha]['semantic_status'] = (
                'selective_pass' if review.get('reviewed') else 'pending'
            )

    framework_path = managed_path(root, curation.relative_to(root) / 'frameworks.json')
    if 'graph/frameworks.trig' in previous.get('outputs', {}) and not framework_path.exists():
        raise ValueError('Framework catalogue missing; reconcile before rebuilding')
    framework_rdf = None
    if framework_path.exists():
        framework_catalog = json.loads(framework_path.read_text())
        framework_rdf = build_frameworks(root, framework_catalog)
        for framework in framework_catalog['frameworks']:
            records[framework['sha256']]['framework_competencies'] = len(framework['skills'])
    serialised = dataset.text().encode('utf-8')
    store = Store()
    store.load(input=serialised, format=RdfFormat.TRIG)
    expected = sum(len(lines) for lines in dataset.graphs.values())
    assert len(store) == expected
    # Candidate and framework validation must finish before any generated output changes.
    for relative_text, content in extracted_texts.items():
        write_bytes(managed_path(root, relative_text), content)
    write_bytes(graph_path, serialised)
    outputs['graph/knowledge.trig'] = digest(serialised)
    if framework_rdf is not None:
        write_bytes(managed_path(root, 'graph/frameworks.trig'), framework_rdf)
        outputs['graph/frameworks.trig'] = digest(framework_rdf)
    summary = {
        'source_occurrences': inventory['summary']['verified_files'],
        'unique_revisions': len(records),
        'text_extracted': len(records),
        'passages': sum(len(r['passages']) for r in records.values()),
        'candidate_assertions': count,
        'rdf_quads': len(store),
        'revisions_with_warnings': sum(bool(r['warnings']) for r in records.values()),
        'semantic_passes': sum(r['semantic_status'] == 'selective_pass' for r in records.values()),
        'human_accepted_assertions': 0,
    }
    if framework_rdf is not None:
        summary['framework_competencies'] = sum(
            len(f['skills']) for f in framework_catalog['frameworks']
        )
        summary['framework_mastery_criteria'] = sum(
            len(s['levels']) for f in framework_catalog['frameworks'] for s in f['skills']
        )
    ledger = {
        'schema_version': 1,
        'converter_version': '0.1.0',
        'generated_at': generated_at,
        'summary': summary,
        'outputs': outputs,
        'revisions': records,
    }
    atomic_json(previous_path, ledger)
    report = (
        '# Migration coverage\n\nImport snapshot only; current decisions and conversation confirmations are reported by `just review summary`.\n\n'
        + '\n'.join(f'- {k}: {v}' for k, v in summary.items())
    )
    report += '\n\nImported claims start unreviewed; the counts above exclude review events and separately confirmed claims. Semantic passes are selective, not proof that every meaning was extracted.\n'
    report += '\n| Source | Semantic pass | Candidates | Warnings and review limitations |\n| --- | --- | --- | --- |\n'
    for record in records.values():
        claims = sum(len(p['assertions']) for p in record['passages'])
        notes = record['warnings'] + record.get('curation_review', {}).get('limitations', [])
        report += f'| {", ".join(record["source_paths"])} | {record["semantic_status"]} | {claims} | {"; ".join(notes).replace("|", "/")} |\n'
    write_bytes(managed_path(root, 'migration/REPORT.md'), report.encode())
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    args = parser.parse_args()
    args.data_root = cli_data_root(parser, args.data_root)
    print(json.dumps(migrate(args.data_root)['summary'], indent=2))


if __name__ == '__main__':
    main()
