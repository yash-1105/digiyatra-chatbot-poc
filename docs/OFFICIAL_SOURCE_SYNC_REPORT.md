# Official source ingestion and knowledge synchronisation (Task 1)

Status as of 2026-11-25. Implementation and offline verification are complete. Nothing has been deployed, and the scheduled job is **implemented but not activated** in production. This report is sanitised: it contains no private knowledge documents, credentials or copied source text, and gives counts, source identifiers and public official URLs only.

## 1. Implemented architecture

Two independent pipelines share only PostgreSQL.

```
Pipeline A — scheduled job / operator CLI (never the chat API)
  registry (due sources) -> SecureFetcher (conditional GET) -> extract (HTML/FAQ/feeds/PDF)
  -> validate (completeness, relevance, injection, statistics) -> deduplicate -> versioned records (PostgreSQL)
  -> build + validate index -> activate publication (one transaction) -> close connections -> exit

Pipeline B — customer chat (unchanged flow, no network except the selected model provider)
  question -> guardrails -> conversation context -> eligible FAQ-cache lookup -> local LanceDB/BM25 retrieval
  (119 approved corpus chunks + active verified official records, expiry checked per request)
  -> selected provider (Sarvam 105B / Anthropic Haiku 5.5 / Novita Qwen3.8 Flash) -> validated answer
```

- **Code:** `backend/app/sync/`:
  - `sources.py`: allow-listed registry
  - `fetcher.py`: SSRF-safe HTTP
  - `extract.py`: DOM and accordion extraction, JSON-LD, feeds, sitemaps
  - `pdf.py` and `_pdf_child.py`: sandboxed pypdf
  - `policy.py`: validation and review rules
  - `job.py`: orchestration, lease, versioning, monitoring
  - `publish.py`: publication and API hot swap
- **Migration:** `0005_official_source_sync` (additive and reversible).
- **No chat-time scraping:** a chat request never fetches, renders, downloads or discovers anything. A cache miss falls through to local retrieval. Existing knowledge-gap counting, which records aggregate topic slugs only, still queues topics for later review without triggering any fetch.
- **Shared knowledge for every provider:** all three providers read the same retriever. Model IDs, keys and provider settings are unchanged.
- **Unchanged features:** the existing reviewed PIB/DigiLocker supplements, the FAQ cache (still disabled by default) and token optimisation. The generated-answer badge was not reintroduced.

## 2. Source inventory and accessibility

| Source ID | Organisation | Type | Cadence | Review | First live run (2026-11-25, from Hostinger) |
|---|---|---|---|---|---|
| `dyf-international-trial` | Digi Yatra Foundation | FAQ accordion | 7 d | required | **Blocked**: HTTP 403 from the CloudFront firewall ("Request blocked") |
| `dyf-airports-current` | Digi Yatra Foundation | page | 7 d | required | **Blocked**: HTTP 403 (CloudFront) |
| `dyf-sitemap` (+ `sitemap_index.xml`, `wp-sitemap.xml`) | Digi Yatra Foundation | sitemap discovery | 14 d | required | **Blocked**: HTTP 403, including `robots.txt` |
| `moca-digital-initiatives` / `-hi` | Ministry of Civil Aviation | page section (Digi Yatra only) | 14 d | low risk | OK: 1 English and 1 Hindi section |
| `moca-guidelines` → PDF | Ministry of Civil Aviation | document → PDF | 14 d | required | OK: 70-page PDF, 113 page-chunk records |
| `moca-search-en` / `moca-search-hi` | Ministry of Civil Aviation | site-search discovery | 7 d | required | OK: 28 relevant child pages discovered |
| `pib-rss` | Press Information Bureau | RSS discovery | 7 d | required | OK: the current feed had no Digi Yatra items |
| `pib-2331200` (+ PIB releases linked from MoCA) | Press Information Bureau | press release | 7 d / 14 d | required | OK: 4 releases |

