# Backend API & Environment

FastAPI service in `backend/`. Bind it to `127.0.0.1` only. The Next.js server proxies `/api/v1/*` to it, so browsers (and SSH tunnels) only need port 3000.

Interactive OpenAPI docs: `http://127.0.0.1:8000/api/docs`

## Endpoints

### `POST /api/v1/chat`

Request (unknown fields are rejected):

```json
{
  "message": "How do I register for Digi Yatra?",
  "conversation_id": "a1b2c3d4-...",
  "history": [{"role": "user", "content": "..."}],
  "locale": "en"
}
```

| Field | Rules |
|---|---|
| `message` | 1–1000 characters; must not be blank |
| `conversation_id` | 8–64 characters from `[A-Za-z0-9_-]` |
| `history` | Optional, at most 20 items. The server keeps its own conversation memory. Client history is used only to recover *user* turns after a restart; client-supplied assistant turns are never trusted. |
| `locale` | `en` or `hi` |

Response `200`:

```json
{
  "message_id": "9f2c…",
  "conversation_id": "a1b2c3d4-...",
  "answer": "Download the official app and register with your Aadhaar-linked mobile number [1]…",
  "status": "answered",
  "sources": [
    {"id": 1, "title": "Digi Yatra Registration Guide — Steps for Registration",
     "source_file": "registration_details.md", "section": "Digi Yatra Registration Guide > Steps for Registration",
     "snippet": "1. Register on the App …", "url": null, "score": 0.57,
     "time_sensitive": false, "verification_status": "not_applicable"}
  ],
  "notices": [],
  "model": "sarvam-105b"
}
```

- **Citations.** `[n]` markers in `answer` refer to `sources[n-1]`. They are produced by the model as `[S#]` references to the retrieved evidence. The server validates and renumbers them, drops any that don't match supplied evidence, and returns only the sources actually cited. An answer with no valid citation is never shown.
- **`status` values:**

  | Value | Meaning | Calls the LLM? |
  |---|---|---|
  | `answered` | Grounded answer | Yes |
  | `insufficient_evidence` | Safe fallback | Yes, or skipped if no evidence |
  | `out_of_scope` | Not about Digi Yatra | No |
  | `refused` | Prompt injection, secret extraction, or a detected leak | No |
  | `greeting` | Greeting or small talk | No |
  | `live_status` | Flight, gate or queue status; can't be answered from static knowledge | No |
- **`notices`:**
  - a PII warning (OTP, Aadhaar, passport, phone, email or PNR was removed before processing);
  - a time-sensitive information warning;
  - a reminder that the assistant can't file or escalate complaints.

### `POST /api/v1/chat/feedback` → `204`

Body: `{"conversation_id": "...", "message_id": "...", "resolved": true}`. It stores only these identifiers, the flag and a timestamp in `backend/data/feedback.jsonl` (no message text). Analytics are a later milestone.

### `POST /api/v1/chat/feedback` — explicit resolution feedback (analytics)

This is the existing feedback endpoint, now backed by the database instead of `feedback.jsonl`.
- **One vote per assistant message.** It is enforced by a unique constraint; repeat submissions return `204` but are never counted twice.
- **Validation.** The message must belong to that conversation, be a real answer (not a greeting or refusal) and be under 24 hours old. Otherwise the endpoint returns `404 unknown_message` or `410 feedback_expired`.
- **Conversation status.** The latest explicit vote sets the conversation's status. "Yes" means `resolved`, with `resolution_seconds` = time of the "Yes" − time of the conversation's **first question**. "No" means `unresolved`. No vote means `unconfirmed`.

### Admin endpoints

