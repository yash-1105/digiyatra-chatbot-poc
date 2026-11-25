# Official social media, YouTube and transcript knowledge (Task 2)

Status as of 2026-11-25, on integration branch `feature/official-source-sync`. The work is implemented, an initial permitted ingestion has run, and the offline tests pass. **Nothing has been deployed, production scheduling is disabled, and no paid API or new infrastructure is used.** This report is sanitised: it gives counts, public identifiers and public URLs only, with no private documents or credentials.

## 1. Architecture

Social media, YouTube and transcripts are additional **source types in the Task 1 registry**, processed by the **same** short-lived job (`sync-run`, Sunday 03:00 IST, cron `30 21 * * 6`). There is no per-platform service or scheduler. Records go through the same versioning, review, withdrawal, atomic publication and lexical TF-IDF LanceDB index (`backend/app/sync/social.py`, `media.py`; migration `0006_social_media_sources`).

The chat request path never contacts a social platform, YouTube or a caption service. It reads the published local index only and keeps working when those platforms are unavailable.

- **Video records are metadata-only:** they are excluded from the model's evidence, so a title is never treated as proof of a procedure. `Retriever.related_videos` recommends at most one verified video when the user asks for one, or when a procedural answer benefits from one.
- **Matching:** it uses concept groups taken from the **title** (registration, Aadhaar, DigiLocker, dependents, delete, boarding pass, privacy, ePassport, Smart Share). Every specific concept in the question must appear in the title. Otherwise no video is offered, which is the honest outcome for ePassport, boarding-pass and international-trial questions today.
- **Links:** every link comes from a verified record (`https://www.youtube.com/watch?v=ID`, plus `&t=SECONDS` only for imported transcript passages).
- **Shared by all providers:** Sarvam 105B, Anthropic Haiku 5.5 and Novita Qwen3.8 Flash share this knowledge. Their configurations are unchanged.
- **Frontend:** the existing Sources panel shows the source type, platform, date and timestamp. There are no embeds or widgets, and the generated-answer badge was not reintroduced.

## 2. Official accounts and verification

| Platform | Account (stable ID) | Status | Evidence | Collection |
|---|---|---|---|---|
| YouTube | @DigiYatraFoundation (`UCAW0wpe_OvaAe3M6EKRGMJw`) | verified | All 7 videos linked from approved Digi Yatra documents are on this channel (oEmbed `author_url`) | Data API v3 when a key is set; otherwise oEmbed checks of known video IDs |
| X | @DigiYatraOffice (handle; a numeric ID needs the X API) | verified | Embedded on the MoCA website (2 pages); oEmbed author "Digi Yatra Official" (one-time manual check) | Posts embedded on civilaviation.gov.in; X API is paid (not enabled) |
| X | @MoCA_GoI, @PIB_India, @AAI_Official | verified (government) | Embedded on the Ministry's own website | Same |
| X | @RamMNK | **excluded** | Personal account | Not ingested |
| LinkedIn | company `digiyatrafoundation` | verified | Linked from approved documents; approved LinkedIn-derived documents | **Blocked** (HTTP 403 / login); organisation export import only |
| Instagram | `digiyatrafoundation` (candidate) | **unverified** | None found (Foundation website blocked) | Login wall; imports refused until verified |
| Facebook | none confirmed | **unverified** | None found | Login wall |

Look-alike handles, fan pages, comments and private messages are never ingested. Official YouTube playlists are discovered only with the Data API, which is not enabled here.

## 3. Permitted collection mechanisms (and what is not used)

| Mechanism | Used? | Reason |
|---|---|---|
| Official posts embedded on civilaviation.gov.in pages | **Yes** (automated, weekly discovery) | Government page already crawled under Task 1 rules |
| YouTube Data API v3 (channels, playlistItems, playlists, videos, captions **list**) | Implemented, **inactive** (no key) | Official; free quota |
| YouTube oEmbed (`/oembed`) for known IDs | **Yes** | Documented endpoint, permitted by robots.txt |
| YouTube channel pages, `/feeds/videos.xml`, `/timedtext_video` | **No** | Feeds and timedtext are disallowed by youtube.com/robots.txt; the terms prohibit scraping |
| Caption download (`captions.download`) | **No** | Requires the channel owner's OAuth consent |
| X oEmbed (`publish.x.com/oembed`) | **No** | robots.txt disallows `/oembed` |
| X API / LinkedIn API / Meta Graph API | **No** | Paid, or organisation permission or app review required |
| Audio download / Whisper / paid speech-to-text | **No** | Not needed (see §8) |

## 4. Initial ingestion (local development database, 2026-11-25)

**Scope:** official channels, the YouTube channel and the 22 MoCA pages already discovered in Task 1. Run time 58.6 s wall, 2.7 s CPU, peak 271 MB, 30 HTTP requests, 0 failures.

