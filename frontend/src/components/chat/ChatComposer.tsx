"use client";

import { forwardRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { SendHorizontal } from "lucide-react";
import { cn } from "@/lib/cn";
import { MAX_MESSAGE_LENGTH } from "./useChat";

interface Props {
  disabled: boolean;
  onSend: (text: string) => void;
}

export const ChatComposer = forwardRef<HTMLTextAreaElement, Props>(function ChatComposer({ disabled, onSend }, ref) {
  const [value, setValue] = useState("");
  const remaining = MAX_MESSAGE_LENGTH - value.length;
  const canSend = value.trim().length > 0 && !disabled;

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!canSend) return;
    onSend(value);
    setValue("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={submit} className="border-t border-line bg-surface p-3">
      <div className="flex items-end gap-2 rounded-xl border border-line bg-page px-3 py-2 focus-within:border-brand">
        <label htmlFor="chat-input" className="sr-only">
          Type your question
        </label>
        <textarea
          id="chat-input"
          ref={ref}
          rows={1}
          value={value}
          maxLength={MAX_MESSAGE_LENGTH}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about Digi Yatra…"
          aria-describedby="chat-input-hint"
          className="max-h-32 min-h-[1.5rem] flex-1 resize-none bg-transparent text-[0.92rem] leading-6 text-ink placeholder:text-ink-soft focus:outline-none [field-sizing:content]"
        />
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Send message"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-white transition-colors hover:bg-brand-strong disabled:bg-line disabled:text-ink-soft [html[data-contrast=high]_&]:text-black"
        >
          <SendHorizontal aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>
      <div id="chat-input-hint" className="mt-1.5 flex justify-between px-1 text-[0.68rem] text-ink-soft">
        <span>Enter to send · Shift+Enter for a new line</span>
        <span className={cn(remaining < 100 ? "text-warning" : "")} aria-live="polite">
          {remaining < 200 ? `${remaining} characters left` : ""}
        </span>
      </div>
    </form>
  );
});
