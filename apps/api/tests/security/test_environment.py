"""A test session never holds the developer's .env in its environment.

Provider keys live only in .env and reach the code through plumbline.settings, which reads
the file without exporting it. A library that loads .env into os.environ, as DeepEval does
on import unless told not to, would put live keys into every test and every subprocess a
test starts (the provider SDKs read ANTHROPIC_API_KEY and the like from there), so a
developer's machine would no longer behave like CI. pyproject.toml turns DeepEval's pytest
plugin off (-p no:deepeval), and plumbline.judge.deepeval_metrics, the one module that
imports DeepEval, switches its loading off first. These tests keep both in place.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import typing
from pathlib import Path

import pytest
from pydantic import SecretStr

from plumbline.settings import ROOT, Settings

# Keys the provider SDKs read from the environment on their own, besides the settings' names.
SDK_KEY_NAMES = frozenset({"GOOGLE_API_KEY", "CO_API_KEY"})
CANARY = "PLUMBLINE_DOTENV_CANARY"

# Runs in a pytest session of its own, started in a folder whose .env sets the canary.
INNER_TESTS = f"""
import os


def test_the_session_starts_without_the_dotenv():
    assert "{CANARY}" not in os.environ


def test_importing_deepeval_through_the_judge_leaves_the_dotenv_out():
    import plumbline.judge.deepeval_metrics  # noqa: F401

    assert "{CANARY}" not in os.environ
"""


def secret_names() -> frozenset[str]:
    """The environment name of every secret setting, and the SDKs' own key names."""
    names = {
        name.upper()
        for name, field in Settings.model_fields.items()
        if SecretStr in (typing.get_args(field.annotation) or (field.annotation,))
    }
    return frozenset(names) | SDK_KEY_NAMES


def test_secret_names_cover_the_provider_keys_and_the_admin_token() -> None:
    assert {"GEMINI_API_KEY", "ANTHROPIC_API_KEY", "ADMIN_TOKEN"} <= secret_names()


def test_no_key_is_in_the_environment_of_a_test() -> None:
    leaked = sorted(name for name in secret_names() if os.environ.get(name))
    assert not leaked, f"{leaked} in os.environ: keys belong in .env, read through settings"


@pytest.mark.slow
def test_a_dotenv_in_the_working_directory_stays_out_of_a_pytest_session(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(f"{CANARY}=leaked\n", encoding="utf-8")
    (tmp_path / "test_inner.py").write_text(textwrap.dedent(INNER_TESTS), encoding="utf-8")
    # Without the Makefile's DEEPEVAL_DISABLE_DOTENV, so the two guards are tested alone.
    env = {k: v for k, v in os.environ.items() if k not in {"DEEPEVAL_DISABLE_DOTENV", CANARY}}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(ROOT / "pyproject.toml"),
        "--rootdir",
        str(tmp_path),
        "-p",
        "no:cacheprovider",
        "test_inner.py",
    ]
    result = subprocess.run(  # noqa: S603 - a fixed pytest command line, no outside input
        command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout, result.stdout
