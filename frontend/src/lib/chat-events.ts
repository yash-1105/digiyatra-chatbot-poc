/** Lets any part of the page open the chat widget (optionally with a question). */
export const OPEN_CHAT_EVENT = "dy:open-chat";

export interface OpenChatDetail {
  question?: string;
}

export function openChat(detail: OpenChatDetail = {}) {
  window.dispatchEvent(new CustomEvent<OpenChatDetail>(OPEN_CHAT_EVENT, { detail }));
}
