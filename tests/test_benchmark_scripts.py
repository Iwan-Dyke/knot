import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('node'), 'Node is needed for benchmark script checks')
class BenchmarkScriptTests(unittest.TestCase):
    def test_explicit_inputs_private_outputs_and_offline_contexts(self):
        subprocess.run(
            ['node', str(Path(__file__).resolve().parents[1] / 'scripts/test_benchmarks.cjs')],
            check=True,
            capture_output=True,
            text=True,
        )
