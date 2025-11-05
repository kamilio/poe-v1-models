#!/usr/bin/env python3
"""
Sort model_mapping.yml by value (provider/model path) and remove comments.
"""

import yaml
from pathlib import Path


def sort_model_mapping():
    """Sort model mapping by value and remove comments."""
    config_path = Path(__file__).parent.parent / "config" / "model_mapping.yml"
    
    # Read the YAML file
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    # Get the model mapping
    model_mapping = data.get('model_mapping', {})
    
    # Sort by value (provider/model path)
    sorted_mapping = dict(sorted(model_mapping.items(), key=lambda item: item[1]))
    
    # Create new data structure without comments
    sorted_data = {'model_mapping': sorted_mapping}
    
    # Write back to file
    with open(config_path, 'w') as f:
        yaml.dump(sorted_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"✓ Sorted {len(sorted_mapping)} models by provider/model path")
    print(f"✓ Removed all comments")
    print(f"✓ Updated {config_path}")


if __name__ == "__main__":
    sort_model_mapping()