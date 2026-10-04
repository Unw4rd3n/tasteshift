# TasteShift — MVP design

Status: proposed implementation plan, 4 October 2026. No application has been implemented yet.

## Product

TasteShift helps people who keep returning to the same music, films and books find something unfamiliar that still connects to their interests. The first useful result should take less than a minute to request, without an account.

The core interaction is a controlled step outside familiar territory. A user provides a few favourites, chooses an exploration level, and gets a short cross-category selection. Every recommendation includes a traceable connection to the inputs. Feedback changes the next selection.

An AI agent turns an intent such as “a quiet evening with something different” into a selection and a short experience plan. Qloo supplies the real candidate entities. The agent can retrieve more candidates or relax an optional preference when coverage is poor; it cannot invent replacement entities.

## First release

Include:

- Entity search and disambiguation for artists, films and books.
- Three to five confirmed favourites; permit one category, encourage a mix.
- Four exploration levels: Safe, Curious, Experimental, Wild.
- Six discovery cards, ideally two per category when coverage allows.
- A Taste DNA view of the selected interests and available cultural connections.
- A short optional “Make an evening of it” plan using returned entities.
- Save, Not for me, Already know it, and Tried it feedback.
- A follow-up selection that reflects explicit feedback.
- A hosted live app, setup instructions, and an open-source license.

Defer local restaurants, travel, maps, payments, social profiles and external account imports. Add places only after a live Qloo coverage check. No need for Redis, a vector database, or model training in the first release.

## User journey

1. Add favourites using search. Each choice shows its type and enough metadata to distinguish namesakes. Free text is not treated as a confirmed Qloo entity.
2. Choose an exploration level and optionally an intent, such as quiet evening, weekend discovery, or free text.
3. Request discoveries. Show meaningful progress: finding connections, choosing discoveries, putting the selection together.
4. Explore six cards. Each contains the item, category, grounded reason, available artwork, and a verified external link where available.
5. Open a card's connection detail: source favourites, relevant returned metadata, and why this item was selected. Do not call correlations proof of individual preference.
6. Save or reject items. Request a new selection or turn the current one into an evening plan.

Changing the level does not repeatedly fire provider calls while dragging. Use four labelled stops and an explicit refresh action. Keep the current selection visible until the replacement is ready.

## Taste DNA

Treat this as a readable map, not a psychological assessment. Show confirmed favourites, their categories, and any returned tags or affinity links. Missing evidence produces fewer connections rather than guessed labels.

The proposed dark/bright and underground/mainstream axes are not part of the initial data contract. Add an axis only if we can document a reproducible derivation and expose its limits. Do not display arbitrary percentages or a probability that a user will like an item.

Saved and Tried it items become explicit new signals. Not for me excludes an item; it does not imply the user dislikes an entire genre. Already know it removes the item from new discoveries without treating it as negative taste. Only explicit Tried it feedback represents an experience; do not claim a user's taste changed merely because they saw a card.

## Recommendation pipeline

1. Resolve and validate selected entity IDs server-side.
2. Query Qloo Insights separately for artists, movies and books using the combined interests.
3. Adapt responses into a stable internal entity model, preserving available scores, tags and source metadata. Do not assume undocumented fields exist.
4. Exclude seed entities, duplicates, rejected items and already-known items. Keep filters separate from taste signals.
5. Form a baseline ranking per category. Compare scores only within the same request/category unless Qloo documents cross-category calibration.
6. Rerank candidates according to the exploration policy and diversity. Do not use random sampling as the main source of surprise.
7. Supply selected candidates and evidence to the agent for explanations and an optional plan. Validate every returned ID against the allowed candidates.
8. Persist the exact result and its evidence so feedback and later explanation views refer to what was actually shown.

### Safe → Wild

“Wild” should mean a more distant but still supported choice. It should not mean selecting the least relevant available item.

Start with rank-based relevance within each category. When sufficient tags are returned, estimate tag distance from the seed profile using a documented overlap measure. Distance is a product heuristic, not a Qloo metric and not evidence that the user has never encountered the item.

Proposed first-pass policy:

| Level | Candidate relevance pool | Selection policy |
| --- | --- | --- |
| Safe | Top 25% | Prioritize affinity; remove near duplicates |
| Curious | Top 50% | Balance affinity with modest tag distance |
| Experimental | Top 75% | Seek more distant tags and greater diversity |
| Wild | Broad pool above a relevance floor | Favor distant, evidenced candidates with varied tags |

