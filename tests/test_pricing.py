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

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


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

    assert len(lookup) == len(mapping), "Each mapping entry should produce MSRP data"
    
    # Create a rich table for MSRP pricing
    table = Table(title="MSRP Pricing Table", show_header=True, header_style="bold magenta")
    table.add_column("Model Name", style="cyan", no_wrap=False, width=30)
    table.add_column("In Poe V1", justify="center", style="green")
    table.add_column("In models.dev", justify="center", style="green")
    table.add_column("Prompt/MTok", justify="right")
    table.add_column("Completion/MTok", justify="right")
    
    models_not_in_poe = []

    for entry in mapping:
        msrp = lookup[entry.output_name]
        prompt_mtok = msrp.get("msrp_prompt_mtok")
        completion_mtok = msrp.get("msrp_completion_mtok")
        
        # Check if model is in Poe v1 models
        is_in_poe = entry.output_name in poe_model_ids
        in_poe_v1 = "[green]✓[/green]" if is_in_poe else "[red]✗[/red]"
        
        if not is_in_poe:
            models_not_in_poe.append(entry.output_name)
        
        # Check if model is in models.dev catalog
        in_models_dev = "[green]✓[/green]" if entry.output_name in lookup else "[red]✗[/red]"
        
        # Format pricing values with colors
        if prompt_mtok:
            # Check if price is 0 (red flag)
            if prompt_mtok == "0":
                prompt_price = f"[red]${prompt_mtok}[/red]"
            else:
                prompt_price = f"[cyan]${prompt_mtok}[/cyan]"
        else:
            prompt_price = "[yellow]N/A[/yellow]"
            
        if completion_mtok:
            # Check if price is 0 (red flag)
            if completion_mtok == "0":
                completion_price = f"[red]${completion_mtok}[/red]"
            else:
                completion_price = f"[cyan]${completion_mtok}[/cyan]"
        else:
            completion_price = "[yellow]N/A[/yellow]"
        
        # Color the model name based on Poe v1 status
        model_name_colored = entry.output_name if is_in_poe else f"[red]{entry.output_name}[/red]"
        
        table.add_row(model_name_colored, in_poe_v1, in_models_dev, prompt_price, completion_price)
        
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
    
    console.print()
    console.print(table)
    console.print()
    
    # Summary statistics
    console.print(f"[bold]Total models in mapping:[/bold] [blue]{len(mapping)}[/blue]")
    console.print(f"[bold]Models found in Poe v1:[/bold] [green]{sum(1 for e in mapping if e.output_name in poe_model_ids)}[/green]")
    console.print(f"[bold]Models found in models.dev:[/bold] [green]{len(lookup)}[/green]")
    
    if models_not_in_poe:
        console.print()
        warning_text = "\n".join([f"• {model}" for model in models_not_in_poe])
        console.print(Panel(
            warning_text,
            title="[bold red]Models NOT in Poe v1 (should be removed)[/bold red]",
            border_style="red"
        ))
    
    console.print()
