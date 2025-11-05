#!/usr/bin/env python3
"""Interactive pricing check report using Rich tables."""

from __future__ import annotations

from pathlib import Path
import sys

from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from poe_v1_models.pipeline import run_pipeline

console = Console()


def check_pricing() -> int:
    result = run_pipeline()

    table = Table(title="Poe Pricing Checks", show_lines=False)
    table.add_column("Model", style="cyan", no_wrap=True)
    table.add_column("Provider", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Reasons", style="yellow")
    table.add_column("Prompt/MTok", justify="right")
    table.add_column("Completion/MTok", justify="right")
    table.add_column("Poe Prompt/MTok", justify="right")
    table.add_column("Poe Completion/MTok", justify="right")

    violations = 0

    for model_id, aggregate in sorted(result.aggregates.items()):
        poe_pricing = aggregate.normalized_pricing.as_dict()
        poe_prompt = poe_pricing.get("prompt_mtok")
        poe_completion = poe_pricing.get("completion_mtok")

        for provider, decision in aggregate.decisions.items():
            pricing = decision.pricing.with_mtok().as_dict() if decision.pricing else {}
            reasons = ", ".join(decision.reasons) if decision.reasons else "—"
            status = decision.status

            if decision.status == "rejected" and any(reason.startswith("lower_than_poe") for reason in decision.reasons):
                violations += 1

            table.add_row(
                f"{model_id}{' ★' if aggregate.selected_provider == provider else ''}",
                provider,
                status,
                reasons,
                pricing.get("prompt_mtok") or "—",
                pricing.get("completion_mtok") or "—",
                poe_prompt or "—",
                poe_completion or "—",
            )

    console.print(table)

    if violations:
        console.print(f"[bold red]Found {violations} provider prices lower than Poe's pricing[/bold red]")
        return 1

    console.print("[bold green]No pricing violations detected[/bold green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(check_pricing())
