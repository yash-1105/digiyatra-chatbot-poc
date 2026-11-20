# Digi Yatra bilingual provider reliability

## Reproduction and diagnosis

The baseline was production code at `b18c533`. The deployed approved index had 119 chunks across 26 documents. The local baseline used the same snapshot, lexical index path, request options and both actual provider APIs. Signed synthetic requests exercised the Vercel proxy and Railway app while bypassing analytics writes. A first batch hit the normal shared rate limit. A paced Hindi replay supplied the missing baseline cells. That initial 429 batch is excluded from answer-quality results.

The route accepted both locale and provider from the frontend. Providers received equivalent approved evidence after intent selection. The exact reviewed FAQ was off with an empty production table. Semantic caching and compression had no runtime implementation. The candidate context optimizer was off. No stale reply or suppressed provider error explained the reported knowledge-gap messages.

| Screenshot case | Baseline behavior and cause | Candidate answer, summarized |
| --- | --- | --- |
| 1. Download charge | Android and iOS store evidence was present. Some replies gave stores or stopped at insufficient evidence because approved material did not establish the price. | Names the two supported store options with a citation and distinguishes the unverified download price from other travel costs. |
| 2. Service charge | Generic fallback. No approved fee statement was found. Marketing wording such as hassle-free is irrelevant to fees. | Explicitly says the approved sources do not specify a service fee. This recognized content gap requires no provider call. |
| 3. International flights | The international keyword guard exited before retrieval and suppressed approved domestic-scope evidence. | Gives the documented domestic-flight scope from supported departure airports, cites it and qualifies its freshness. |
| 4. Facial verification | English facial verification and Hindi face-verification variants missed the existing selfie intent. Models declined or their generated sentences lacked sufficient citation support. | Gives cited app selfie capture advice and distinguishes the documented manual airport process under the system-down condition. |
| 5. Internet connection | Weak lexical coverage retrieved a login error or other nearby topics. Some Sarvam replies gave a partial answer. Approved sources do not specify per-stage connectivity requirements. | Describes the documented registration, boarding-pass and airport stages. It explicitly identifies the remaining internet requirement gap. |
| 6. DigiLocker comparison | Some questions retrieved registration snippets but did not retrieve complementary airport evidence. Combined comparisons sometimes failed grounding. | Gives separately cited statements for Digi Yatra's airport role and using DigiLocker to link Aadhaar during registration. |
| 7. International ePassport | The broad pre-retrieval guard blocked the approved roadmap evidence. | Distinguishes the documented domestic scope from proposed ePassport support, cites the roadmap and explains that live availability is unverified. |
| 8. Repeated international flight question | The same guard returned the same uncited fallback after paraphrasing. | Repeats the cited domestic scope with the same freshness boundary across both languages and providers. |

The corpus includes relevant registration, end-to-end travel, general eligibility and troubleshooting passages. The retrieval logic selects by facts in the approved passage body. An FAQ question premise cannot establish a claim. Draft and excluded records remain outside the index. The term “international” in an airport name does not establish international-flight eligibility.

