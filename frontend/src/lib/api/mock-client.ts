import { mockAnswers, mockFallback } from "@/content/mock-answers";
import { ChatApiError, type ChatClient, type ChatRequest, type ChatResponse, type FeedbackRequest } from "./types";

/** Typing this phrase in mock mode simulates a backend failure (to exercise retry UI). */
export const MOCK_ERROR_TRIGGER = "#test-error";

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new ChatApiError("Request cancelled.", "aborted"));
      },
      { once: true },
    );
  });
}

function score(message: string, keywords: readonly string[]): number {
  const text = message.toLowerCase();
  return keywords.reduce((total, k) => (text.includes(k) ? total + k.length : total), 0);
}

/**
 * DEVELOPMENT ONLY. Returns canned answers written from the project
 * knowledge base using simple keyword matching. It is not AI and must
 * always be labelled as a mock in the UI (origin: "mock").
 */
export class MockChatClient implements ChatClient {
  readonly mode = "mock" as const;
  private counter = 0;

  async sendMessage(request: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
    await delay(700 + Math.random() * 600, signal);

    if (request.message.toLowerCase().includes(MOCK_ERROR_TRIGGER)) {
      throw new ChatApiError("Simulated failure (mock mode). Press Retry to try again.", "server", 503);
    }

    let best = mockFallback;
    let bestScore = 0;
    for (const entry of mockAnswers) {
      const s = score(request.message, entry.keywords);
      if (s > bestScore) {
        best = entry;
        bestScore = s;
      }
    }

    this.counter += 1;
    return {
      messageId: `mock-${Date.now()}-${this.counter}`,
      answer: best.answer,
      sources: [...best.sources],
      origin: "mock",
      status: best === mockFallback ? "insufficient_evidence" : "answered",
      notices: [],
    };
  }

  async sendFeedback(_feedback: FeedbackRequest): Promise<void> {
    void _feedback;
    await delay(150);
  }
}
