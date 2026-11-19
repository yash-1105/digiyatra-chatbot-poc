"use client";

import Link from "next/link";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useChatText } from "./chat-language";
import type { FeedbackState } from "./useChat";

interface Props {
  state: FeedbackState;
  onFeedback: (resolved: boolean) => void;
}

export function FeedbackControls({ state, onFeedback }: Props) {
  const t = useChatText();
  if (state === "yes") {
    return <p className="mt-2 text-xs text-success" role="status">{t.thanks}</p>;
  }
  if (state === "no") {
    return (
      <div className="mt-2 rounded bg-band p-2.5 text-xs leading-relaxed text-ink" role="status">
        <p className="font-semibold text-heading">{t.unresolved}</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-ink-muted">
          <li>{t.rephrase}</li>
          <li>
            {t.email}{" "}
            <a href="mailto:customercare@digiyatrafoundation.com" className="text-brand underline">
              customercare@digiyatrafoundation.com
            </a>{" "}
            {t.device}
          </li>
          <li>{t.gate}</li>
        </ul>
        <Link href="/#support" className="mt-1 inline-block text-brand underline">
          {t.support}
        </Link>
      </div>
    );
  }

  const busy = state === "sending";
  const btn =
    "inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-xs text-ink-muted hover:border-brand hover:text-brand disabled:opacity-50";

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs" role="group" aria-label={t.resolved}>
      <span className="text-ink-soft">{t.resolved}</span>
      <button type="button" className={btn} disabled={busy} onClick={() => onFeedback(true)}>
        <ThumbsUp aria-hidden="true" className="h-3.5 w-3.5" /> {t.yes}
      </button>
      <button type="button" className={btn} disabled={busy} onClick={() => onFeedback(false)}>
        <ThumbsDown aria-hidden="true" className="h-3.5 w-3.5" /> {t.no}
      </button>
      {state === "failed" ? <span className="text-danger" role="alert">{t.feedbackError}</span> : null}
    </div>
  );
}
