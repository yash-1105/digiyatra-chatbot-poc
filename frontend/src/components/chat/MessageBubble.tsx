"use client";

import { AlertCircle, FlaskConical, Info, RotateCw, Sparkles } from "lucide-react";
import { cn } from "@/lib/cn";
import { FeedbackControls } from "./FeedbackControls";
import { useChatText } from "./chat-language";
import { RichText } from "./RichText";
import { SourceList } from "./SourceList";
import type { UiMessage } from "./useChat";

interface Props {
  message: UiMessage;
  canRetry: boolean;
  onRetry: (id: string) => void;
  onFeedback: (id: string, resolved: boolean) => void;
}

function time(ts: number) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function MessageBubble({ message, canRetry, onRetry, onFeedback }: Props) {
  const t = useChatText();
  if (message.role === "user") {
    return (
      <div className="flex flex-col items-end animate-fade-in">
        <div
          className={cn(
            "max-w-[85%] rounded-2xl rounded-br-sm px-3.5 py-2.5 text-[0.92rem] leading-relaxed",
            message.error ? "border border-danger/50 bg-danger-soft text-ink" : "bg-brand text-white [html[data-contrast=high]_&]:text-black",
          )}
        >
          <span className="sr-only">{t.you} </span>
          <RichText text={message.content} />
        </div>
        {message.error ? (
          <div role="alert" className="mt-1.5 flex max-w-[85%] flex-wrap items-center justify-end gap-2 text-xs text-danger">
            <AlertCircle aria-hidden="true" className="h-3.5 w-3.5" />
            <span>{canRetry ? message.error.message : t.notSent}</span>
            {canRetry && message.error.retryable ? (
              <button
                type="button"
                onClick={() => onRetry(message.id)}
                className="inline-flex items-center gap-1 rounded border border-danger/50 px-2 py-0.5 font-medium hover:bg-danger hover:text-white"
              >
                <RotateCw aria-hidden="true" className="h-3 w-3" /> {t.retry}
              </button>
            ) : null}
          </div>
        ) : (
          <span className="mt-1 text-[0.68rem] text-ink-soft">{time(message.createdAt)}</span>
        )}
      </div>
    );
  }

  const isMock = message.origin === "mock";
  const notices = (message.notices ?? []).filter(
    (notice) => notice !== "Some of this information is time-sensitive and may have changed. Please verify on the official Digi Yatra website before you travel." && notice !== "यह जानकारी समय के साथ बदल सकती है। यात्रा से पहले आधिकारिक डिजी यात्रा वेबसाइट पर जाँचें।",
  );
  return (
    <div className="flex flex-col items-start animate-fade-in">
      <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-line-soft bg-surface px-3.5 py-2.5 text-[0.92rem] leading-relaxed text-ink shadow-card">
        <span className="sr-only">{t.assistant} </span>
        {isMock ? (
          <span className="mb-1.5 inline-flex items-center gap-1 rounded bg-warning-soft px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-warning">
            <FlaskConical aria-hidden="true" className="h-3 w-3" /> Mock response · not AI
          </span>
        ) : message.origin === "live" && message.status === "answered" ? (
          <span className="mb-1.5 inline-flex items-center gap-1 rounded bg-brand-soft px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide text-brand">
            <Sparkles aria-hidden="true" className="h-3 w-3" /> {t.generated}
          </span>
        ) : null}
        <div>
          <RichText text={message.content} />
        </div>
        {notices.length > 0 ? (
          <ul className="mt-2 space-y-1">
            {notices.map((n) => (
              <li key={n} className="flex gap-1.5 rounded bg-warning-soft px-2 py-1.5 text-[0.75rem] leading-snug text-ink">
                <Info aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                {n}
              </li>
            ))}
          </ul>
        ) : null}
        {message.sources ? <SourceList sources={message.sources} /> : null}
        {message.feedback ? (
          <FeedbackControls state={message.feedback} onFeedback={(resolved) => onFeedback(message.id, resolved)} />
        ) : null}
      </div>
      <span className="mt-1 text-[0.68rem] text-ink-soft">{time(message.createdAt)}</span>
    </div>
  );
}