Local traces distinguished model-declared insufficient evidence, missing valid citations and sentence grounding rejection. One earlier Anthropic Hindi offline replay returned HTTP 200 from Anthropic with `stop_reason=max_tokens`, only a thinking block and all 900 output tokens reported as thinking. The app correctly treated this as an upstream failure. The provider now receives explicit thinking-disabled requests for this tool-free, grounded application. Model, effort and output budget are preserved. The client distinguishes workspace selection, model access, quota, authentication, rate and timeout failures, without surfacing vendor text or switching providers. Sarvam keeps its existing model and reasoning settings. [Haiku 5.5 thinking behavior](https://platform.claude.com/docs/en/build-with-claude/thinking)

## Fix and safeguards

- `app/rag/{multilingual,query,retriever}.py` adds Hindi and Hinglish aliases, source-body matching for the new query scopes, and preserves intent during retrieval retry. Whole approved passages and the configured global ranking thresholds remain in use.
- `app/services/{answering,chat_service,localization,prompts}.py` limits pre-retrieval restrictions to genuinely restricted requests, separates sourced facts from gaps, and permits one bounded reattempt when a scoped reply omitted grounded information.
- `app/security/grounding.py` rejects unsupported pricing, offline and current international claims and handles orphan citation markers. The numeric and lexical grounding thresholds are unchanged.
- `app/clients/{anthropic,base}.py` and `app/services/usage.py` handle the provider failure classes and reported thinking tokens. The new stable prompt changes the effective FAQ knowledge version, so any previously signed reply would require revalidation.
- `evaluation/bilingual_reliability.py` and its case JSON check provider and locale, substantive claims, named gaps, citation mapping and freshness. Regression tests exercise both context selectors, draft and passenger-specific guards, multilingual aliases and provider error handling. The broad replay set contains over 80 distinct questions.
- The public API and frontend selector require no contract change. The existing request body carries the selected locale and provider and the response confirms them.

## Measured results before deployment

The content grader checks for specific answer facts rather than HTTP success or a site link. A documented information gap passes only if it names the missing claim and any available partial guidance meets its own evidence checks. The full camera/gate, travel-scope, pricing, DigiLocker and connectivity cases ran in natural Hindi and English. Each configuration ran twice across a continuing conversation, with Anthropic native cache off in the first local round and on in the second. The temporary local database and private capped transport captured reported tokens. The reviewed exact cache cannot match the screenshot questions. Existing synthetic hit tests verify scope, expiry, source integrity and revocation.

| Provider | English, local real API | Hindi, local real API |
| --- | --- | --- |
| Sarvam | PASS 16/16 | PASS 16/16 |
| Anthropic | PASS 16/16 | PASS 16/16 |

All 56 locally supported replies passed citation and content checks. Eight service-cost requests gave the specific evidence gap. In the matched local baseline, the generic or blanket refusal rate among the 56 requests with useful approved material was 50/56. The candidate was 0/56. The production baseline recorded 22/28 such refusals across its four lanes. Strict baseline content checks also rejected the partial replies when they omitted required facts or caveats. These are fixture results, with human inspection of representative failures and responses.

| Lane | Provider-reported input baseline → candidate | Provider-reported output baseline → candidate | Local P50 baseline → candidate | Local P95 baseline → candidate |
| --- | ---: | ---: | ---: | ---: |
| Sarvam English | 14,932 → 19,362 | 764 → 1,479 | 0.611 → 0.753 s | 1.324 → 1.680 s |
| Sarvam Hindi | 20,354 → 18,554 | 931 → 1,615 | 0.556 → 0.724 s | 1.689 → 1.278 s |
| Anthropic English | 23,921 → 30,213 | 833 → 2,514 | 1.266 → 1.706 s | 2.723 → 2.058 s |
| Anthropic Hindi | 26,915 → 32,074 | 266 → 5,038 | 1.258 → 2.334 s | 2.358 → 3.378 s |

The candidate performs inference for supported requests previously blocked before retrieval, so aggregate usage increased across this targeted matrix. The local candidate made 14 successful provider calls per lane. Service-fee evidence gaps invoke no provider. Provider failures, cache read/write differences and cold/warm runs influence comparisons. Production synthetic replay skips analytics, so its per-call token usage is not included in the deployment results.

## Reproducing the live matrix

From the backend directory with an authorized evaluation secret supplied privately through the process environment:

```sh
PYTHONPATH=. .venv/bin/python -m evaluation.bilingual_reliability \
  --url https://digiyatra-chatbot-poc.vercel.app --rounds 2 --inr 100 --usd 2.4
```

The harness reserves a conservative retry-inclusive list-price ceiling and paces the shared rate-limit bucket. It publishes only grades and timing. The existing signed synthetic route keeps test activity out of user analytics. Response examples in this report are summaries. The private source text and raw test replies stay outside GitHub.

## Knowledge gaps

The approved corpus lacks explicit store-download pricing, a Digi Yatra service-fee statement, and a per-stage offline capability matrix. The approved corpus establishes DigiLocker's enrollment relationship. Independent DigiLocker policies are outside that evidence. The public DigiLocker site describes its broader document-wallet purpose and can be reviewed as a separate source. The undated roadmap establishes a proposal only. Current international or ePassport availability requires an updated approved source. [Official DigiLocker overview](https://www.digilocker.gov.in/web/ecosystem)
