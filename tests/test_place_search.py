"""Run the browser-independent place-search contract with Node's JS engine."""

import shutil
import subprocess

import pytest


def test_place_search_contract(root):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the browser JavaScript contract test")
    result = subprocess.run(
        [node, str(root / "tests/place_search.cjs")],
        cwd=root, capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
