from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.update_models import (
    MTOK_MULTIPLIER,
    build_msrp_lookup,
    load_model_mapping,
    load_models_dev,
    load_poe_models,
)


def to_decimal(value):
    assert value is not None, "Expected a numeric string"
    return Decimal(value)


def test_all_mapped_models_have_msrp_values():
    mapping = load_model_mapping()
    catalog = load_models_dev()
    lookup = build_msrp_lookup(catalog, mapping)
    
    # Fetch Poe v1 models to check if model keys exist
    poe_models = load_poe_models()
    poe_model_ids = {model.get("id") for model in poe_models.get("data", [])}

    print("\n" + "="*110)
    print("MSRP PRICING TABLE")
    print("="*110)
    print(f"{'Model Name':<30} {'In Poe V1':<12} {'In models.dev':<15} {'Prompt/MTok':<20} {'Completion/MTok':<20}")
    print("-"*110)

    assert len(lookup) == len(mapping), "Each mapping entry should produce MSRP data"

    for entry in mapping:
        msrp = lookup[entry.output_name]
        prompt_mtok = msrp.get("msrp_prompt_mtok")
        completion_mtok = msrp.get("msrp_completion_mtok")
        
        # Check if model is in Poe v1 models
        in_poe_v1 = "✓" if entry.output_name in poe_model_ids else "✗"
        
        # Check if model is in models.dev catalog
        in_models_dev = "✓" if entry.output_name in lookup else "✗"
        
        # Format pricing values
        prompt_price = f"${prompt_mtok}" if prompt_mtok else "N/A"
        completion_price = f"${completion_mtok}" if completion_mtok else "N/A"
        
        print(f"{entry.output_name:<30} {in_poe_v1:<12} {in_models_dev:<15} {prompt_price:<20} {completion_price:<20}")
        
        assert prompt_mtok is not None or completion_mtok is not None, f"No MSRP pricing for {entry.output_name}"

        if prompt_mtok is not None:
            prompt = msrp.get("msrp_prompt")
            prompt_decimal = to_decimal(prompt)
            assert prompt_decimal == to_decimal(prompt_mtok) / MTOK_MULTIPLIER

        if completion_mtok is not None:
            completion = msrp.get("msrp_completion")
            completion_decimal = to_decimal(completion)
            assert completion_decimal == to_decimal(completion_mtok) / MTOK_MULTIPLIER

        for field in ("msrp_prompt_mtok", "msrp_completion_mtok", "msrp_prompt", "msrp_completion"):
            value = msrp.get(field)
            if value is not None:
                decimal_value = to_decimal(value)
                assert decimal_value >= 0, f"{field} for {entry.output_name} must be non-negative"
    
    print("="*110)
    print(f"Total models in mapping: {len(mapping)}")
    print(f"Models found in Poe v1: {sum(1 for e in mapping if e.output_name in poe_model_ids)}")
    print(f"Models found in models.dev: {len(lookup)}")
    print("="*110 + "\n")
