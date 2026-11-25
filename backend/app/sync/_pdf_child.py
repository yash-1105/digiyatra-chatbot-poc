"""PDF text extraction child (stdlib + pypdf only). Invoked by app.sync.pdf with rlimits."""

import json
import sys


def main(max_pages: int) -> None:
    import io
    import logging

    from pypdf import PdfReader

    logging.disable(logging.CRITICAL)
    data = sys.stdin.buffer.read()
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            print(json.dumps({"reason": "encrypted", "page_count": 0}))
            return
        n = len(reader.pages)
        if n > max_pages:
            print(json.dumps({"reason": "too_many_pages", "page_count": n}))
            return
        pages = [(page.extract_text() or "")[:200_000] for page in reader.pages]
        title = (reader.metadata.title if reader.metadata else None) or None
        print(json.dumps({"pages": pages, "page_count": n, "title": str(title)[:300] if title else None}))
    except Exception as exc:  # noqa: BLE001 - any parser failure is reported, never raised
        print(json.dumps({"reason": f"parse_error:{type(exc).__name__}", "page_count": 0}))


if __name__ == "__main__":
    main(int(sys.argv[1]))
