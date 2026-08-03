# Provider strategy

## Kimi K3

Use official Kimi Code OAuth as the primary orchestration route. It owns long-running project context, permissions, local tools and final synthesis. `k3-256k` is the normal default; `k3` is reserved for genuinely large cross-module context.

## DeepSeek

1. NVIDIA NIM DeepSeek V4 Flash: first free/prototype coding worker.
2. NVIDIA NIM DeepSeek V4 Pro: difficult review/security/architecture.
3. DeepSeek official API: low-cost and high-concurrency fallback.
4. Personal DeepSeek web session: plan/review only after API routes fail.

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

## Route customization

Copy and edit:

- `config/provider-profiles.example.json` → `config/provider-profiles.json`
- `config/routes.example.json` → `config/routes.json`

Secrets stay in `.env`; profile JSON contains only the name of the secret variable.
