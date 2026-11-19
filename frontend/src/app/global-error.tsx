"use client";

/** Last-resort boundary (root layout failed). Plain markup; no internal details are rendered. */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "Arial, sans-serif", background: "#eef1f6", margin: 0 }}>
        <main style={{ maxWidth: 520, margin: "15vh auto", background: "#fff", padding: 32, borderTop: "4px solid #ee7d22", textAlign: "center" }}>
          <h1 style={{ color: "#1d3b6b", fontWeight: 500 }}>Digi Yatra Information Portal (POC)</h1>
          <p style={{ color: "#4b5563" }}>The site is temporarily unavailable. Please try again shortly.</p>
          <button type="button" onClick={reset} style={{ marginTop: 16, padding: "10px 28px", borderRadius: 999, border: 0, background: "#1659a5", color: "#fff" }}>
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