| Result | Count |
|---|---|
| Posts discovered from verified official accounts (on MoCA pages) | 11 |
| Posts excluded (personal account, greetings, thank-you posts, events, contests) | 5 + 1 personal |
| Historical posts (older than 365 days; stored, never served) | 7 |
| Posts pending review (consequential: airport coverage, registration or voluntariness) | 4 |
| Posts verified and indexed | 0 (all current posts are consequential and need a reviewer) |
| Videos discovered and verified (oEmbed, approved-corpus IDs) | 7 |
| Videos indexed (metadata-only, verified, low risk) | 7, in the local publication only |
| Official channel records (verified, indexed) | 6 |
| Authorised transcripts available | **0** (none supplied; caption download not authorised) |
| Transcript-derived records | 0 |
| Storage growth | about 24 records and roughly 12 KB of text in PostgreSQL |

**Videos:** registration (3 Steps / Aadhaar / DigiLocker), adding a dependent or minor, deleting a credential, Smart Share, and self-sovereign identity and data safety. With no Data API key, durations, descriptions, playlists and publication dates are unknown, and all videos are recorded as `metadata_only`.

A post that stated "38 airports" was briefly auto-verified locally because it lacked a launch keyword. The classifier was fixed so that any airport count is consequential, and the two local approvals were revoked.

The local publication (development only) has 15 verified official records. The index holds 134 chunks: 119 from the original approved corpus plus 15 official records. Production publication is empty until review.

## 5. Example answers (mocked provider, local index)

These were produced through the real chat pipeline with a **mocked** model that echoes the first evidence sentence. They show retrieval and link behaviour only, not live model quality.

