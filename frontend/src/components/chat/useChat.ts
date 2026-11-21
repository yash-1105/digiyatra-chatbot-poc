"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChatApiError, getChatClient, type AnswerStatus, type ChatSource } from "@/lib/api";
import type { Locale } from "@/lib/i18n/dictionary";
import type { AIProvider } from "@/lib/api";

export const MAX_MESSAGE_LENGTH = 1000;
const STORAGE_KEY = "dy-poc-chat";
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
  /** User only: set when the request for this message failed. */
  error?: { message: string; retryable: boolean };
}

interface StoredChat {
  conversationId: string;
  messages: UiMessage[];
  locale?: Locale;
  provider?: AIProvider;
}

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function loadStored(): StoredChat | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredChat;
    if (typeof parsed.conversationId !== "string" || !Array.isArray(parsed.messages)) return null;
    // A message that was in flight when the page unloaded cannot be resumed.
    return { ...parsed, messages: parsed.messages.map((m) => (m.feedback === "sending" ? { ...m, feedback: "none" } : m)) };
  } catch {
    return null;
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

  useEffect(() => {
    const stored = loadStored();
    setConversationId(stored?.conversationId ?? newId());
    setMessages(stored?.messages ?? []);
    setLocale(stored?.locale === "hi" ? "hi" : "en");
    setProvider(stored?.provider === "anthropic" || stored?.provider === "novita" ? stored.provider : "sarvam");
    hydrated.current = true;
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!hydrated.current || !conversationId) return;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ conversationId, messages, locale, provider } satisfies StoredChat));
    } catch {
      /* storage unavailable — conversation simply won't survive a reload */
    }
  }, [conversationId, messages, locale, provider]);

  const request = useCallback(
    async (userMessage: UiMessage, priorMessages: UiMessage[]) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);

      const history = priorMessages
        .filter((m) => !m.error && m.role === "user")
        .slice(-HISTORY_LIMIT)
        .map((m) => ({ role: m.role, content: m.content }));

      try {
        const res = await client.sendMessage(
          { message: userMessage.content, conversationId, history, locale, provider },
          controller.signal,
        );
        setMessages((prev) => [
          ...prev,
          {
            id: res.messageId,
            role: "assistant",
            content: res.answer,
            sources: res.sources,
            origin: res.origin,
            status: res.status,
            notices: res.notices,
            // Yes/No feedback only makes sense for real attempts to answer a question.
            feedback: res.status === "greeting" || res.status === "refused" ? undefined : "none",
            createdAt: Date.now(),
          },
        ]);
      } catch (err) {
        const apiErr =
          err instanceof ChatApiError ? err : new ChatApiError("Something went wrong. Please try again.", "server");
        if (apiErr.kind === "aborted") return;
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
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
    setMessages([]);
    setConversationId(newId());
  }, []);

  return { messages, loading, send, retry, giveFeedback, clear, mode: client.mode, locale, setLocale, provider, setProvider };
}
