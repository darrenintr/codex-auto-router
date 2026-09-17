# External provider routing

`codex-auto-router` can optionally use `codex-api-provider` after the normal task classifier chooses a tier.

The responsibilities remain separate:

- Auto Router decides the required capability tier (`luna_low` through `sol_medium`).
- `codex-api-provider` reports available models, free/paid metadata and quota/capacity state.
- `external.toml` explicitly maps each tier to external model candidates. Auto Router does not guess cross-vendor model quality.

## 1. Configure Codex

Run `codex-api-provider` locally and add this to `~/.codex/config.toml`:

```toml
[model_providers.external]
name = "codex-api-provider"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"
```

## 2. Configure external tier candidates

Copy `external.example.toml` to:

```text
~/.config/codex-auto-router/external.toml
```

Example:

```toml
[external]
enabled = true
api_base = "http://127.0.0.1:8765"
codex_provider = "external"
prefer_free = true
min_remaining_tokens = 16000
timeout_seconds = 1.5
fallback_official = true

[tiers.luna_low]
models = [
  "openrouter/qwen/qwen3-coder:free",
  "groq/openai/gpt-oss-120b",
]
```

Candidate order is the configured fallback order. When `prefer_free = true`, a model explicitly reported as free by the provider gateway is preferred over paid candidates.

## Capacity behavior

A candidate is skipped when its provider reports `available=false`, `state=exhausted`, or `state=error`.

If the provider reports an exact or observed token window, `min_remaining_tokens` is enforced. Unknown token capacity is not treated as zero because many APIs do not expose a real remaining-token figure.

If no external candidate survives:

- `fallback_official = true` uses the original official GPT route.
- `fallback_official = false` stops rather than silently consuming official quota.

The gateway timeout is intentionally short. If `codex-api-provider` is down, the normal official route remains usable when fallback is enabled.
