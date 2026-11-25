# Manual import of Digi Yatra Foundation pages

`digiyatrafoundation.com` blocks automated access from the Hostinger server (CloudFront HTTP 403, including `robots.txt`). This authorised workaround uses pages that an operator saves from a normal browser session. The captures go through the same extraction, validation, review, publication and indexing pipeline as automated fetches.

## 1. Pages to save

| Priority | Page | Registered as |
|---|---|---|
| 1 | `https://digiyatrafoundation.com/international-passenger-trial` | `dyf-international-trial` |
| 2 | `https://digiyatrafoundation.com/digi-yatra-implementation-current/` (supported airports) | `dyf-airports-current` |
| 3 | The Foundation's FAQ page(s), reached from the site menu (e.g. "FAQs") | registered on import with `--url` |
| 4 | Pages on registration / how it works, privacy / data protection, help / support / troubleshooting, airports, airlines, children / dependents, and dated news or announcements | registered on import with `--url` |

Import with `--url` accepts only `digiyatrafoundation.com` pages whose first path segment contains one of these keywords: faq, about, how, register, registration, aadhaar, digilocker, boarding, face, privacy, data, security, support, help, troubleshoot, airport, airline, international, trial, child, dependent, news, announcement, press, update, implementation, passenger, journey. Do not save careers, tenders, media galleries or login pages; they are refused.

## 2. How to save (preferred format: HTML, "Webpage, Complete")

Use Chrome or Edge on the MacBook. Safari's "Web Archive" format is not supported.

1. Open the page normally and accept any cookie banner.
2. **Expand everything.** Click each FAQ category or tab, then open every question, so that every answer is visible on screen.
3. Choose **File → Save Page As… → Format: "Webpage, Complete"**. This saves the page exactly as displayed, with expanded answers, and records its address in the file. Only the `.html` file is needed: do not upload the `…_files` folder.
4. If a page's tabs cannot all be open at once, save **one file per tab**, with each tab's questions expanded. All files for one page are imported together and merged.
5. Name the files after the page: `international-passenger-trial-01-general.html`, `international-passenger-trial-02-eligibility.html`, `implementation-current.html`, `faqs.html`, and so on.

**Fallback:** Print → Save as PDF with "Headers and footers" enabled, so the URL is printed. Use this only if HTML is impossible: a PDF loses the question-and-answer structure, so its content becomes section records rather than FAQ pairs.

A capture is rejected, and nothing is stored, if any of these is true:
- its embedded page address doesn't match the page;
- any visible question has no answer (partial capture);
- it is a block or CAPTCHA page;
- HTML and PDF are mixed for one page.

## 3. Upload with SFTP

Connect as **`claudeuser`**, not root, so the files arrive with the right owner and permissions:

```
sftp claudeuser@<hostinger-host>
sftp> cd /home/claudeuser/Yash/digiyatra-latest/knowledge/imports/digiyatrafoundation
sftp> put ~/Downloads/international-passenger-trial-*.html
sftp> put ~/Downloads/implementation-current.html
sftp> put ~/Downloads/faqs.html
sftp> bye
```

`knowledge/imports/` is private: Git ignores it, the local pre-push check blocks it, and the folder is mode 0700.

## 4. Import, review and publish (run on Hostinger)

From `backend/`. The examples use the local development database. The same commands work against production only through the transfer bundle described in `DEPLOYMENT_HANDOFF.md` §17.

```sh
export DATABASE_URL="sqlite:///$PWD/data/official-sync-dev.db"
I=../knowledge/imports/digiyatrafoundation
.venv/bin/python -m app.cli sync-import dyf-international-trial --file $I/international-passenger-trial-01-general.html \
    --file $I/international-passenger-trial-02-eligibility.html
.venv/bin/python -m app.cli sync-import dyf-airports-current --file $I/implementation-current.html
.venv/bin/python -m app.cli sync-import --url https://digiyatrafoundation.com/<faq-path>/ --file $I/faqs.html
.venv/bin/python -m app.cli sync-review-report      # private pack in .cache/review (grouped, with conflicts)
#   edit the decision sheet: verified / rejected / defer per group (+ reject_ids / defer_ids)
.venv/bin/python -m app.cli sync-review-apply ../.cache/review/<pack>.decisions.json --reviewer "Name"
.venv/bin/python -m app.cli sync-publish            # validated, atomic publication
OFFICIAL_KNOWLEDGE_SERVING_ENABLED=true .venv/bin/python -m app.cli ensure-index
```

Imported records are **never** auto-approved, and a later partial capture never withdraws earlier records. Reviewer approval applies only to the imported official content. Content-owner sign-off of the original approval manifest remains pending.
