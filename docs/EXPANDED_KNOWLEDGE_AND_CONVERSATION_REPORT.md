# Expanded knowledge and persistent conversation (Task 3) — final readiness report

Status as of 2026-11-25, on integration branch `feature/official-source-sync` (unmerged). This report covers Tasks 1–3 together and is sanitised: it contains no private documents, prompts, conversations or credentials.

| State | Meaning here |
|---|---|
| **Implemented / tested / committed** | Everything in this report, unless it is marked otherwise |
| **Deployed** | **Nothing.** Railway and Vercel are unchanged |
| **Scheduled** | **No.** The cron service is designed but not provisioned; production scheduling is pending |
| **Live-model verified** | **No.** All model tests used mocked providers; the live script is prepared |
| **Blocked** | The Digi Yatra Foundation website (CloudFront 403); X, LinkedIn, Instagram and Facebook direct access; transcripts (none supplied) |

## 1. Architecture

```
Pipeline A (short-lived job, Sunday 03:00 IST = cron 30 21 * * 6; never in chat)
  registry -> due sources only (+ sources mapped from queued knowledge-gap topics)
  -> SSRF-safe conditional fetch / oEmbed / YouTube Data API (optional key) / operator imports
  -> extract -> validate -> deduplicate -> versioned records (PostgreSQL) -> human review rules
  -> validated index build -> atomic publication -> exit

Pipeline B (chat; local only)
  question -> guardrails/redaction -> conversation context (bounded) -> FAQ cache (disabled by default)
  -> lexical TF-IDF + BM25 retrieval over 119 approved chunks + active verified publication
  (expiry/effective dates checked per request; metadata-aware ranking)
  -> selected provider (Sarvam 105B | Anthropic Haiku 5.5 | Novita Qwen3.8 Flash) -> grounding checks
  -> optional verified video recommendation -> response with expandable Sources
```

- **One shared knowledge path:** every provider receives the same classification, retrieval, ranking, freshness checks, provenance, cache rules and context selection. Provider model IDs, endpoints, Anthropic workspace headers, Qwen reasoning settings, error handling and analytics are unchanged.
- **No frontend deploy needed for new knowledge:** the API loads new publications by itself. It checks PostgreSQL at most every 300 s (triggered by chat traffic, with no polling loop), builds a complete index in a fresh directory, then swaps it in. A failed build keeps the previous index.
- **Durable storage:** PostgreSQL holds sources, records, runs, publications and the job lease. LanceDB is always rebuilt from the corpus plus the active publication, so nothing important lives only on ephemeral disks.

### Retrieval changes in Task 3 (existing lexical architecture; no embeddings or reranker; same context budgets)

- **Ranking:** social posts are down-weighted for privacy, biometric, retention, fee and eligibility questions, so policy documents win. Dated government items and verified posts get a small boost for "latest / announced / new airport" questions. Official-channel records count only for "follow / official channel" questions. Ties prefer the newer publication date.
- **Near-duplicates:** for dated official items the **newer** version replaces the older one, so an updated announcement overrides an earlier one.
- **ePassport and DY-IPT questions** now route to the reviewed trial evidence instead of the domestic Aadhaar steps.
- **Hindi and Hinglish:** added Hinglish question forms (kya hai, kaam karta hai, fayde, wapas, kya karu, dikhao, …) and Hindi terms (complaint, follow, YouTube, channel, announcement, Smart Share, DY-IPT, consent, …). Hindi and Hinglish follow-up pronouns are now recognised.
- **Videos:** recommendations use the user's **own** earlier questions when the request is just "Can you show me a video?". The video leads the answer for explicit requests, and the answer names a video that an approved document already cites rather than adding a duplicate source. Earlier assistant replies reach models only as truncated (≤360 characters) context labelled "not evidence; current evidence overrides it".

## 2. Knowledge sources

| Source | State |
|---|---|
| Original approved corpus | 119 chunks from 26 documents; unchanged, hash `adff17c04192…`; content-owner sign-off still **pending** |
| Reviewed supplements (PIB trial, PIB domestic count, DigiLocker) | Unchanged; production rows preserved, and migrations are additive |
| MoCA digital-initiatives page (English and Hindi) | Accessible; 2 sections (low risk) |
| MoCA Digi Yatra guidelines PDF (70 pages, OCR of version 7.8, March 2021) | 113 page records **pending review** (7 review groups); a duplicate copy was collapsed |
| MoCA search discovery → PIB releases | 4 releases: 2 historical, 2 pending (trial release 2026-11-01; May 2026 milestone) |
| Digi Yatra Foundation website (trial FAQs, current airports, FAQ pages) | **Blocked** (CloudFront 403); manual import workflow ready (`docs/MANUAL_IMPORT_FOUNDATION.md`); **0 trial FAQ pairs collected** |
| Official social posts (embedded on MoCA pages) | 11 discovered: 7 historical, 4 **pending review**, 0 verified |
| YouTube @DigiYatraFoundation | 7 videos verified (metadata only); Data API path implemented, not enabled |
| Authorised transcripts | **0** (none supplied; the import path is ready) |
| Official channel records | 6 verified (YouTube; X @DigiYatraOffice, @MoCA_GoI, @PIB_India, @AAI_Official; LinkedIn) |
| Pending approvals | 122 records (`sync-review-report` → 9 grouped decisions + social and trial items) |

