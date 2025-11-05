from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.config import load_general_config
from poe_v1_models.mapping import load_model_mapping
from poe_v1_models.pipeline import run_pipeline
from poe_v1_models.pricing import MTOK_MULTIPLIER
from poe_v1_models.reporting import build_checks_report


def to_decimal(value):
    assert value is not None, "Expected numeric string"
    return Decimal(value)


def test_pipeline_populates_msrp_and_pricing_consistency():
    result = run_pipeline()
    mapping = load_model_mapping()
    models = {model["id"]: model for model in result.payload.get("data", [])}

    for entry in mapping:
        model = models.get(entry.poe_id)
        if not model:
            # Model filtered out by exclusions; skip assertions for it.
            continue
        pricing = model.get("pricing", {})
        for field in ("msrp_prompt", "msrp_completion", "msrp_prompt_mtok", "msrp_completion_mtok"):
            assert field in pricing, f"Missing {field} for {entry.poe_id}"

        prompt = pricing.get("msrp_prompt")
        prompt_mtok = pricing.get("msrp_prompt_mtok")
        if prompt is not None and prompt_mtok is not None:
            assert to_decimal(prompt) == to_decimal(prompt_mtok) / MTOK_MULTIPLIER

        completion = pricing.get("msrp_completion")
        completion_mtok = pricing.get("msrp_completion_mtok")
        if completion is not None and completion_mtok is not None:
            assert to_decimal(completion) == to_decimal(completion_mtok) / MTOK_MULTIPLIER


def test_overrides_applied_and_exclusions_respected():
    result = run_pipeline()
    config = load_general_config()
    models = {model["id"]: model for model in result.payload.get("data", [])}

    assert "Assistant" not in models, "Assistant should be excluded via config"

    override_model = config.overrides.keys()
    for model_id in override_model:
        model = models.get(model_id)
        assert model is not None, f"Override target {model_id} missing from output"
        metadata = model.get("metadata", {})
        assert metadata.get("curated") is True
        assert metadata.get("tier") == "flagship"
        assert "flagship" in model.get("tags", [])


def test_provider_priority_reflected_in_aggregates():
    result = run_pipeline()
    priority = result.config.providers.priority
    for aggregate in result.aggregates.values():
        if aggregate.selected_provider:
            assert aggregate.selected_provider in priority
            decision = aggregate.decisions.get(aggregate.selected_provider)
            assert decision is not None
            assert decision.status == "accepted"


def test_checks_report_includes_exclusions_and_providers():
    result = run_pipeline()
    report = build_checks_report(result)

    assert "generated_at" in report
    assert isinstance(report.get("models"), list) and report["models"], "Expected populated models list"
    assert isinstance(report.get("providers"), list) and report["providers"], "Expected providers metadata"
    assert isinstance(report.get("excluded_models"), list) and report["excluded_models"], "Expected excluded models list"

    sample_provider = report["providers"][0]
    assert {"name", "columns"}.issubset(sample_provider.keys())
    sample_model = report["models"][0]
    assert isinstance(sample_model.get("providers"), dict) and sample_model["providers"], "Expected provider data per model"
    provider_payload = next(iter(sample_model["providers"].values()))
    assert {"values", "severity", "status"}.issubset(provider_payload.keys())


def test_models_dev_auto_mapping_populates_gpt5_pricing():
    result = run_pipeline()
    aggregate = result.aggregates.get("GPT-5")
    assert aggregate is not None, "Expected GPT-5 aggregate from pipeline"

    decision = aggregate.decisions.get("models.dev")
    assert decision is not None, "models.dev decision missing for GPT-5"
    assert decision.status == "accepted"
    assert decision.pricing is not None, "models.dev should provide pricing for GPT-5"
    assert decision.reasons == []
    assert decision.pricing.prompt is not None
    assert decision.pricing.completion is not None


def test_boosts_prioritize_models():
    result = run_pipeline()
    boosts = result.config.boosts
    if not boosts.rules:
        pytest.skip("No boosts configured in config.yaml")

    payload = result.payload.get("data", [])
    assert payload, "Expected pipeline to produce models data"

    sentinel = len(boosts.rules)
    priorities = []
    for model in payload:
        position = boosts.position_for(model)
        priorities.append(position if position is not None else sentinel)

    assert priorities == sorted(priorities), "Expected models ordered by boost priority"
    assert priorities[0] == 0, "First model should correspond to the highest priority boost rule"