All admin endpoints are under `/api/v1/admin` and require a valid session, except login.

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /auth/login` `{email, password}` | Origin check, login throttling | Sets two cookies: `dy_admin_session` (HttpOnly, SameSite=Strict, Secure in production) and `dy_admin_csrf` (readable by the page). Returns `{email, expires_at, csrf_token}`. Errors: `401 invalid_credentials` (same message for wrong password and unknown email), `429 too_many_attempts` (5 failures per email+IP per 15 min), `403 bad_origin`. |
| `POST /auth/logout` | Session + `X-CSRF-Token` header | Revokes the server-side session and clears the cookies. Returns `204`, or `403 csrf_failed`. |
| `GET /session` | Session | `{email, expires_at}`, or `401`. Used by the Next.js middleware and the protected layout. |
| `GET /analytics?days=7\|30` | Session | Dashboard report (below). Returns `422` for any other `days` value. |

Sessions are stored server-side as SHA-256 hashes of random tokens. They expire after 8 hours (absolute) or 60 minutes of inactivity, and are revoked on logout or password reset.

`GET /api/v1/admin/analytics` response:

```json
{
  "range": {"days": 7, "start": "…Z", "end": "…Z"},
  "totals": {"conversations": 3, "questions": 5},
  "resolution": {"resolved": 1, "unresolved": 1, "unconfirmed": 1, "confirmed": 2,
                 "rate_percent": 50.0, "avg_resolution_seconds": 1.7},
  "top_topics": [{"topic": "aadhaar_registration", "label": "Aadhaar registration", "count": 2}],
  "unanswered": [{"topic": "aadhaar_registration", "label": "Aadhaar registration", "count": 1, "keywords": ["fees"]}],
  "out_of_scope_count": 0,
  "daily": [{"date": "2026-11-19", "conversations": 3, "questions": 5}],
  "recent": [{"conversation": "C-63EC2205", "topic": "aadhaar_registration", "topic_label": "Aadhaar registration",
              "questions": 2, "status": "resolved", "started_at": "…Z", "resolution_seconds": 1.7}]
}
```

Metric definitions:

| Metric | Definition |
|---|---|
| Conversations | Conversations whose first question falls in the window and that have at least one question (greeting-only chats are excluded) |
| Questions | Every chat request except greetings |
| Confirmed resolution rate | `resolved / (resolved + unresolved) × 100`. It is `null` when there is no feedback, and unconfirmed conversations are never included. |
| Average resolution time | Mean of `resolution_seconds` over **resolved** conversations only; `null` if there are none |
| Unanswered | Questions with `status=insufficient_evidence`, grouped by topic with allow-listed keywords |
| Daily | Conversations and questions per UTC day, zero-filled |

The values above come from the synthetic acceptance run, which was deleted afterwards.

### `GET /api/v1/health`

Returns:
- index status (document and chunk counts, and which embedder built it);
- whether Sarvam is configured (a boolean only, never the key).

`status` is `degraded` if the index or key is missing.

### Errors

Every error is `{"error": {"code": "...", "message": "<user-safe text>"}}`:

| HTTP | code | When |
|---|---|---|
| 413 | `request_too_large` | Body over `MAX_REQUEST_BYTES` (16 KB) |
| 422 | `validation_error` | Schema violation |
| 429 | `rate_limited` | More than `RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_S` per client IP. Includes a `Retry-After` header. |
| 502 | `assistant_unavailable` | Upstream returned an unusable response |
| 503 | `assistant_unavailable` | Sarvam not configured, auth/quota error, overloaded (after retries) |
| 503 | `index_unavailable` | Knowledge index not built |
| 504 | `upstream_timeout` | Sarvam timed out (after retries) |
| 500 | `internal_error` | Unexpected error (details only in server logs) |

Upstream error bodies are never forwarded, because they could contain request details.

## Request pipeline

1. **Validation and limits:** body size, schema, and per-IP rate limit. `X-Forwarded-For` is trusted only from the local Next.js proxy.
2. **Input guardrails:**
   - redact PII;
   - detect prompt injection and secret extraction (refuse without calling the LLM);
   - classify greetings, live-status requests and requests to file complaints.
3. **Retrieval:** hybrid search over **approved chunks only**:
   - LanceDB vector similarity combined with BM25 keyword ranking and query-term coverage;
   - a minimum score threshold, near-duplicate suppression, at most 2 chunks per source, and top-k (default 5);
   - for follow-up questions, the previous user question is included in the retrieval query.
4. **Off-topic gate:** no evidence, or weak evidence plus no Digi Yatra terms, means `out_of_scope` with no LLM call.
5. **Sarvam `sarvam-105b`** (Chat Completions V2, `POST /v2/chat/completions`):
   - the system prompt holds the rules;
   - retrieved text is wrapped as numbered, **untrusted** `<evidence>`, with flags for time-sensitive and conflicting sources;
   - the model must cite `[S#]` or reply `INSUFFICIENT_EVIDENCE`;
   - an uncited reply gets **one** citation-repair request (the model occasionally omits markers); if it is still uncited, the safe fallback is returned;
   - **sentence-level grounding** (`app/security/grounding.py`): every factual sentence must share ≥40 % of its content words with the evidence it cites (otherwise the citation is re-attributed to a retrieved source with ≥50 % support, or the sentence is dropped); numbers must appear in the supporting evidence; declines/advice are not treated as claims; conflicting sources add a notice;
   - a cited reply that opens by declining ("I cannot determine…") is returned with its sources but with `status: insufficient_evidence`;
   - timeouts and retries use exponential backoff on 429, 5xx and timeouts, and honour `Retry-After`.
6. **Output guardrails:**
   - block system-prompt or secret leaks (checked with a per-process canary and the key value);
   - strip fabricated claims of action ("I have escalated…");
   - remove URLs that are neither in the evidence nor official;
   - validate citations; uncited answers fall back to `insufficient_evidence`.
7. **Logging:** status, source count, top score, PII types and latency. No message text is logged unless `LOG_CHAT_CONTENT=true`. A redaction filter masks the key, ID numbers, phone numbers and emails.

## Environment variables

Backend variables are listed in `backend/.env.example`, and frontend variables in `frontend/.env.example`.

| Variable | Where | Default | Notes |
|---|---|---|---|
| `SARVAM_API_KEY` | backend `.env` only | — | Required for AI answers. Never in frontend env, code, logs or Git. |
| `SARVAM_CHAT_MODEL` | backend | `sarvam-105b` | |
| `SARVAM_TIMEOUT_S` / `SARVAM_MAX_RETRIES` | backend | 35 / 2 | |
| `SARVAM_REASONING_EFFORT` / `SARVAM_MAX_TOKENS` | backend | `none` / 1200 | Live testing showed that with reasoning on, sarvam-105b can spend the whole token budget reasoning and return empty content. If a reasoning call comes back empty, the client retries once with reasoning off. |
| `EMBEDDING_PROVIDER` | backend | `auto` | `auto` uses `embeddinggemma-2` if the key has access, otherwise lexical. Reindex after changing it. |
| `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_SCORE` | backend | 5, 0.15 | |
| `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_S` | backend | 20, 60 | |
| `MAX_REQUEST_BYTES` | backend | 16384 | |
| `LOG_LEVEL`, `LOG_CHAT_CONTENT` | backend | INFO, false | |
| `NEXT_PUBLIC_CHAT_MODE` | frontend | `api` | `mock` works only in `next dev`; production builds always use the real API |
| `TRUSTED_PROXY_HOPS` | backend | 0 | Behind Vercel → Railway use 2 (verify after deploy) |
| `ENVIRONMENT` | backend | development | `production`: Secure cookies, no `/api/docs`, insecure-config start refusal |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | empty | Empty means same origin via the Next.js proxy (recommended) |
| `BACKEND_URL` | frontend (server-side) | `http://127.0.0.1:8000` | Proxy target for `/api/v1/*` |
| `NEXT_PUBLIC_CHAT_TIMEOUT_MS` | frontend | 120000 | |

## Embeddings

- **`SarvamEmbedder`:** hosted `embeddinggemma-2` via `POST /v2/embeddings`, producing 768-dimension neural vectors. This requires Provisioned Throughput.
  - **Probe result for this project's key (2026-11-19):** `HTTP 400 invalid_request_error`, *"This model runs on Provisioned Throughput and is not enabled for your organisation."*
  - The index therefore uses the lexical fallback; `index_meta.json` records the reason.
- **`LexicalEmbedder`:** deterministic hashed TF-IDF over unigrams and bigrams (4096 dimensions, L2-normalised). This is **lexical, not semantic**. It is always combined with BM25 keyword ranking.

The index stores which embedder built it, and queries always use the same one. To migrate, set `EMBEDDING_PROVIDER` and run `python -m app.cli reindex`.
