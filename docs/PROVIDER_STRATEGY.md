# Provider strategy

## Kimi K3

Use official Kimi Code OAuth as the primary orchestration route. It owns long-running project context, permissions, local tools and final synthesis. `k3-256k` is the normal default; `k3` is reserved for genuinely large cross-module context. The optional `kimi-k3-api` profile targets the official OpenAI-compatible API model `kimi-k3`, while `kimi-k3-self-hosted` targets an OpenAI-compatible vLLM/SGLang endpoint serving `moonshotai/Kimi-K3`; both require exact `/v1/models` discovery and never use DS2API credentials.

## DeepSeek

1. NVIDIA NIM DeepSeek V4 Flash: first free/prototype coding worker.
2. DS2API DeepSeek V4 Flash: opt-in local compatibility fallback when the NVIDIA flash route is unavailable.
3. NVIDIA NIM DeepSeek V4 Pro: difficult review/security/architecture.
4. DeepSeek official API: low-cost and high-concurrency fallback.
5. Personal DeepSeek web session: plan/review only after API routes fail.

DS2API is a DeepSeek-only upstream. Its account login, password and session refresh remain inside the DS2API service. The gateway connects only to its OpenAI-compatible health/model/chat endpoints and never aliases K3 or GLM to DS2API.

The official API is preferable to browser automation whenever a key and small balance are available because it has a documented protocol, tool calls and explicit error behavior.

## GLM-5.2

1. NVIDIA NIM GLM-5.2: first route because the hosted free endpoint exposes the exact model without local weights.
2. Z.AI general pay-as-you-go API: official fallback.
3. Personal GLM web session: advisory-only fallback.

The bundled Z.AI profile uses the general API endpoint, not a Coding Plan subscription endpoint. Coding Plan benefits have tool/use restrictions and should be configured only through tools explicitly covered by the user's plan.

## Why NVIDIA is first for DeepSeek and GLM

- Exact hosted model IDs are available.
- OpenAI-compatible protocol works with Kimi Code's temporary provider mechanism.
- No local multi-hundred-GB or TB-scale weights.
- Free prototype access is useful for experimentation.

The gateway still treats it as non-guaranteed capacity. Official vendor APIs are retained for predictable fallback.

The DeepSeek coding route is bounded to three total attempts. A 429 may be retried once using `Retry-After`; timeout/5xx/capacity errors open the provider circuit, 401/403 blocks the provider for a cooldown, and 404/410 permanently disables only the affected model until a provider refresh.

## Route customization

Copy and edit:

- `config/provider-profiles.example.json` → `config/provider-profiles.json`
- `config/routes.example.json` → `config/routes.json`

Secrets stay in `.env`; profile JSON contains only the name of the secret variable.