The counts above come from the **local development database**. Production has none of these records until the deploy, the initial ingestion and review have happened. Videos stay metadata-only recommendations and are never factual evidence. Transcript passages, once imported and reviewed, would be evidence with `&t=` links.

## 3. Synchronisation

- **Schedule:** one consolidated job.
  - Weekly (7 d): trial FAQs, announcements and MoCA/PIB discovery, airports, social announcements.
  - Fortnightly (14 d): general FAQs, policies, registration and troubleshooting pages, YouTube.
  - Transcripts: only when a new or changed caption file is imported.
- **Verified by tests:** sources are processed only when due, unchanged content is skipped (304 or same hash), the lease prevents overlapping runs, the watchdog hard-exits, the lease is released, and the process ends.
- **Knowledge gaps:** queued gap topics (aggregate slugs) make their mapped, allow-listed sources due in the next run. Chat never fetches.
- **Measured locally:**

  | Run | Wall time | CPU | Peak memory | Requests |
  |---|---|---|---|---|
  | Initial website ingestion | 112 s | 26.7 s | 276 MB | 50 |
  | Weekly incremental | 20 s | 2.2 s | 171 MB | 13 |
  | Social/YouTube initial | 58.6 s | 2.7 s | 271 MB | 30 |
  | Social/YouTube incremental | 58.5 s (politeness gaps) | 2.5 s | 172 MB | 30 |

- **Activation:** **not activated.** The cron service needs owner approval (`DEPLOYMENT_HANDOFF.md` §19).
- **Recovery:** last-known-good knowledge is kept on failures; withdrawals happen only for complete extractions or 404/410; `sync-rollback [--to ID]` re-activates an earlier publication without a redeploy.

## 4. Conversation history

**What existed before:** `sessionStorage` key `dy-poc-chat`. It survived a refresh but not closing the browser, had no expiry or limits, and stored typed text unredacted. Requests sent the last 4 user turns. The server kept a 1-hour, in-memory, cookie-scoped context.

**What it is now (one mechanism, extended rather than duplicated):**
- **Storage:** `localStorage` key `dy-chat-history-v1`, on this browser or device only.
  - **Retention:** 7 days, enforced per message on every load and save, with a cap of 60 messages / 150 KB.
  - **Validation and migration:** stored data is schema-validated on load because it is untrusted. The old session key is migrated (redacted) and then deleted.
  - **On-screen notice:** "This conversation is saved only on this browser for 7 days (personal details are not saved). Use the clear button on shared devices." English and Hindi versions.
- **Privacy:**
  - The server returns `pii_redacted` and `redacted_message`; the browser stores and shows that redaction instead of the typed text.
  - A second, independent client redactor covers Aadhaar/VID, passport, OTP, PNR/booking references, phone numbers, email, card numbers and credentials.
  - A message that still looks like an identifier after redaction is replaced by a placeholder rather than stored.
  - No keys, tokens or cookies are stored. Analytics and logs contain no chat text (tested).
- **Clear:** removes the stored messages and the legacy key, calls the cookie-scoped `POST /api/v1/chat/forget` to drop the server context, and starts a new conversation ID. A generation guard discards in-flight answers, and clearing in one tab clears the others.
- **Context:** display history and model context are separate. Models receive at most 4 client-recovered user turns, or the server's own turns, within the existing 600-token history budget. Earlier replies are labelled and truncated. Measured overhead was 0–319 estimated tokens per request across a 6-turn conversation. There are no summarisation LLM calls. Client-supplied assistant turns and injection attempts in history are ignored.
- **Switching:**
  - Model: all 6 transitions keep context and call only the selected provider (tested); answers keep provider attribution in local history.
  - Language: English↔Hindi and Hinglish switches keep the conversation; the selected language decides the next answer.
- **Not offered:** cross-device sync, user accounts or a server-side chat archive.

## 5. Provider validation (offline, mocked providers)

`python -m evaluation.expanded` runs **92 distinct intents**, each in English, Hindi and Hinglish, including follow-up, provider-switch and language-switch cases. They go through the real chat pipeline with deterministic grounded mock providers. Checks: status and false refusals, required evidence, provider routing, verified links only, video expectations, redaction, and Hindi fallback language.

| Provider | English | Hindi | Hinglish |
|---|---|---|---|
| Sarvam 105B (mocked) | 92/92 | 92/92 | 92/92 |
| Anthropic Haiku 5.5 (mocked) | 92/92 | 92/92 | 92/92 |
| Novita Qwen3.8 Flash (mocked) | 92/92 | 92/92 | 92/92 |