These are starting settings, not measured performance claims. Define a minimum pool size, fall back gracefully when coverage is sparse, and tune with real responses. Use deterministic tie-breaking so comparisons are reproducible.

Normalize per-category affinity ranks and tag distance to bounded values. A simple reranking objective is `(1 - exploration_weight) * relevance + exploration_weight * distance`, with a penalty for similarity to already selected items. Tune the four weights only after inspecting actual metadata. All levels retain a relevance floor and at least one evidenced seed connection.

If tags are absent, keep affinity-based candidates and explain that available data limits exploration. Do not manufacture distance or silently imply all four modes are equally supported. Test whether higher levels increase average distance over a representative set of seed profiles; do not promise strict monotonicity for every individual card.

## Agent

Use one small, bounded tool-calling agent in Python. A large multi-agent workflow is unnecessary for this release.

Tools exposed to the agent:

- `get_candidates(category, seed_ids, constraints)` — retrieves validated Qloo candidates.
- `get_entity_details(entity_ids)` — retrieves documented metadata when needed.
- `get_feedback()` — reads feedback for the current authorized session, bound by the server.
- `select_discoveries(candidate_ids, level)` — applies the deterministic ranking policy.
- `build_experience(selected_ids, intent)` — returns a plan containing only allowed entities.

The server owns session identity, allowed categories, call budgets and candidate validation. The model never chooses an arbitrary session ID, URL, SQL query or provider endpoint. Entity descriptions and user intent are data, not tool instructions.

Limit a run to two retrieval rounds, six provider requests total, and two model turns after retrieval. Account for cached responses and detail requests within the same budget. Hard constraints and excluded entities are never relaxed. If optional constraints need relaxing, report exactly what changed.

Explanations distinguish a returned cultural affinity from descriptive interpretation. An explanation may summarize available tags; it must not fabricate a causal story. Use plain factual fallback text when the model is unavailable. Recommendations should still work if explanation generation fails.

## Architecture

```text
Browser / React + Vite
       |
       | same-origin /api
       v
FastAPI
  |-- session + discovery endpoints
  |-- Qloo adapter --> Qloo hackathon API
  |-- ranking service
  |-- bounded agent --> model provider
  |-- result validation + evidence
  `-- PostgreSQL
```

Use React, TypeScript, Vite and Tailwind for the frontend; Python, FastAPI, Pydantic and httpx for the backend; PostgreSQL with SQLAlchemy and Alembic for storage. FastAPI serves the compiled frontend and API under the same origin. Provider keys stay on the server. The detailed implementation decisions are in [architecture.md](architecture.md).

Start without accounts. Use an opaque HttpOnly session cookie, enforce ownership on every read and write, and validate request origins for mutations. Store only the selected interests, results and feedback required by the experience. Set a session expiry and clean up expired data.

Begin with synchronous discovery requests and a visible progress state. Set an end-to-end deadline and cancel work on timeout. Introduce durable jobs and polling only if observed latency makes them necessary; do not add a task queue pre-emptively.

Deployment proposal: one Docker app service serving FastAPI and compiled frontend assets, plus managed PostgreSQL on Render, Railway or an equivalent host. Node is used at build time only. Final hosting depends on available accounts and budget. Verify provider connectivity, same-origin cookies, proxy timeouts and public access before choosing the final deployment.

## App API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/entities/search?q=...&category=...` | Debounced entity lookup |
| POST | `/api/discoveries` | Validate seeds, retrieve and return a selection |
| GET | `/api/discoveries/{id}` | Read a discovery owned by this session |
| POST | `/api/discoveries/{id}/feedback` | Record explicit item feedback |
| POST | `/api/discoveries/{id}/experience` | Make a plan using this selection |
| GET | `/api/health` | Deployment health without exposing credentials |

A discovery request contains `seed_ids`, `level`, and optional `intent`. A discovery response contains `id`, `items`, `connections`, `coverage`, and `data_mode`. Each item contains its source entity ID, category, name, available media and URLs, explanation, evidence references and selection reason. Numeric provider scores remain internal until a useful, defensible display is defined.

## Storage

