"use client";

import Link from "next/link";
import { useEffect } from "react";

/** Production error boundary: a friendly portal-styled message, never error details or stack traces. */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Only the opaque digest is useful for correlating with server logs; nothing else is shown.
    if (error.digest) console.error("Page error reference:", error.digest);
  }, [error]);

  return (
    <main className="flex min-h-[60vh] items-center justify-center bg-band px-4 py-16">
      <div className="max-w-lg rounded-md border-t-4 border-t-accent bg-surface p-8 text-center shadow-card">
        <h1 className="text-2xl text-heading">Something went wrong</h1>
        <p className="mt-3 text-ink-muted">
          This page could not be displayed. Please try again. If the problem continues, return to the homepage.
        </p>
        {error.digest ? <p className="mt-2 text-xs text-ink-soft">Reference: {error.digest}</p> : null}
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <button type="button" onClick={reset} className="btn-pill rounded-full px-8 py-2.5 font-medium">
            Try again
          </button>
          <Link href="/" className="rounded-full border border-brand px-8 py-2.5 font-medium text-brand hover:bg-brand-soft">
            Homepage
          </Link>
        </div>
      </div>
    </main>
  );
}
