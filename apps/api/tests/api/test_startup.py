"""The API starts in the tree the deployed image has: the package and evals/configs, with
no data/, no cache/ and nothing writable. A start-up that reads the corpus works on every
machine with a checkout and fails only in the container, where CI finds it last."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from plumbline.settings import ROOT

CHECK = """
from fastapi.testclient import TestClient
from plumbline.api.app import create_app

with TestClient(create_app()) as client:
    assert client.get("/api/health").status_code == 200
print("started")
"""


def test_the_app_starts_and_answers_without_a_data_directory(tmp_path: Path) -> None:
    (tmp_path / "evals").symlink_to(ROOT / "evals", target_is_directory=True)
    # PLUMBLINE_ROOT is read when the settings module is imported, so this needs a process.
    env = {**os.environ, "PLUMBLINE_ROOT": str(tmp_path)}
    done = subprocess.run(  # noqa: S603 (this interpreter and a fixed script)
        [sys.executable, "-I", "-c", CHECK], env=env, capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip() == "started"
    assert not (tmp_path / "data").exists()