- `sessions`: opaque ID, created/expiry timestamps.
- `taste_seeds`: session ID, entity ID, category, explicit signal source.
- `discoveries`: session ID, input snapshot, level, policy version, status and timestamps.
- `discovery_items`: discovery ID, entity ID, category, position, normalized metadata and evidence snapshot.
- `feedback`: session ID, discovery/item ID, action and timestamp; idempotent writes.
- `experiences`: discovery ID, intent, validated selected IDs and plan.

Add a bounded provider cache if API quota or response time warrants it. Avoid retaining full raw responses indefinitely. Redact credentials, user intent and session tokens from logs.

## Qloo integration: verified facts and open checks

The [official hackathon developer guide](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide) specifies:

- Base URL: `https://hackathon.api.qloo.com` for hackathon keys.
- Authentication: `X-Api-Key` header.
- Entity lookup: `/search`; supported search types differ from Insights types.
- Recommendations: `GET /v2/insights`, with parameters in the query string.
- Required category filter: `filter.type`; initial categories are `urn:entity:artist`, `urn:entity:movie`, and `urn:entity:book`.
- Resolved input IDs can be supplied through `signal.interests.entities`.
- Legacy `/recs` and `/recommendations` endpoints are unsupported.
- Unsupported parameters may be silently ignored, so validate against the entity-type parameter guide.

Before implementing ranking, use a real key to verify search syntax, pagination, per-category response fields, available tag metadata, score meaning, supported exclusion filters, image/link availability, quota and empty-result behavior. The guide was read; live authenticated responses have not been tested. Do not encode guessed wire schemas as established contracts.

No API key has been requested from the user or copied into the repository. Configure `QLOO_API_KEY`, `QLOO_BASE_URL`, `MODEL_API_KEY`, `MODEL_NAME`, and `DATABASE_URL` privately; commit only variable names and empty examples.

## Failure behavior

- Ambiguous search: ask the user to choose the correct entity.
- No coverage: keep other successful categories, explain the missing category, and allow seed changes.
- Missing artwork: use a text-based card with a consistent fallback.
- Rate limit or timeout: bounded retry where appropriate, then a useful recoverable error. Do not return unrelated invented entities.
- Model failure: retain Qloo results and use factual evidence summaries.
- Demo fixtures: allow clearly labelled fixture data for development; never represent fixtures as a live Qloo response. Fixture-only operation does not satisfy launch acceptance.

## Build order

1. Integration spike: authenticate Qloo; inspect search and Insights responses for three real seed profiles; document contracts and coverage.
2. Vertical slice: seed search → real discoveries → evidence view. Run locally before expanding features.
3. Exploration: reranking, all four levels, deduplication, Saved/Not for me/Already know it feedback.
4. Agent: intent-aware retrieval and validated evening plans; demonstrate one explicit feedback loop.
5. Finish: responsive UI, accessible controls, error states, public deployment, setup documentation and license.

## Acceptance

- A new visitor can complete the main flow without an account or private access.
- Every live recommendation resolves to a real provider entity and excludes supplied seeds and negative feedback.
- Multiple input categories influence discovery; capture the provider request evidence needed to inspect this.
- Exploration modes change candidate selection, with distance/diversity checks on recorded representative responses.
- Every explanation references available evidence; no invented venues, links or unsupported taste probabilities.
- The optional plan uses only validated discoveries and reacts to explicit feedback.
- Provider errors and missing metadata leave a recoverable interface.
- Session data cannot be read or modified from another session; keys never appear in frontend assets or logs.
- The hosted app works end-to-end with live Qloo. README explains setup and the repository contains an open-source license.

Write focused tests for response adaptation, exclusions, ranking policy, allowed-ID validation, session ownership and provider failures. Add one browser test of the complete discovery/feedback flow. Avoid tests that only duplicate implementation details.

## Submission and design status

The [hackathon requirements](https://qloo.devpost.com/) call for an externally hosted functional demo, public source code, project description and an open-source license. Replace the current repository URL in the demo field once the app is hosted. The repository URL remains the code link.

Visual design is pending. Lazyweb reference search completed; `lazyweb_generate_report` with `objective=create` returned a redirect to `lazyweb-deep-design-research`, but fetching that workflow returned `WORKFLOW_NOT_FOUND`. Its workflow inventory instead lists `lazyweb-design-create`. No hosted design report or validated visual mockup was produced. The supplied screenshot depicts the Devpost submission, not an existing TasteShift app screen.

This document specifies product behavior and engineering decisions. It is not a substitute for the requested Lazyweb visual report.
