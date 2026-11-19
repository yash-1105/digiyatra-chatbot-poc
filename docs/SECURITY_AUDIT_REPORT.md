# Internal security assessment — Digi Yatra information assistant

**Assessment date:** 19 November 2026

**Public target:** https://digiyatra-chatbot-poc.vercel.app

**Repository:** https://github.com/yash-1105/digiyatra-chatbot-poc

**Verdict:** **CONDITIONAL PASS**

This is an independent internal technical assessment. It is **not CERT-In certification**, an empanelled-auditor attestation, a complete ASVS certification, or a declaration of regulatory compliance. No confirmed Critical/High vulnerability remains within the verified scope. Residual database privileges and assurance gaps require owner action.

## Executive summary

Controlled reproduction confirmed four Medium issues: Unicode-obfuscated sensitive values bypassed redaction; source-link prefix validation accepted lookalike origins; anonymous conversation/feedback state lacked a browser ownership boundary when identifiers were shared; and limiter/authentication resource controls were insufficiently bounded. These were remediated and regression tested. Two Low control gaps—multi-provider/exception log redaction and missing browser CSP—were also addressed.

A Medium database least-privilege issue remains: the application's database principal has superuser capabilities. Changing credentials or database principals was outside the authorized remediation scope. Repository protection and build-integrity improvements remain Low-priority follow-ups.

The redesigned frontend, animated hero, assistance launcher, provider/language selection, retrieval/citations, admin analytics and existing API schemas remain. No billing configuration, credentials, production records, schema, approved knowledge content or resource count was changed. The private corpus remains excluded from GitHub.

## Scope and methodology

Reviewed the Next.js frontend/proxy, FastAPI routes, request/output handling, both provider clients, RAG ingestion/index/retrieval, conversation/cache behavior, admin authentication, analytics, deployment files and public Git history. Performed targeted source tracing, Bandit static analysis, pinned-dependency audits, historical secret matching/pattern scans, isolated vulnerability reproduction, full automated regressions, read-only deployed configuration/privilege inspection, controlled HTTP/browser checks and real-model evaluation.

Production testing excluded flooding, password guessing, credential changes, data deletion, poisoning the live corpus, admin sign-in/session creation and analytics mutations. State-changing/abuse tests used synthetic databases, mocked transports or in-memory instances. Signed synthetic live inference used the existing operator evaluation facility without production analytics persistence. Private evidence is retained locally in an ignored, access-restricted audit directory; it is not included here.

Findings are confirmed only to the evidence stated. Missing organizational evidence, unscanned components and finite adversarial coverage are identified separately. This is a risk-based technical assessment across the requested standards, not an exhaustive control-by-control attestation.

## Standards and CERT-In mapping

References verified during the assessment:

