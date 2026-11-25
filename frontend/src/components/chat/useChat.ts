"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChatApiError, getChatClient, type AnswerStatus, type ChatSource } from "@/lib/api";
import type { Locale } from "@/lib/i18n/dictionary";
import type { AIProvider } from "@/lib/api";
import {
  LEGACY_SESSION_KEY,
  MAX_BYTES,
  STORAGE_KEY,
  persistable,
  prune,
  redactSensitive,
  validMessage,
} from "@/lib/chat/history";

export const MAX_MESSAGE_LENGTH = 1000;
/** User turns sent as context; the server bounds them again by its own token budget. */
const HISTORY_LIMIT = 4;

export type FeedbackState = "none" | "sending" | "yes" | "no" | "failed";

export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  /** Assistant only */
  sources?: ChatSource[];
  origin?: "mock" | "live";
  status?: AnswerStatus;
  notices?: string[];
  feedback?: FeedbackState;
  /** Assistant only: provider that produced the answer. */
  provider?: AIProvider;
  /** User only: set when the request for this message failed. */
  error?: { message: string; retryable: boolean };
}

interface StoredChat {
  v: 1;
  conversationId: string;
  savedAt: number;
  messages: UiMessage[];
  locale?: Locale;
  provider?: AIProvider;
}

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function sanitizeSources(value: unknown): ChatSource[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value
    .filter((s): s is ChatSource => typeof s === "object" && s !== null && typeof (s as ChatSource).title === "string")
    .slice(0, 8)
    .map((s) => ({
      title: s.title.slice(0, 200),
      url: typeof s.url === "string" && /^https:\/\//.test(s.url) ? s.url : undefined,
      snippet: typeof s.snippet === "string" ? s.snippet.slice(0, 300) : undefined,
      file: typeof s.file === "string" ? s.file.slice(0, 120) : undefined,
      sourceType: typeof s.sourceType === "string" ? s.sourceType.slice(0, 24) : undefined,
      platform: typeof s.platform === "string" ? s.platform.slice(0, 16) : undefined,
      publishedOn: typeof s.publishedOn === "string" ? s.publishedOn.slice(0, 10) : undefined,
      timestampS: typeof s.timestampS === "number" ? s.timestampS : undefined,
    }));
}

/** Restore history: validate every field (stored data is untrusted), migrate the old session key
 * (redacting it), and drop expired or excess messages. */
function loadStored(): StoredChat | null {
  const store = storage();
  let raw: string | null = null;
  try {
    raw = store?.getItem(STORAGE_KEY) ?? null;
    const legacy = window.sessionStorage.getItem(LEGACY_SESSION_KEY);
    if (legacy) {
      window.sessionStorage.removeItem(LEGACY_SESSION_KEY);
      if (!raw) raw = legacy;
    }
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredChat>;
    if (typeof parsed.conversationId !== "string" || !/^[A-Za-z0-9_-]{8,64}$/.test(parsed.conversationId)) return null;
    if (!Array.isArray(parsed.messages)) return null;
    const messages = prune(parsed.messages.filter(validMessage) as UiMessage[]).map((m) => ({
      id: m.id,
      role: m.role,
      createdAt: m.createdAt,
      content: persistable(m.content),
      ...(m.role === "assistant"
        ? {
            sources: sanitizeSources(m.sources),
            status: m.status,
            notices: Array.isArray(m.notices) ? m.notices.filter((n) => typeof n === "string").slice(0, 4) : undefined,
            origin: m.origin === "mock" ? ("mock" as const) : ("live" as const),
            provider: m.provider === "anthropic" || m.provider === "novita" || m.provider === "sarvam" ? m.provider : undefined,
            // A message that was in flight when the page unloaded cannot be resumed.
            feedback: m.feedback === "sending" ? ("none" as const) : m.feedback,
          }
        : {}),
    }));
    if (messages.length === 0) {
      store?.removeItem(STORAGE_KEY);
      return { v: 1, conversationId: parsed.conversationId, savedAt: Date.now(), messages: [], locale: parsed.locale, provider: parsed.provider };
    }
    return { v: 1, conversationId: parsed.conversationId, savedAt: parsed.savedAt ?? Date.now(), messages, locale: parsed.locale, provider: parsed.provider };
  } catch {
    store?.removeItem(STORAGE_KEY);
    return null;
  }
}

function saveStored(chat: StoredChat): void {
  const store = storage();
  if (!store) return;
  if (chat.messages.length === 0) {
    store.removeItem(STORAGE_KEY);
    return;
  }
  // Persist only sanitised content; never errors, raw identifiers or in-flight state.
  let messages = prune(chat.messages).map((m) => ({
    ...m,
    content: m.role === "user" ? persistable(m.content) : redactSensitive(m.content).text,
    error: undefined,
    feedback: m.feedback === "sending" ? ("none" as const) : m.feedback,
  }));
  let body = JSON.stringify({ ...chat, messages });
  while (body.length > MAX_BYTES && messages.length > 2) {
    messages = messages.slice(2);
    body = JSON.stringify({ ...chat, messages });
  }
  try {
    store.setItem(STORAGE_KEY, body);
  } catch {
    /* quota or private mode: history simply isn't persisted */
  }
}

