import json
from pathlib import Path

import pytest

from plumbline.observability.spend import main, provider_of, scan, spent, tally


def record(
    directory: Path,
    key: str,
    model: str,
    cost: float,
    *,
    provider: str | None = None,
    kind: str = "llm",
) -> None:
    request: dict[str, object] = {"model": model}
    if provider is not None:
        request["provider"] = provider
    path = directory / kind / key[:2] / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "key": key,
        "kind": kind,
        "model": model,
        "request": request,
        "response": "never read",
        "input_tokens": 100,
        "output_tokens": 10,
        "cost_usd": cost,
    }
    path.write_text(json.dumps(body), encoding="utf-8")


@pytest.mark.parametrize(
    ("model", "request_", "provider"),
    [
        ("gemini-3.8-flash", {"provider": "gemini"}, "gemini"),
        ("gemini-3.8-flash", {}, "gemini"),  # a parse recording has no provider field
        ("claude-haiku-5-5", {}, "anthropic"),
        ("docling-serve 1.37.0", {}, "local"),
        ("Qwen/Qwen3-Embedding-0.6B", {}, "local"),
        ("any-model", {"provider": "openai"}, "openai"),
    ],
)
def test_provider_of(model: str, request_: dict[str, str], provider: str) -> None:
    assert provider_of(model, request_) == provider


def test_tally_sums_per_provider_and_model_and_counts_a_key_once(tmp_path: Path) -> None:
    repo, fetched = tmp_path / "cache", tmp_path / "fetched"
    record(repo, "aa01", "gemini-3.8-flash", 0.25, provider="gemini")
    record(repo, "aa02", "gemini-3.8-flash", 0.50, provider="gemini")
    record(repo, "bb01", "claude-haiku-5-5", 0.10, provider="anthropic")
    record(fetched, "cc01", "gemini-3.8-flash", 1.00, kind="parse")
    record(fetched, "aa01", "gemini-3.8-flash", 0.25, provider="gemini")  # a copy of repo's
    (repo / "llm" / "aa" / "stray.json").write_text("not json", encoding="utf-8")

    lines = tally(scan([repo, fetched, tmp_path / "missing"]))

    flash = lines[("gemini", "gemini-3.8-flash")]
    assert (flash.calls, flash.input_tokens, flash.output_tokens) == (3, 300, 30)
    assert spent(lines, "gemini") == pytest.approx(1.75)
    assert spent(lines, "anthropic") == pytest.approx(0.10)


def test_main_passes_a_run_under_the_stop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record(tmp_path, "aa01", "gemini-3.8-flash", 4.00, provider="gemini")
    assert main(["--dir", str(tmp_path), "--plan", "0.40"]) == 0
    out = capsys.readouterr().out
    assert "gemini: US$4.0000 recorded of the US$4.50 stop" in out
    assert "US$0.1000 left" in out


def test_main_refuses_a_run_that_would_cross_the_stop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record(tmp_path, "aa01", "gemini-3.8-flash", 4.00, provider="gemini")
    assert main(["--dir", str(tmp_path), "--plan", "0.60"]) == 1
    assert "would cross the gemini stop" in capsys.readouterr().err


def test_the_stop_counts_only_its_provider(tmp_path: Path) -> None:
    record(tmp_path, "bb01", "claude-haiku-5-5", 9.00, provider="anthropic")
    assert main(["--dir", str(tmp_path), "--plan", "1.00"]) == 0
