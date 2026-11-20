# Digi Yatra token optimization benchmarks

## Method

Measured on 2026-11-20 against baseline Git commit `e4529f3` and the same 119-chunk approved deployment snapshot. The replay uses 122 distinct synthetic question/locale pairs per provider (97 English, 25 Hindi), combining the three checked-in evaluation sets and added contrastive cases. The set covers follow-ups, Hindi and Hinglish, registration, upload, DigiLocker, eligibility, privacy, airport operations versus documented snapshots, excluded material and injection. Existing expectations are exercised where available. The added contrastive cases supplement the security and retrieval tests. They are not individually human-graded answers.

Live evaluation used the application's selected-provider client with a disposable database and no production analytics writes. The harness reserves cost for every upstream HTTP attempt, including provider retries, using the request size and full output allowance at conservative rates. It requires an explicit cap. The full branches each reserved at most ₹130 or $7. Run costs below are reconstructed from reported tokens at list rates. Provider invoices, taxes, credit effects and unreported failed-attempt usage are unavailable. Small provider scheduling and experiment-concurrency effects can influence latency.

```sh
cd backend
PYTHONPATH=. .venv/bin/python evaluation/token_optimization.py --provider sarvam
PYTHONPATH=. .venv/bin/python evaluation/token_optimization.py --provider sarvam --optimized
PYTHONPATH=. .venv/bin/python evaluation/token_optimization.py --provider sarvam --live --optimized --cap 130
PYTHONPATH=. .venv/bin/python evaluation/token_optimization.py --provider anthropic --live --optimized --no-prompt-cache --cap 7
```

Run the same harness from a private baseline checkout with its approved corpus, flag defaults and explicit cap for release comparisons. Credentials come through the private process environment. Use `--only` with fixture IDs for a small paired sample. `--faq-bundle` publishes a privately supplied reviewed fixture only in the disposable database. Output contains aggregate metrics and failing fixture identifiers, no prompts or answers.

