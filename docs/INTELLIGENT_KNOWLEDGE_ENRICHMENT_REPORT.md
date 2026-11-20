# Digi Yatra intelligent answering and verified enrichment

## What changed

The previous approved snapshot described domestic flights and a proposed international rollout. Strong grounding correctly kept models from treating that material as current evidence. It also meant the chatbot could give an undated snapshot introduction when a newer authoritative source existed outside its index. An additional issue was definition routing that matched phrases such as DigiLocker being a preferred registration option, even though the passage did not define the service.

The application now routes conversational answers through three evidence paths. Existing approved evidence goes through LanceDB retrieval and sentence grounding. Verified supplemental facts take precedence for the topic and applicability period they cover. Pure, allowlisted technology definitions can use the selected model's stable general knowledge with no sources and with product policy, eligibility, privacy, legal and other consequential claims screened out. Input guardrails, the selected-provider call and error reporting, and source approval remain part of the request flow.

Routine source-backed responses keep validated sources in the expandable Sources panel. The backend removes markers from selected routine answers only after grounding. The trial keeps an inline link to the authoritative evidence through its citation marker. The existing frontend renders these forms using its current contract. The response text leads with the answer when current evidence supports it.

## Source review and serving

The Ministry of Civil Aviation announcement dated November 1, 2026 confirms a limited November–December 2026 trial, seven Indian airports, eligible Indian ePassport holders, and selected Air India and IndiGo international flights. Usual documents, airline checks and immigration remain required. The 2027 announcement is planning information. IndiGo's November 1 release corroborates its participation and enabled touchpoints. The released source is independent of the excluded draft. [Ministry release](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2331200&lang=2&reg=48) · [IndiGo release](https://www.goindigo.in/content/dam/s6web/in/en/assets/investor-relations/press-releases/2026/261101-Press-Release-IndiGo-Partners-with-Digi-Yatra-for-International-Passenger-Trials-Across-Seven-Indian-Airports.pdf)

The runtime uses the published trial evidence for international availability and related questions during the effective window. The older domestic evidence stays available for domestic and historical questions. At the start of January 1, 2027 in India the trial row is ineligible for current retrieval. The application gives an expiry-specific response and avoids promoting the former roadmap or wider rollout into current policy. A missing or broken supplemental store falls back to safe ordinary RAG.

The application also has a separately verified low-risk DigiLocker definition from the Ministry of Electronics and IT. It can pair that definition with approved Digi Yatra registration and airport evidence when users compare the services. [DigiLocker government overview](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2198743&lang=2&reg=3)

### Storage and publication

Migration `0004_supplemental_knowledge` adds the following PostgreSQL structures.

- `knowledge_gap` contains allowlisted canonical topic, observation count and last-seen timestamp. No user, conversation, query, embedding or model answer is stored. Signed synthetic requests and sensitive or unsafe input bypass gap recording.
- `knowledge_revision` contains source registry ID, canonical topic, evidence digest, source URL, published and retrieved dates, effective period, risk, verification method, bounded evidence, reviewed claim, conflict note and review decision. The topic index and one-published-revision constraint form an independent serving index. Publishing a reviewed replacement supersedes the previous revision in one transaction. Revocation and expiry take effect on the next lookup.
- The deployed 119-chunk approved corpus is served through the existing LanceDB index. Supplemental lookups are a bounded indexed PostgreSQL read over a small registered topic set. This keeps serving state and publication state atomic, with no second index to reconcile. Approved FAQ lookup is bypassed for supplemental scopes and its existing publisher accepts approved corpus citations only. General replies and pending candidates cannot enter the FAQ cache.

Passenger requests do not run network research. They produce aggregate gap candidates. Operators use `knowledge-inventory`, `knowledge-verify SOURCE_ID`, `knowledge-inspect REVISION` and `knowledge-review REVISION published|rejected|revoked --reviewer NAME` in the authorized CLI. A pinned source must satisfy document-specific date and evidence checks before the candidate exists. An operator can alternatively supply an authenticated capture with `--file`; it still needs a review. The verifier uses exact built-in HTTPS URLs, public DNS addresses, TLS, no redirects or environment proxies, bounded reads and timeouts, HTML content validation, and evidence-block injection checks. No HTML, user text or source-supplied instructions become model instructions.

Eligibility, international operations and any registered conflict require an explicit review. Optional auto-publication is limited to a first verified revision for a stable pinned source with no registered conflict. Later revisions go through review. The government trial was manually verified against the primary source and IndiGo corroboration using the operator path. No draft was published.

### Controls and rollback

| Setting | Purpose |
| --- | --- |
| `GENERAL_KNOWLEDGE_ENABLED` | Selected-provider, scope-limited general definitions |
| `CONVERSATIONAL_ANSWERS_ENABLED` | Natural style and risk-aware marker presentation |
| `KNOWLEDGE_ENRICHMENT_ENABLED` | Serve reviewed supplements and collect canonical gap counts |
| `OFFICIAL_SOURCE_LOOKUP_ENABLED` | Permit pinned network fetches in the operator CLI |
| `KNOWLEDGE_AUTO_PUBLISH_ENABLED` | Permit explicitly low-risk source-specific automatic publication |

Disable enrichment to return to the approved-only path, or revoke a single published revision to withdraw it. Reverification of the same evidence is idempotent. Publication state survives restart and deployment in PostgreSQL. The migration is additive and reversible. Application rollback can retain its tables.

## Verification scope and limitations

The isolated lifecycle test starts from an unsupported scoped question and checks its canonical gap record. It verifies a source, requires review for a conflict-bearing trial, retrieves the evidence on a paraphrase, checks citation/provenance, and simulates expiry and revocation. It also tests a false upstream model claim, source injection, altered dates, an arbitrary URL, and a sensitive question. Subsequent chat requests do not fetch the source. Low-risk automatic publication is tested separately and stays off for untrusted captures and replacement revisions.

