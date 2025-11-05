#!/usr/bin/env python3
"""Interactive CLI for exploring Poe models and maintaining model mappings."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import URLError
from urllib.request import urlopen

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text


POE_API_URL = "https://api.poe.com/v1/models"
MODELS_DEV_API_URL = "https://models.dev/api.json"
LOCAL_MODELS_PATH = Path("dist/models.json")
MAPPING_PATH = Path("config/model_mapping.yml")

console = Console()


@dataclass(frozen=True)
class PoeModel:
    """Minimal representation of a Poe model needed for exploration."""

    id: str
    owned_by: str
    description: str


def fetch_json(url: str) -> Dict[str, Any]:
    """Download JSON content from a URL."""
    with urlopen(url) as response:  # nosec: B310 - API is HTTPS and trusted
        if response.status != 200:
            raise RuntimeError(f"Failed to fetch {url}: {response.status}")
        return json.load(response)


def load_poe_models(force_remote: bool = False) -> List[PoeModel]:
    """Load Poe models from the local cache or directly from the API."""
    payload: Dict[str, Any]
    if not force_remote and LOCAL_MODELS_PATH.exists():
        payload = json.loads(LOCAL_MODELS_PATH.read_text(encoding="utf-8"))
    else:
        payload = fetch_json(POE_API_URL)
    models: List[PoeModel] = []
    for entry in payload.get("data", []):
        model_id = entry.get("id")
        owned_by = entry.get("owned_by", "")
        description = entry.get("description") or ""
        if not model_id:
            continue
        models.append(PoeModel(id=model_id, owned_by=owned_by, description=description.strip()))
    return models


def load_model_mapping(path: Path = MAPPING_PATH) -> Dict[str, Dict[str, str]]:
    """Load existing Poe -> provider mappings."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mapping = data.get("model_mapping", {}) if isinstance(data, dict) else {}
    if not isinstance(mapping, dict):
        raise ValueError("model_mapping config must be a mapping")
    
    # Convert to dict of dicts for multi-provider support
    result: Dict[str, Dict[str, str]] = {}
    for poe_id, providers in mapping.items():
        if isinstance(providers, dict):
            result[str(poe_id)] = {str(k): str(v) for k, v in providers.items()}
        elif isinstance(providers, str):
            # Legacy format: single string value assumed to be models.dev
            result[str(poe_id)] = {"models.dev": str(providers)}
    return result


def load_models_dev_catalog(force_remote: bool = False) -> Dict[str, Any]:
    """Load the models.dev provider catalog."""
    # Always fetch remotely – the catalog is not part of the repository.
    return fetch_json(MODELS_DEV_API_URL)


def normalize_provider(value: str) -> str:
    """Normalise provider strings for comparison."""
    return "".join(ch for ch in value.lower() if ch.isalnum())


def normalize_model_name(value: str) -> str:
    """Normalise model identifiers for fuzzy matching."""
    lowered = value.lower().replace(" ", "-").replace("_", "-")
    filtered = "".join(ch for ch in lowered if ch.isalnum() or ch in {"-", "."})
    while "--" in filtered:
        filtered = filtered.replace("--", "-")
    return filtered


def match_providers(owners: Iterable[str], providers: Iterable[str]) -> Dict[str, str]:
    """Map Poe owned_by values to provider keys present in the config."""
    normalized_providers = {normalize_provider(provider): provider for provider in providers}
    owner_matches: Dict[str, str] = {}
    for owner in owners:
        normalized_owner = normalize_provider(owner)
        provider = normalized_providers.get(normalized_owner)
        if provider:
            owner_matches[owner] = provider
    return owner_matches


def group_models_by_provider(models: Sequence[PoeModel], owner_map: Dict[str, str]) -> Dict[str, List[PoeModel]]:
    """Group models by provider, based on their owned_by field."""
    grouped: Dict[str, List[PoeModel]] = {}
    for model in models:
        provider = owner_map.get(model.owned_by)
        if not provider:
            continue
        grouped.setdefault(provider, []).append(model)
    return grouped


def suggest_models(provider: str, poe_model_id: str, catalog: Dict[str, Any]) -> List[str]:
    """Suggest models.dev identifiers that may correspond to a Poe model."""
    provider_block = catalog.get(provider, {})
    models = provider_block.get("models", {}) if isinstance(provider_block, dict) else {}
    if not isinstance(models, dict):
        return []

    norm_lookup = {normalize_model_name(name): name for name in models.keys()}
    normalized_id = normalize_model_name(poe_model_id)
    if normalized_id in norm_lookup:
        return [norm_lookup[normalized_id]]

    matches = difflib.get_close_matches(normalized_id, norm_lookup.keys(), n=5, cutoff=0.6)
    return [norm_lookup[match] for match in matches]


