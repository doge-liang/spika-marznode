"""Each concrete VPNBackend must implement every abstract method on the base.

This guards against a backend silently going partially-abstract when the
contract evolves (e.g. a new abstract method is added but a backend forgets
to implement it).
"""

from __future__ import annotations

import pytest

from marznode.backends.abstract_backend import VPNBackend


def _concrete_backends():
    """Import each backend lazily so an import error in one doesn't break the
    others' tests."""
    classes = []
    try:
        from marznode.backends.xray.xray_backend import XrayBackend

        classes.append(XrayBackend)
    except Exception as exc:  # pragma: no cover
        classes.append(pytest.param(None, marks=pytest.mark.skip(reason=str(exc))))
    try:
        from marznode.backends.singbox.singbox_backend import SingBoxBackend

        classes.append(SingBoxBackend)
    except Exception as exc:  # pragma: no cover
        classes.append(pytest.param(None, marks=pytest.mark.skip(reason=str(exc))))
    try:
        from marznode.backends.hysteria2.hysteria2_backend import HysteriaBackend

        classes.append(HysteriaBackend)
    except Exception as exc:  # pragma: no cover
        classes.append(pytest.param(None, marks=pytest.mark.skip(reason=str(exc))))
    return classes


@pytest.mark.parametrize("backend_cls", _concrete_backends())
def test_backend_implements_abstract_contract(backend_cls):
    abstract_methods = getattr(VPNBackend, "__abstractmethods__", set())
    missing = abstract_methods - set(dir(backend_cls))
    assert not missing, (
        f"{backend_cls.__name__} is missing abstract methods: {missing}"
    )
    # Class should not itself be abstract — i.e. all abstracts overridden.
    assert not getattr(backend_cls, "__abstractmethods__", set()), (
        f"{backend_cls.__name__} still has unimplemented abstract methods: "
        f"{backend_cls.__abstractmethods__}"
    )


@pytest.mark.parametrize("backend_cls", _concrete_backends())
def test_backend_declares_required_class_attributes(backend_cls):
    assert isinstance(getattr(backend_cls, "backend_type", None), str)
    assert isinstance(getattr(backend_cls, "config_format", None), int)
