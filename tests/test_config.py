"""Unit tests for Dev-Mate configuration and provider factories."""

from pathlib import Path
import pytest
from devmate.config import Config, as_bool
from devmate.providers import make_provider, GoogleProvider, OpenRouterProvider, ProviderError


def test_as_bool():
    import os
    os.environ["TEST_TRUE_1"] = "true"
    os.environ["TEST_TRUE_2"] = "1"
    os.environ["TEST_FALSE_1"] = "false"
    os.environ["TEST_FALSE_2"] = "0"

    assert as_bool("TEST_TRUE_1") is True
    assert as_bool("TEST_TRUE_2") is True
    assert as_bool("TEST_FALSE_1") is False
    assert as_bool("TEST_FALSE_2") is False
    assert as_bool("NON_EXISTENT", default=True) is True
    assert as_bool("NON_EXISTENT", default=False) is False


def test_provider_factory(tmp_path):
    cfg_openrouter = Config(root=tmp_path, provider="openrouter", openrouter_key="test-key")
    p1 = make_provider(cfg_openrouter)
    assert isinstance(p1, OpenRouterProvider)
    assert p1.key == "test-key"

    cfg_google = Config(root=tmp_path, provider="google", google_key="test-key")
    p2 = make_provider(cfg_google)
    assert isinstance(p2, GoogleProvider)
    assert p2.key == "test-key"


def test_missing_api_key_raises_error(tmp_path):
    cfg = Config(root=tmp_path, provider="openrouter", openrouter_key="")
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY is not set"):
        make_provider(cfg)

    cfg2 = Config(root=tmp_path, provider="google", google_key="")
    with pytest.raises(ProviderError, match="GOOGLE_API_KEY is not set"):
        make_provider(cfg2)
