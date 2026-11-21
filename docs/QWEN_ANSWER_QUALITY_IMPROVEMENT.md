# Qwen3.8 Flash answer quality

## Baseline and scope

The November 21 credential review passed 40 of 49 answers. The replay used the same 22 English, 22 Hindi and five Hinglish questions, including the original follow-up and language selections. The baseline audit used only synthetic conversations. Its output stays out of the public repository. The checked-in question catalogue and nine regression assertions are in `backend/evaluation/qwen_quality_cases.json` and `backend/evaluation/qwen_quality.py`.

The Novita client still sends `qwen/qwen3.8-flash` with thinking disabled. Provider settings, shared system prompt text, frontend and API schema are untouched. Qwen adds short instructions on scoped questions. The dated airport evidence is shared across providers.

## Evidence and root causes

The Ministry of Civil Aviation reported Digi Yatra journeys across **39 domestic airports** in its November 1, 2026 announcement. An August parliamentary answer also reports coverage of 39 airports. Neither gives a complete current list of names. The historical 24 names are corroborated by an older Ministry release. The app preserves its original approved evidence and serves the newer count from separately reviewed supplemental revision 3. It labels the older list as historical and makes no claim about live gates. [November PIB release](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2331200&lang=1&reg=1) · [August Lok Sabha statement](https://sansad.in/getFile/lsapps/loksabhaquestions/annex/188/AS273_Y4e9cy.pdf) · [Historical PIB list](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2089984&lang=2&reg=3)

The published revision records the source URL, November 1 publication and applicability date, verified count, evidence block, source conflict and review status. Current airport questions and historical list requests take separate paths. The new airport intent bypasses dependent FAQ reuse when supplemental knowledge is enabled. Answer rules revision 2 changes the effective FAQ knowledge version, invalidating existing version-1 signatures for serving. The prior 24 names remain available as an archived list. The seven-airport international trial, its dates, eligible Indian e-passport holders, selected airlines and normal passport and immigration checks remain separate.

The table paraphrases the observed answers and identifies the failed factual assertions. The exact answer and retrieval traces were inspected in the private replay.

| Original case | Failure and evidence | Updated behavior |
|---|---|---|
| English basics | The answer repeated a promotional mission and omitted biometric passenger verification. `about_us.md` and an airport catalogue outranked the approved definition in `general_01_introduction.md`. | Gives the travel purpose and facial identity check with the approved definition and airport process evidence. |
| Hindi basics | The same poorly ranked context produced a generic refusal. The locally reproduced top passages were the mission, upcoming airports and the old list. | Gives a Devanagari introduction using those same approved definition and airport process sources. |
| English airport coverage | An undated `available_airports.md` list was presented as current despite the caveat appended by the application. | Gives the dated 39-airport count and explains that the official announcement supplies no complete list. |
| Hindi airport coverage | The same stale source and prompt precedence produced a current-sounding 24-airport list. | Gives the same dated count in Hindi and distinguishes the historical directory. |
| English children | The top context included the exception and infant guidance, with the under-18 registration passage displaced by other candidates. The answer started with caveats and omitted guardian eligibility and consent. | Prioritizes the approved dependent registration, guardian consent and under-five guidance. Any omitted qualification is included only when its approved passage supplies the required evidence. |
| Hindi children | The context had relevant child sources, but the answer omitted under-five biometric guidance and the general dependent age rule. | Separately presents dependent registration, guardian consent, Aadhaar verification, the under-five recommendation and the manual alternative when applicable. |
| English offline | The underlying evidence describes registration, sharing and gate verification, with no network rule. The original model returned a decline twice and a replay omitted registration. | Describes the supported travel stages and says which offline capabilities remain unverified. It does not infer connectivity from an OTP or a gate scan. |
| English airport data retention | The approved airport and privacy passages say within 24 hours, but Qwen described an exact duration. The grounding matcher verified the number without rejecting the duration wording. | States the deadline relative to the scheduled departure and distinguishes airport-held data from device storage. If Qwen omits the deadline or its starting event, the application uses the approved scheduled-departure passage to state the policy precisely. |
| Hindi e-passport definition | The closed definition matcher accepted “क्या है” but missed “क्या होता है”; lexical retrieval substituted nearby travel policy for a stable definition. | Recognizes the definitional form. If Qwen omits the chip or identity check, a corroborated general definition supplies them without a Digi Yatra eligibility claim. |

The airport retention guidance is corroborated by the August Lok Sabha statement. The general e-passport fallback is corroborated by the Ministry of External Affairs parliamentary reply. [Ministry of External Affairs e-passport description](https://sansad.in/getFile/loksabhaquestions/annex/179/AU2282.pdf?source=pqals) The replay did not indicate context-budget rejection or a stale exact-match hit. The active production FAQ cache is disabled. The approved context cap, output cap and retry ceilings are unchanged. The introduction and children scopes use in-memory approved passage selection. This keeps the safety-critical child passages in the ordinary context rather than expanding the token budget.

## Verification

| Language | Before | After |
|---|---:|---:|
| English | 17/22 | 22/22 |
| Hindi | 18/22 | 22/22 |
| Hinglish | 5/5 | 4/5 |
| **Total** | **40/49 (81.6%)** | **48/49 (98.0%)** |

- The final cache-bypassed run scored 48/49. The initial production run on the normal path scored 47/49. The two misses there were Hindi retention and the Hindi e-passport definition, which prompted the final release. The final normal-path result above ran all 49 cases against the deployed Railway chat service and its live provider, approved index and supplemental database.
- All nine original failures passed a separate signed HTTP replay through the public Vercel site. Forty-three of the 49 final answers included sources. Every returned source was in the approved index or verified supplemental registry, and every inline marker resolved. The two fee cases gave specific evidence limitations and were graded as appropriate uncertainty. The complete current airport names and per-stage offline guarantees remain unverified.
- The final Hinglish registration answer included mobile OTP and the identity-linking step but omitted the selfie verification step. The cache-bypassed sample instead had an incomplete Hinglish boarding-pass answer that omitted consent. These are remaining completeness risks across repeated generations.
- The backend suite passed 616 offline tests, with 15 legacy live tests deselected. The 46 Qwen-specific tests include bilingual phrasing, child versus adult scope, stale versus current airports, the complete historical list, invalid or revoked coverage evidence, retention, trial scope, live gate status and definition boundaries. Ruff and the backend container build passed.
- English and Hindi regression smoke tests each passed on Sarvam and Anthropic through the public production app (2/2 per provider). Their model configurations and shared prompt file are unchanged. The existing authenticated admin route returned 401 without credentials.

| Metric, 49 cases | Before | After |
|---|---:|---:|
| Novita completions | 50 | 45 |
| Provider-reported input tokens | 56,684 | 49,821 |
| Provider-reported output tokens | 5,782 | 4,690 |
| Total tokens per question | 1,275 | 1,112 |
| Provider prompt-cache read tokens | 2,048 | 0 |
| Reviewed FAQ hits | 0 | 0 |
| Estimated cost at versioned list prices | $0.010946 | $0.009677 |
| Estimated cost per question | $0.000223 | $0.000197 |
| Chat P50 / P95 | 2.61 / 6.29 s | 2.49 / 3.90 s |

The final matrix ran below its $0.30 cap, with 45 successful provider completions and no upstream errors. Costs use returned tokens rather than invoice data. Latency measures end-to-end chat service time inside Railway and excludes the public HTTP replay. Signed replay and other provider checks ran separately under bounded caps. Thinking remained disabled. A thinking experiment was unnecessary because the production sample met the acceptance target. Reviewed FAQ caching remains disabled in production. The existing eligibility and signature tests ran with the new answer-rules version.

The backend-only release at commit `3e80a4c` reached Railway deployment `816550b3-bc8b-484e-9ba0-3e0ff63cc50d`. The running prompt, chat and source-registry modules matched the committed checksums. The airport source remained published at revision 3 and the reviewed international trial remained available. No frontend release, database reset, credential change or billing change was required. [Production chatbot](https://digiyatra-chatbot-poc.vercel.app)

## Release files

- `backend/app/services/knowledge.py` and `backend/app/services/faq.py` register the independently verified airport count and advance the answer rules revision.
- `backend/app/rag/retriever.py`, `backend/app/services/answering.py` and `backend/app/services/chat_service.py` select scoped approved evidence and apply the Qwen-only guidance and response checks.
- `backend/tests/unit/test_qwen_quality.py` adds localized, historical, freshness, approval and policy-boundary cases. `backend/tests/unit/test_novita.py` keeps prompt parity assertions for cases outside the scoped changes.
- `backend/evaluation/qwen_quality_cases.json` and `backend/evaluation/qwen_quality.py` retain the exact evaluation questions and grade the nine original regressions.
