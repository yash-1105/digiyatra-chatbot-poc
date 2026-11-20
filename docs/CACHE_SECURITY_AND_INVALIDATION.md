# Reviewed FAQ cache security and invalidation

## Eligibility and provenance

The cache domain is separate from LanceDB and has no public write endpoint. Startup verifies the bundled approved corpus before initializing lookup. The runtime exact match list starts with public app platform and download questions. It uses Unicode NFC, lowercase text, collapsed whitespace and one optional trailing question mark. It preserves qualifiers, dates, locations, negations, numbers and other punctuation. It never performs fuzzy matching, language inference or translation for cache hits. Each allowed wording and output locale has its own reviewed row.

Requests with server or submitted history, detected personal data, prompt injection, live status, greetings or action requests bypass lookup. Questions outside the static list bypass PostgreSQL lookup. Only preapproved public match keys are sent to the cache query. Cache access shares the existing request, abuse and anonymous session controls. The answer uses the selected provider label and a null model, with `cached=true` and ordinary citation fields. No provider usage row is written on an FAQ hit.

Publishing and lookup both validate source approval, membership in the current corpus, chunk ID, chunk hash, original document hash, citation order, sentence grounding and allowed links. Conflict-bearing, unverified and time-sensitive passages are excluded. Review also checks factual completeness, required caveats, language and public redistribution rights. Grounding is an extra runtime check. It cannot authorize an answer or a reviewer. The required human approval comes from the restricted publishing workflow.

The server binds the cache payload and revocation state to an HMAC-SHA-256 signature. Provision `FAQ_CACHE_SIGNING_KEY` as a dedicated random secret of at least 32 bytes through the existing private configuration system when approved for rollout. The signing key is separate from provider credentials and anonymous-session secrets. No arbitrary question text, digest or passenger identity is inserted into cache or usage tables. Do not put the signing key, review bundle or private source material in GitHub, shell history or application logs.

## Versioning and failure behavior

Effective knowledge version hashes the corpus bytes, manifest hash, approved document hashes, deterministic indexed revision, answer rules revision and system prompt without its random canary. Bump `ANSWER_RULES_REVISION` when approval, eligibility, output filtering or applicable answer rules change. Published entries bind to this version, explicit source hashes and a UTC expiry. A corpus change invalidates the previous version conservatively across all rows. A changed live LanceDB table version disables lookup for that process until normal indexing and restart. Refresh the deployed approved corpus and restart the service to advance its knowledge version. Coordinate any temporary deployment overlap by leaving the FAQ flag off for a source withdrawal until old instances are drained.

Lookup verifies signature and state, and stale, revoked, tampered, unverifiable or unavailable rows go through normal RAG. A PostgreSQL statement timeout and a bounded lookup wait protect the request path. Outcome telemetry records only coarse categories, provider/locale and aggregate timing. Cache timeouts and absence of a signing key have the same safe fallback.

## Private publication and maintenance

1. Verify that the reviewer can approve public redistribution and that the deployment is on the current approved corpus. Export no private corpus content as part of the review record in GitHub.
2. With the target corpus, schema and private signing key present, run `python -m app.cli faq-version` for the knowledge version and `python -m app.cli faq-source CHUNK_ID` for each approved citation reference.
3. Prepare a private JSON array. Each entry has `question`, `locale`, `intent` (`app_download`), `answer` with numbered `[1]` citations in source-list order, `sources` from the CLI, `knowledge_version`, increasing `revision`, authorized `reviewer` identifier, `eligibility` (`public_static`), `origin` (`human_reviewed`) and `expires_at` in UTC without a timezone suffix. The publication TTL is at most 30 days. Use a private operator identifier in reviewer metadata.
4. Run `python -m app.cli faq-publish /private/path/reviewed.json` from the backend with the target database configuration. PostgreSQL serializes publishers and commits the bundle atomically. Reapplying the identical active revision is idempotent. Review and publish a higher revision for a changed, expired or revoked entry. The CLI never publishes generated chat answers.
5. Enable `FAQ_CACHE_ENABLED` only after smoke checks for the reviewed hits, wrong-language misses, forged content, source withdrawal and rollback. Use `python -m app.cli faq-revoke 'Canonical public question' --locale en` for individual revocation. Set `FAQ_CACHE_ENABLED=false` for immediate feature rollback on service restart. Invalid or retired rows can remain for audit. Restoration does not require clearing the knowledge index or resetting PostgreSQL.

The production corpus still carries pending final content-owner sign-off. The benchmark used one local public-platform fixture in a disposable database. Its publication status does not transfer to production.
