/**
 * Chat API contract shared by the mock client and the FastAPI client.
 * The FastAPI backend (next milestone) should implement:
 *
 *   POST {API_BASE}/api/v1/chat            ChatRequest  -> ChatResponse
 *   POST {API_BASE}/api/v1/chat/feedback   FeedbackRequest -> 204
 *
 * JSON bodies use snake_case on the wire; see http-client.ts for mapping.
 */
export type ChatRole = "user" | "assistant";

export interface ChatSource {
  /** Human-readable title of the cited document or section. */
  title: string;
  /** Original knowledge-base filename the passage came from. */
  file?: string;
  /** Optional external URL; omitted for internal knowledge-base documents. */
  url?: string;
  /** Short quoted passage supporting the answer. */
  snippet?: string;
}

export interface ChatHistoryItem {
  role: ChatRole;
  content: string;
}

export interface ChatRequest {
  message: string;
  conversationId: string;
  history: ChatHistoryItem[];
  locale: "en" | "hi";
}

export type AnswerStatus =
  | "answered"
  | "insufficient_evidence"
  | "out_of_scope"
  | "refused"
  | "greeting"
  | "live_status";

export interface ChatResponse {
  messageId: string;
  answer: string;
  sources: ChatSource[];
  /** "mock" responses are canned development previews, never AI output. */
  origin: "mock" | "live";
  /** How the backend handled the question (grounded answer, safe fallback, refusal …). */
  status: AnswerStatus;
  /** Safety / freshness notices to show with the answer (e.g. "don't share OTPs"). */
  notices: string[];
}

export interface FeedbackRequest {
  conversationId: string;
  messageId: string;
  resolved: boolean;
}

export interface ChatClient {
  readonly mode: "mock" | "api";
  sendMessage(request: ChatRequest, signal?: AbortSignal): Promise<ChatResponse>;
  sendFeedback(feedback: FeedbackRequest): Promise<void>;
}

export type ChatErrorKind = "network" | "timeout" | "server" | "rate_limited" | "bad_request" | "aborted";

export class ChatApiError extends Error {
  constructor(
    message: string,
    readonly kind: ChatErrorKind,
    readonly status?: number,
  ) {
    // `message` is always user-safe (either our own text or the backend's error.message).
    super(message);
    this.name = "ChatApiError";
  }

  get retryable(): boolean {
    return this.kind !== "bad_request" && this.kind !== "aborted";
  }
}
