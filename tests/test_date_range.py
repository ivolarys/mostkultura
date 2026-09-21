"""Run the browser-independent date-range contract with Node's JS engine."""

import shutil
import subprocess

import pytest


def test_date_range_contract(root):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the browser JavaScript contract test")
    result = subprocess.run(
        [node, str(root / "tests/date_range.cjs")],
        cwd=root, capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
