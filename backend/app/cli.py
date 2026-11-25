"""Command-line tools.

    python -m app.cli ingest                 parse knowledge/raw -> knowledge/curated (+report)
    python -m app.cli index                  build LanceDB index from the deployment corpus (knowledge/deploy)
    python -m app.cli ensure-index           build the index only if missing or built from a different corpus
                                             (container start-up: deterministic rebuild, no raw files needed)
    python -m app.cli reindex                ingest + full rebuild (use after editing the manifest)
    python -m app.cli reindex-file FILE      re-ingest and replace one document's chunks
    python -m app.cli delete FILE            remove one document's chunks from the index
    python -m app.cli query "text" [-k 5]    show retrieval results with scores
    python -m app.cli stats                  index statistics
    python -m app.cli probe-embeddings       check whether the key can use Sarvam embeddinggemma-2
    python -m app.cli db-upgrade             apply database migrations (Alembic) to DATABASE_URL
    python -m app.cli sync-run [--source ID ...]   official-source synchronisation (short-lived; exits when done)
    python -m app.cli sync-status | sync-pending | sync-publish
    python -m app.cli sync-enable ID | sync-disable ID | sync-import ID --file CAPTURE
    python -m app.cli sync-review RECORD verified|rejected|revoked --reviewer NAME
    python -m app.cli create-admin [--email admin@gmail.com] [--reset-password]
                                             create the administrator; prompts for the password (not echoed)
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Callable

from app.config import PROJECT_DIR, get_settings
from app.logging_config import configure_logging
from app.rag.factory import (
    build_retriever,
    choose_index_embedder,
    query_embedder,
    sarvam_embedder,
)
from app.rag.store import KnowledgeIndex
from ingestion.pipeline import run_pipeline


def _load_chunks(settings) -> tuple[list[dict], dict]:
    from ingestion.corpus import load_corpus

    try:
        return load_corpus(settings.knowledge_corpus_dir)
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(str(exc))


def cmd_ingest(settings) -> None:
    from ingestion.corpus import export_corpus

    r = run_pipeline(settings.knowledge_raw_dir, settings.knowledge_curated_dir, settings.approval_manifest)
    info = export_corpus(r, settings.approval_manifest, settings.knowledge_corpus_dir)
    print(f"Deployment corpus: {info['chunk_count']} chunks / {info['document_count']} approved documents "
          f"-> {settings.knowledge_corpus_dir} (sha256 {info['corpus_sha256'][:12]}…)")
    by_status: dict[str, int] = {}
    for f in r.files:
        by_status[f.status] = by_status.get(f.status, 0) + 1
    print(f"Files: {len(r.files)}  by status: {by_status}")
    print(f"Records: {len(r.records)}  approved chunks: {len(r.chunks)}  review items: {len(r.review_queue)}")
    print(f"Report: {settings.knowledge_curated_dir / 'ingestion_report.md'}")


def _publication(settings):
    """Active verified official-source publication (serving enabled + migrated DB), else (None, [])."""
    if not settings.official_knowledge_serving_enabled:
        return None, []
    from app.db.session import Database
    from app.sync.publish import active_publication, publication_records

    db = Database(settings.database_url)
    try:
        if not db.is_migrated():
            return None, []
        pub = active_publication(db)
        return pub, publication_records(db, pub)
    finally:
        db.engine.dispose()


def cmd_index(settings) -> None:
    from app.sync.publish import INDEX_SCHEMA, record_chunk

    chunks, corpus = _load_chunks(settings)
    pub, records = _publication(settings)
    embedder, reason = choose_index_embedder(settings)
    print(f"Embedder: {embedder.describe()['name']} ({reason})")
    index = KnowledgeIndex(settings.index_dir, settings.index_table)
    all_chunks = chunks + [record_chunk(r, i) for i, r in enumerate(records)]
    n = index.build(all_chunks, embedder, extra_meta={
        "embedder_reason": reason, "corpus_sha256": corpus["corpus_sha256"],
        "requested_provider": settings.embedding_provider, "index_schema": INDEX_SCHEMA,
        "publication_id": pub.id if pub else None, "publication_digest": pub.digest if pub else None,
        "official_records": len(records), "base_chunk_count": len(chunks),
    })
    meta = index.meta()
    print(f"Indexed {n} chunks ({len(chunks)} approved corpus + {len(records)} verified official records) "
          f"from {meta['document_count']} documents into {settings.index_dir}")


def create_admin(
    settings, email: str, reset: bool, prompt: Callable[[str], str] = getpass.getpass, out=print
) -> int:
    """Interactive admin setup. The password is read with getpass (never echoed, never logged/stored in clear)."""
    from app.db.session import Database
    from app.services.auth import AuthService, validate_new_password

    db = Database(settings.database_url)
    if not db.is_migrated():
        out("Database is not initialised. Run `python -m app.cli db-upgrade` first.")
        return 2
    out(f"{'Resetting password for' if reset else 'Creating'} administrator: {email}")
    for _ in range(3):
        pw = prompt("New administrator password: ")
        problems = validate_new_password(pw)
        if problems:
            out("Password " + "; ".join(problems) + ". Try again.")
            continue
        if prompt("Confirm password: ") != pw:
            out("Passwords did not match. Try again.")
            continue
        try:
            result = AuthService(db, 60, 60).create_or_reset_admin(email, pw, reset=reset)
        except ValueError as exc:
            out(str(exc))
            return 1
        finally:
            pw = ""  # noqa: F841 - drop the reference promptly
        out(f"Administrator {email} {result}. Only an Argon2id hash was stored.")
        return 0
    out("Too many failed attempts; nothing was changed.")
    return 1


def cmd_ensure_index(settings) -> int:
    """Idempotent start-up step: keep a valid index, rebuild when missing/stale. Never reads raw files."""
    from app.sync.publish import INDEX_SCHEMA

    _, corpus = _load_chunks(settings)
    pub, records = _publication(settings)
    index = KnowledgeIndex(settings.index_dir, settings.index_table)
    reason = None
    if not index.exists():
        reason = "index missing"
    else:
        meta = index.meta()
        if meta.get("corpus_sha256") != corpus["corpus_sha256"]:
            reason = "built from a different corpus"
        elif meta.get("requested_provider") != settings.embedding_provider:
            reason = "embedding provider setting changed"
        elif meta.get("index_schema") != INDEX_SCHEMA:
            reason = "index schema changed"
        elif meta.get("publication_digest") != (pub.digest if pub else None):
            reason = "official knowledge publication changed"
        elif meta.get("chunk_count") != corpus["chunk_count"] + len(records):
            reason = "chunk count mismatch"
    if reason is None:
        print(f"Index OK: {corpus['chunk_count']} corpus chunks + {len(records)} official records, "
              f"corpus {corpus['corpus_sha256'][:12]}… (no rebuild)")
        return 0
    print(f"Rebuilding index ({reason})")
    cmd_index(settings)
    return 0


def cmd_sync(settings, args) -> int:
    """Pipeline A commands. Never invoked by the chat API."""
    from pathlib import Path

    from app.db.session import Database
    from app.sync import job as J

    db = Database(settings.database_url)
    try:
        if not db.is_migrated():
            print("Database is not initialised. Run `python -m app.cli db-upgrade` first.")
            return 3
        if args.cmd == "sync-run":
            if not settings.official_source_lookup_enabled:
                print("OFFICIAL_SOURCE_LOOKUP_ENABLED=true is required for network synchronisation.")
                return 3
            code = J.SyncJob(settings, db).run(trigger=args.trigger, force=args.source)
            report = J.status_report(db, settings)
            print(json.dumps({"exit_code": code, "last_run": report["recent_runs"][:1],
                              "active_publication": report["active_publication"]}, indent=2, default=str))
            return code
        if args.cmd == "sync-publish":
            code = J.SyncJob(settings, db).run(trigger="manual", publish_only=True)
            print(json.dumps(J.status_report(db, settings)["active_publication"], indent=2))
            return code
        if args.cmd == "sync-status":
            J.sync_registry(db, settings)
            print(json.dumps(J.status_report(db, settings), indent=2, ensure_ascii=False, default=str))
        elif args.cmd == "sync-pending":
            print(json.dumps(J.pending_records(db), indent=2, ensure_ascii=False))
        elif args.cmd in ("sync-enable", "sync-disable"):
            J.sync_registry(db, settings)
            J.set_enabled(db, args.source_id, args.cmd == "sync-enable")
            print(f"{args.source_id}: {'enabled' if args.cmd == 'sync-enable' else 'disabled'}")
        elif args.cmd == "sync-import":
            blobs = []
            for name in args.file:
                path = Path(name)
                if not path.is_file() or path.stat().st_size > settings.sync_max_pdf_bytes:
                    raise ValueError(f"Capture missing or too large: {path.name}")
                blobs.append(path.read_bytes())
            result = J.SyncJob(settings, db).import_capture(args.source_id, blobs, url=args.url)
            print(json.dumps(result, indent=2))
            print("Capture stored; every resulting record requires review (sync-pending / sync-review-report).")
        elif args.cmd == "sync-export":
            from app.sync.transfer import export_bundle

            print(json.dumps(export_bundle(db, Path(args.out)), indent=2))
        elif args.cmd == "sync-import-bundle":
            from app.sync.transfer import import_bundle

            print(json.dumps(import_bundle(db, Path(args.bundle), dry_run=args.dry_run, as_pending=args.as_pending), indent=2))
            if not args.dry_run:
                print("Insert-only import done. Review with sync-review-report, then run sync-publish.")
        elif args.cmd == "sync-review-report":
            from app.sync.review import build_groups, write_report

            groups = build_groups(db, settings.knowledge_corpus_dir)
            md, sheet = write_report(groups, Path(args.out))
            print(f"{sum(len(g['record_ids']) for g in groups)} pending records in {len(groups)} groups")
            print(f"Report (private): {md}\nDecision sheet: {sheet}")
        elif args.cmd == "sync-review-apply":
            import re as _re

            from app.sync.review import apply_sheet

            if not _re.fullmatch(r"[\w .@-]{1,80}", args.reviewer):
                raise ValueError("Invalid reviewer name")
            print(json.dumps(apply_sheet(db, Path(args.sheet), args.reviewer), indent=2))
            print("Run `sync-publish` to publish the verified set.")
        elif args.cmd == "sync-review":
            if args.record.startswith("source:"):
                n = J.review_source(db, args.record[7:], args.decision, args.reviewer)
                print(f"{n} record(s) of {args.record[7:]}: {args.decision}. Run `sync-publish` to publish.")
            else:
                J.review_record(db, int(args.record), args.decision, args.reviewer)
                print(f"Record {args.record}: {args.decision}. Run `sync-publish` to publish the verified set.")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Sync command failed: {exc}")
        return 1
    finally:
        db.engine.dispose()


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest")
    sub.add_parser("index")
    sub.add_parser("ensure-index")
    sub.add_parser("reindex")
    rf = sub.add_parser("reindex-file")
    rf.add_argument("file")
    d = sub.add_parser("delete")
    d.add_argument("file")
    q = sub.add_parser("query")
    q.add_argument("text")
    q.add_argument("-k", type=int, default=5)
    sub.add_parser("stats")
    sub.add_parser("probe-embeddings")
    sub.add_parser("db-upgrade")
    from app.services.knowledge import SOURCES

    verify = sub.add_parser("knowledge-verify")
    verify.add_argument("source_id", choices=sorted(SOURCES))
    verify.add_argument("--file", help="Operator-authenticated HTTPS capture for manual review")
    review = sub.add_parser("knowledge-review")
    review.add_argument("revision", type=int)
    review.add_argument("decision", choices=("published", "rejected", "revoked"))
    review.add_argument("--reviewer", required=True)
    sub.add_parser("knowledge-inventory")
    show = sub.add_parser("knowledge-inspect")
    show.add_argument("revision", type=int)
    sub.add_parser("faq-version")
    faq_source = sub.add_parser("faq-source")
    faq_source.add_argument("chunk_id")
    faq_publish = sub.add_parser("faq-publish")
    faq_publish.add_argument("bundle")
    faq_revoke = sub.add_parser("faq-revoke")
    faq_revoke.add_argument("question")
    faq_revoke.add_argument("--locale", choices=("en", "hi"), required=True)
    sr = sub.add_parser("sync-run")
    sr.add_argument("--source", action="append", help="Force-refresh these registered source IDs only")
    sr.add_argument("--trigger", default="schedule", choices=("schedule", "manual", "initial"))
    for name in ("sync-status", "sync-pending", "sync-publish"):
        sub.add_parser(name)
    for name in ("sync-enable", "sync-disable"):
        sub.add_parser(name).add_argument("source_id")
    si = sub.add_parser("sync-import")
    si.add_argument("source_id", nargs="?", help="Registered source ID (or use --url)")
    si.add_argument("--url", help="Allow-listed Digi Yatra Foundation page URL (registered on first import)")
    si.add_argument("--file", action="append", required=True,
                    help="Operator-saved HTML (preferred) or PDF of the page; repeat for one file per FAQ tab")
    ex = sub.add_parser("sync-export")
    ex.add_argument("--out", required=True, help="Private bundle path (e.g. ../.cache/exports/official.json)")
    ib = sub.add_parser("sync-import-bundle")
    ib.add_argument("bundle")
    ib.add_argument("--dry-run", action="store_true")
    ib.add_argument("--as-pending", action="store_true", help="Re-queue every imported record for review")
    rr = sub.add_parser("sync-review-report")
    rr.add_argument("--out", default=str(PROJECT_DIR / ".cache" / "review"), help="Private output directory")
    ra = sub.add_parser("sync-review-apply")
    ra.add_argument("sheet")
    ra.add_argument("--reviewer", required=True)
    sv = sub.add_parser("sync-review")
    sv.add_argument("record", help="Record id, or source:<SOURCE_ID> for every pending record of a source")
    sv.add_argument("decision", choices=("verified", "rejected", "revoked"))
    sv.add_argument("--reviewer", required=True)
    ca = sub.add_parser("create-admin")
    ca.add_argument("--email", default="admin@gmail.com")
    ca.add_argument("--reset-password", action="store_true")
    args = p.parse_args(argv)
    settings = get_settings()

    if args.cmd == "ingest":
        cmd_ingest(settings)
    elif args.cmd == "index":
        cmd_index(settings)
    elif args.cmd == "ensure-index":
        sys.exit(cmd_ensure_index(settings))
    elif args.cmd == "reindex":
        cmd_ingest(settings)
        cmd_index(settings)
    elif args.cmd in ("reindex-file", "delete"):
        index = KnowledgeIndex(settings.index_dir, settings.index_table)
        emb = query_embedder(index, settings)
        if args.cmd == "delete":
            print(f"Removed {index.delete_source(args.file, emb)} chunks for {args.file}")
        else:
            run_pipeline(settings.knowledge_raw_dir, settings.knowledge_curated_dir, settings.approval_manifest)
            chunks = [c for c in _load_chunks(settings) if c["source_file"] == args.file]
            print(f"Replaced {args.file}: {index.replace_source(args.file, chunks, emb)} chunks "
                  f"({'not approved — removed from index' if not chunks else 'approved'})")
    elif args.cmd == "query":
        r = build_retriever(settings)
        for hit in r.search(args.text, args.k):
            print(f"{hit.score:.3f} (vec {hit.vector_score:.3f} kw {hit.keyword_score:.3f} cov {hit.coverage:.2f}) "
                  f"{hit.source_file} :: {hit.section} :: {(hit.question or hit.text)[:90]!r}")
    elif args.cmd == "stats":
        print(json.dumps(KnowledgeIndex(settings.index_dir, settings.index_table).meta(), indent=2))
    elif args.cmd == "db-upgrade":
        from app.db.migrate import upgrade

        (settings.index_dir.parent).mkdir(parents=True, exist_ok=True)  # backend/data for the SQLite file
        upgrade(settings.database_url)
        print("Database schema is up to date.")
    elif args.cmd.startswith("knowledge-"):
        from pathlib import Path

        from app.db.session import Database
        from app.services.knowledge import MAX_SOURCE_BYTES, Knowledge

        db = Database(settings.database_url)
        service = Knowledge(db)
        try:
            if args.cmd == "knowledge-verify":
                if args.file:
                    with Path(args.file).open("rb") as source:
                        data = source.read(MAX_SOURCE_BYTES + 1)
                    if len(data) > MAX_SOURCE_BYTES:
                        raise ValueError("Source capture is too large")
                    revision = service.verify(args.source_id, snapshot=data.decode("utf-8"))
                else:
                    if not settings.official_source_lookup_enabled:
                        raise ValueError("OFFICIAL_SOURCE_LOOKUP_ENABLED is required for network fetch")
                    revision = service.verify(args.source_id, auto_publish=settings.knowledge_auto_publish_enabled)
                print(f"Verified source revision {revision}")
            elif args.cmd == "knowledge-review":
                service.review(args.revision, args.decision, args.reviewer)
                print(f"Revision {args.revision}: {args.decision}")
            elif args.cmd == "knowledge-inspect":
                print(json.dumps(service.inspect(args.revision), ensure_ascii=False, indent=2))
            else:
                print(json.dumps(service.inventory(), ensure_ascii=False, indent=2))
        except (KeyError, OSError, ValueError, RuntimeError) as exc:
            sys.exit(f"Knowledge command failed: {exc}")
        finally:
            db.engine.dispose()
    elif args.cmd.startswith("faq-"):
        from pathlib import Path

        from pydantic import TypeAdapter

        from app.db.session import Database
        from app.services.faq import FAQEntry, ReviewedFAQs, faq_key

        db = Database(settings.database_url)
        try:
            faq = ReviewedFAQs(db, settings, build_retriever(settings))
            if args.cmd == "faq-version":
                print(faq.version)
            elif args.cmd == "faq-source":
                print(faq.source_ref(args.chunk_id).model_dump_json())
            elif args.cmd == "faq-publish":
                entries = TypeAdapter(list[FAQEntry]).validate_json(Path(args.bundle).read_bytes())
                faq.publish(entries)
                print(f"Processed {len(entries)} reviewed FAQ rows.")
            elif args.cmd == "faq-revoke":
                key = faq_key(args.question)
                if not key:
                    raise ValueError("Ineligible FAQ question")
                faq.revoke(key, args.locale)
        except Exception as exc:  # noqa: BLE001 - validation and DB exceptions can include private data
            sys.exit(f"FAQ maintenance failed ({type(exc).__name__})")
        finally:
            db.engine.dispose()
    elif args.cmd.startswith("sync-"):
        sys.exit(cmd_sync(settings, args))
    elif args.cmd == "create-admin":
        if not sys.stdin.isatty():
            sys.exit("create-admin must be run in an interactive terminal (the password is typed privately).")
        sys.exit(create_admin(settings, args.email, args.reset_password))
    elif args.cmd == "probe-embeddings":
        emb = sarvam_embedder(settings)
        if emb is None:
            print("SARVAM_API_KEY is not set — cannot probe embeddinggemma-2.")
            sys.exit(2)
        ok, detail = emb.probe()
        print(f"embeddinggemma-2 access: {'AVAILABLE' if ok else 'UNAVAILABLE'} — {detail}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