- **"Is there an official video showing how to register?"** → the answer leads with "Yes — the official Digi Yatra Foundation video 'Enrol on the Digi Yatra App in 3 Simple Steps …': https://www.youtube.com/watch?v=-nlJBCwg0nM", followed by the grounded registration answer. The video appears in Sources as "YouTube video".
- **"How do I add my child to Digi Yatra?"** → the grounded answer plus "HOW TO ADD A DEPENDENT/MINOR" (https://www.youtube.com/watch?v=j2lw7LljME0).
- **"Where can I follow official Digi Yatra announcements?"** → the official channel record for @DigiYatraOffice (https://x.com/DigiYatraOffice), shown as "Official channel".
- **"Is there a video explaining privacy?"** → "SELF-SOVEREIGN IDENTITY | DATA SAFETY WITH DIGI YATRA" (https://www.youtube.com/watch?v=Wlc6iqgwQDU).
- **"Is there an official international passenger trial video?"** → no video is offered, because none is verified; the existing cautious trial response is returned.
- **Hindi "पंजीकरण का वीडियो दिखाइए"** → the Hindi video line linking the official registration video.

## 6. Scheduling

- **Weekly (7 d):** discovery of MoCA pages carrying official posts (`moca-search-en/hi`), and any organisation social imports.
- **Fortnightly (14 d):** the YouTube channel (new uploads, metadata and availability; removed videos are withdrawn and transient errors keep the last known good), the official-accounts registry, and re-checks of discovered pages.
- **Transcripts:** processed when an authorised caption file is imported; reprocessed only if the file changes, and a corrected file supersedes older passages.
- **Configuration:** all intervals and limits are configurable (`SYNC_*`). Manual urgent refresh: `sync-run --source ID`.
- **Implemented vs active:** implemented in the existing job. **Production scheduling is disabled and the cron service is not provisioned.**

## 7. Records, states and review

- **Stored per record:** platform, post or video ID, account ID and name, permalink, publication and modification dates, relevant text, language, topic, referenced URLs, media metadata (duration, playlists, languages, caption tracks, transcript status and type), content hash, verification state, effective and expiry dates, and claim type (announced / pilot / future / proposed / operational-or-general).
- **States:** discovered → `pending_review` / `conflict` → `verified` (social, transcript or metadata-only video) → `superseded` / `withdrawn` / `historical` / `rejected`.
- **Review rules:** consequential topics (airports, airlines, international, privacy, registration, advisories) and all transcript passages require a named reviewer. They carry the flag "confirm consequential claims against formal official documentation". A promotional post can never override policy: it isn't auto-approved, and verified government and approved documents remain the primary evidence. Usage statistics are removed with the Task 1 filter, and the private review pack (`sync-review-report`) groups these records like the others.

## 8. Transcripts and audio

- **Supported input:** creator-provided or organisation-supplied WebVTT or SRT files via `sync-import-transcript VIDEO_ID --file F --kind human|auto [--language en|hi]`.
- **Processing:** timestamps are preserved; rolling automatic-caption repeats and `[Music]` tags are removed; text is grouped into passages of about 75 s; statistics are stripped and injection is screened.
- **Flags:** automatic captions are flagged ("verify airport names, technical terms and numbers"), and videos older than two years are flagged as possibly outdated demonstrations.
- **Links:** passages link with `&t=SECONDS`.
- **No LLM processing:** deterministic only, so there are no model costs and no unsupported generated facts.
- **Audio transcription:** not enabled and not proposed. The approved written documents and the video titles already cover the passenger topics. If later approved, an offline CPU model on a short-lived job would be the economical option, but it would need explicit permission and a benchmark first.

## 9. Costs and resources

| Run | Wall | CPU | Peak RAM | Requests |
|---|---|---|---|---|
| Initial social/YouTube ingestion | 58.6 s | 2.7 s | 271 MB | 30 |
| Incremental (nothing changed) | 58.5 s (mostly 2 s per-host politeness gaps) | 2.5 s | 172 MB | 30 |

The job's own usage estimate is about $0.00006–0.00008 per run. Combined with Task 1, the job stays well under $0.01 per month at Railway list prices. External API costs: **$0**. The YouTube Data API, if enabled, uses free quota: about 5–20 units per run plus 50 per caption-track listing, capped at 10 checks per run, out of 10,000 per day. There is no Redis, no extra database, no always-on worker and no embedding model.

## 10. Security and privacy

- Social, video and transcript text is untrusted evidence: it is injection-screened, never used as instructions, and never triggers actions.
- Only allow-listed hosts are contacted. On YouTube only the `oembed` endpoint is called, and on Google only the official Data API.
- SSRF, redirect, size and time limits, and robots.txt rules from Task 1 all apply.
- The API key is never stored or logged (tested).
- No comments, direct messages or personal data are collected, and passenger questions never leave the API.

## 11. Tests

- **Backend (offline):** 667 passed (654 existing + 13 new Task 2 tests), 0 failed, plus 5 PostgreSQL-only tests skipped on SQLite. On a local socket-only PostgreSQL 16.2: 135 passed, covering the sync, social, analytics, API and admin suites and migrations 0005 and 0006.
- **Frontend:** typecheck, lint and production build pass.
- **New tests cover:**
  - account verification and look-alike handles
  - extraction, classification and exclusions
  - initial discovery with review, cross-page post deduplication and modified posts (versioning)
  - social exports with withdrawal, plus refusal of unverified platforms and invalid permalinks
  - oEmbed mode: verification, impostor channel, 404 withdrawal, transient errors keeping the last known good
  - API mode: metadata, durations, playlists, caption-track availability with no download, quota note, cursor, key never persisted
  - VTT/SRT parsing, rolling-caption deduplication and grouping
  - transcript import: timestamps, review, no reprocessing of unchanged files, corrections
  - timestamp URL safety
  - source failures, persistence and lease release
  - the network-free account registry
  - provenance, video exclusion, expiry and FAQ-cache revision invalidation
- **Chat isolation:** **90 chat requests** (10 representative questions × English/Hindi/Hinglish × the 3 mocked providers) ran with DNS, sockets and all ingestion code blocked. They made **zero** external requests, every link was verified, and none was fabricated. The registration and privacy videos were recommended, no trial video was invented, and the channel record was returned for the "follow" question.
- **Live model verification is pending:** there are no development keys on this server, and production keys were not copied.

## 12. Credentials and permissions needed (do not share them in chat)

1. **Optional, recommended: a YouTube Data API v3 key.** Create a Google Cloud project, enable "YouTube Data API v3", create an API key restricted to that API, and set it as `YOUTUBE_API_KEY` on the future cron service. This enables upload, playlist, description, duration and caption-availability discovery. It costs nothing within the free quota.
2. **Transcripts:** the Digi Yatra team exports caption files (YouTube Studio → Subtitles → download .vtt/.srt) and supplies them via SFTP. Automated caption download would instead need the channel owner's OAuth consent for this application, which is not requested.
3. **LinkedIn / X / Instagram / Facebook:** organisation-provided exports (JSON/CSV with `url`, `published`, `text`, optional `language`, `withdrawn`), imported with `sync-import-social`. Automated access would need LinkedIn Community Management API approval from an organisation admin, a paid X API plan, or Meta app review plus business-account tokens. None of these is requested. Instagram and Facebook also need an official website reference before any import.

## 13. Git and deployment

- **Branch:** commits are pushed to `feature/official-source-sync` (unmerged), after review of the staged files, the pre-push check and a dry run. No transcripts, exports, private knowledge, development databases or credentials are committed.
- **Private Railway build folder:** `.cache/railway-context` is rebuilt with the existing script.
- **Deployment:** nothing is deployed. Production enablement follows `DEPLOYMENT_HANDOFF.md` §17 (migration 0006 runs at start-up). The Railway configuration migration before 2026-12-01 remains a separate open item.
