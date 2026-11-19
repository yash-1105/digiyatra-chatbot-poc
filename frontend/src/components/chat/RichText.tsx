import { Fragment } from "react";

const TOKEN = /(https?:\/\/[^\s)]*[^\s).,;:!?]|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})/g;

/**
 * Renders assistant/user text safely (no HTML injection): preserves line
 * breaks and turns URLs and email addresses into links.
 */
export function RichText({ text }: { text: string }) {
  const parts = text.split(TOKEN);
  return (
    <span className="whitespace-pre-line break-words">
      {parts.map((part, i) => {
        if (i % 2 === 1) {
          const isEmail = !part.startsWith("http");
          return (
            <a
              key={i}
              href={isEmail ? `mailto:${part}` : part}
              {...(isEmail ? {} : { target: "_blank", rel: "noopener noreferrer" })}
              className="break-all underline underline-offset-2"
            >
              {part}
            </a>
          );
        }
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </span>
  );
}
