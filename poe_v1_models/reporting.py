from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from poe_v1_models.checks import ProviderDecision
from poe_v1_models.pipeline import PipelineResult
from poe_v1_models.pricing import PricingSnapshot


def build_checks_report(result: PipelineResult) -> Dict[str, Any]:
    models: List[Dict[str, Any]] = []

    for model in result.payload.get("data", []):
        model_id = model.get("id")
        aggregate = result.aggregates.get(model_id)
        if not aggregate:
            continue

        model_entry: Dict[str, Any] = {
            "id": model_id,
            "selected_provider": aggregate.selected_provider,
            "overrides_applied": aggregate.overrides_applied,
            "poe_pricing": aggregate.normalized_pricing.as_dict(),
            "providers": [],
            "excluded": False,
        }

        for provider, decision in aggregate.decisions.items():
            model_entry["providers"].append(_provider_entry(provider, decision))

        models.append(model_entry)

    for model_id, model_data in result.excluded_models.items():
        models.append(
            {
                "id": model_id,
                "selected_provider": None,
                "overrides_applied": False,
                "poe_pricing": None,
                "providers": [],
                "excluded": True,
                "exclusion_reason": "config_exclusion",
                "owned_by": model_data.get("owned_by"),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
    }


def _provider_entry(name: str, decision: ProviderDecision) -> Dict[str, Any]:
    pricing_payload: Optional[Dict[str, Any]] = None
    if decision.pricing:
        pricing_payload = _snapshot_dict(decision.pricing)

    severity = "ok"
    if decision.status == "missing":
        severity = "muted"
    elif decision.status == "rejected":
        if any(reason.startswith("lower_than_poe") for reason in decision.reasons):
            severity = "red"
        else:
            severity = "yellow"

    return {
        "name": name,
        "status": decision.status,
        "reasons": list(decision.reasons),
        "severity": severity,
        "pricing": pricing_payload,
    }


def _snapshot_dict(pricing: PricingSnapshot) -> Dict[str, Any]:
    enriched = pricing.with_mtok()
    payload = enriched.as_dict()
    payload["prompt"] = payload.get("prompt")
    payload["completion"] = payload.get("completion")
    return payload


def render_checks_html() -> str:
    return """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Poe Pricing Checks</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }
    h1 { margin-bottom: 0.5rem; }
    .timestamp { color: #94a3b8; margin-bottom: 1.5rem; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; font-size: 0.9rem; }
    th, td { border: 1px solid rgba(148, 163, 184, 0.3); padding: 0.5rem; text-align: left; }
    th { background: rgba(30, 41, 59, 0.8); position: sticky; top: 0; }
    tr:nth-child(even) { background: rgba(15, 23, 42, 0.4); }
    tr.status-accepted { background: rgba(34, 197, 94, 0.12); }
    tr.status-missing { color: #94a3b8; }
    tr.severity-yellow { background: rgba(234, 179, 8, 0.2); }
    tr.severity-red { background: rgba(220, 38, 38, 0.3); }
    .tag { display: inline-block; padding: 0.125rem 0.5rem; border-radius: 999px; font-size: 0.75rem; margin-right: 0.25rem; }
    .tag.accepted { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
    .tag.rejected { background: rgba(248, 113, 113, 0.2); color: #fca5a5; }
    .tag.missing { background: rgba(148, 163, 184, 0.2); color: #cbd5f5; }
    .warning { color: #fbbf24; }
    .error { color: #f87171; }
  </style>
</head>
<body>
  <h1>Poe Pricing Checks</h1>
  <div class=\"timestamp\" id=\"timestamp\">Loading…</div>
  <table id=\"checks-table\">
    <thead>
      <tr>
        <th>Model</th>
        <th>Provider</th>
        <th>Status</th>
        <th>Reasons</th>
        <th>Prompt / MTok</th>
        <th>Completion / MTok</th>
        <th>Poe Prompt / MTok</th>
        <th>Poe Completion / MTok</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>
  <script>
    async function loadChecks() {
      const response = await fetch('checks.json');
      const data = await response.json();
      const tbody = document.querySelector('#checks-table tbody');
      tbody.innerHTML = '';
      document.getElementById('timestamp').textContent = `Generated at ${new Date(data.generated_at).toLocaleString()}`;
      data.models
        .filter(model => !model.excluded)
        .forEach(model => {
          const poePrompt = model.poe_pricing ? model.poe_pricing.prompt_mtok : null;
          const poeCompletion = model.poe_pricing ? model.poe_pricing.completion_mtok : null;
          model.providers.forEach(provider => {
            const row = document.createElement('tr');
            row.classList.add(`status-${provider.status}`);
            if (provider.severity && provider.severity !== 'ok') {
              row.classList.add(`severity-${provider.severity}`);
            }
            const prompt = provider.pricing ? provider.pricing.prompt_mtok || provider.pricing.prompt || '—' : '—';
            const completion = provider.pricing ? provider.pricing.completion_mtok || provider.pricing.completion || '—' : '—';
            row.innerHTML = `
              <td>${model.id}${model.selected_provider === provider.name ? ' ★' : ''}</td>
              <td>${provider.name}</td>
              <td><span class="tag ${provider.status}">${provider.status}</span></td>
              <td>${provider.reasons.length ? provider.reasons.join(', ') : '—'}</td>
              <td>${prompt}</td>
              <td>${completion}</td>
              <td>${poePrompt ?? '—'}</td>
              <td>${poeCompletion ?? '—'}</td>
            `;
            tbody.appendChild(row);
          });
        });

      const excludedModels = data.models.filter(model => model.excluded);
      if (excludedModels.length) {
        const separator = document.createElement('tr');
        separator.innerHTML = '<td colspan="8"><strong>Excluded models</strong></td>';
        tbody.appendChild(separator);
        excludedModels.forEach(model => {
          const row = document.createElement('tr');
          row.classList.add('status-missing');
          row.innerHTML = `
            <td>${model.id}</td>
            <td>—</td>
            <td><span class="tag missing">excluded</span></td>
            <td>${model.exclusion_reason || 'config rule'}</td>
            <td colspan="4">Owned by: ${model.owned_by || 'unknown'}</td>
          `;
          tbody.appendChild(row);
        });
      }
    }

    loadChecks().catch(error => {
      const tbody = document.querySelector('#checks-table tbody');
      tbody.innerHTML = `<tr><td colspan="8" class="error">Failed to load checks: ${error}</td></tr>`;
    });
  </script>
</body>
</html>
"""
