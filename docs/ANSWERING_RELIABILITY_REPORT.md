# Answering reliability release — 19 November 2026

Application: https://digiyatra-chatbot-poc.vercel.app  
Backend: https://backend-production-ab8a175f.up.railway.app  
Source implementation: `2571c5b`  
Railway deployment: `672b8b54-3855-4cf7-8698-59d6d85fb2ce`

## Root causes confirmed

1. `restricted_request` rejected supported-airport questions before retrieval, treating a documented catalog as a request for live operations. The shared system prompt also prohibited “current airport lists.” Live gate-operation detection is a separate input guard and remains active.
2. Organizational questions lacked intent expansion and evidence-based promotion. The baseline government-app question retrieved registration/privacy passages rather than the operator/framework sources; English returned unrelated ID/privacy material and Hindi lost all grounded sentences.
3. Approved FAQs are split into multiple indexed fragments. Source caps and ranking favored short count/link paragraphs over the 24 airport names. Retention questions similarly missed the paragraph specifying the airport retention period. This was an assembly/ranking problem, not an approval failure.
4. There was no targeted second retrieval before model-insufficiency or post-validation fallbacks. Hindi organizational paraphrases also lacked several concept equivalents in lexical claim validation.
5. The retrieval threshold was already 0.15; lowering it globally would not fix the routing or missing-fragment problems. Grounding support thresholds remain 0.40 (cited) and 0.50 (reattribution).

## Changes

- Added organization, supported-airport catalog, planned-airport and airport-retention intent signals, with English/Hindi/Hinglish normalization. Promotion requires anchors in approved text rather than filenames.
- Reassemble all approved fragments of the same source, section and FAQ question before source caps/context budgeting. Preserve exact bodies, constituent chunk IDs, dates, verification flags, conflicts and URLs. Different FAQs, especially planned versus supported airports, are never merged.
- Keep TF-IDF/LanceDB plus BM25 retrieval. Preserve approval filtering, thresholds, bounded context/history, provider allowlists and no paid-provider failover.
- Try one alternate lexical/FAQ retrieval before an insufficient-evidence fallback. A second paid generation is allowed only when the selected evidence changes. Interaction analytics are recorded once, with genuine provider calls accounted separately.
- Shared prompts permit documented snapshots and retention guidance while prohibiting invented live status. Answers retain substantive claim citations; server-generated date qualifications use actual metadata and never invent a date. Official verification links come from retrieved source metadata.
- Preserve valid paraphrases through bounded Hindi equivalents. Add evidence-derived airport code/name validation to reject fabricated entries despite shared words such as “International Airport.” Numbers, policy polarity, prerequisites, draft exclusion and unsupported-claim removal remain enforced.
- Diagnostic events contain provider, language, intent, selected chunk IDs/scores, retry decisions and fallback reason codes. They do not contain question/answer text, passenger identifiers or credentials under default logging settings.

## Files changed

| Files | Purpose |
| --- | --- |
| `backend/app/rag/query.py`, `multilingual.py`, `retriever.py` | Intent/concept normalization, evidence ranking, full approved FAQ assembly and retry retrieval. |
| `backend/app/services/answering.py`, `prompts.py`, `chat_service.py` | Answer boundaries, snapshot-aware shared prompts, metadata qualification, diagnostic reasons and bounded recovery. |
| `backend/app/security/grounding.py` | Evidence-derived airport identity validation while preserving existing claim thresholds. |
| `backend/app/security/evaluation.py`, `backend/app/api/routes/chat.py`, `backend/app/main.py` | Signed no-write public deployment evaluation with isolated bounded memory and normal rate/guardrail enforcement. |
| `backend/evaluation/bilingual.py`, `reliability_questions.json` | Reusable 39-case evaluation, provider selection and explicit snapshot/list checks. |
| `backend/tests/unit/test_answering_reliability.py`, `test_api.py`, `test_conversational_answers.py`, `backend/tests/live/test_sarvam_live.py` | Both-provider, retrieval, citation, isolation, retry, airport-snapshot and existing-safety regressions. |
| `docs/ANSWERING_RELIABILITY_REPORT.md`, `PRODUCTION_DEPLOYMENT_REPORT.md` | Release findings and actual verification status. |

## Before and after

These are observations from real Sarvam calls using the previous release and the candidate, not mocked quality results.

| Question | Previous release | Updated behavior |
| --- | --- | --- |
| Is Digi Yatra a government application? | Unrelated references to future government ID options and third-party privacy. | Identifies the Foundation as the Section 8 not-for-profit operator and distinguishes it from the MoCA policy/framework, with organizational citations. |
| Same question in Hindi | Insufficient approved evidence fallback. | Hindi explanation of the Foundation/operator and government framework, with citations. |
| Which airports support Digi Yatra? | Immediate live-verification refusal; no retrieval/model call. | All 24 documented airport names/codes with citations, an undated-snapshot qualification and the official airport-list link. |
| How long does the airport retain my data? | Device storage and unrelated support-correspondence retention, without the requested airport timeframe. | Documented airport biometric/travel retention within 24 hours after the stated flight departure event, distinguishing airport scope from phone-wallet data. Snapshot qualification does not certify deletion of an individual's records. |
| Are Digi Yatra gates at Delhi working right now? | Live-status fallback. | Live-status fallback retained; no invented operation status. |