Pricing snapshot `2026-11-20-list` uses Sarvam ₹10 / ₹0.25 / ₹25 per million fresh input, cached input and output tokens. Anthropic short-context rates are $0.10 input, $0.50 output, $0.125 five-minute write, $0.20 one-hour write and $0.01 cache reads. Admin usage distinguishes provider-reported counts from byte-based input/retrieval estimates, versions the rates and retains the earlier USD estimate for UI compatibility. Reprice comparisons on one rate card. [Sarvam pricing](https://docs.sarvam.ai/api/getting-started/pricing) · [Haiku 5.5 pricing](https://platform.claude.com/docs/en/models/haiku-5-5/overview)

## A and B full-suite live comparison

A is the existing deployment code, including its generated exact cache and native Anthropic prompt caching. B activates whole-passage context selection and compact prompts with response cache off. Anthropic native caching is off in B to expose undiscounted prompt usage. A and B raw token counts can be compared directly with the call-count and cache caveats below. Their Anthropic price difference also includes removal of the existing cache discount. D isolates that billing effect on the baseline RAG path.

| Variant | Provider · locale | Successful model calls | Reported input / output | Retrieval estimate | Cached read / write | Priced total / 100 questions | P50 / P95 (ms) | Terminal provider errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | Sarvam · en | 83 | 87,609 / 9,288 | 40,157 | 57,248 / 0 | ₹0.550122 / ₹0.567136 | 656 / 2,950 | 1 |
| B | Sarvam · en | 82 | 83,426 / 9,487 | 43,681 | 53,248 / 0 | ₹0.552267 / ₹0.569347 | 637 / 2,585 | 3 |
| A | Sarvam · hi | 20 | 20,727 / 2,521 | 8,962 | 11,136 / 0 | ₹0.161719 / ₹0.646876 | 650 / 1,363 | 0 |
| B | Sarvam · hi | 21 | 22,196 / 2,418 | 10,010 | 11,680 / 0 | ₹0.168530 / ₹0.674120 | 775 / 1,181 | 0 |
| A | Anthropic · en | 87 | 145,260 / 17,103 | 43,943 | 78,400 / 980 | $0.016046 / $0.016542 | 1,626 / 3,656 | 0 |
| B | Anthropic · en | 87 | 143,658 / 25,401 | 50,472 | 0 / 0 | $0.027066 / $0.027903 | 1,720 / 4,879 | 0 |
| A | Anthropic · hi | 21 | 36,729 / 8,169 | 9,777 | 17,802 / 989 | $0.006180 / $0.024720 | 1,999 / 3,598 | 0 |
| B | Anthropic · hi | 21 | 35,980 / 8,182 | 10,010 | 0 / 0 | $0.007689 / $0.030756 | 2,030 / 3,763 | 0 |

Cost per submitted question is the cost per 100 divided by 100. The denominator includes deterministic responses, errors and exact hits. Latency is end-to-end within the local chat service replay. Retrieval estimates count rendered evidence across prepared calls. Input includes cached tokens exactly once. Sarvam reasoning was off, and captured matches with explicit reasoning accounting reported zero. Anthropic gave no separate reasoning count. Sarvam terminal errors were rate limits. Older transport retries may incur costs without usage counters.

| Provider · locale | Expected concepts A → B | Knowledge mode / citation checks A → B | Expected source checks A → B |
| --- | --- | --- | --- |
| Sarvam · en | 54/54 → 51/53 | 53/54 → 52/53 | 54/54 → 53/53 |
| Sarvam · hi | 21/21 → 21/21 | 21/21 → 21/21 | 21/21 → 21/21 |
| Anthropic · en | 54/55 → 54/55 | 54/55 → 54/55 | 55/55 → 55/55 |
| Anthropic · hi | 21/21 → 21/21 | 21/21 → 21/21 | 21/21 → 21/21 |

Citation checks measure returned cited responses for the fixture, and the backend grounding suite validates the sentence-to-evidence mapping. Explicit complete supported-airport lists passed the 24-item response checks in both languages in the matched samples. A and B each failed one broader current-airports expectation. B also had English concept misses and higher reported output across the Anthropic English run. Earlier Anthropic B samples missed one Hindi language check. Both providers were live-tested, and scoped-key access worked during this replay. Production history included Anthropic availability errors, and mocked quota, restricted access and workspace-header tests cover those cases.

Sarvam B used 4,183 fewer measured English input tokens and 1,469 more Hindi input tokens. Its repriced spend rose ₹0.008956 across the two groups, with different success and retry counts. Anthropic B used 2,351 fewer input tokens across both languages and 8,311 more output tokens. Even at uncached list rates for both sets of observed usage, Anthropic B's modeled cost was higher. Full A returned two generated exact hits per provider among 122 cases. A read-only seven-day production aggregate saw no generated exact hits, 17 successful Sarvam calls, and 3 successful plus 6 failed Anthropic calls. It did not identify repeated passenger queries. The candidate remains off for both providers.

## C. Reviewed FAQ incremental result

One locally reviewed synthetic fixture was tested through the cache with production-shaped approved evidence. Both providers took one real uncached call on the paired miss run and zero on the matched cache run. The hits returned the expected concept and a valid citation. The one-call sample was English only and exercised a fully reviewed exact variant. Separate tests exercise English/Hindi mismatches, history, tampering, expiry, source removal, revocation and adversarial variants. The seven-case Sarvam C run returned one hit (1/7 overall, 1/3 English, 0/4 Hindi). A one-query exact-match trial is not a production hit-rate estimate.

| Paired exact fixture | Matched miss input / output | Hit input / output | Estimated cost avoided at the tested rates | Miss → hit service latency |
| --- | ---: | ---: | ---: | ---: |
| Sarvam · en | 722 / 58 | 0 / 0 | ₹0.008670 | 768 → 14 ms |
| Anthropic · en | 1,155 / 91 | 0 / 0 | $0.000161 | 1,331 → 13 ms |

Two live provider calls were avoided in these controlled trials. The paired misses establish the counterfactual token and cost estimates. The cache-hit path's zero provider calls and zero tokens are observed. The production cache has no published rows. Production call, token and invoice reductions from FAQs remain unmeasured.

## D. Anthropic native caching with baseline retrieval

The seven-case stable-prefix trial held baseline source selection and response-cache state fixed. All seven cases passed the matched mode, language, citation, list and concept checks in both runs.

| Variant | Locale | Logical input / output | Cache reads / writes | Priced total / 100 | P50 / P95 (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| No prompt cache | en | 4,996 / 1,035 | 0 / 0 | $0.001017 / $0.03390 | 1,714 / 3,200 |
| Five-minute prefix | en | 5,014 / 978 | 2,895 / 0 | $0.000730 / $0.02433 | 1,625 / 2,988 |
| No prompt cache | hi | 6,678 / 1,635 | 0 / 0 | $0.001485 / $0.03713 | 1,527 / 3,323 |
| Five-minute prefix | hi | 6,702 / 1,656 | 2,922 / 974 | $0.001260 / $0.03149 | 1,856 / 3,600 |

Using the same observed logical input and output for the cached run, discounted reads minus write premiums reduced modeled charges by $0.00049918. The English prefix was warm at the first observation. Cache discounts reduce price, while the stable cached variant processed 42 more logical input tokens in this sample. The cached Hindi sample was slower. This proves the mechanism and sample rate-card benefit. It does not establish incremental savings over the previous deployment's already-active native prompt cache.

At these prices a write has a 25% premium and a later read saves 90% of base input cost. Break-even needs reads greater than 27.8% of write tokens. Existing production volume is sparse and curated FAQ traffic could further decrease prompt reuse. Monitor that ratio and actual latency as traffic changes. Keep the five-minute policy, with no one-hour pilot until usage supports it.

## E and F. Applicability gates

- **Semantic cache.** EmbeddingGemma 2 was unavailable to the account and existing vectors are lexical. The project has no measured eligible paraphrase rate or calibrated answer-equivalence dataset. The experiment stopped before embedding and candidate tests. No embedding charges or cache savings are assumed. [Sarvam EmbeddingGemma 2](https://docs.sarvam.ai/api/token-factory/models/embeddinggemma-2)
- **Headroom.** Ran `headroom-ai==0.44.0` in-process on Python 3.12 inside a separate container, with networking disabled, no keys, no corpus mount and telemetry off. Synthetic English/Hindi prose represented dates, exceptions, negations, conditions and citations. Short and eight-repeat samples were byte-identical after compression. Headroom's own tokenizer estimates stayed 179/1,265 for Sarvam and 202/1,443 for Anthropic. Cold calls took 129 and 36 ms, respectively, with process peak RSS about 33–40 MiB. Warm calls took under 1 ms. These figures include library and tokenizer overhead in the experiment and do not measure incremental Railway RSS or billable tokens. No transport was called. The learned optional Kompress path could alter authoritative text and requires extra model/runtime dependencies. There is no measured reason to ship the package or a proxy. [Headroom README](https://github.com/headroomlabs-ai/headroom) · [Headroom compressors](https://github.com/headroomlabs-ai/headroom/blob/main/docs/content/docs/how-compression-works.mdx)
- **LLMLingua-2 and heavier reranking.** The context candidate did not establish a safe retrieval win, and the prose is policy-bearing. LLMLingua-2's local learned compressor would add model memory and a separate validation burden. No runtime or cost benchmark was warranted after the applicability gate. [LLMLingua project](https://github.com/microsoft/LLMLingua)

## Release gates

The staged release keeps the RAG candidate and production FAQ cache disabled. Existing approved-source enforcement, public input protection, rate limiting, selected-provider routing, citations, admin controls and feedback remain tested. Persisted reporting records provider/model/locale, provider-reported usage, estimated retrieval sizes, priced usage, error and timeout counts, FAQ outcomes and latency. Quality scoring and per-case comparisons run in replay. The application does not infer factual accuracy from production answers or log passenger content.

## Build and test verification

The complete non-live backend regression suite exercised both providers and the optimized retrieval flag, including the security suite and reviewed FAQ cases. The amd64 backend image built and started with the approved corpus and additive migration in a synthetic environment. The credential-free container reported a loaded index, migrated database and expected degraded provider health. Frontend lint, type checking and the Next.js production build passed.
