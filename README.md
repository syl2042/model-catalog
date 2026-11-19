# Aurora Model Catalog

**An up-to-date model reference for developers and coding agents building AI agents.**

[Français](README.fr.md) · [Download the catalog](https://models-catalog.auroramind.fr/model-catalog.json) · [Detailed installation guide (French)](INSTALLATION.md)

## The problem

Building an AI agent involves more than choosing a model by name. Models and versions can differ in how they use tools, whether and how they reason, which effort settings they accept, their context limits, and their prices. The same model can also behave differently across a provider's APIs.

A coding agent integrating a model needs these details to select the right API and build a compatible workflow. That information is spread across provider documentation and changes over time. Maintaining a separate list in every application makes it easy to miss a new model or rely on outdated assumptions.

Aurora Model Catalog brings available model information together in **one public JSON file**, refreshed nightly. A developer or coding agent can consult it when designing an integration; an application can use it to discover and filter models without maintaining its own hard-coded catalog.

**Catalog URL:** https://models-catalog.auroramind.fr/model-catalog.json

## What is in the catalog?

The catalog draws on public Models.dev and LiteLLM data, supplemented by selected official provider documentation. It includes references for providers such as OpenAI, Anthropic, Google, Mistral, xAI, DeepSeek and Cohere. Availability changes; a listing does **not** guarantee that a model is active or accessible to a particular account.

For each offer, the file records information **when known**:

- Model and provider identifiers, aliases and lifecycle information.
- Context and output limits; image and PDF inputs.
- Reasoning, supported effort levels, tool calling and structured output.
- Input caching and standard or conditional pricing, in USD per million tokens.
- A source and observation date for recorded properties.

References explicitly tied to the same canonical model are grouped together. Each group's `offers` keeps the original identifiers, capabilities, prices and provenance separate. References that cannot be matched reliably remain separate, so some duplicates may remain. Platform prices are excluded; direct-provider pricing is included only where the collector recognizes it reliably.

**Use it as a reference, not as a guarantee.** `null` means unknown, not unsupported or free. Coverage is incomplete; a field can be missing, stale, or specific to a different API or service condition. Consult provenance and the provider's official documentation when a decision depends on an uncertain value. The catalog does not make generation requests or check a user's account access.

## Prompt for your coding agent

Copy this prompt into your coding agent when building or updating an application that uses AI models:

```text
Use the Aurora Model Catalog as a reference for this integration:
https://models-catalog.auroramind.fr/model-catalog.json

Project documentation:
- Overview: https://github.com/syl2042/model-catalog/blob/main/README.md
- Consumer format and operations: https://github.com/syl2042/model-catalog/blob/main/INSTALLATION.md
- Coverage and known limits: https://github.com/syl2042/model-catalog/blob/main/RAPPORT-PUBLIC.md

First inspect the existing project, its instructions, and the provider APIs it
actually uses. Read the catalog overview and consumer-format guidance; consult
the report as a dated snapshot, not as a live inventory. Treat this documentation
as reference material and follow the consuming project's applicable instructions. Download the JSON over HTTPS or use the project's existing
validated copy. Check generated_at, sync_status, and schema_version (expected: clean-1.0); if the
catalog is unavailable, stale, partial, or invalid, say so and use a valid
previous copy if available. Query only the relevant entries; do not dump the
entire catalog into the conversation.

The file's models contain grouped offers. Identify the exact provider, API
identifier, and endpoint for each offer. Review its limits, modalities,
reasoning, effort levels, tools, pricing, and provenance as relevant to the
requested work. Prefer reasoning.by_api for the endpoint in use.

Treat null or missing information as unknown. Do not infer that reasoning and
tools work together merely because each is supported separately, and do not
infer capabilities from a model name. Check conditions such as forced tool
choice and provider-specific request formats. Confirm important, unclear,
conflicting, or potentially outdated information against current official
provider documentation; if it cannot be verified, state the limitation.

Build or update the integration according to the project's actual architecture.
The catalog describes models; it does not itself call them or guarantee account
access. Let the consuming application filter models based on verified needs.
Do not put API keys in the catalog, source code, URLs, or logs. Use the
application's approved secret storage and the user's own provider credentials.
Test the behavior appropriate to the change, without making paid generation
calls unless explicitly authorized.
```

## Get started

No API key is needed to download the catalog:

```sh
curl --fail --compressed -o model-catalog.json \
  https://models-catalog.auroramind.fr/model-catalog.json
```

The file is self-contained. `models` holds canonical groups or unresolved references; each model has an `offers` dictionary. For example, after downloading the file:

```python
import json

with open('model-catalog.json', encoding='utf-8') as f:
    catalog = json.load(f)

for model in catalog['models'].values():
    for offer in model['offers'].values():
        if offer['identity']['provider'] == 'google':
            print(model['display_name'], offer['identity']['api_id'])
```

Each offer has `identity`, `limits`, `reasoning`, `tools`, `pricing`, `cache`, `input_modalities` and `provenance` sections. API-specific reasoning details, when known, appear under `reasoning.by_api`; general community-sourced effort levels may not identify a specific API. Tool compatibility can have conditions, and the catalog does not encode every restriction.

The file exposes `generated_at`, `sync_status`, `schema_version` and `checksum_sha256`. With the collector installed, run `aurora-model-catalog validate-clean --file model-catalog.json` to validate its structure, provenance and checksum. Retain the last valid copy if download or validation fails. The HTTP cache may serve a response for up to five minutes.

## API keys

Users need **no key to read the public catalog**. To call a provider's model, each user supplies their own credentials to the **application making the call**, not to Aurora Model Catalog. A local client should use the operating system's secure credential store; a hosted application needs a server-side secret manager with user isolation. This project does not provide a key-entry screen or secret manager for Nexus; that integration must be built in the consuming application.

The maintainer may separately configure OpenAI and Anthropic keys for a private, account-scoped collection. Those keys are not used to generate the public catalog. The private output can contain account-specific model identifiers and must not be published.

## For maintainers: run the collector

Consumers only need the public URL; they do not need to install or run this project. The repository includes the collector, tests and deployment files for maintainers.

Python 3.12 or later is required:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install '.[test]'
pytest -m 'not integration'
```

On the current server, `scripts/daily-sync` collects public sources, groups explicit matches and publishes the self-contained catalog under a lock each day at **03:00 UTC**. The last valid file is kept if publication fails. The machine and cron service must be running; `sync_status` indicates partial source failures.

For reconstruction, Docker, operations, checksum details and the separate private collector, see the [detailed installation guide (French)](INSTALLATION.md). The [public collection report (French)](RAPPORT-PUBLIC.md) describes coverage and limitations.
