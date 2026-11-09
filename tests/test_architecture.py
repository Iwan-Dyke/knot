"""Dependency direction and frozen public retrieval behaviour."""

import ast
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from retrieval_fixture import SEED, make_fixture

from knot.discovery import discover, gather
from knot.retrieval import Policy, retrieve, serialise

SOURCE = Path(__file__).resolve().parents[1] / 'src/knot'
OWNERS = {
    'rdf': 'graph.rdf',
    'storage': 'shared.storage',
    'vocabulary': 'shared.vocabulary',
    'review_state': 'reviewing.state',
    'ranking': 'retrieval_engine.ranking',
    'response': 'retrieval_engine.response',
    'retrieval_context': 'retrieval_engine.context',
    'retrieval_policy': 'retrieval_engine.policy',
    'evidence': 'retrieval_engine.evidence',
    'graph_retrieval': 'retrieval_engine.graph',
    'search': 'retrieval_engine.search',
    'selection': 'retrieval_engine.selection',
    'source_selection': 'retrieval_engine.source_selection',
}


def module_path(module):
    return SOURCE / (OWNERS.get(module, module).replace('.', '/') + '.py')


def responses(root):
    for mode in ('graph', 'text', 'hybrid'):
        for budget in (4000, 12000):
            yield (
                f'{mode}-{budget}',
                retrieve(root, SEED, Policy(max_chars=budget), question='Orion retries', mode=mode),
            )
    yield 'graph-unranked', retrieve(root, SEED)
    yield 'accepted-only', retrieve(root, SEED, Policy(accepted_only=True))
    yield 'discovery', discover(root, 'Orion retries')
    yield 'gather', gather(root, [SEED], 'Orion retries')


class ArchitectureTests(unittest.TestCase):
    def test_all_legacy_modules_resolve_to_their_implementation(self):
        for path in (SOURCE / '_compat').glob('*.py'):
            if path.stem == '__init__':
                continue
            imports = [
                (node.module, alias.name)
                for node in ast.walk(ast.parse(path.read_text()))
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
                if alias.asname == '_implementation'
            ]
            self.assertEqual(len(imports), 1, path.name)
            package, name = imports[0]
            self.assertIs(
                importlib.import_module(f'knot.{path.stem}'),
                importlib.import_module(f'{package}.{name}'),
            )

    def test_legacy_module_commands_still_start(self):
        for module in (
            'inventory',
            'migrate',
            'knowledge',
            'query',
            'retrieval',
            'note_cli',
            'quality',
            'curation',
            'benchmark',
            'mcp_server',
            'review',
            'visualise',
        ):
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, '-m', f'knot.{module}', '--help'],
                    env={**os.environ, 'PYTHONPATH': str(SOURCE.parent)},
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage:', result.stdout)

    def test_package_root_contains_only_initialisation(self):
        self.assertEqual(sorted(p.name for p in SOURCE.iterdir() if p.is_file()), ['__init__.py'])

    def test_implementations_do_not_import_compatibility_modules(self):
        legacy = {p.stem for p in (SOURCE / '_compat').glob('*.py')} - {'__init__'}
        self.assertTrue(legacy)
        for path in SOURCE.rglob('*.py'):
            if '_compat' in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module, {f'knot.{name}' for name in legacy}, str(path))

    def test_legacy_imports_share_the_same_implementation(self):
        for legacy, owner in {
            'search': 'retrieval_engine.search',
            'selection': 'retrieval_engine.selection',
            'source_selection': 'retrieval_engine.source_selection',
            'discovery': 'retrieval_engine.discovery',
            'discovery_score': 'retrieval_engine.discovery_score',
            'review': 'reviewing.writer',
        }.items():
            self.assertIs(
                importlib.import_module(f'knot.{legacy}'),
                importlib.import_module(f'knot.{owner}'),
            )
        owners = {
            'inventory': {'storage': ['atomic_json', 'digest']},
            'knowledge': {'vocabulary': ['KINDS', 'TYPES', 'local_name']},
            'review': {'review_state': ['apply_reviews', 'fingerprint', 'inspect_assertion']},
            'search': {'ranking': ['tokens', '_Question']},
            'retrieval': {
                'response': ['serialise', '_measure', '_prune', '_quotation'],
                'retrieval_context': ['lookup', '_prepare'],
                'retrieval_policy': ['Policy'],
                'evidence': ['_Evidence'],
                'graph_retrieval': ['_retrieve'],
            },
        }
        for legacy, modules in owners.items():
            facade = importlib.import_module(f'knot.{legacy}')
            for module, names in modules.items():
                owner = importlib.import_module(f'knot.{OWNERS.get(module, module)}')
                for name in names:
                    self.assertIs(getattr(facade, name), getattr(owner, name))

    def test_lower_layers_do_not_import_retrieval_facade(self):
        for path in SOURCE.rglob('*.py'):
            if path.stem in {'retrieval', 'cli', 'mcp_server', 'authoring', 'benchmark'}:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, 'knot.retrieval', str(path))

    def test_shared_leaves_have_no_application_dependencies(self):
        allowed = {
            'storage': set(),
            'vocabulary': set(),
            'response': set(),
            'ranking': {'vocabulary'},
            'review_state': {'rdf', 'storage'},
            'retrieval_policy': set(),
        }
        for module, dependencies in allowed.items():
            tree = ast.parse(module_path(module).read_text())
            actual = {
                node.module.removeprefix('knot.')
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith('knot.')
            }
            self.assertLessEqual(actual, {OWNERS.get(d, d) for d in dependencies}, module)

    def test_retrieval_engines_do_not_depend_on_discovery_or_interfaces(self):
        forbidden = {
            'discovery',
            'discovery_score',
            'retrieval',
            'mcp_server',
            'retrieval_engine.discovery',
            'retrieval_engine.discovery_score',
            'retrieval_engine.cli',
            'retrieval_engine.service',
            'interfaces.mcp_server',
        }
        for module in ('graph_retrieval', 'search', 'selection', 'source_selection'):
            tree = ast.parse(module_path(module).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.removeprefix('knot.'), forbidden, module)

    def test_frozen_wire_responses(self):
        # Recorded before moving code. Includes ordering, budgets and exact Unicode JSON.
        expected = json.loads(Path(__file__).with_name('retrieval_wire_hashes.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            for name, result in responses(root):
                with self.subTest(name=name):
                    wire = serialise(result)
                    self.assertEqual(hashlib.sha256(wire.encode()).hexdigest(), expected[name])
