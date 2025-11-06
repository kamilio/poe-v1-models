import copy
import json
from decimal import Decimal
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.config import load_general_config
from poe_v1_models.checks import evaluate_provider_decisions
from poe_v1_models.mapping import load_model_mapping
from poe_v1_models.pipeline import run_pipeline, _msrp_fields_with_discount
from poe_v1_models.pricing import MTOK_MULTIPLIER, PricingSnapshot
from poe_v1_models.reporting import build_checks_report

SNAPSHOT_ROOT = Path(__file__).resolve().parent / "snapshots"
PIPELINE_SNAPSHOTS = SNAPSHOT_ROOT / "pipeline"
PROVIDER_SNAPSHOTS = SNAPSHOT_ROOT / "providers"


@pytest.fixture(autouse=True)
def pipeline_snapshots(monkeypatch):
    from poe_v1_models import config as config_module
    from poe_v1_models import mapping as mapping_module
    from poe_v1_models.providers.models_dev import ModelsDevProvider
    from poe_v1_models.providers.openrouter import OpenRouterProvider

    poe_payload = json.loads((PIPELINE_SNAPSHOTS / "poe_models.json").read_text(encoding="utf-8"))
    openrouter_payload = json.loads((PROVIDER_SNAPSHOTS / "openrouter.json").read_text(encoding="utf-8"))
    models_dev_payload = json.loads((PROVIDER_SNAPSHOTS / "models_dev.json").read_text(encoding="utf-8"))
    config_path = PIPELINE_SNAPSHOTS / "config.yaml"
    mapping_path = PIPELINE_SNAPSHOTS / "model_mapping.yml"

    def fake_fetch_json(url: str):
        return copy.deepcopy(poe_payload)

    monkeypatch.setattr("poe_v1_models.pipeline.fetch_json", fake_fetch_json)

    real_load_config = config_module.load_general_config

    def load_config_override(path=config_path):
        return real_load_config(config_path)

    monkeypatch.setattr(config_module, "load_general_config", load_config_override)
    monkeypatch.setattr("poe_v1_models.pipeline.load_general_config", load_config_override)
    monkeypatch.setattr(sys.modules[__name__], "load_general_config", load_config_override)

    real_load_mapping = mapping_module.load_model_mapping

    def load_mapping_override(path=mapping_path):
        return real_load_mapping(mapping_path)

    monkeypatch.setattr(mapping_module, "load_model_mapping", load_mapping_override)
    monkeypatch.setattr("poe_v1_models.pipeline.load_model_mapping", load_mapping_override)
    monkeypatch.setattr(sys.modules[__name__], "load_model_mapping", load_mapping_override)

    def openrouter_load(self):
        index = {}
        for record in openrouter_payload.get("snapshots", []):
            raw = record.get("raw", {})
            model_id = raw.get("id")
            if model_id:
                index[model_id] = raw
        self._index = index

    def models_dev_load(self):
        catalog = {}
        for record in models_dev_payload.get("snapshots", []):
            provider = record.get("provider")
            raw = record.get("raw", {})
            model_id = raw.get("id")
            cost = raw.get("cost")
            if not provider or not model_id or not isinstance(cost, dict):
                continue
            provider_entry = catalog.setdefault(provider, {"models": {}})
            provider_entry["models"][model_id] = {"cost": cost}
        self._catalog = catalog

    monkeypatch.setattr(OpenRouterProvider, "load", openrouter_load, raising=False)
    monkeypatch.setattr(ModelsDevProvider, "load", models_dev_load, raising=False)


def to_decimal(value):
    assert value is not None, "Expected numeric string"
    return Decimal(value)


def make_pricing_snapshot(prompt=None, completion=None, input_cache_read=None, input_cache_write=None):
    return PricingSnapshot(
        prompt=Decimal(str(prompt)) if prompt is not None else None,
        completion=Decimal(str(completion)) if completion is not None else None,
        input_cache_read=Decimal(str(input_cache_read)) if input_cache_read is not None else None,
        input_cache_write=Decimal(str(input_cache_write)) if input_cache_write is not None else None,
    )


def test_msrp_fields_cleared_when_pricing_equal():
    provider_pricing = make_pricing_snapshot(prompt="0.003", completion="0.006")
    poe_pricing = make_pricing_snapshot(prompt="0.003", completion="0.006").with_mtok()

    msrp_fields = _msrp_fields_with_discount(provider_pricing, poe_pricing)

    assert all(value is None for value in msrp_fields.values()), "Expected MSRP fields cleared when Poe pricing is higher or equal"


def test_msrp_fields_retained_when_poe_pricing_lower():
    provider_pricing = make_pricing_snapshot(prompt="0.005", completion="0.010")
    poe_pricing = make_pricing_snapshot(prompt="0.004", completion="0.009").with_mtok()

    msrp_fields = _msrp_fields_with_discount(provider_pricing, poe_pricing)

    assert msrp_fields["msrp_prompt"] == "0.005"
    assert msrp_fields["msrp_completion"] == "0.01"


def test_equal_pricing_rejected_by_checks():
    provider_pricing = {"models.dev": make_pricing_snapshot(prompt="0.003", completion="0.006")}
    poe_pricing = make_pricing_snapshot(prompt="0.003", completion="0.006").with_mtok()

    decisions, selected = evaluate_provider_decisions(["models.dev"], provider_pricing, poe_pricing)

    decision = decisions["models.dev"]
    assert decision.status == "rejected"
    assert "price_equal" in decision.reasons
    assert selected is None


def test_pipeline_exposes_provider_lookup_metadata():
    result = run_pipeline()
    aggregate = result.aggregates.get("GPT-5")
    assert aggregate is not None, "Expected GPT-5 aggregate from pipeline"

    lookup = aggregate.provider_lookup.get("models.dev")
    assert lookup is not None, "Expected models.dev lookup metadata"
    assert lookup["requested"] == "auto"
    assert lookup["resolved"] == "openai/gpt-5"


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
        for field in (
            "msrp_prompt",
            "msrp_completion",
            "msrp_prompt_mtok",
            "msrp_completion_mtok",
            "msrp_input_cache_read",
            "msrp_input_cache_write",
            "msrp_input_cache_read_mtok",
            "msrp_input_cache_write_mtok",
        ):
            assert field in pricing, f"Missing {field} for {entry.poe_id}"

        for base_key, mtok_key in (
            ("msrp_prompt", "msrp_prompt_mtok"),
            ("msrp_completion", "msrp_completion_mtok"),
            ("msrp_input_cache_read", "msrp_input_cache_read_mtok"),
            ("msrp_input_cache_write", "msrp_input_cache_write_mtok"),
        ):
            base_value = pricing.get(base_key)
            mtok_value = pricing.get(mtok_key)
            if base_value is not None and mtok_value is not None:
                assert to_decimal(base_value) == to_decimal(mtok_value) / MTOK_MULTIPLIER


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
    assert {"values", "severity", "status", "lookup", "reasons"}.issubset(provider_payload.keys())


def test_models_dev_auto_mapping_populates_gpt5_pricing():
    result = run_pipeline()
    aggregate = result.aggregates.get("GPT-5")
    assert aggregate is not None, "Expected GPT-5 aggregate from pipeline"

    decision = aggregate.decisions.get("models.dev")
    assert decision is not None, "models.dev decision missing for GPT-5"
    assert decision.status == "rejected"
    assert "price_equal" in decision.reasons
    assert decision.pricing is not None, "models.dev should provide pricing for GPT-5"
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