**Blocked sources:** all Digi Yatra Foundation URLs return a CloudFront 403 block page to this server, including `robots.txt`. They were recorded as failures (`forbidden_or_waf_blocked`), not as successful ingestion. No bypass was attempted: the user agent was not changed, no browser was spoofed and no proxy was used. Supported alternatives:

1. Ask the Foundation to allow-list the scheduled job, or to provide a feed or export.
2. Run `sync-import dyf-international-trial --file <saved page>` with an operator-saved copy of the page. Every record from a capture requires human review.
3. Check whether Railway's egress IPs are blocked as well. This is **unverified**.

The DY-IPT FAQ screenshot mentioned in the request was not available in this session. It has not been used, and no answer was inferred from headings.

**Excluded by policy:**
- MoCA pages that only embed social posts (most search results). Task 2 adds social sources properly.
- Careers, tender and media paths.
- The private DY-IPT draft, which stays excluded by the manifest.
- MoCA `/digi-yatra`, whose body is not present in the delivered HTML. It was removed from the registry.

## 3. Initial ingestion results (isolated local development database)

The run used a separate local database (`backend/data/official-sync-dev.db`, ignored by Git), not production, and `KNOWLEDGE_AUTO_PUBLISH_ENABLED=true` for this local run only.

| Measure | Value |
|---|---|
| Sources processed / HTTP requests | 38 / 50 |
| Child pages discovered | 28 (22 MoCA press/document pages, 4 PIB releases, 2 PDFs) |
| Records extracted | 125 |
| `verified` (low risk, first version, no conflict) | 2 (MoCA English and Hindi Digi Yatra descriptions) |
| `pending_review` (consequential or policy topics) | 118 (113 guidelines-PDF chunks, the trial release, a May 2026 announcement) |
| `historical` (announcements older than 365 days; never served) | 5 (February 2024 PII release, September 2024 nine-airport release) |
| Duplicates collapsed | 1 PDF (the Hindi-folder policy PDF has text identical to the English guidelines) |
| Usage statistics removed | sentence-level, in record text and titles |
| Extracted FAQ pairs | 0 live, because the Foundation FAQ source is blocked. Accordion extraction is verified offline only. |
| Active publication | 2 records. In production (`KNOWLEDGE_AUTO_PUBLISH_ENABLED=false`) it would contain 0 until reviewed. |

**New information acquired (pending review):**
- The PIB international-trial release of 2026-11-01. The job assigned it the window 2026-11-01 to 2026-12-31 and removed the sentence containing usage statistics.
- A dated May 2026 milestone release. Its title contained usage statistics and was replaced with a neutral one.
- MoCA's Digi Yatra guidelines. This is an OCR text layer of version 7.8 from March 2021, flagged for OCR errors and for being a dated policy document.

A local reviewer action (`local-dev-verification`, on the development database only) published the trial release. The rebuilt index then held 123 chunks: the 119 approved corpus chunks plus 4 official records. English and Hindi international-trial questions retrieved the PIB evidence first.

**Supported airports (C):** the Foundation implementation page is blocked, so no airport names were extracted, and no names are inferred from counts.
- The 24-airport directory in the approved corpus remains historical.
- The latest verified count is still the existing reviewed PIB supplement: 39 domestic airports on 2026-11-01.
- A known limitation: the new PIB record dropped that same sentence because it also contained usage statistics.
- The 38-airport figure (May 2026) is pending review and would be superseded by the newer count.

## 4. Scheduling: implemented vs. active

