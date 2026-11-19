import { publicConfig } from "@/lib/config";
import { HttpChatClient } from "./http-client";
import { MockChatClient } from "./mock-client";
import type { ChatClient } from "./types";

export * from "./types";
export { MOCK_ERROR_TRIGGER } from "./mock-client";

let client: ChatClient | null = null;

/**
 * Returns the real FastAPI client. The labelled mock is available ONLY in `next dev` with an explicit
 * NEXT_PUBLIC_CHAT_MODE=mock; production builds always use the real API (the mock branch is compiled out).
 */
export function getChatClient(): ChatClient {
  if (!client) {
    client =
      process.env.NODE_ENV !== "production" && publicConfig.chatMode === "mock"
        ? new MockChatClient()
        : new HttpChatClient(publicConfig.apiBaseUrl, publicConfig.chatTimeoutMs);
  }
  return client;
}
