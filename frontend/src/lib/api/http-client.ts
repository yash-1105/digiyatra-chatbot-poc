import {
  ChatApiError,
  type AnswerStatus,
  type ChatClient,
  type ChatRequest,
  type ChatResponse,
  type ChatSource,
  type FeedbackRequest,
} from "./types";

interface WireSource {
  title?: unknown;
  url?: unknown;
  snippet?: unknown;
  source_file?: unknown;
  source_type?: unknown;
  platform?: unknown;
  published_on?: unknown;
  timestamp_s?: unknown;
}

interface WireChatResponse {
  message_id?: unknown;
  answer?: unknown;
  sources?: unknown;
  status?: unknown;
  notices?: unknown;
}

const STATUSES: AnswerStatus[] = ["answered", "insufficient_evidence", "out_of_scope", "refused", "greeting", "live_status"];

function parseSources(value: unknown): ChatSource[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((s): s is WireSource => typeof s === "object" && s !== null)
    .filter((s) => typeof s.title === "string" && s.title.length > 0)
    .map((s) => ({
      title: s.title as string,
      url: typeof s.url === "string" && /^https?:\/\//.test(s.url) ? s.url : undefined,
      snippet: typeof s.snippet === "string" ? s.snippet : undefined,
      file: typeof s.source_file === "string" ? s.source_file : undefined,
      sourceType: typeof s.source_type === "string" && /^[a-z_]{2,24}$/.test(s.source_type) ? s.source_type : undefined,
      platform: typeof s.platform === "string" && /^[a-z]{1,16}$/.test(s.platform) ? s.platform : undefined,
      publishedOn: typeof s.published_on === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s.published_on) ? s.published_on : undefined,
      timestampS: typeof s.timestamp_s === "number" && Number.isInteger(s.timestamp_s) && s.timestamp_s >= 0 ? s.timestamp_s : undefined,
    }));
}

/** Builds a user-facing error, preferring the backend's own safe `error.message`. */
async function errorFromResponse(res: Response): Promise<ChatApiError> {
  let serverMessage: string | undefined;
  try {
    const body = (await res.json()) as { error?: { message?: unknown } };
    if (typeof body.error?.message === "string" && body.error.message.length < 300) serverMessage = body.error.message;
  } catch {
    /* non-JSON error (e.g. proxy cannot reach backend) */
  }
  const { status } = res;
  if (status === 429)
    return new ChatApiError(serverMessage ?? "Too many requests. Please wait a moment and try again.", "rate_limited", status);
  if (status === 504) return new ChatApiError(serverMessage ?? "The assistant took too long to respond.", "timeout", status);
  if (status >= 400 && status < 500)
    return new ChatApiError(serverMessage ?? "The assistant could not process this request.", "bad_request", status);
  return new ChatApiError(serverMessage ?? "The assistant service is temporarily unavailable.", "server", status);
}

/**
 * Talks to the FastAPI backend. Selected when NEXT_PUBLIC_CHAT_MODE=api.
 */
export class HttpChatClient implements ChatClient {
  readonly mode = "api" as const;

  constructor(
    private readonly baseUrl: string,
    private readonly timeoutMs: number,
  ) {}

  private async post(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), this.timeoutMs);
    const onAbort = () => controller.abort(signal?.reason);
    signal?.addEventListener("abort", onAbort, { once: true });

    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
        credentials: "same-origin",
      });
      if (!res.ok) throw await errorFromResponse(res);
      return res;
    } catch (err) {
      if (err instanceof ChatApiError) throw err;
      if (signal?.aborted) throw new ChatApiError("Request cancelled.", "aborted");
      if (controller.signal.aborted) throw new ChatApiError("The assistant took too long to respond.", "timeout");
      throw new ChatApiError("Unable to reach the assistant service. Check your connection.", "network");
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }
  }

  async sendMessage(request: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
    const res = await this.post(
      "/api/v1/chat",
      {
        message: request.message,
        conversation_id: request.conversationId,
        history: request.history,
        locale: request.locale,
        provider: request.provider ?? "sarvam",
      },
      signal,
    );

    let data: WireChatResponse;
    try {
      data = (await res.json()) as WireChatResponse;
    } catch {
      throw new ChatApiError("The assistant returned an unreadable response.", "server", res.status);
    }
    if (typeof data.answer !== "string" || typeof data.message_id !== "string") {
      throw new ChatApiError("The assistant returned an incomplete response.", "server", res.status);
    }
    return {
      messageId: data.message_id,
      answer: data.answer,
      sources: parseSources(data.sources),
      origin: "live",
      status: STATUSES.includes(data.status as AnswerStatus) ? (data.status as AnswerStatus) : "answered",
      notices: Array.isArray(data.notices) ? data.notices.filter((n): n is string => typeof n === "string") : [],
    };
  }

  async sendFeedback(feedback: FeedbackRequest): Promise<void> {
    await this.post("/api/v1/chat/feedback", {
      conversation_id: feedback.conversationId,
      message_id: feedback.messageId,
      resolved: feedback.resolved,
    });
  }
}
