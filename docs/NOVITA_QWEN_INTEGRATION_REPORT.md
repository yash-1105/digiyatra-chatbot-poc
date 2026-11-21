# Novita Qwen3.8 Flash integration

Date 2026-11-21

## Application changes

The chat selector adds **Novita AI — Qwen3.8 Flash** alongside **Sarvam AI — 105B** and **Anthropic — Haiku 5.5**. The existing session stores the selected provider and the existing chat API accepts `provider: "novita"`. The backend selects a fixed model and endpoint. It returns the existing service error when Novita fails.

| Files | Changes |
|---|---|
| `backend/app/clients/novita.py`, `backend/app/config.py`, `backend/.env.example` | Async client, fixed model, bounded limits and versioned pricing. |
| `backend/app/main.py`, `backend/app/api/routes/chat.py`, `backend/app/schemas/chat.py` | Provider lifecycle, independent rate limit and API allowlist. |
| `backend/app/services/chat_service.py`, `backend/app/services/faq.py`, `backend/app/logging_config.py` | Novita credential redaction in shared output and diagnostic paths. |
| `backend/app/services/usage.py`, `frontend/src/components/admin/DashboardView.tsx` | USD pricing and Novita usage in the existing admin report and panel. |
| `frontend/src/components/chat/ChatWidget.tsx`, `frontend/src/components/chat/useChat.ts`, `frontend/src/lib/api/types.ts` | Selector option, session restoration and room for the longer label on narrow screens. |
| `backend/tests/unit/test_novita.py`, `backend/tests/unit/test_reviewed_faq.py`, `backend/evaluation/novita_questions.json`, `backend/evaluation/novita_smoke.py` | Wire and integration regressions, multilingual cases and capped live checks. |

Sarvam and Anthropic retain their existing models, authentication, workspace headers, client files and prompts. The public health and error schemas retain their existing shapes. The existing provider usage schema accepts Novita. No migrations or corpus updates were needed.

## Endpoint, controls and pricing