- **Result:** 828/828 checks (100%), **0 critical failures**. The first run scored 90.0%. That run exposed real gaps (Hinglish basics, Hindi and Hinglish terms, follow-up pronouns, ePassport routing, the Smart Share domain term, video deduplication), and the code was fixed for each. Two dataset errors were corrected: a missing valid source (`general_04` for a changed phone) and Hinglish translations that had dropped "Digi Yatra".
- **Expected non-answers:** live flight status, live queue length, weather, injection, and service fee (the approved documents contain no fee statement).
- **Weaker partial answers:** download fee (Hindi/Hinglish), the after-trial question (Hinglish), glasses (Hinglish) and the Hinglish language-switch follow-up are allowed partial outcomes but remain worth checking live.
- **Not measured:** model wording quality, claim correctness and Hindi answer fluency. These are checked only by the live mode (`--live`, signed synthetic route, enforced spending caps), which is **pending**. No real-model results are claimed. P50/P95 of about 0.25/0.5 s is in-process latency with mocks, not production latency.

Earlier real-provider evidence remains in the previous reports (for example the Qwen 49-case and knowledge-matrix runs). No new before/after live examples exist for Task 3.

## 6. Browser tests (local production build + test-only synthetic backend, mocked providers)

`frontend/scripts/history-e2e.mjs` ran against `backend/scripts/e2e_stack.py`, which uses a synthetic database, outbound network blocked, and loopback ports 18731 and 18732. **27/27 checks passed** on desktop (1366×900) and mobile (390×844):

| Scenario | What passed |
|---|---|
| A | Close and reopen the widget |
| B | Refresh |
| C | Browser restart with a persistent profile |
| D | Sarvam → Anthropic |
| E | Novita contextual video follow-up |
| F | English → Hindi |
| G | Clear, including an in-flight answer |
| H | 7-day expiry |
| I | Synthetic Aadhaar and PNR not stored, shown or logged; no credentials in storage |
| J | Separate profile isolation |
| K | Zero outbound attempts while chatting |
| M | Video and official-channel links open from Sources (stubbed) with `rel=noopener` |

**Scenario L** (updated knowledge overrides an earlier answer) was verified by backend test rather than in the browser.

**Note:** a first launch attempt used port 8100, which belongs to another local service. Two read-only health requests reached it before I switched to unused ports. Nothing else touched it.

## 7. Cost and performance

| Item | Value |
|---|---|
| Sync job (projected; measured locally) | About 1–2 min per week, ≤ 30 CPU-seconds, ~280 MB peak → under $0.01 per month at Railway list prices |
| Storage growth (local development) | 157 records, 119 KB of text; SQLite file 0.5 MB; local LanceDB 4.4 MB |
| History-related tokens | ≤ 319 estimated tokens per request in the 6-turn test (budget 600); no summarisation calls |
| External API cost | $0 (no paid APIs; YouTube Data API free quota if enabled) |
| Live provider tokens and costs | **Not measured** (no live runs) |

## 8. Security

See the addendum in `docs/SECURITY_AUDIT_REPORT.md`. Dependency audits are clean (`pip-audit`, `npm audit --omit=dev`). No disruptive testing was done, and this is not a CERT-In certification.

## 9. Final readiness

- **Backend tests:** 678 passed, 5 PostgreSQL-only skipped, 15 live deselected. The baseline was 616 (Task 1) and then 667 (Task 2).
- **PostgreSQL integration:** 182 passed, on a local socket-only server.
- **Frontend:** typecheck, lint and production build pass.
- **Lint:** ruff is clean.
- **Browser:** 27/27.
- **Expanded matrix:** 828/828 (mocked).
- **Private Railway build folders:**
  - `.cache/railway-context` (API, with `railway.toml`) and `.cache/railway-context-sync` (job, **without** `railway.toml`, so the API start command and health check can't apply to the cron service).
  - Both contain the code, migrations 0001–0006, the sync modules, `sync.sh` and the approved corpus only: no raw documents, `.env` files, credentials or tests.
  - The Docker image build is **not verified** (no Docker daemon on Hostinger).
- **Railway configuration:** Config as Code is deprecated and stops being read for legacy services on **2026-12-01** (verified against the official docs). Migrate via `railway config migrate` before then (`DEPLOYMENT_HANDOFF.md` §18). This is an open item.
- **Deployment and scheduler:** the exact commands are in `DEPLOYMENT_HANDOFF.md` §19 (deploy, migrations, flags, initial ingestion, cron service, termination check, manual refresh, logs, disabling, rollback, live validation).
- **Git:** pushed to `feature/official-source-sync` after the pre-push check and a dry run. Not merged and not deployed.

### Remaining risks and blockers

1. The Foundation website is blocked, so the trial FAQs and current airport list need allow-listing or manual captures.
2. 122 records await a content reviewer, and the original manifest's content-owner sign-off is pending.
3. Live model quality in all six provider-language lanes, plus Hinglish, is unverified, as are live costs and latency.
4. The Railway configuration migration deadline is 2026-12-01.
5. The cron service and production flags are unprovisioned, the Docker build is unverified, and the transcripts and the YouTube API key are not yet supplied.
6. Redaction is pattern-based (defence in depth). History is unencrypted on the device and per browser profile.