The broad existing catalog covers more than 60 distinct questions with English, Hindi and Hinglish coverage. The focused paired live suite has nine questions in each provider/language lane. Receipt of HTTP 200 alone does not pass. The evaluator checks substantive trial scope, selected providers, Hindi text, source identity and presentation, general-knowledge content and post-trial uncertainty. Safety checks remain heuristic. The report describes observed coverage and does not extrapolate a production hallucination rate.

The approved evidence still lacks a service-fee statement and a complete per-stage internet requirement. The international release covers selected flights and enabled touchpoints. It cannot confirm a passenger's booking, a specific flight's participation, live gate status or continuation after December. New authoritative source registrations require a reviewed code change. There is no external search service or unattended research job.

Implementation files are grouped in `backend/app/services/{knowledge,answering,chat_service,prompts}.py`, `backend/app/security/grounding.py`, `backend/app/rag/multilingual.py`, the app/CLI/settings wiring, the migration and models, and the evaluation and test modules.

## Paired local provider measurements

The 36-question paired run used the same approved index, real providers and disposable databases. The old code returned an answered status on 18/36, including historical or partial replies. The updated code answered all 36 and passed all 36 scoped claim, language and provenance checks. The targeted false-refusal count was 18 before and zero after. The trial's authorized source supplied evidence on 24 questions. Eight general definitions had no citations. The comparison cases retained Sources metadata without inline markers.

| Provider and language | Reported input tokens before → after | Reported output before → after | P50 before → after | P95 before → after |
| --- | ---: | ---: | ---: | ---: |
| Sarvam English | 7,886 → 11,491 | 470 → 984 | 0.645 → 0.616 s | 0.926 → 1.021 s |
| Sarvam Hindi | 12,161 → 9,484 | 704 → 1,008 | 0.816 → 0.591 s | 1.646 → 1.131 s |
| Anthropic English | 12,186 → 15,945 | 810 → 1,437 | 1.239 → 1.420 s | 2.089 → 1.714 s |
| Anthropic Hindi | 18,131 → 16,699 | 1,946 → 2,936 | 2.106 → 1.885 s | 2.984 → 3.150 s |

Provider-attempt count rose from 29 to 37 as previously refused questions received answers. The existing list-rate accounting prices the observed Sarvam sample at ₹0.132476 before and ₹0.166262 after, and Anthropic at $0.004410 before and $0.005451 after. These are usage-based estimates. Two operator source fetches added no paid research-service or LLM verification calls. There were no response-cache hits or savings claimed in this matrix. The simulated post-expiry answer used zero model calls. Both providers also traversed 122 questions each in the separate zero-billable-call preparation replay. Those broad checks exercise retrieval and prompt assembly, while the 36-case live run scores generated content.

### Examples

- Before, an international-flight question led with an undated snapshot and described domestic coverage. After, both providers led with selected international flights under a trial ending December 31, 2026, followed by the Indian ePassport and carrier limits and continuing immigration checks. The Hindi reply likewise led with the limited trial and its conditions.
- Before, the narrow definition path did not cover DigiLocker and often returned a generic gap. After, both providers explained it as a digital document wallet in English and Hindi, with general answer mode and no sources.
- A Delhi paraphrase retrieved the same PIB revision after publication. The response described Delhi's participation and advised checking the specific flight with the airline. Serving the paraphrase reused the database record and made no government-source fetch.

## Production verification

Application commit `5d78fb2` deployed successfully on Railway. The running code matched the checked-in source hash, and migration `0004_supplemental_knowledge` applied to PostgreSQL. The operator verified and published two HTTPS-backed entries. Revision 1 is the PIB international trial and revision 2 is the DigiLocker overview. Automatic publication remained off. The Vercel health route returned a healthy backend and the 119-chunk approved index. Anonymous admin analytics returned HTTP 401.

| Provider | English, first production run | Hindi, first production run |
| --- | ---: | ---: |
| Sarvam | 8/9 | 9/9 |
| Anthropic | 9/9 | 9/9 |

All 36 production requests succeeded and selected the expected provider. All 24 trial cases passed the claim, date and provenance checks on the first run. One Sarvam English ePassport definition missed the chip concept check. Two focused live repeats both passed, for 37/38 observations across the first run and repeats. First-run HTTPS P50/P95, in seconds, were 1.621/2.432 for Sarvam English, 1.705/2.244 for Sarvam Hindi, 1.691/1.995 for Anthropic English, and 1.963/3.460 for Anthropic Hindi. Both a cited English trial answer and a Hindi comparison with an expandable Sources panel rendered in a production browser. That browser continued to call the real production endpoint, using signed synthetic identity for analytics isolation.

The full backend suite passed 538 tests, with 15 network-opt-in tests handled separately by the real-provider evaluation. The 10 enrichment lifecycle and security tests passed on disposable PostgreSQL as well. Ruff, the amd64 backend build, frontend lint, type checks and frontend production build passed. The local security checks rejected injected or mismatched evidence and demonstrated that a fabricated provider answer cannot create a source revision. No prohibited policy claim was observed in the scoped live trials. Unattended discovery, production traffic-level cost savings and future trial extension remain unverified.

The focused production content suite is reproducible with the authorized synthetic route and existing secret injection. From `backend` run:

```sh
PYTHONPATH=. .venv/bin/python -m evaluation.knowledge_matrix \
  --url https://digiyatra-chatbot-poc.vercel.app --inr 65 --usd 1.5
```

The caps reserve worst-case retry-inclusive usage for this deployed configuration. Matrix output contains aggregate grades and timing. It does not store synthetic traffic in production analytics.
