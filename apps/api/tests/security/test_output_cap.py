"""The cap on output tokens: what bounds the cost of one answer, whatever a question or a
planted instruction asks for. Every configuration the API can answer with caps an answer at
1,024 tokens, and every provider client sends the request's cap in its own field, so no
call goes out without one. (A lease check's two calls cap at 4,096 each, in leases/.)
"""

from __future__ import annotations

import pytest

from plumbline.core.config import load_configs
from plumbline.generation.llm import (
    AnthropicClient,
    BaseClient,
    GeminiClient,
    LLMRequest,
    Message,
    OpenAICompatibleClient,
)
from plumbline.settings import ROOT, Settings

ANSWER_CAP = 1024
CONFIGS = load_configs(ROOT / "evals" / "configs")


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_every_answer_configuration_caps_its_output(name: str) -> None:
    assert CONFIGS[name].generation.max_output_tokens <= ANSWER_CAP


def test_the_serving_configuration_is_one_of_them() -> None:
    assert Settings(_env_file=None).answer_config in CONFIGS


@pytest.mark.parametrize(
    ("client", "field"),
    [
        (GeminiClient(), ("config", "max_output_tokens")),
        (AnthropicClient(), ("max_tokens",)),
        (OpenAICompatibleClient(), ("max_tokens",)),
    ],
)
def test_every_provider_sends_the_cap(client: BaseClient, field: tuple[str, ...]) -> None:
    request = LLMRequest(
        model="any", messages=[Message(role="user", content="x")], max_output_tokens=321
    )
    value: object = client.payload(request)
    for key in field:
        assert isinstance(value, dict)
        value = value[key]
    assert value == 321


def test_a_request_never_goes_out_uncapped() -> None:
    assert LLMRequest.model_fields["max_output_tokens"].default == ANSWER_CAP
