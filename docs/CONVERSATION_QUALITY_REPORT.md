# Conversational answer quality and deployment verification

Date: 2026-11-19. Application: https://digiyatra-chatbot-poc.vercel.app

## Root causes and changes

The previous retrieval pipeline lacked platform and boarding-pass intent signals. Short colloquial queries such as “only iPhone?” and “Samsung?” could miss the store-link document, fall below the domain gate, or favor an unrelated troubleshooting FAQ. URLs also contributed noisy BM25 terms. Broad process documents competed with specific instructions. Conversation recovery treated any short question as a follow-up, sometimes carrying stale subjects into a new question.

Queries now normalize platform names, spelling, punctuation and ticket terminology. Intent-specific expansion feeds both LanceDB lexical TF-IDF vectors and BM25. Approved chunks with matching evidence anchors join the candidate set even when initially missed. Specific platform, PDF, scan and upload evidence receives priority; platform questions exclude unrelated device-error documents. Ties are deterministic. The approval filter, minimum retrieval threshold, duplicate suppression and source caps remain enforced. Embeddings remain lexical, not neural semantic embeddings.

The previous prompt requested factual summaries but did not consistently request direct answers or usable procedures. The new prompt asks for the passenger's actual question to be answered immediately, natural second-person language, brief Yes/No answers, and evidence-supported numbered instructions. Store links remain clickable. Follow-ups use recent user questions only when relevant; fresh definition questions reset the subject. Client-supplied assistant history remains untrusted, and recovered user history is screened for injection and personal data.

The citation validator previously collapsed step formatting and could treat step labels as factual numbers. It also missed paraphrase equivalents and treated many short “you can” statements as harmless advice. Validation now preserves line breaks, separates list labels from factual quantities, renumbers surviving steps, recognizes bounded synonyms, checks short factual instructions, and rejects selected policy reversals and claims about technologies absent from their evidence. FAQ questions are not themselves evidence for their premises. Existing fabricated-number, link, secret, injection and unsupported-claim checks remain active.

## Explicit answer policy

| Mode | Backend behavior |
|---|---|
| Knowledge | Retrieve approved evidence, generate with Sarvam-105B, validate claims and citations, return only cited sources. |
| General | Full-question allow-list for basic Android, OTP, QR, NFC and facial-recognition explanations, only when no approved definition is retrieved. Sarvam-105B supplies a clearly labelled general explanation. No knowledge-base citations or Digi Yatra policy claims are allowed. |
| Insufficient | Do not invent live airport status, current airport lists, international-trial policy, account access, unsupported device requirements or unsupported features. Give a concise fallback or official guidance. |

General knowledge cannot answer mixed definition/policy questions. It cannot establish Digi Yatra eligibility, retention, procedures, supported devices or operating status. The additive API field `answer_mode` exposes the selection without changing existing status values or the database schema.

## Evaluation method

The committed `backend/evaluation/questions.json` contains 40 natural passenger questions, including all ten requested examples and contextual follow-ups. `backend/evaluation/run.py` runs the real Sarvam model with an isolated synthetic analytics database. Full responses and retrieved passages remain in ignored private artifacts; the public repository contains only questions, evaluation code and this summary.

A pre-change baseline and final comparison use the same question set and checks. Automated concept checks are keyword probes, not semantic correctness guarantees. Source checks verify expected source relevance and citation structure; regression tests additionally exercise unsupported claims, invented numbers, policy reversals, malicious input and general-mode boundaries. Answers were also inspected for practical usefulness and conversational tone.

Results and deployment identity are recorded in `PRODUCTION_DEPLOYMENT_REPORT.md`.

## Before and after examples

These are concise summaries of observed behavior, rather than publication of private source passages.

| Question | Before | After |
|---|---|---|
| Is Digi Yatra only for iPhone? | Insufficient-information fallback. | Directly explains Android and iPhone availability with store evidence. |
| Where do I upload my boarding pass? | Generic description of pre-travel upload and extraction. | Identifies the app, supported boarding-pass methods and practical PDF-sharing instructions with citations. |
| How do I upload a PDF from my phone? | A paragraph describing sharing. | Numbered steps: locate the PDF, use Share, select Digi Yatra, grant consent; citations preserved. |
| What is an OTP? | Could fall back or retrieve registration text. | Short general explanation, explicitly distinguished from Digi Yatra policy, without fabricated citations. |
| Are Delhi gates working right now? | Cannot verify live status. | Continues to decline live-status claims and directs the passenger to the airline/airport. |
| Can I use Digi Yatra for international travel? | Retrieved static domestic-travel guidance. | Does not infer current eligibility or trial availability from static or unapproved material. |

## Limits

The approved retrieval corpus and its publication restrictions are unchanged; content-owner signoff remains pending. No new procedures, live operating data or policy facts were added. Lexical claim validation is a heuristic, not a semantic entailment proof, and generative wording can vary. Ambiguous questions and policy contradictions can still require clarification or official confirmation.

The existing screenshot suite reports a pre-existing 404 for `/favicon.ico`; no application layout or runtime assets were changed to address that unrelated issue. Railway CLI also warns that legacy configuration files will need migration before its stated 2026-12-01 cutoff; that infrastructure migration is outside this change.
