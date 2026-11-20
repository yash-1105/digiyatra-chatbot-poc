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
    python -m app.cli create-admin [--email admin@gmail.com] [--reset-password]
                                             create the administrator; prompts for the password (not echoed)
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Callable

from app.config import get_settings
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


def cmd_index(settings) -> None:
    chunks, corpus = _load_chunks(settings)
    embedder, reason = choose_index_embedder(settings)
    print(f"Embedder: {embedder.describe()['name']} ({reason})")
    index = KnowledgeIndex(settings.index_dir, settings.index_table)
    n = index.build(chunks, embedder, extra_meta={"embedder_reason": reason, "corpus_sha256": corpus["corpus_sha256"],
                                                  "requested_provider": settings.embedding_provider})
    meta = index.meta()
    print(f"Indexed {n} chunks from {meta['document_count']} approved documents into {settings.index_dir}")


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
    _, corpus = _load_chunks(settings)
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
        elif meta.get("chunk_count") != corpus["chunk_count"]:
            reason = "chunk count mismatch"
    if reason is None:
        print(f"Index OK: {corpus['chunk_count']} chunks, corpus {corpus['corpus_sha256'][:12]}… (no rebuild)")
        return 0
    print(f"Rebuilding index ({reason})")
    cmd_index(settings)
    return 0


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
    sub.add_parser("faq-version")
    faq_source = sub.add_parser("faq-source")
    faq_source.add_argument("chunk_id")
    faq_publish = sub.add_parser("faq-publish")
    faq_publish.add_argument("bundle")
    faq_revoke = sub.add_parser("faq-revoke")
    faq_revoke.add_argument("question")
    faq_revoke.add_argument("--locale", choices=("en", "hi"), required=True)
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