/**
 * Conversation state machine for the chat widget. Talks only to the
 * ChatClient abstraction, so switching mock → FastAPI needs no UI change.
 */
export function useChat() {
  const [locale, setLocale] = useState<Locale>("en");
  const [provider, setProvider] = useState<AIProvider>("sarvam");
  const client = getChatClient();
  const [conversationId, setConversationId] = useState<string>("");
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const hydrated = useRef(false);
  /** Incremented on "clear": a response that belongs to an older generation is discarded. */
  const generation = useRef(0);

  useEffect(() => {
    const stored = loadStored();
    setConversationId(stored?.conversationId ?? newId());
    setMessages(stored?.messages ?? []);
    setLocale(stored?.locale === "hi" ? "hi" : "en");
    setProvider(stored?.provider === "anthropic" || stored?.provider === "novita" ? stored.provider : "sarvam");
    hydrated.current = true;
    // History cleared in another tab of this browser must not reappear here.
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY && e.key !== null) return;
      if (e.newValue === null) {
        generation.current += 1;
        abortRef.current?.abort();
        setMessages([]);
        setConversationId(newId());
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("storage", onStorage);
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!hydrated.current || !conversationId) return;
    saveStored({ v: 1, conversationId, savedAt: Date.now(), messages, locale, provider });
  }, [conversationId, messages, locale, provider]);

  const request = useCallback(
    async (userMessage: UiMessage, priorMessages: UiMessage[]) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const gen = generation.current;
      setLoading(true);

      const history = priorMessages
        .filter((m) => !m.error && m.role === "user" && !m.content.startsWith("[Message not saved"))
        .slice(-HISTORY_LIMIT)
        .map((m) => ({ role: m.role, content: m.content }));

      try {
        const res = await client.sendMessage(
          { message: userMessage.content, conversationId, history, locale, provider },
          controller.signal,
        );
        if (gen !== generation.current) return; // cleared while in flight: never restore it
        setMessages((prev) => [
          // Show and keep the server's redaction when the question contained personal data.
          ...prev.map((m) =>
            m.id === userMessage.id && res.piiRedacted && res.redactedMessage ? { ...m, content: res.redactedMessage } : m,
          ),
          {
            id: res.messageId,
            role: "assistant",
            content: res.answer,
            sources: res.sources,
            origin: res.origin,
            status: res.status,
            notices: res.notices,
            provider: res.provider ?? provider,
            // Yes/No feedback only makes sense for real attempts to answer a question.
            feedback: res.status === "greeting" || res.status === "refused" ? undefined : "none",
            createdAt: Date.now(),
          },
        ]);
      } catch (err) {
        const apiErr =
          err instanceof ChatApiError ? err : new ChatApiError("Something went wrong. Please try again.", "server");
        if (apiErr.kind === "aborted" || gen !== generation.current) return;
        setMessages((prev) =>
          prev.map((m) => (m.id === userMessage.id ? { ...m, error: { message: locale === "hi" ? "चुने गए AI प्रदाता से जवाब नहीं मिला। कृपया फिर प्रयास करें।" : apiErr.message, retryable: apiErr.retryable } } : m)),
        );
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
          setLoading(false);
        }
      }
    },
    [client, conversationId, locale, provider],
  );

  const send = useCallback(
    (text: string) => {
      const content = text.trim().slice(0, MAX_MESSAGE_LENGTH);
      if (!content || loading) return;
      const userMessage: UiMessage = { id: newId(), role: "user", content, createdAt: Date.now() };
      const prior = messages;
      setMessages((prev) => [...prev, userMessage]);
      void request(userMessage, prior);
    },
    [loading, messages, request],
  );

  const retry = useCallback(
    (messageId: string) => {
      if (loading) return;
      const index = messages.findIndex((m) => m.id === messageId);
      const target = messages[index];
      if (!target) return;
      const cleared = { ...target, error: undefined };
      setMessages((prev) => prev.map((m) => (m.id === messageId ? cleared : m)));
      void request(cleared, messages.slice(0, index));
    },
    [loading, messages, request],
  );

  const giveFeedback = useCallback(
    async (messageId: string, resolved: boolean) => {
      const setFeedback = (feedback: FeedbackState) =>
        setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, feedback } : m)));
      setFeedback("sending");
      try {
        await client.sendFeedback({ conversationId, messageId, resolved });
        setFeedback(resolved ? "yes" : "no");
      } catch {
        setFeedback("failed");
      }
    },
    [client, conversationId],
  );

  const clear = useCallback(() => {
    generation.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    const old = conversationId;
    try {
      storage()?.removeItem(STORAGE_KEY);
      window.sessionStorage.removeItem(LEGACY_SESSION_KEY);
    } catch {
      /* nothing stored */
    }
    setMessages([]);
    setConversationId(newId());
    if (old) void client.forget(old);
  }, [client, conversationId]);

  return { messages, loading, send, retry, giveFeedback, clear, mode: client.mode, locale, setLocale, provider, setProvider };
}