- [CERT-In AI Security Auditing Guidelines v1.0, 4 November 2026](https://www.cert-in.org.in/PDF/AI_Security_Auditing_Guidelines.pdf) (107-page primary document reviewed locally).
- [CERT-In Comprehensive Cyber Security Audit Policy Guidelines v1.0, 25 July 2025](https://www.cert-in.org.in/PDF/Comprehensive_Cyber_Security_Audit_Policy_Guidelines.pdf).
- [OWASP ASVS 5.0.0](https://asvs.owasp.org/), [WSTG 4.2](https://owasp.org/www-project-web-security-testing-guide/), [API Security Top 10:2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/).
- [OWASP LLM Top 10:2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/). The 2026 ordering is used, rather than silently reusing the 2025 numbering.

**Provisional AI tier: Tier 2 / Moderate.** This public assistant influences passenger interactions and uses paid external inference, but does not perform biometric verification, authorize airport entry, operate gates, book flights or execute autonomous tools. This is an auditor's conservative applicability assessment; formal organizational risk scoring/sign-off was not supplied. Critical operational deployment or consequential automated decisions would require reassessment.

| AI assurance area | Evidence / remaining obligation |
| --- | --- |
| Ownership and governance | Technical scope and model allowlists inspected; formal accountable-owner/risk acceptance evidence pending. |
| Data handling | Redaction, synthetic analytics isolation and approved-corpus controls tested; organizational retention/deletion policy needs approval. |
| Model assurance | Both clients and shared guardrails tested; Sarvam evaluated live; Anthropic live inference remains credit-blocked. |
| Fairness | English/Hindi/Hinglish functional/adversarial samples; no demographic fairness certification or comprehensive harm study. |
| Transparency | Independent-site/AI disclosures, actual source citations and snapshot qualification inspected. |
| Adversarial protection | Input/output, authorization, Unicode, origin, token and resource controls tested; finite coverage does not prove injection immunity. |
| Ongoing validation | Usage counters, cache revision binding and regression tests inspected; SOC/drift/incident evidence not supplied. |
| Human control | No model tools or consequential actions; official-support fallback retained. |
| Vendor/build assurance | Dependencies/history checked; provider contracts, retention configuration, OS-image scanning and provenance need further evidence. |

Application testing covered ASVS authentication/session/access-control/input/output/configuration/logging areas and the WSTG configuration, identity, authorization, injection and client-side topics. API testing addressed object/function/property authorization, consumption, sensitive flows, SSRF, configuration, inventory and upstream-response handling. LLM testing covered injection, disclosure, agency, supply chain, poisoning, consumption, misinformation, hidden context, vector controls and output handling. Not every individual requirement was independently attested.

## Confirmed findings

### SEC-01 — Medium — Sensitive-input normalization bypass (fixed)

- **Location:** `backend/app/security/guardrails.py:106`; `backend/app/rag/multilingual.py:342`.
- **Cause:** invisible format characters and inconsistent digit/marker normalization defeated selected PII patterns. Explicit password/passcode assignments also lacked dedicated redaction.
- **Reproduction/evidence:** isolated `test_format_obfuscated_identifiers_are_redacted_before_inference` cases failed before remediation. Synthetic Aadhaar/OTP representations reached the redaction result unmasked. No real passenger identifier was used or production leakage established.
- **Impact:** otherwise recognizable sensitive input could reach external inference or conversation memory.
- **Remediation:** security canonicalization before matching; retain ordinary Hindi letters/marks; normalize numeric variants; remove invisible controls; recognize additional supported separators/OTP forms and explicit credential assignments. Production message-content logging is now refused. Relevant existing bilingual and benign-question tests pass.

### SEC-02 — Medium — Official-link lookalike origins accepted (fixed)

- **Location:** `backend/app/security/guardrails.py:170`.
- **Cause:** string-prefix validation confused a trusted origin with attacker-controlled suffix/userinfo/port variants.
- **Reproduction/evidence:** `test_official_link_prefix_is_not_an_origin_allowlist` used non-routable synthetic domains. Three disallowed variants survived the old filter and are now removed; genuine approved/store URLs remain valid.
- **Impact:** a manipulated model response could present a misleading clickable link as an official resource. No SSRF or arbitrary server-side URL fetch was demonstrated.
- **Remediation:** compare parsed scheme, hostname, userinfo and expected HTTPS port; retain exact approved-source URLs. Existing citation/grounding checks remain.

### SEC-03 — Medium — Anonymous conversation/feedback isolation (fixed)

- **Location:** `backend/app/api/routes/chat.py`; `backend/app/security/anonymous.py:18`.
- **Cause:** client-supplied conversation IDs alone selected server memory; feedback accepted conversation/message ID possession without an additional browser boundary.
- **Reproduction/evidence:** isolated clients reusing a synthetic ID caused one visitor's question to appear in the other's model history; a second cookie-less client could vote on a known synthetic message. This depended on identifier knowledge; guessing production UUIDs or extracting real conversations was not demonstrated.
- **Impact:** cross-browser context mixing or feedback manipulation if identifiers were shared, predictable or disclosed.
- **Remediation:** opaque host-only Secure/HttpOnly/SameSite session capability binds internal conversation and feedback identifiers. Responses retain the public conversation ID and unchanged JSON schema. Cookie state is separate from admin authorization and does not bypass rate limits. Operator evaluation follows the same ownership path with separate no-write storage. Provider-error responses preserve the session so retries do not fragment conversation analytics.
- **Compatibility note:** normal same-origin frontend requests retain cookies automatically. API consumers must retain the anonymous cookie. Previously open, pre-upgrade messages may no longer accept feedback; existing rows were not rewritten or deleted. Starting a fresh conversation restores the normal flow.

### SEC-04 — Low — Log redaction coverage gap (fixed)

- **Location:** `backend/app/logging_config.py:18`, `:36`, `:51`; `backend/app/config.py:131`.
- **Cause:** exact secret redaction focused on one provider and did not sanitize separately formatted exception tracebacks. Raw content logging could be enabled in production.
- **Evidence:** synthetic log records/exception tests confirm all configured provider/proxy secrets and database URL are masked, including tracebacks. Production raw-content logging is rejected. No actual credential leak was found in the reviewed evidence.
- **Remediation:** multi-secret redaction using the app's actual settings, exception/stack sanitization and fail-closed production logging configuration. Platform access-log handling is a separate assurance item.

### SEC-05 — Low — Missing browser content security policy (fixed)

- **Location:** `frontend/next.config.ts:3`.
- **Evidence:** baseline live homepage lacked CSP. Remediated live responses include the policy; browser/renderer checks pass.
- **Impact:** absent defense in depth against content injection; no exploitable XSS was established.
- **Remediation:** constrain resource origins, objects, base URLs, framing and form targets. Next.js currently needs inline scripts/styles, so `unsafe-inline` remains; this is not a nonce-based, strict-XSS-prevention claim. Existing HTTPS/security headers are preserved.

### SEC-06 — Medium — Authentication/limiter resource state (fixed)

- **Location:** `backend/app/services/auth.py:153`; `backend/app/security/rate_limit.py:15`; `backend/app/api/routes/admin.py:62`.
- **Cause:** checking unknown login identities allocated persistent throttle entries; old rate-state cleanup was not a hard bound; expensive password checks lacked a separate in-flight cap.
- **Reproduction/evidence:** 1,000 isolated in-memory checks created 1,001 old entries versus zero after the fix, with **zero network requests**. Capacity tests verify fail-closed identity saturation. A mocked concurrent-login test verifies that excess parallel hashing is rejected without allocating real Argon2 memory for a stress test.
- **Impact:** avoidable memory growth and potential authentication resource exhaustion at scale. Production exhaustion was neither attempted nor observed.
- **Remediation:** bounded identity maps, expiry cleanup without allocating empty identities, fail-closed saturation and a small non-blocking password-hashing concurrency cap. Normal login/throttle/session regressions pass.

### SEC-07 — Medium — Excessive application database privileges (open)

- **Affected component:** deployed application database principal; not an application SQL-injection finding.
- **Evidence:** an authorized read-only privilege query confirmed superuser/role-administration capability. No credentials, role names, connection endpoints or row data are published here.
- **Impact:** a future application compromise would have broader database authority than normal application operations require.
- **Remediation:** owner-managed migration to a least-privileged runtime principal, separating migration authority. Credential/principal changes were prohibited in this engagement and were not performed. Private evidence contains the reproducible read-only query.

### SEC-08 — Low — Repository change-control gaps (open)

- **Affected component:** repository settings.
- **Evidence:** authenticated read-only API inspection confirmed the default branch lacks protection and automatic dependency security updates are disabled. Provider secret scanning and push protection are enabled; no secret alerts were returned.
- **Impact:** review/check enforcement depends on maintainers' manual process.
- **Remediation:** owner-approved required reviews/checks and a dependency-update workflow. Settings were not changed in this assessment.

### SEC-09 — Low — Build provenance hardening (open)

- **Location:** `backend/Dockerfile:4`; `backend/requirements.lock`.
- **Evidence:** runtime packages are version-pinned, but the base image uses a mutable tag and Python installs lack artifact hashes. No malicious package/image or known Python dependency vulnerability was found.
- **Impact:** weaker reproducibility/provenance assurance than digest/hash-controlled builds.
- **Remediation:** adopt reviewed image digests, dependency hashes and scheduled OS-image scanning. Do not blindly pin an unreviewed digest; no build-tool migration was introduced here.

## Tests and scan results

| Assessment | Result and limits |
| --- | --- |
| Full backend suite | **405 passed**, 15 live-marker tests deselected; security/auth/CSRF/session expiry/revocation, SQL literal handling, forged sessions, approval filters, corrupted/draft corpus, citations, caching, token/rate/provider controls included. |
| Frontend checks | Typecheck, lint and production build passed. The visual change passed **80/80** responsive checks. |
| Static Python analysis | Bandit scanned application/ingestion code; one Low `B101` assert finding triaged as a checked-configuration type invariant, not an authorization bypass. No Medium/High static finding. |
| Python dependencies | `pip-audit` on all **43 pinned lock entries**: zero known advisories at scan time. No-deps/lock audit does not validate OS packages or malicious-but-unreported packages. |
| npm dependencies | npm audit: **zero known vulnerabilities**, 405 reported dependencies including development/optional entries. No dependency change needed. |
| Git history | **332 reachable blobs across 23 commits through `0c081de`** scanned for current-secret exact matches, credential/hash/private-key patterns and forbidden payload paths: zero findings. Not a proof about unreachable remote objects or every historical secret format. |
| GitHub secret scanning | Enabled with push protection; zero returned alerts. |
| Controlled public HTTP checks | **24 baseline and 24 post-remediation requests**: admin APIs denied, forged admin cookie denied, unsafe request/model fields rejected, tested environment/Git/private-corpus/schema paths unavailable; hostile CORS preflight not authorized. CSP absent before/present after. No brute force or analytics writes. |
| Live browser/renderer | **17/17 checks** passed for CSP, assistance callout, heading motion/reduced motion, chat opening/viewport, literal HTML rendering and non-executable script/JavaScript-URL text. |
| Live adversarial API samples | **13/13 checks** passed: direct/Hindi/Unicode/draft extraction refused consistently for both provider selections; live-operation requests did not invent status; normalized sensitive input withheld from displayed answers; secure host-only browser isolation verified. Actual paid Anthropic inference remained unavailable. |
| Real Sarvam regression | **39/39** deployed-runtime cases passed after the main fixes, with synthetic DB/feedback; module hashes matched source. Final release: **8/8** focused cases passed, all 48 deployed Python modules matched source, and synthetic feedback returned 204. |
| Live Anthropic | Actual benign inference returned a safe unavailable response due to insufficient credits. Its transport, payload, failure isolation, shared guardrails and mocked security tests passed. Real Anthropic answer quality remains **unverified**. |

## Infrastructure/privacy observations and boundaries

Read-only inspection verified production startup checks, disabled raw chat logging, secure-cookie settings, configured production origins, private TLS database connectivity, and a non-root serving process. No public database URL/TCP proxy was observed in the inspected service configuration; this is not a full external port-discovery assertion. No arbitrary fetch, command-execution, file-upload or model-tool API was identified. ORM value binding and literal input behavior were inspected/tested; no SQL injection, SSRF, command injection, stored/reflected XSS or admin privilege escalation was confirmed.

Analytics persist category/allowlisted keyword/status/timing/usage metadata, not message bodies. Conversation memory and browser session storage do hold transient user text; redaction is pattern-based and **not a guarantee of universal PII recognition**. Cache eligibility is a narrow non-personal FAQ allowlist scoped to corpus revision/provider/language. Expired analytics/session-row deletion schedules, backups and vendor/platform access-log retention need an approved policy; none was invented or enforced by deleting production data.

The approved-only corpus integrity/status checks and draft exclusion passed. Content-owner release sign-off remains an organizational evidence gap; retrieval approval is not GitHub redistribution permission. No private corpus or raw documents were published. No live poisoning or training-data access was attempted.

Provider request text/evidence is transmitted to the selected external inference service. [Anthropic's published commercial retention policy](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) describes a standard period with exceptions/contract variations; it does not establish this account's terms. [Sarvam's platform documentation](https://docs.sarvam.ai/api/platform/faq) describes owner-controlled training/retention settings. Actual workspace choices, key scopes, DPA/ZDR terms, subprocessors and deletion assurances were not available for verification. Do not promise zero retention or no training without that evidence.

OS-layer CVE scanning of the deployed image/filesystem, host isolation/patching, cloud IAM/MFA, private backups, SOC monitoring, penetration from inside provider networks, comprehensive fairness evaluation and an exhaustive human/multilingual red team were not completed. The mutable-base-image issue and this OS-scan gap must not be confused with the clean Python/npm advisory results.

## Incident-reporting and organizational requirements

For an operator within the covered entity categories, the [CERT-In Directions of 28 April 2022](https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf) include reporting specified incidents within six hours, a designated contact, appropriate time synchronization, and secure 180-day logs maintained within Indian jurisdiction. This audit has not established the operator's legal category or verified incident drills, contact registration, clock-source attestations, India-resident archives, retention/export controls or platform contracts. Application tests and cloud deployment locations do not establish compliance. The owner must obtain the relevant organizational/legal evidence and approve risk acceptance.

## Release status and final verdict

UI commit `933db60` was committed/pushed separately. Security implementation commits are `00c0a93`, `1dcd0dd` and `0c081de`. Deployments preserve the existing public frontend, one backend and the existing database, without billing or credential changes. No new database migration was introduced.

The final Railway release for `0c081de` succeeded. All **48 runtime Python module hashes** matched the local source; **8/8** focused real Sarvam regressions and **13/13** public synthetic security checks passed again. The production schema revision remained unchanged. A fresh-browser Anthropic failure returned 503 with the expected Secure, HttpOnly, SameSite=Strict, host-only anonymous cookie; the provider-credit limitation remains. Vercel deployment is ready with the assistance callout, staggered hero reveal and CSP; desktop/mobile screenshots and **17/17** live browser checks passed. The frontend source is unchanged by the two subsequent backend-only commits.

The in-memory rate limits assume the current single worker/replica and reset on restart; they are not a distributed abuse or absolute spending ceiling. No billing settings were checked or changed. **CONDITIONAL PASS** remains appropriate because the database privilege issue and assurance gaps are unresolved, even though no confirmed Critical/High finding remains in the tested scope. Re-test after owner-managed privilege/provenance/governance changes and whenever models, corpus, dependencies or exposure materially change.