- **Implemented:** `sync-run`, run by `backend/scripts/sync.sh`. Per-source `next_due_at`, `refresh_days`, ETag, Last-Modified, content hash, version, failures and failure reason are all stored in PostgreSQL. Weekly sources (trial, announcements, MoCA/PIB discovery, airports) are due every 7 days and the others every 14 days, both configurable. A single run processes the weekly sources and only those fortnightly sources that are due.
- **Proposed activation:** a Railway cron service running `30 21 * * 6` UTC, which is Sunday 03:00 IST (`docs/DEPLOYMENT_HANDOFF.md` §17). **Not provisioned:** it requires approval.
- **Safeguards:**
  - a lease row prevents overlapping runs, and a crashed job's lease expires after `SYNC_LOCK_TTL_S`
  - runs left "running" are marked `interrupted`
  - a watchdog hard-exits after `SYNC_MAX_RUNTIME_S` + 60 s
  - each run is limited to `SYNC_MAX_FETCHES_PER_RUN` requests
  - requests to the same host are spaced 2 s apart

## 5. Persistent storage, publication and recovery

- **PostgreSQL** stores:
  - `official_source`: the registry and its state
  - `official_record`: versioned records (verified, pending_review, conflict, superseded, withdrawn, rejected, historical). Each keeps its question, answer, category, title, URL and anchor, organisation, language, dates (published, updated, effective, expiry, extracted), hash, authority, topic and review reason.
  - `sync_run`: aggregate history
  - `knowledge_publication`: immutable record sets with a digest; at most one is active
  - `job_lease`
- **LanceDB** stays a derived artefact rebuilt from the corpus (`knowledge/deploy`) plus the active publication. Nothing exists only on an ephemeral filesystem.
- **Atomicity:** the job builds and validates a full index before activating a publication. A failed build leaves the previous publication active, which is tested. Each API process builds the new version in a separate folder and swaps its retriever only after validation. Requests therefore see the old or the new complete index, and multiple instances never serve a partial one.
- **Restart and redeploy:** `ensure-index` rebuilds whenever the corpus, schema or publication digest differs. Without a publication, the original 119 approved chunks remain intact and reproducible (tested).
- **Failures keep the last known good:** a temporary failure (403/429/5xx/timeout) never deletes or replaces verified records. Records are withdrawn only when a page returns 410, returns 404 twice in a row, or no longer contains them in an otherwise complete extraction that still keeps at least half of the previous records. Changed content of a verified record stays pending, and the old version is still served until a reviewer verifies the change.

## 6. Verification, freshness and cache invalidation

- **Category separation:**
  - (A) the manifest-approved corpus, unchanged, with its sign-off **still pending**
  - (B) `verified` official records
  - (C) `pending_review` / `conflict` candidates
  - (D) the FAQ cache, which accepts approved-corpus sources only, so official records are never cached
- **Review rules:** records with `risk=high` (trial, airports, announcements, policy, discovered press and PDF content) always require a named reviewer. Records with `risk=low` are auto-verified only when `KNOWLEDGE_AUTO_PUBLISH_ENABLED=true` and the record is a first version with no conflict. Airport-count disagreements with verified records become `conflict`. No LLM extracts, rewrites or approves anything.
- **Expiry per request:** effective and expiry dates are checked locally in India time on every request, so an expired trial disappears on 1 January 2027 even if no sync has run. Historical announcements are never served.
- **Cache invalidation:** a new publication changes the retriever revision, which is part of the FAQ-cache version. The API rebuilds its FAQ validator on swap, so older cached answers can no longer match.

## 7. Security

The following are tested:
- exact host allow-list, HTTPS only, credentials and ports refused
- public-IP checks on DNS answers **and** on the connected server address
- every redirect re-validated
- no environment proxies, size limits for HTML (2 MB) and PDF (15 MB, 120 pages)
- per-request and total time limits, and content-type checks
- robots.txt honoured (RFC 9309)
- XML parsing with entity resolution and network access off
- block-page and partial-FAQ detection
- prompt-injection screening of source text
- removal of usage statistics
- PDF parsing in a separate process limited to 768 MB of memory, 60 s of CPU and no file writes, with stdin input only
- logs that record reason codes only, never content

Public chat users cannot supply URLs, and passenger text is never sent to official sites.

## 8. Tests (offline)

