#!/usr/bin/env python3
"""
Check if all Poe prices are lower than or equal to MSRP from models.dev.
"""

from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.update_models import (
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
    """Convert value to Decimal, return None if invalid."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def check_pricing():
    """Check if Poe prices are lower than MSRP."""
    console.print("[bold cyan]Loading data...[/bold cyan]")
    
    mapping = load_model_mapping()
    catalog = load_models_dev()
    msrp_lookup = build_msrp_lookup(catalog, mapping)
    poe_models = load_poe_models()
    
    # Create lookup for Poe models by ID
    poe_lookup = {model.get("id"): model for model in poe_models.get("data", [])}
    
    # Track violations
    violations = []
    compliant = []
    no_poe_pricing = []
    no_msrp = []
    
    console.print(f"[bold cyan]Checking {len(mapping)} models...[/bold cyan]\n")
    
    for entry in mapping:
        model_id = entry.output_name
        poe_model = poe_lookup.get(model_id)
        
        if not poe_model:
            continue
            
        poe_pricing = poe_model.get("pricing") or {}
        msrp = msrp_lookup.get(model_id, {})
        
        # Get Poe prices (per million tokens)
        poe_prompt = to_decimal(poe_pricing.get("prompt_mtok"))
        poe_completion = to_decimal(poe_pricing.get("completion_mtok"))
        
        # Get MSRP prices (per million tokens)
        msrp_prompt = to_decimal(msrp.get("msrp_prompt_mtok"))
        msrp_completion = to_decimal(msrp.get("msrp_completion_mtok"))
        
        # Check if we have pricing data
        has_poe_pricing = poe_prompt is not None or poe_completion is not None
        has_msrp = msrp_prompt is not None or msrp_completion is not None
        
        if not has_poe_pricing:
            no_poe_pricing.append(model_id)
            continue
            
        if not has_msrp:
            no_msrp.append(model_id)
            continue
        
        # Check for violations
        prompt_violation = False
        completion_violation = False
        
        if poe_prompt is not None and msrp_prompt is not None:
            if poe_prompt > msrp_prompt:
                prompt_violation = True
        
        if poe_completion is not None and msrp_completion is not None:
            if poe_completion > msrp_completion:
                completion_violation = True
        
        if prompt_violation or completion_violation:
            violations.append({
                "model": model_id,
                "poe_prompt": poe_prompt,
                "msrp_prompt": msrp_prompt,
                "poe_completion": poe_completion,
                "msrp_completion": msrp_completion,
                "prompt_violation": prompt_violation,
                "completion_violation": completion_violation,
            })
        else:
            compliant.append(model_id)
    
    # Display results
    if violations:
        table = Table(title="[bold red]⚠️  Pricing Violations (Poe > MSRP)[/bold red]",
                     show_header=True, header_style="bold red")
        table.add_column("Model", style="cyan", no_wrap=False, width=30)
        table.add_column("Type", style="yellow")
        table.add_column("Poe Price/MTok", justify="right", style="red")
        table.add_column("MSRP/MTok", justify="right", style="green")
        table.add_column("Difference", justify="right", style="magenta")
        
        for v in violations:
            if v["prompt_violation"]:
                diff = v["poe_prompt"] - v["msrp_prompt"]
                table.add_row(
                    v["model"],
                    "Prompt",
                    f"${v['poe_prompt']}",
                    f"${v['msrp_prompt']}",
                    f"+${diff}"
                )
            if v["completion_violation"]:
                diff = v["poe_completion"] - v["msrp_completion"]
                table.add_row(
                    v["model"],
                    "Completion",
                    f"${v['poe_completion']}",
                    f"${v['msrp_completion']}",
                    f"+${diff}"
                )
        
        console.print()
        console.print(table)
        console.print()
    
    # Summary
    console.print(Panel(
        f"[bold green]✓ Compliant:[/bold green] {len(compliant)} models\n"
        f"[bold red]✗ Violations:[/bold red] {len(violations)} models\n"
        f"[bold yellow]⚠ No Poe pricing:[/bold yellow] {len(no_poe_pricing)} models\n"
        f"[bold yellow]⚠ No MSRP:[/bold yellow] {len(no_msrp)} models",
        title="[bold]Pricing Check Summary[/bold]",
        border_style="cyan"
    ))
    
    if no_poe_pricing:
        console.print("\n[bold yellow]Models without Poe pricing:[/bold yellow]")
        for model in no_poe_pricing:
            console.print(f"  • {model}")
    
    if no_msrp:
        console.print("\n[bold yellow]Models without MSRP:[/bold yellow]")
        for model in no_msrp:
            console.print(f"  • {model}")
    
    # Exit with error code if violations found
    if violations:
        console.print("\n[bold red]❌ Pricing check failed: Found models where Poe price exceeds MSRP[/bold red]")
        return 1
    else:
        console.print("\n[bold green]✅ All Poe prices are at or below MSRP[/bold green]")
        return 0


if __name__ == "__main__":
    sys.exit(check_pricing())