The corpus remains private and unchanged (119 approved chunks, 26 documents). The full private airport list and raw benchmark answers are intentionally excluded from this public report.

## Verification

- Backend: **368 passed**, 15 live tests deselected in the offline suite. This includes 39 shared cases exercised through each provider's mocked transport, new retrieval/grounding regressions, authenticated synthetic-evaluation tests, recovery/retry tests, and existing admin/authentication/CSRF/analytics/PII/rate-limit/injection tests.
- Frontend: type check, ESLint and Next.js production build passed. No frontend code changes or Vercel redeployment required.
- Local real Sarvam evaluation: **39/39** cases passed automated checks for answer mode, selected language, required concepts, citations, relevant sources, procedure formatting and full snapshot entries where applicable. Both English and Hindi and mixed-language follow-ups are included. These finite checks do not prove universal factual accuracy; examples were also reviewed.
- Real Anthropic requests returned a quota/insufficient-credit error (upstream HTTP 400, public safe HTTP 503). Provider transport and shared answering/security rules pass offline tests. Live Anthropic answer quality cannot be certified until the account has credits. No provider switch, secret change or billing change was performed.

- Deployed Railway runtime: **39/39 Sarvam cases passed** the same checks. SHA-256 checks matched all **47 deployed application Python modules** to the implementation source. Tests used a temporary synthetic DB; synthetic resolution feedback returned **204**. The primary migration revision was read-only verified as `0002_ai_usage`.
- Actual public website: **28/28 Chrome checks passed**, using fresh browser context and real HTTP requests through the production Vercel proxy (no mocked/intercepted responses). Government-app questions succeeded in English and Hindi; airport-list questions succeeded in English and Hinglish-to-Hindi, each with all 24 exact code/name entries, real source metadata, undated qualification and official airport-list link. The live Delhi-gate question returned `live_status` with no fabricated citations. The homepage returned HTTP 200 without an authentication challenge. `/admin/login` displayed the existing form; anonymous dashboard access redirected to login; `/api/v1/admin/session` and `/api/v1/admin/analytics` returned 401.
- Anthropic also returned safe HTTP 503 through the public browser. Its selector remained Anthropic, confirming no silent paid-provider failover. This is a provider account limitation, not a verified successful answer.
- Railway reports deployment `672b8b54-3855-4cf7-8698-59d6d85fb2ce` **SUCCESS**. The implementation commit was pushed to the existing **PUBLIC** GitHub repository. The source audit scanned 193 candidate files with no forbidden payload paths or production-secret matches. Private benchmark responses, databases, screenshots, corpus and deployment staging remain ignored locally.

A live English response explained that Digi Yatra is operated by the Digi Yatra Foundation, a not-for-profit company incorporated under Section 8 of the Companies Act 2013, operating under the Ministry of Civil Aviation policy framework rather than as a government department. The actual Hindi answer likewise distinguished the Foundation from the government framework. These are model-generated answers grounded in the approved sources, not hardcoded response templates.

## Analytics isolation and scope

Local/runtime benchmarks use temporary synthetic SQLite databases, never production PostgreSQL. Public-browser evaluation requests traverse the real Vercel proxy and Railway route. An operator-only HMAC bound to the exact request body with a 60-second validity enables a separate bounded in-memory conversation store and disables analytics/usage persistence for that request only. It uses the existing server-only proxy secret with a distinct HMAC purpose; no secret is sent to page JavaScript. Public rate limits, provider limits, all validation and guardrails still apply. An unsigned `eval-` conversation name has no special privileges. Invalid signatures are rejected. Synthetic responses cannot submit feedback against production messages.

Normal visitors continue to produce existing privacy-safe analytics. No production rows, credentials, billing settings, database schema or knowledge content were changed. Existing startup migration/index checks were retained; no new migration was added. No authenticated production admin session was created for testing; unchanged auth/CSRF behavior was exercised in isolated tests and anonymous protection was checked live.

## Remaining limitations

- Stored airport and policy documents have no verified snapshot date. Responses explicitly identify them as undated and link to official verification where available; they are not live operational guarantees.
- Citation grounding remains a conservative lexical/concept heuristic, not a formal entailment proof. New regressions cover paraphrases and common numerical/policy/catalog fabrications without relaxing thresholds.
- International-trial availability, personal records, missing eligibility rules and unsupported device/payment features remain restricted.
- Anthropic live verification requires resolving the provider credit balance outside this deployment task.
- Railway's existing CLI warns that legacy `railway.toml` support ends 1 December 2026. Infrastructure/config migration is outside this answering-only release; the present deployment uses the existing Docker/startup configuration.
