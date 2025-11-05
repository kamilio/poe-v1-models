#!/usr/bin/env python3
"""Consolidate model_mapping.yml by switching to 'auto' when name/owner matches."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import yaml

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.pipeline import load_poe_models


MAPPING_PATH = Path("config/model_mapping.yml")


def extract_owner_and_name(models_dev_key: str) -> tuple[str, str]:
    """Extract owner and model name from models.dev key format 'owner/model-name'."""
    if "/" not in models_dev_key:
        return "", ""
    parts = models_dev_key.split("/", 1)
    return parts[0], parts[1]


def should_use_auto(poe_id: str, models_dev_key: str, poe_models: Dict[str, Any]) -> bool:
    """
    Determine if we should use 'auto' instead of explicit mapping.
    
    Returns True if the owner and name from models.dev key match the Poe model's
    owned_by and id fields.
    """
    # Find the Poe model data
    poe_model = None
    for model in poe_models.get("data", []):
        if model.get("id") == poe_id:
            poe_model = model
            break
    
    if not poe_model:
        print(f"Warning: Poe model '{poe_id}' not found in API data", file=sys.stderr)
        return False
    
    # Extract owner and name from models.dev key
    owner, model_name = extract_owner_and_name(models_dev_key)
    if not owner or not model_name:
        return False
    
    # Get Poe model's owned_by field
    poe_owned_by = str(poe_model.get("owned_by", "")).lower()
    poe_model_id = str(poe_model.get("id", "")).lower()
    
    # Normalize for comparison
    owner_lower = owner.lower()
    model_name_lower = model_name.lower()
    
    # Check if owner matches
    owner_matches = poe_owned_by == owner_lower
    
    # Check if model name matches (case-insensitive, allowing for variations)
    # The Poe ID might have variations like "GPT-4o" vs "gpt-4o"
    name_matches = (
        poe_model_id == model_name_lower or
        poe_model_id.replace("-", "") == model_name_lower.replace("-", "") or
        model_name_lower in poe_model_id or
        poe_model_id in model_name_lower
    )
    
    if owner_matches and name_matches:
        print(f"✓ {poe_id}: owner='{owner}' matches owned_by='{poe_owned_by}', "
              f"name='{model_name}' matches id='{poe_model_id}'")
        return True
    
    return False


def consolidate_mapping() -> None:
    """Load model mapping, consolidate to 'auto' where appropriate, and save."""
    print("Loading Poe models from API...")
    poe_models = load_poe_models()
    print(f"Loaded {len(poe_models.get('data', []))} Poe models")
    
    print(f"\nLoading model mapping from {MAPPING_PATH}...")
    with MAPPING_PATH.open("r", encoding="utf-8") as f:
        mapping_data = yaml.safe_load(f)
    
    if not mapping_data or "model_mapping" not in mapping_data:
        print("Error: Invalid mapping file structure", file=sys.stderr)
        sys.exit(1)
    
    model_mapping = mapping_data["model_mapping"]
    changes_made = 0
    
    print("\nAnalyzing mappings...\n")
    
    # Process each model mapping
    for poe_id, provider_mappings in model_mapping.items():
        if not isinstance(provider_mappings, dict):
            continue
        
        # Check models.dev mapping
        if "models.dev" in provider_mappings:
            models_dev_key = provider_mappings["models.dev"]
            
            # Skip if already using 'auto'
            if models_dev_key == "auto":
                continue
            
            # Check if we should switch to auto
            if should_use_auto(poe_id, models_dev_key, poe_models):
                provider_mappings["models.dev"] = "auto"
                changes_made += 1
                print(f"  → Changed to 'auto'")
    
    print(f"\n{'='*60}")
    print(f"Total changes: {changes_made}")
    print(f"{'='*60}\n")
    
    if changes_made > 0:
        # Save the updated mapping
        print(f"Saving updated mapping to {MAPPING_PATH}...")
        with MAPPING_PATH.open("w", encoding="utf-8") as f:
            yaml.dump(mapping_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        print("✓ Mapping file updated successfully!")
    else:
        print("No changes needed.")


def main() -> None:
    try:
        consolidate_mapping()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()