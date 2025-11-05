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

# ANSI color codes
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


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

    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*110}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}MSRP PRICING TABLE{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*110}{Colors.ENDC}")
    print(f"{Colors.BOLD}{'Model Name':<30} {'In Poe V1':<12} {'In models.dev':<15} {'Prompt/MTok':<20} {'Completion/MTok':<20}{Colors.ENDC}")
    print(f"{Colors.BOLD}{'-'*110}{Colors.ENDC}")

    assert len(lookup) == len(mapping), "Each mapping entry should produce MSRP data"
    
    models_not_in_poe = []

    for entry in mapping:
        msrp = lookup[entry.output_name]
        prompt_mtok = msrp.get("msrp_prompt_mtok")
        completion_mtok = msrp.get("msrp_completion_mtok")
        
        # Check if model is in Poe v1 models
        is_in_poe = entry.output_name in poe_model_ids
        in_poe_v1 = f"{Colors.OKGREEN}✓{Colors.ENDC}" if is_in_poe else f"{Colors.FAIL}✗{Colors.ENDC}"
        
        if not is_in_poe:
            models_not_in_poe.append(entry.output_name)
        
        # Check if model is in models.dev catalog
        in_models_dev = f"{Colors.OKGREEN}✓{Colors.ENDC}" if entry.output_name in lookup else f"{Colors.FAIL}✗{Colors.ENDC}"
        
        # Format pricing values with colors
        if prompt_mtok:
            # Check if price is 0 (red flag)
            if prompt_mtok == "0":
                prompt_price = f"{Colors.FAIL}${prompt_mtok}{Colors.ENDC}"
            else:
                prompt_price = f"{Colors.OKCYAN}${prompt_mtok}{Colors.ENDC}"
        else:
            prompt_price = f"{Colors.WARNING}N/A{Colors.ENDC}"
            
        if completion_mtok:
            # Check if price is 0 (red flag)
            if completion_mtok == "0":
                completion_price = f"{Colors.FAIL}${completion_mtok}{Colors.ENDC}"
            else:
                completion_price = f"{Colors.OKCYAN}${completion_mtok}{Colors.ENDC}"
        else:
            completion_price = f"{Colors.WARNING}N/A{Colors.ENDC}"
        
        # Color the model name based on Poe v1 status
        model_name_colored = entry.output_name if is_in_poe else f"{Colors.FAIL}{entry.output_name}{Colors.ENDC}"
        
        print(f"{model_name_colored:<30} {in_poe_v1:<12} {in_models_dev:<15} {prompt_price:<20} {completion_price:<20}")
        
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
    
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*110}{Colors.ENDC}")
    print(f"{Colors.BOLD}Total models in mapping: {Colors.OKBLUE}{len(mapping)}{Colors.ENDC}")
    print(f"{Colors.BOLD}Models found in Poe v1: {Colors.OKGREEN}{sum(1 for e in mapping if e.output_name in poe_model_ids)}{Colors.ENDC}")
    print(f"{Colors.BOLD}Models found in models.dev: {Colors.OKGREEN}{len(lookup)}{Colors.ENDC}")
    
    if models_not_in_poe:
        print(f"\n{Colors.BOLD}{Colors.FAIL}Models NOT in Poe v1 (should be removed):{Colors.ENDC}")
        for model in models_not_in_poe:
            print(f"  {Colors.FAIL}• {model}{Colors.ENDC}")
    
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*110}{Colors.ENDC}\n")
