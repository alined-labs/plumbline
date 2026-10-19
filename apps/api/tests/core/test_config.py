from pathlib import Path

import pytest
from pydantic import ValidationError

from plumbline.core.config import EvalConfig, load_config, load_configs
from plumbline.settings import ROOT

CONFIGS = ROOT / "evals" / "configs"
ABLATIONS = {"A0", "A1", "A2", "A3", "A4", "A5", "A6", "E1", "R1", "LC"}


def test_every_planned_configuration_exists_and_loads() -> None:
    configs = load_configs(CONFIGS)
    assert set(configs) >= ABLATIONS


def test_configurations_differ_in_behaviour() -> None:
    hashes = {name: c.config_hash() for name, c in load_configs(CONFIGS).items()}
    assert len(set(hashes.values())) == len(hashes)


def test_the_hash_ignores_labels_but_not_behaviour() -> None:
    a2 = load_config(CONFIGS / "A2.yaml")
    relabelled = a2.model_copy(update={"name": "X", "description": "other", "judged": True})
    assert relabelled.config_hash() == a2.config_hash()
    retrieval = a2.retrieval.model_copy(update={"rrf_k": 10})
    assert a2.model_copy(update={"retrieval": retrieval}).config_hash() != a2.config_hash()


def test_the_name_must_match_the_file(tmp_path: Path) -> None:
    path = tmp_path / "B9.yaml"
    path.write_text((CONFIGS / "A0.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="must match the file name"):
        load_config(path)


def test_unknown_keys_are_refused() -> None:
    with pytest.raises(ValidationError):
        EvalConfig.model_validate(
            {
                "name": "x",
                "description": "",
                "chunker": {"kind": "fixed", "size": 3},
                "retrieval": {"mode": "dense"},
            }
        )
