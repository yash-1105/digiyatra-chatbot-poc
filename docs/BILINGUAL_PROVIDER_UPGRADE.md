# Bilingual providers, token budgets and usage accounting

Release date: 2026-11-19. Public application: https://digiyatra-chatbot-poc.vercel.app

## Features

The chatbot has independent English/हिन्दी and AI-provider selectors. English and Sarvam are defaults. Language/provider selection survives a page reload and is retained when a conversation is cleared; switching either keeps the current conversation. Greetings, starters, typing indicators, feedback, retries, fallbacks and source-list controls are localized. Existing messages retain their original text. Original English source passages are preserved rather than translated into purported new evidence.

Backend provider allow-list:

| Provider | Fixed model | API | Inference |
|---|---|---|---|
| Sarvam | `sarvam-105b` | Existing Sarvam Chat Completions V2 | Reasoning off; default output cap 900 |
| Anthropic | `claude-haiku-5-5` | Official `POST https://api.anthropic.com/v1/messages` | `output_config.effort=low`; default output cap 900; no unsupported sampling parameters |

The Anthropic API key already existed securely in Railway and was verified without printing or changing it. Neither key is sent to the frontend, stored in analytics or committed. Arbitrary browser model names, provider names and languages are rejected. Provider failures do not select a different paid provider.

Both providers share the existing approved LanceDB corpus, RAG orchestration, citations, general-knowledge allow-list, unsupported-information restrictions, authentication and analytics. Devanagari and bounded Hinglish synonyms normalize into English retrieval concepts. Generation receives the original redacted question and explicit output-language instructions. Hindi claims are validated against English evidence using bounded equivalent concepts; unknown Hindi words remain factual tokens rather than disappearing through the English tokenizer. Numeric and policy-polarity checks also apply to Hindi. No translation API is used.

## Optimization

- A shorter security-preserving system prompt retains evidence-only policy facts, citations, injection/secret controls, uncertainty, conflict handling and privacy conditions.
- Query-aware retrieval selects complete approved FAQ chunks, not blindly shortened passages. Existing units were already small enough; no re-ingestion or fact-deleting compressor was introduced.
- Context defaults: three ranked chunks within an estimated 1,800-token budget. Conflicting partners stay together or the whole group is omitted. Retrieval remains configurable and approval-filtered.
- History defaults: estimated 600-token budget and at most ten server turns; the browser sends only the last four user questions for recovery, never redundant assistant replies. Whole messages are kept or omitted.
- Rolling summaries are bounded intent/topic anchors, not generated facts or private identifiers. They require no extra model call and cannot override a new explicit intent.
- Estimated prompt budget: 6,000 tokens plus a conservative UTF-8 byte ceiling. This is not an exact provider tokenizer. Provider `max_tokens` enforces the output cap. Existing signed-client rate limiting remains; Anthropic additionally defaults to ten requests/minute per client IP.
- Anthropic caching covers sufficiently long stable system instructions only. It excludes passenger messages and needs no padding. Actual cache-read/write token fields are recorded.
- A bounded five-minute public-FAQ answer cache is keyed by provider, language and approved corpus revision. Personal questions, follow-ups, conflicts, time-sensitive notices, refusals and errors bypass it. Corpus reloads invalidate hits. A hit still gets a new message ID and normal resolution-feedback accounting.
- Classification, query translation and topic summaries add no model calls. Existing citation repair remains a conditional safety exception; its tokens and cost are counted.

Reviewed [Headroom](https://github.com/headroomlabs-ai/headroom) by Tejas Chopra, including its [dependency/configuration source](https://github.com/headroomlabs-ai/headroom/blob/main/pyproject.toml), and [Microsoft LLMLingua](https://github.com/microsoft/LLMLingua). Headroom's repository is active and Apache-2.0 licensed. Neither was integrated: incremental savings and Hindi/citation fidelity for this short approved-FAQ workload were not demonstrated, and additional transforms or model dependencies were unnecessary. This is not a security certification or a claim that the libraries cannot help other workloads.

## Measured comparison

`backend/evaluation/bilingual_questions.json` contains 24 representative questions, exercised against each provider. It includes English, Devanagari, Hinglish, mixed language, language switching, follow-ups, citations, OTP/NFC definitions, privacy, dependents, unsupported information and injection attempts. Benchmark code is `backend/evaluation/bilingual.py`.

The baseline used the prior longer prompt, up to five full-context chunks, a larger history budget, 1,200 output tokens and no Anthropic prompt caching. The optimized sample used the new prompt and budgets, 900 output tokens and Anthropic system caching. FAQ answer caching was disabled for both samples. This is a bounded before/after configuration sample; generation and network latency can vary. It does not isolate the contribution of every technique.

Results from the final matched sample and deployment verification are recorded in `PRODUCTION_DEPLOYMENT_REPORT.md`. All token/cost measurements use provider usage fields; missing values are flagged, not represented as exact. Full answers and retrieved passages remain in ignored private artifacts. Synthetic analytics databases are separate from primary production analytics.

## Costs and operations

Migration `0002_ai_usage` adds an independent accounting table without changing existing account or analytics records. It stores provider/model, timestamps, token/cache counts, estimated USD, status and latency. It contains no questions, answers, IPs or conversation identifiers. The existing session-protected analytics API and dashboard include an AI Usage & Costs section, provider counters, cache/error counts, average tokens/cost and daily token trends.

All dollar figures are estimates, not invoices. Reference rates are configurable in `backend/.env.example`. Default Sarvam estimates use INR 10 input / 0.25 cached / 25 output per million tokens with an explicit reference conversion of INR 85/USD; this is not a live exchange rate or confirmation of account-specific introductory-price eligibility. Anthropic estimates use USD 0.10 input / 0.50 output / 0.01 cache read / 0.125 five-minute cache write per million tokens. Failed calls can have unreported usage.

Primary references: [Haiku 5.5 model](https://platform.claude.com/docs/en/models/haiku-5-5/overview), [migration/parameter requirements](https://platform.claude.com/docs/en/models/haiku-5-5/migration-guide), [prompt caching and prices](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Sarvam model/pricing reference](https://docs.sarvam.ai/api/token-factory/models/sarvam-105b).

Railway resources, billing settings, API secrets, production administrator credentials, approved corpus and existing schema records are preserved. The new table is migrated automatically by the existing startup script. One backend replica/worker remains required because rate limits, FAQ caching and conversation memory are in-process. Usage accounting persists in PostgreSQL. Content-owner approval remains pending, and private knowledge files remain outside public GitHub.
