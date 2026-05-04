"""Tests for the pydantic User and Inbound models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from marznode.models import Inbound, User


def test_user_required_fields():
    with pytest.raises(ValidationError):
        User()  # type: ignore[call-arg]


def test_user_default_inbounds_is_empty():
    user = User(id=1, username="alice", key="k")
    assert user.inbounds == []


def test_user_round_trips_via_json():
    inb = Inbound(tag="t", protocol="vmess", config={"port": 8080})
    user = User(id=42, username="alice", key="k", inbounds=[inb])

    raw = user.model_dump_json()
    restored = User.model_validate_json(raw)

    assert restored == user
    assert restored.inbounds[0].tag == "t"


def test_inbound_required_fields():
    with pytest.raises(ValidationError):
        Inbound()  # type: ignore[call-arg]


def test_inbound_accepts_arbitrary_config_dict():
    inb = Inbound(
        tag="t",
        protocol="vless",
        config={"nested": {"a": [1, 2, 3]}, "flag": True},
    )
    assert inb.config["nested"]["a"] == [1, 2, 3]


def test_inbound_rejects_non_dict_config():
    with pytest.raises(ValidationError):
        Inbound(tag="t", protocol="vless", config="not-a-dict")  # type: ignore[arg-type]
