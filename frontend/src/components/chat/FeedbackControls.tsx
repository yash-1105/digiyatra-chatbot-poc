"use client";

import Link from "next/link";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import type { FeedbackState } from "./useChat";

interface Props {
  state: FeedbackState;
  onFeedback: (resolved: boolean) => void;
}

export function FeedbackControls({ state, onFeedback }: Props) {
  if (state === "yes") {
    return <p className="mt-2 text-xs text-success" role="status">Thank you for your feedback.</p>;
  }
  if (state === "no") {
    return (
      <div className="mt-2 rounded bg-band p-2.5 text-xs leading-relaxed text-ink" role="status">
        <p className="font-semibold text-heading">Sorry this didn&apos;t resolve your issue. You can:</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-ink-muted">
          <li>Rephrase your question or ask about one specific step.</li>
          <li>
            Email customer care at{" "}
            <a href="mailto:customercare@digiyatrafoundation.com" className="text-brand underline">
              customercare@digiyatrafoundation.com
            </a>{" "}
            with your device model and app version. Never share Aadhaar numbers or OTPs.
          </li>
          <li>For problems at an airport gate, ask the airport staff on site.</li>
        </ul>
        <Link href="/#support" className="mt-1 inline-block text-brand underline">
          Support &amp; Contact information
        </Link>
      </div>
    );
  }

  const busy = state === "sending";
  const btn =
    "inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-xs text-ink-muted hover:border-brand hover:text-brand disabled:opacity-50";

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs" role="group" aria-label="Did this resolve your issue?">
      <span className="text-ink-soft">Did this resolve your issue?</span>
      <button type="button" className={btn} disabled={busy} onClick={() => onFeedback(true)}>
        <ThumbsUp aria-hidden="true" className="h-3.5 w-3.5" /> Yes
      </button>
      <button type="button" className={btn} disabled={busy} onClick={() => onFeedback(false)}>
        <ThumbsDown aria-hidden="true" className="h-3.5 w-3.5" /> No
      </button>
      {state === "failed" ? <span className="text-danger" role="alert">Couldn&apos;t send — please try again.</span> : null}
    </div>
  );
}
