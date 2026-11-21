"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FlaskConical, Trash2, X } from "lucide-react";
import { LogoMark } from "@/components/brand/LogoMark";
import { starterQuestions } from "@/content/starter-questions";
import { MOCK_ERROR_TRIGGER } from "@/lib/api";
import { OPEN_CHAT_EVENT, type OpenChatDetail } from "@/lib/chat-events";
import { cn } from "@/lib/cn";
import { ChatComposer } from "./ChatComposer";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { useChat } from "./useChat";
import { ChatLanguage, hindiStarters, useChatText } from "./chat-language";
import type { Locale } from "@/lib/i18n/dictionary";
import type { AIProvider } from "@/lib/api";

type Phase = "closed" | "open" | "closing";
const CLOSE_ANIMATION_MS = 160;

/**
 * Floating assistant: round navy launcher at the bottom-right (as on the DGCA
 * portal) that opens an animated chat panel — full-screen on phones.
 */
export function ChatWidget() {
  const chat = useChat();
  return <ChatLanguage.Provider value={chat.locale}><ChatPanel chat={chat} /></ChatLanguage.Provider>;
}

function ChatPanel({ chat }: { chat: ReturnType<typeof useChat> }) {
  const t = useChatText();
  const [phase, setPhase] = useState<Phase>("closed");
  const [confirmClear, setConfirmClear] = useState(false);
  const { messages, loading, send, retry, giveFeedback, clear, mode, locale, setLocale, provider, setProvider } = chat;
  const launcherRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const pendingQuestion = useRef<string | null>(null);
  const closeTimer = useRef<number | null>(null);
  const [pendingTick, setPendingTick] = useState(0);

  const open = useCallback(() => {
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
    setPhase("open");
  }, []);
  const close = useCallback(() => {
    setPhase((p) => (p === "open" ? "closing" : p));
    setConfirmClear(false);
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      closeTimer.current = null;
      setPhase("closed");
      launcherRef.current?.focus();
    }, CLOSE_ANIMATION_MS);
  }, []);

  useEffect(() => () => {
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
  }, []);

  // Other page elements (FAQ, Support) can open the chat via a custom event.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<OpenChatDetail>).detail;
      if (detail?.question) {
        pendingQuestion.current = detail.question;
        setPendingTick((n) => n + 1);
      }
      open();
    };
    window.addEventListener(OPEN_CHAT_EVENT, handler);
    return () => window.removeEventListener(OPEN_CHAT_EVENT, handler);
  }, [open]);

  // Send a question handed over from elsewhere on the page once the panel is open.
  useEffect(() => {
    if (phase !== "open" || !pendingQuestion.current || loading) return;
    send(pendingQuestion.current);
    pendingQuestion.current = null;
  }, [phase, pendingTick, loading, send]);

  useEffect(() => {
    if (phase !== "open") return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [phase, close]);

  // Keep the newest message in view.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading, phase]);

  const lastMessage = messages[messages.length - 1];
  const hasConversation = messages.length > 0;

  return (
    <>
      {phase !== "closed" ? (
        <div
          role="dialog"
          aria-modal="false"
          lang={locale}
          aria-labelledby="chat-title"
          className={cn(
            "chat-panel fixed inset-0 z-50 flex flex-col overflow-hidden bg-band-alt shadow-float",
            "sm:inset-auto sm:bottom-24 sm:right-6 sm:h-[min(640px,calc(100dvh-8rem))] sm:w-[420px] sm:rounded-3xl sm:border sm:border-line",
            "origin-bottom-right",
            phase === "closing" ? "animate-chat-out" : "animate-chat-in",
          )}
        >
          {/* Header */}
          <div className="chat-header flex items-center gap-3 bg-navy px-4 py-4 text-white">
            <LogoMark className="chat-brand shrink-0" title="" />
            <div className="min-w-0 flex-1">
              <h2 id="chat-title" className="truncate font-semibold leading-tight">{t.title}</h2>
              <p className="truncate text-xs text-white/75">
                <span lang="hi" className="font-devanagari">डिजी यात्रा सहायक</span> ·{" "}
                {mode === "mock" ? "Dev preview (mock)" : t.approved}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              disabled={!hasConversation}
              aria-label={t.clear}
              title={t.clear}
              className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-white/15 disabled:opacity-40"
            >
              <Trash2 aria-hidden="true" className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={close}
              aria-label={t.close}
              title={`${t.close} (Esc)`}
              className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-white/15"
            >
              <X aria-hidden="true" className="h-5 w-5" />
            </button>
          </div>

          <div className={cn("flex items-center gap-3 border-b border-line bg-surface px-4 py-2 text-xs text-ink", provider === "novita" && "max-[350px]:gap-2 max-[350px]:px-3")}>
            <label className="flex min-w-0 flex-1 items-center gap-1.5">
              <span className={provider === "novita" ? "max-[350px]:hidden" : undefined}>{locale === "hi" ? "भाषा" : "Language"}</span>
              <select aria-label="Response language" value={locale} disabled={loading} onChange={(e) => setLocale(e.target.value as Locale)} className="min-w-0 flex-1 rounded border border-line bg-page px-1 py-1 text-ink">
                <option value="en">English</option><option value="hi">हिन्दी</option>
              </select>
            </label>
            <label className={cn("flex min-w-0 items-center gap-1.5", provider === "novita" ? "flex-[1.7] max-[350px]:flex-[2.8]" : "flex-1")}>
              <span>AI</span>
              <select aria-label="AI provider" title={{ sarvam: "Sarvam AI — sarvam-105b", anthropic: "Anthropic — claude-haiku-5-5", novita: "Novita AI — Qwen3.8 Flash" }[provider]} value={provider} disabled={loading} onChange={(e) => setProvider(e.target.value as AIProvider)} className="min-w-0 flex-1 rounded border border-line bg-page px-1 py-1 text-ink">
                <option value="sarvam">Sarvam AI — 105B</option><option value="anthropic">Anthropic — Haiku 5.5</option><option value="novita">Novita AI — Qwen3.8 Flash</option>
              </select>
            </label>
          </div>

          {/* Mode banner — never let a mock pass for real AI */}
          {mode === "mock" ? (
            <div role="note" className="flex items-start gap-2 border-b border-warning/30 bg-warning-soft px-4 py-2 text-[0.75rem] leading-snug text-ink">
              <FlaskConical aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
              <span>
                <strong className="text-warning">Development mock</strong> — AI backend not connected. Replies are
                pre-written samples, not AI. Send <code className="rounded bg-surface px-1">{MOCK_ERROR_TRIGGER}</code> to
                preview errors.
              </span>
            </div>
          ) : null}

          {confirmClear ? (
            <div role="alertdialog" aria-labelledby="clear-q" className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-4 py-2.5 text-sm">
              <span id="clear-q" className="text-ink">{t.clearQuestion}</span>
              <span className="flex gap-2">
                <button
                  type="button"
                  autoFocus
                  onClick={() => {
                    clear();
                    setConfirmClear(false);
                    inputRef.current?.focus();
                  }}
                  className="rounded bg-danger px-3 py-1 text-xs font-medium text-white hover:opacity-90"
                >
                  {t.clearButton}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmClear(false)}
                  className="rounded border border-line px-3 py-1 text-xs font-medium text-ink hover:bg-band"
                >
                  {t.cancel}
                </button>
              </span>
            </div>
          ) : null}

          {/* Conversation log */}
          <div ref={logRef} role="log" aria-live="polite" aria-label={t.conversation} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
            <div className="flex flex-col items-start">
              <div className="max-w-[90%] rounded-2xl rounded-bl-sm border border-line-soft bg-surface px-3.5 py-2.5 text-[0.92rem] leading-relaxed text-ink shadow-card">
                <p className="font-semibold text-heading">{t.welcome}</p>
                <p className="mt-1">
                  {t.greeting}
                </p>
              </div>
            </div>

            {!hasConversation ? (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-soft">{t.suggestions}</p>
                <ul className="flex flex-col gap-2">
                  {(locale === "hi" ? hindiStarters : starterQuestions).map((q) => (
                    <li key={q}>
                      <button
                        type="button"
                        onClick={() => send(q)}
                        className="w-full rounded-lg border border-brand/40 bg-surface px-3 py-2 text-left text-sm text-brand transition-colors hover:border-brand hover:bg-brand-soft"
                      >
                        {q}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                canRetry={m.id === lastMessage?.id && !loading}
                onRetry={retry}
                onFeedback={giveFeedback}
              />
            ))}
            {loading ? <TypingIndicator /> : null}
          </div>

          <ChatComposer ref={inputRef} disabled={loading} onSend={send} />
        </div>
      ) : null}

      {/* Launcher */}
      <button
        ref={launcherRef}
        type="button"
        onClick={phase === "open" ? close : open}
        aria-expanded={phase === "open"}
        aria-label={phase === "open" ? t.closeLauncher : t.open}
        className={cn(
          "chat-launcher group fixed bottom-5 right-5 z-50 flex h-16 w-16 items-center justify-center rounded-full bg-navy text-white shadow-float ring-4 ring-white transition-transform hover:scale-105 sm:bottom-6 sm:right-6 [html[data-contrast=high]_&]:ring-[#ffff00]",
          phase === "closed" ? "chat-launcher-inviting" : "max-sm:hidden",
        )}
      >
        {phase === "open" ? <X aria-hidden="true" className="h-7 w-7" /> : <LogoMark className="launcher-brand" title="" />}
        {phase === "closed" ? (
          <span className="launcher-callout" aria-hidden="true">
            <span>{locale === "hi" ? "मदद के लिए चैट करें" : "Chat for assistance"}</span>
            <strong>{locale === "hi" ? "डिजी यात्रा सहायक" : "Digi Yatra Assistant"}</strong>
          </span>
        ) : null}
      </button>
    </>
  );
}