- The client uses the existing `httpx.AsyncClient` dependency and sends `POST https://api.novita.ai/openai/v1/chat/completions` with Bearer authentication and model `qwen/qwen3.8-flash`. The key comes from backend-only `NOVITA_API_KEY`. [Novita model](https://novita.ai/models/model-detail/qwen-qwen3.8-flash) · [Chat Completions API](https://docs.novita.ai/api-reference/model-apis-llm-create-chat-completion)
- The defaults are 1,200 output tokens per completion, 25 seconds per completion including retries, eight concurrent calls per worker and 10 requests per client per existing rate-limit window. One retry is allowed for a provider throttle or transient service error when the wait fits the retry policy and deadline. Authentication, billing and ambiguous transport failures fail immediately. The limits are configurable via `NOVITA_*` variables. [Novita error codes](https://docs.novita.ai/api-reference/basic-error-code)
- `NOVITA_ENABLE_THINKING=false` uses the model's documented non-thinking mode. The client requests separate reasoning and returns only the visible assistant answer. It rejects truncated or mismatched-model completions. Thinking-mode quality and savings require live comparison. [Thinking controls and response format](https://docs.novita.ai/api-reference/model-apis-llm-create-chat-completion)
- The list rates checked on 2026-11-21 are USD per million tokens. Fresh input is $0.15, cache-read input is $0.016, five-minute cache-write input is $0.20 and output is $0.47. All rates and the pricing version are configurable. Cache counters are subsets of reported input. Reported reasoning is a subset of completion tokens. The admin report calculates costs from those buckets and labels estimates separately from provider usage. An invoice is required to confirm realized spending. [Model-specific pricing](https://novita.ai/models/model-detail/qwen-qwen3.8-flash) · [Prompt usage metadata](https://docs.novita.ai/guides/llm-prompt-cache)

## RAG, privacy and cache

Novita uses the same approved LanceDB index, lexical ranking, optional context optimization, conversation budgets, general-definition rules, supplemental evidence, citation validation and safe fallback. The tests exercise an approved passage, a reviewed current supplemental passage, expiry, genuine source references and citation presentation. Reviewed FAQ hits are validated before invoking any provider. The Novita cache test saw one call avoided, a sourced cache reply with no model attribution and misses on wrong-language, contextual and revoked entries. The cloud deployment has the shared conversational and verified supplemental paths enabled. The existing reviewed FAQ cache and optional context optimization remain at their current production defaults. The repository has no semantic response cache.

The API rejects arbitrary provider and model values. It has no caller-selectable provider URL. Upstream error details, credentials, prompts and reasoning are excluded from integration diagnostics. Existing auth, feedback and conversation isolation run through their original API paths.

## Verification

### Automated and browser checks

- Backend regression and security suite: **570 passed**, 15 legacy live cases deselected. This includes 32 additional Novita tests. Ruff, frontend lint, TypeScript, Next.js production build and the Railway Dockerfile build passed.
- The Novita mock corpus exercised 30 English, 30 Devanagari Hindi and 10 Hinglish questions. Every case matched the baseline Sarvam prompt, approved evidence and routing for the corresponding variant. Additional mocked answers passed language and content assertions for English (2/2), Hindi (2/2) and Hinglish (1/1). The English complete-airport-list request sent all 24 documented entries to the model. These checks measure integration and validation with controlled completions.
- This parity test also exposed inherited retrieval limitations. An alternate Devanagari wording for the complete airport list did not receive the complete list, and some phrasing of the live-gate question in Hindi went through RAG instead of the early live-status response. Both providers took the same paths. The integration retains the existing retrieval rules and factual constraints. The approved sources still lack a public service-fee statement for the tested pricing question.
- Chrome verified exactly three options, immediate switching, Novita selection restoration, full selected-label width and no horizontal overflow at 1280, 390 and 320 px on the deployed site.
- Synthetic usage with 100 input tokens (80 read from cache, 10 written) and 20 completion tokens (including four reasoning tokens) costs **$0.00001418** at the documented rates. The measured test counters were recorded in the isolated database. No credential or private question content is needed to calculate the total.

### Production rollout

Implementation commit: `c6478076f30d8d905e496a3e07635cdd71b60845` on `origin/main`.

- Railway deployment `c28eddf9-6889-46bf-bac8-a30b2b3df253` succeeded. The running provider, registry and accounting modules matched the committed source hashes. The public API health check passed, unauthenticated admin analytics returned 401 and the production API schema returned 404. The PostgreSQL-backed admin report returned the Novita provider and model. [Railway backend health](https://backend-production-ab8a175f.up.railway.app/api/v1/health)
- Vercel built deployment `dpl_5CEWRe7UKmbSxtMM65hMWHZXfCCc` from the same integration and promoted it to the production alias. [Production chatbot](https://digiyatra-chatbot-poc.vercel.app)

### Live result matrix

| Provider | English | Hindi | API working | Existing functionality |
|---|---|---|---|---|
| Sarvam 105B | PASS 1/1, 2.48 s | PASS 1/1, 2.71 s | PASS | Existing integration retained |
| Anthropic Haiku 5.5 | PASS 1/1, 1.60 s | PASS 1/1, 2.57 s | PASS | Existing integration retained |
| Novita Qwen3.8 Flash | BLOCKED 0/1 | BLOCKED 0/1 | BLOCKED, upstream HTTP 401 | New option and localized error path verified |

The successful browser cases used signed synthetic requests and checked the exact provider and model, response language, limited international trial conditions and verified PIB source. They did not write production analytics. The first Hindi Anthropic response rendered the airline names in Devanagari. The test matcher was corrected to accept either script and the case then passed. Timings are single browser samples.

Novita rejected the configured Railway credential on direct and Railway-hosted probes. Post-deployment selection reached the Novita client in both languages. Railway recorded upstream authentication failure (401), and Vercel rendered the existing provider service error (503) in English and Hindi. The deployed page and its 13 linked JavaScript assets passed a scan for the configured credential values.

There were zero successful billable Novita generations observed and no usage metadata returned. Actual Novita spend, generation latency, accuracy, live Hinglish behavior, prompt-cache use and the thinking-mode comparison remain unverified. The 0.50 s English and 0.78 s Hindi browser timings are failed-request latencies. The reviewed FAQ call avoided was measured in the isolated test. The production FAQ cache was left at its existing disabled default.

To resume the controlled checks after a valid credential is available, run the following from `backend/` with secrets injected through the secure backend operator environment. Use the first command for the isolated provider and thinking-mode checks. The second also verifies signed production chat requests without analytics writes and requires the existing server-side evaluation credential.

```sh
.venv/bin/python -m evaluation.novita_smoke --cap-usd 0.001
.venv/bin/python -m evaluation.novita_smoke --cap-usd 0.60 --url https://digiyatra-chatbot-poc.vercel.app
```
