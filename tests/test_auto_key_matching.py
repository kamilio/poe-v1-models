from __future__ import annotations

from decimal import Decimal

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.providers.models_dev import ModelsDevProvider
from poe_v1_models.providers.openrouter import OpenRouterProvider
from poe_v1_models.providers.utils import parse_lowercase_provider_key


def test_parse_lowercase_provider_key_requires_exact_format():
    assert parse_lowercase_provider_key("openai/gpt-5") == ("openai", "gpt-5")
    assert parse_lowercase_provider_key("OpenAI/gpt-5") is None
    assert parse_lowercase_provider_key("openai/GPT-5") is None
    assert parse_lowercase_provider_key("openai") is None
    assert parse_lowercase_provider_key("") is None


def test_models_dev_auto_key_requires_exact_lowercase_match():
    provider = ModelsDevProvider()
    provider._catalog = {
        "openai": {"models": {"gpt-5": {"cost": {"input": Decimal("1.25"), "output": Decimal("10")}}}}
    }
    poe_model = {"owned_by": "OpenAI", "root": "gpt-5", "id": "GPT-5"}

    # exact lowercase key works
    direct = provider.find("openai/gpt-5", poe_model)
    assert direct is not None

    # AUTO fallback succeeds
    auto = provider.find("auto", poe_model)
    assert auto is not None

    # Any deviation fails
    assert provider.find("OpenAI/GPT-5", poe_model) is None
    assert provider.find("openai/GPT-5", poe_model) is None


def test_models_dev_default_key_handles_dotted_decimal_names():
    provider = ModelsDevProvider()
    provider._catalog = {
        "anthropic": {
            "models": {
                "claude-sonnet-4-5": {"cost": {"input": Decimal("3"), "output": Decimal("15")}}
            }
        }
    }
    poe_model = {"owned_by": "Anthropic", "id": "Claude-Sonnet-4.5", "root": "Claude-Sonnet-4.5"}

    assert provider.default_key(poe_model) == "anthropic/claude-sonnet-4-5"


def test_openrouter_auto_key_requires_exact_lowercase_match():
    provider = OpenRouterProvider()
    provider._index = {
        "openai/gpt-5": {
            "pricing": {
                "prompt": "0.00000125",
                "completion": "0.00001",
                "request": "0",
                "image": "0",
                "input_cache_read": "0.000000125",
                "input_cache_write": None,
            }
        }
    }
    poe_model = {"owned_by": "OpenAI", "root": "gpt-5", "id": "GPT-5"}

    assert provider.find("openai/gpt-5", poe_model) is not None
    assert provider.find("auto", poe_model) is not None
    assert provider.find("OpenAI/gpt-5", poe_model) is None
    assert provider.default_key({"owned_by": "Anthropic", "root": "claude-sonnet-4.5"}) is None


def test_openrouter_default_key_matches_hyphenated_variants():
    provider = OpenRouterProvider()
    provider._index = {
        "anthropic/claude-sonnet-4.5": {
            "pricing": {
                "prompt": "0.000003",
                "completion": "0.000015",
                "request": "0",
                "image": "0",
            }
        }
    }
    poe_model = {"owned_by": "Anthropic", "id": "Claude-Sonnet-4-5", "root": "Claude-Sonnet-4-5"}

    assert provider.default_key(poe_model) == "anthropic/claude-sonnet-4.5"
