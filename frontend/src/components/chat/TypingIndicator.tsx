export function TypingIndicator() {
  return (
    <div className="flex items-start" role="status">
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm border border-line-soft bg-surface px-4 py-3 shadow-card">
        <span className="typing-dot h-2 w-2 rounded-full bg-brand" />
        <span className="typing-dot h-2 w-2 rounded-full bg-brand" />
        <span className="typing-dot h-2 w-2 rounded-full bg-brand" />
        <span className="sr-only">The assistant is typing…</span>
      </div>
    </div>
  );
}