- **Baseline before changes:** 616 passed.
- **After changes:** **636 passed**, 0 failed, 15 live tests deselected. Ruff is clean.
- **New tests** (`tests/unit/test_official_sync.py`, 20 tests) cover:
  - initial ingestion and the review policy
  - weekly and fortnightly schedules with restart persistence
  - conditional 304 requests
  - unchanged, changed and last-known-good content
  - withdrawal rules
  - complete accordion extraction, including collapsed panels, categories and JSON-LD
  - partial FAQ extraction, Hindi content and dates, PDF text, scanned PDFs and non-PDF input
  - duplicates, conflicts and historical records
  - 403, 429 and 500 handling, blocked pages, social embeds and injection
  - SSRF and redirect defences, size, type and robots limits
  - leases, interrupted runs, failed index publication and recovery
  - operator captures
  - expiry and effective-date filtering, and FAQ-cache revision invalidation
  - the API hot swap, including a failed build
  - preservation of the 119 corpus chunks
- **Zero-fetch proof:** 60 chat requests (10 required questions × English and Hindi × 3 mocked providers) ran with DNS and sockets blocked and ingestion code patched to fail. They made **zero** fetches, sync jobs or socket calls, and local RAG returned sources.

**Pending (not claimed as passed):**
- Live answer quality on all three providers (no development keys on this server; production keys were not copied).
- PostgreSQL-specific paths (`LOCK TABLE`, partial unique indexes on PostgreSQL); the project's isolated PostgreSQL test cluster is not installed on this server.
- A Docker image build, because the shared Docker daemon is off-limits.
- Live markup of the Foundation FAQ page, which is blocked.

## 9. Runtime, resources and Railway cost

| Run | Wall time | CPU | Peak memory | Requests |
|---|---|---|---|---|
| Initial (all sources) | 112 s | 26.7 s | 276 MB | 50 |
| Weekly incremental (weekly sources) | 20 s | 2.2 s | 171 MB | 13 |
| API rebuild after a publication | about 2 s (lexical, 123 chunks) | n/a | n/a | 0 (PostgreSQL only) |

At Railway's list prices ($20 per vCPU-month, $10 per GB-month), checked 2026-11-25, the job's own estimate is $0.0003 for the initial run and $0.00003 for a weekly run. Including container start-up, plan for about $0.001 per run, which is **under $0.01 per month** for about 4.3 runs. Egress is negligible. There is no always-on worker, no Redis, no new database and no paid scraping service.

## 10. Deployment preparation

- **Railway Config as Code is deprecated (verified against official docs):** existing `railway.toml` files work only **until 2026-12-01**. Migrate with `railway config migrate --apply` / `plan` / `cutover` from the authenticated laptop before that date (`DEPLOYMENT_HANDOFF.md` §18). The IaC reference does not document Dockerfile or cron options, so no unvalidated hand-written file was committed.
- **Private build folder:** `scripts/make_railway_context.sh` now packages `backend/scripts/sync.sh`, and the Dockerfile copies it. `.cache/railway-context` was rebuilt and audited: code, migrations, configuration and the approved deploy corpus only. It contains no raw documents, tests, `.env` files or credentials.
- **Production enablement steps** (for approval):
  1. Deploy the backend; migration 0005 runs at start.
  2. Set `OFFICIAL_KNOWLEDGE_SERVING_ENABLED=true`.
  3. Create the cron service described in §17 of the handoff.
  4. Run `sync-run --trigger initial` once.
  5. Review `sync-pending` and publish.

## 11. Remaining blockers

1. Foundation access is blocked, so the trial FAQs and current airport list can't be collected automatically. Allow-listing or a reviewed manual capture is needed.
2. 118 pending records need a content reviewer, and the manifest's content-owner sign-off is still pending.
3. Railway configuration migration and cron-service creation need the authenticated Railway CLI and approval. The deadline is 2026-12-01.
4. Live provider tests, PostgreSQL integration tests and the Docker image build are pending.
5. `CLAUDE.md` still says Sarvam is the only generative provider, while the codebase has three. This needs a separate owner decision; it was not changed here.
