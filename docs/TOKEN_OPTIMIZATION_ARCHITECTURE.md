# Digi Yatra token optimization architecture

## Request path

The Vercel frontend still sends the existing chat contract through its same-origin proxy. FastAPI applies request-size, schema, anonymous session scoping and rate-limit controls before calling the chat service. The service checks redaction and input guardrails, then consults the reviewed public FAQ cache for eligible requests. Both a miss and a cache failure use the normal RAG path and the selected provider. Returned model answers still pass output filtering and sentence grounding before the service exposes citations. Feedback and the existing admin interface use their current endpoints.

PostgreSQL stores analytics and reviewed FAQs. LanceDB remains the rebuildable knowledge index. The production index has 119 approved chunks from 26 documents. It uses 4,096-dimensional hashed TF-IDF vectors plus BM25, multilingual concept expansion, intent boosts and approved-only filtering. FAQ fragments from the same source are reassembled before selection. Existing retrieval confidence and grounding thresholds are unchanged. Retrieval uses deterministic chunk ordering and precomputes the ID-to-position map when the index loads.

## Context and budgets

The current production selector remains the default. The opt-in selector retains the highest-ranked passage, prioritizes remaining passages that add question-term coverage, deduplicates identical passages with matching source and caveat metadata and treats overlapping conflict groups as whole units. It measures rendered evidence, including citation labels and conflict notes. It carries the original passages and source references through grounding and citation creation. It may request more whole passages for airport catalog questions and on the existing one-time insufficient-evidence retry. Airport snapshots and live gate questions retain separate handling.

`PROMPT_TOKEN_BUDGET` limits the input. The candidate accounts for system text, bounded history and question text before allocating evidence. `CONTEXT_TOKEN_BUDGET`, `CONTEXT_TOP_K`, `RETRIEVAL_TOP_K`, `RAG_EXPANDED_CONTEXT_TOKEN_BUDGET` and `RAG_EXPANDED_TOP_K` control selection. Language controls and long-list instructions remain part of the prompt. Both provider output limits default to 900 tokens and remain separately configurable. Byte-based input limits use conservative estimates. Provider totals determine reported usage after the call.

## Provider settings

- Sarvam continues to use `sarvam-105b`, temperature 0.2 and production `reasoning_effort=none`. The client preserves its request behavior. A reported cached-input count establishes discounted input accounting only. Sarvam documents session affinity for Gemma 4, and the replay does not establish any causal effect of that header on 105B. [Sarvam model and chat docs](https://docs.sarvam.ai/api/token-factory/chat-completions)
- Anthropic continues to use `claude-haiku-5-5` at low output effort. Supply `ANTHROPIC_WORKSPACE_ID` only when the existing key requires it. Workspace-scoped keys work with the header omitted. Error mapping and selected-provider routing are preserved. [Anthropic authentication](https://platform.claude.com/docs/en/manage-claude/authentication)
- The optional Anthropic explicit breakpoint covers the deterministic language-specific system prefix. The process leak canary stays in an uncached system block. Evidence, conversation text and the question remain in user messages. Haiku 5.5 requires at least 512 provider tokens. The client uses an inexpensive 2 KiB prefix heuristic and requests a five-minute TTL. The provider determines actual eligibility. Automatic request-level caching would advance the breakpoint into dynamic messages, so the implementation uses an explicit breakpoint. [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) · [Claude Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/overview)

## Decisions and controls

| Approach | Decision |
| --- | --- |
| Existing lexical hybrid retrieval, approved-source control and grounding | Retained. Deterministic index ordering and ranking lookup improvements are active. |
| Whole-passage coverage selection and compact prompts | Implemented behind `RAG_CONTEXT_OPTIMIZATION_ENABLED`, default off. The paired replay did not clear release gates. |
| PostgreSQL reviewed exact FAQ cache | Implemented behind `FAQ_CACHE_ENABLED`, default off. Content-owner review and a private production bundle are pending. The previous generated-response cache was removed. |
| Anthropic five-minute prefix caching | Implemented behind `ANTHROPIC_PROMPT_CACHE_ENABLED`, default off and explicitly on in production to retain native caching with a stable prefix. The old `ANTHROPIC_PROMPT_CACHE` setting remains an alias. |
| Semantic response caching | Blocked by account entitlement and absence of an existing dense index. No semantic lookup code or runtime flag. |
| Headroom, LLMLingua-2 and heavier reranking | Declined for production after the applicability review. No dependencies, process, proxy or runtime flags. |
| Redis | Unnecessary. PostgreSQL provides the existing persistence and transaction boundary. |

The EmbeddingGemma 2 account probe returned provisioning required. TF-IDF similarity cannot establish answer equivalence. A separate cache would also require measured repeat traffic and calibration across language, modality, entities, dates and negation. Railway serves the knowledge index from an ephemeral backend filesystem. The PostgreSQL volume supplies FAQ durability. No backend resource or billing changes are required for the shipped application code. [Sarvam EmbeddingGemma 2](https://docs.sarvam.ai/api/token-factory/models/embeddinggemma-2) · [Railway storage behavior](https://docs.railway.com/deployments/reference#ephemeral-storage)

The backend release uses the existing private Railway build context and approved corpus. Public GitHub contains code, tests and aggregate reports only. The frontend requires no code changes. The schema upgrade adds two tables and nullable usage columns through migration `0003_faq_telemetry`. Roll back application behavior with the feature flags or restore the prior Railway deployment. Keep the additive migration in place during application rollback.

See [benchmark data](TOKEN_OPTIMIZATION_BENCHMARKS.md) and [cache publication and rollback](CACHE_SECURITY_AND_INVALIDATION.md).

## Changed code

- Retrieval, prompts and request flow run through `app/rag/retriever.py`, `app/services/{context,prompts,chat_service}.py`, `app/main.py` and settings in `app/config.py` with `.env.example`.
- FAQ publication and accounting use `app/services/{faq,usage}.py`, `app/db/models.py`, `app/cli.py` and `migrations/versions/0003_faq_telemetry.py`.
- Anthropic request handling is in `app/clients/anthropic.py`. Replay and regressions are in `evaluation/{bilingual,token_optimization}.py` and `tests/unit/test_{answering_reliability,bilingual_providers,reviewed_faq}.py`.

For production rollback set the relevant flag to `false` on the Railway backend and confirm its replacement deployment is healthy. If application rollback is required, restore the prior Railway deployment or build the prior verified Git commit with the authorized private corpus. Keep the additive schema in place. Vercel's proxy can verify backend health at `/api/v1/health`.
