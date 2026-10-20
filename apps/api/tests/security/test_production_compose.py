"""Production Compose holds to its own rules (deploy/compose.prod.yaml, docs/security.md):
read from the file, so an edit that publishes a port or drops a limit fails here before it
reaches MX3. The preflight checks the running machine; this checks what will run on it.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from plumbline.settings import ROOT

COMPOSE = ROOT / "deploy" / "compose.prod.yaml"
PINNED = re.compile(r"^[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}$")
BUILT = "plumbline-api:prod"  # built from this checkout by deploy/prod build
ONE_SHOT = {"migrate"}


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return loaded


SERVICES: dict[str, dict[str, Any]] = _compose()["services"]


def test_it_is_a_project_of_its_own() -> None:
    assert _compose()["name"] == "plumbline-prod"


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_no_service_publishes_a_port(name: str) -> None:
    assert "ports" not in SERVICES[name]
    assert SERVICES[name].get("network_mode") != "host"


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_every_image_is_pinned_or_built_here(name: str) -> None:
    image = SERVICES[name]["image"]
    assert image == BUILT or PINNED.match(image), image


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_every_service_is_limited_rotated_and_unprivileged(name: str) -> None:
    service = SERVICES[name]
    assert service.get("mem_limit"), "no memory limit"
    assert service["logging"]["driver"] == "local"
    assert service["logging"]["options"]["max-size"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert not service.get("privileged")
    expected = "no" if name in ONE_SHOT else "unless-stopped"
    assert service["restart"] == expected


@pytest.mark.parametrize("name", sorted(set(SERVICES) - ONE_SHOT))
def test_every_long_running_service_is_health_checked_or_says_why_not(name: str) -> None:
    check = SERVICES[name].get("healthcheck")
    # The API's check is its image's HEALTHCHECK (deploy/api/Dockerfile).
    assert check or SERVICES[name]["image"] == BUILT, "no healthcheck"


def test_the_data_stores_have_no_route_out() -> None:
    networks = _compose()["networks"]
    assert networks["backend"]["internal"] is True
    for name in ("db", "redis"):
        assert SERVICES[name]["networks"] == ["backend"], name


def test_the_api_trusts_forwarded_headers_from_the_tunnel_only() -> None:
    tunnel = SERVICES["cloudflared"]["networks"]["egress"]["ipv4_address"]
    assert SERVICES["api"]["environment"]["FORWARDED_ALLOW_IPS"] == tunnel


def test_secrets_are_mounted_read_only_from_the_root_only_folder() -> None:
    for name, service in SERVICES.items():
        for volume in service.get("volumes", []):
            if isinstance(volume, str) and volume.startswith("/etc/plumbline/"):
                assert volume.endswith(":ro"), (name, volume)
        for value in (service.get("environment") or {}).values():
            # Secrets come from files: no key, token or password inline.
            assert not re.search(r"(?i)(key|token|password)=", str(value)), name


def test_the_embedder_keeps_its_batch_cap() -> None:
    command = SERVICES["embed"]["command"]
    assert command[command.index("--max-batch-tokens") + 1] == "4096"