def find_cross_provider_suggestions(
    poe_model_id: str,
    catalog: Dict[str, Any],
    exclude_provider: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """Search the entire models.dev catalog for potential matches."""
    normalized_id = normalize_model_name(poe_model_id)
    exact_matches: List[Tuple[str, str]] = []
    fuzzy_matches: List[Tuple[str, str]] = []

    for provider_key, provider_block in catalog.items():
        if exclude_provider and normalize_provider(provider_key) == normalize_provider(exclude_provider):
            continue
        if not isinstance(provider_block, dict):
            continue
        models = provider_block.get("models")
        if not isinstance(models, dict):
            continue

        norm_lookup = {normalize_model_name(name): name for name in models.keys()}
        if normalized_id in norm_lookup:
            exact_matches.append((provider_key, norm_lookup[normalized_id]))
            continue

        matches = difflib.get_close_matches(normalized_id, norm_lookup.keys(), n=3, cutoff=0.7)
        for match in matches:
            fuzzy_matches.append((provider_key, norm_lookup[match]))

    if exact_matches:
        return exact_matches

    # Deduplicate while preserving order for fuzzy matches
    seen: set[Tuple[str, str]] = set()
    deduped: List[Tuple[str, str]] = []
    for entry in fuzzy_matches:
        if entry in seen:
            continue
        seen.add(entry)
        deduped.append(entry)
    return deduped


def should_use_auto(poe_model: PoeModel, provider_key: str) -> bool:
    """Determine if 'auto' should be used instead of explicit mapping."""
    if "/" not in provider_key:
        return False
    
    provider, model_name = provider_key.split("/", 1)
    
    # Normalize for comparison
    poe_owned_by = poe_model.owned_by.lower()
    poe_id = poe_model.id.lower()
    provider_lower = provider.lower()
    model_name_lower = model_name.lower()
    
    # Check if owner matches provider
    owner_matches = poe_owned_by == provider_lower
    
    # Check if model name matches (allowing for variations)
    name_matches = (
        poe_id == model_name_lower or
        poe_id.replace("-", "") == model_name_lower.replace("-", "") or
        model_name_lower in poe_id or
        poe_id in model_name_lower
    )
    
    return owner_matches and name_matches


def prompt_for_mapping(
    provider: str,
    poe_model: PoeModel,
    suggestions: Sequence[str],
    cross_provider_suggestions: Sequence[Tuple[str, str]] = (),
) -> Optional[str]:
    """Interactively gather a mapping choice from the user."""
    console.print()
    console.print(f"[bold cyan]Candidate:[/bold cyan] [yellow]{poe_model.id}[/yellow] [dim](owned by {poe_model.owned_by})[/dim]")
    if poe_model.description:
        first_line = poe_model.description.splitlines()[0]
        console.print(f"  [italic]{first_line}[/italic]")

    option_index = 0
    indexed_choices: List[str] = []
    if suggestions:
        console.print("  [bold]Suggested models.dev entries:[/bold]")
        for suggestion in suggestions:
            option_index += 1
            full_key = f"{provider}/{suggestion}"
            indexed_choices.append(full_key)
            if should_use_auto(poe_model, full_key):
                console.print(f"    [green][{option_index}][/green] [cyan]{full_key}[/cyan] [bold green](→ auto)[/bold green]")
            else:
                console.print(f"    [green][{option_index}][/green] [cyan]{full_key}[/cyan]")
    else:
        console.print("  [yellow]No models.dev suggestions were found for this provider.[/yellow]")

    if cross_provider_suggestions:
        console.print("  [bold]Other providers with matching entries:[/bold]")
        seen_keys: set[str] = set()
        for provider_key, model_name in cross_provider_suggestions:
            full_key = f"{provider_key}/{model_name}"
            if full_key in seen_keys:
                continue
            seen_keys.add(full_key)
            option_index += 1
            indexed_choices.append(full_key)
            if should_use_auto(poe_model, full_key):
                console.print(f"    [green][{option_index}][/green] [cyan]{full_key}[/cyan] [bold green](→ auto)[/bold green]")
            else:
                console.print(f"    [green][{option_index}][/green] [cyan]{full_key}[/cyan]")

    console.print("  [dim]Options: [1-9] select, [m] manual entry, [a] use 'auto', [Enter] skip[/dim]")

    while True:
        try:
            raw = Prompt.ask("  Select option",
                           default="",
                           show_default=False,
                           console=console).strip()
        except EOFError:
            console.print("\n[yellow]Input closed – aborting.[/yellow]")
            return None
        except KeyboardInterrupt:
            console.print("\n[red]Operation cancelled by user.[/red]")
            sys.exit(1)

        if raw == "":
            console.print("  [dim]Skipping.[/dim]")
            return None
        if raw.lower() == "a":
            console.print(f"  [green]✓[/green] Selected [cyan]auto[/cyan]")
            return "auto"
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(indexed_choices):
                choice = indexed_choices[index - 1]
                # Automatically use 'auto' if it matches
                if should_use_auto(poe_model, choice):
                    console.print(f"  [green]✓[/green] Selected [cyan]auto[/cyan] [dim](matches {choice})[/dim]")
                    return "auto"
                else:
                    console.print(f"  [green]✓[/green] Selected [cyan]{choice}[/cyan]")
                    return choice
            console.print("  [red]Invalid selection.[/red]")
            continue
        if raw.lower() == "m":
            manual = Prompt.ask("  Enter provider/model or 'auto'", console=console).strip()
            if not manual:
                continue
            if manual.lower() == "auto":
                console.print(f"  [green]✓[/green] Selected [cyan]auto[/cyan]")
                return "auto"
            if "/" not in manual:
                console.print("  [red]Expected format 'provider/model' or 'auto'.[/red]")
                continue
            # Check if we should recommend auto
            if should_use_auto(poe_model, manual):
                use_auto = Prompt.ask(
                    f"  [yellow]This matches the pattern for 'auto'. Use 'auto' instead?[/yellow]",
                    choices=["Y", "n"],
                    default="Y",
                    console=console
                ).strip().lower()
                if use_auto != "n":
                    console.print(f"  [green]✓[/green] Selected [cyan]auto[/cyan]")
                    return "auto"
            console.print(f"  [green]✓[/green] Selected [cyan]{manual}[/cyan]")
            return manual
        console.print("  [red]Unrecognised input.[/red]")


def append_single_mapping(poe_id: str, provider: str, target: str, path: Path = MAPPING_PATH) -> None:
    """Append a single mapping entry to the YAML config immediately."""
    # Load existing mapping to update properly
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        data = {}
    
    if "model_mapping" not in data:
        data["model_mapping"] = {}
    
    # Add or update the mapping
    if poe_id not in data["model_mapping"]:
        data["model_mapping"][poe_id] = {}
    
    if not isinstance(data["model_mapping"][poe_id], dict):
        # Convert legacy format
        old_value = data["model_mapping"][poe_id]
        data["model_mapping"][poe_id] = {"models.dev": old_value}
    
    data["model_mapping"][poe_id][provider] = target
    
    # Write back the entire file
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True), encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Explore Poe models and update the provider mapping.")
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Fetch Poe models directly from the API instead of using dist/models.json when available.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing updates to config/model_mapping.yml.",
    )
    parser.add_argument(
        "--provider",
        dest="providers",
        action="append",
        help="Limit exploration to specific provider keys (can be repeated).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    try:
        mapping = load_model_mapping()
        models = load_poe_models(force_remote=args.remote)
        catalog = load_models_dev_catalog()
    except (OSError, URLError, RuntimeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        return 1

    # Extract provider keys directly from the models.dev catalog. This avoids relying on existing mappings.
    providers_in_catalog_set: set[str] = set()
    for provider_key, provider_block in catalog.items():
        if not isinstance(provider_block, dict):
            continue
        models_block = provider_block.get("models")
        if isinstance(models_block, dict) and models_block:
            providers_in_catalog_set.add(provider_key)
    providers_available: List[str] = sorted(providers_in_catalog_set)

    if args.providers:
        requested = {normalize_provider(provider) for provider in args.providers}
        providers_available_filtered: List[str] = [
            provider for provider in providers_available if normalize_provider(provider) in requested
        ]
        providers_available = providers_available_filtered
        if not providers_available:
            console.print("[yellow]No providers from the request are present in the models.dev catalog.[/yellow]")
            return 0

    owned_by_values = sorted({model.owned_by for model in models if model.owned_by})
    owner_matches = match_providers(owned_by_values, providers_available)
    grouped_models = group_models_by_provider(models, owner_matches)

    if not grouped_models:
        console.print("[yellow]No overlapping providers found between Poe models and the provider catalog.[/yellow]")
        return 0

    # Track which models have mappings in models.dev for which actual providers
    # e.g., if models.dev: "openai/gpt-4o", track that this model has "openai" mapped
    existing_mappings: Dict[str, set[str]] = {}
    for poe_id, provider_dict in mapping.items():
        if isinstance(provider_dict, dict):
            providers_for_model: set[str] = set()
            for provider_key, value in provider_dict.items():
                if provider_key == "models.dev" and isinstance(value, str):
                    if value != "auto" and "/" in value:
                        # Extract actual provider from "provider/model"
                        actual_provider = value.split("/", 1)[0]
                        providers_for_model.add(actual_provider)
                    elif value == "auto":
                        # For auto, we consider it mapped (we'll skip it)
                        providers_for_model.add("auto")
            existing_mappings[poe_id] = providers_for_model
    
    # Create a table for matched providers
    table = Table(title="Matched Providers", show_header=True, header_style="bold magenta")
    table.add_column("Provider", style="cyan", no_wrap=True)
    table.add_column("Total Models", justify="right", style="green")
    table.add_column("Already Mapped", justify="right", style="yellow")
    table.add_column("Owners", style="dim")
    
    for provider, provider_models in sorted(grouped_models.items()):
        owners = sorted({model.owned_by for model in provider_models})
        mapped_count = sum(
            1 for model in provider_models
            if model.id in existing_mappings and (
                provider in existing_mappings.get(model.id, set()) or
                "auto" in existing_mappings.get(model.id, set())
            )
        )
        table.add_row(
            provider,
            str(len(provider_models)),
            str(mapped_count),
            ", ".join(owners)
        )
    
    console.print(table)

    additions_count = 0
    for provider, provider_models in sorted(grouped_models.items()):
        # Find candidates that don't have this provider mapped yet
        candidates = sorted(
            (
                model for model in provider_models
                if model.id not in existing_mappings or (
                    provider not in existing_mappings.get(model.id, set()) and
                    "auto" not in existing_mappings.get(model.id, set())
                )
            ),
            key=lambda model: model.id.lower(),
        )
        if not candidates:
            continue

        for candidate in candidates:
            suggestions = suggest_models(provider, candidate.id, catalog)
            cross_suggestions: Sequence[Tuple[str, str]] = ()
            if not suggestions:
                cross_suggestions = find_cross_provider_suggestions(candidate.id, catalog, exclude_provider=provider)
            choice = prompt_for_mapping(provider, candidate, suggestions, cross_provider_suggestions=cross_suggestions)
            if not choice:
                continue

            # Check if this specific provider mapping already exists
            if candidate.id in existing_mappings:
                existing = existing_mappings.get(candidate.id, set())
                if provider in existing or "auto" in existing:
                    console.print(f"  [yellow]This model already has a {provider} mapping; skipping duplicate.[/yellow]")
                    continue

            # Validate provider if not using 'auto'
            if choice != "auto" and "/" in choice:
                choice_provider = choice.split("/", 1)[0]
                if choice_provider != provider:
                    confirm = Prompt.ask(
                        f"  [yellow]Provider differs from Poe owner ({provider}). Add anyway?[/yellow]",
                        choices=["y", "N"],
                        default="N",
                        console=console
                    ).strip().lower()
                    if confirm != "y":
                        console.print("  [dim]Skipped due to provider mismatch.[/dim]")
                        continue

            # Write immediately to file (unless dry-run)
            if args.dry_run:
                console.print(f"  [yellow][DRY RUN][/yellow] Would add: [cyan]{candidate.id}[/cyan] [{provider}] → [green]{choice}[/green]")
            else:
                append_single_mapping(candidate.id, provider, choice)
                console.print(f"  [bold green]✓ Saved:[/bold green] [cyan]{candidate.id}[/cyan] [{provider}] → [green]{choice}[/green]")
            
            # Update existing_mappings to prevent duplicates in the same session
            if candidate.id not in existing_mappings:
                existing_mappings[candidate.id] = set()
            if choice == "auto":
                existing_mappings[candidate.id].add("auto")
            elif "/" in choice:
                actual_provider = choice.split("/", 1)[0]
                existing_mappings[candidate.id].add(actual_provider)
            additions_count += 1

    if additions_count == 0:
        console.print("[yellow]No new mappings were added.[/yellow]")
        return 0

    if args.dry_run:
        console.print(f"\n[yellow]Dry run complete. Would have added {additions_count} mapping(s).[/yellow]")
    else:
        console.print(f"\n[bold green]✓ Successfully added {additions_count} mapping(s) to [cyan]{MAPPING_PATH}[/cyan].[/bold green]")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
