"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  CircleHelp,
  Clock3,
  HelpCircle,
  Loader2,
  MessagesSquare,
  RefreshCw,
  ShieldCheck,
  Table2,
  Target,
  XCircle,
} from "lucide-react";
import { AdminApiError, fetchAnalytics, type AnalyticsReport, type RangeDays, type ResolutionStatus } from "@/lib/api/admin-client";
import { cn } from "@/lib/cn";

/* ------------------------------------------------------------------ helpers */

const nf = new Intl.NumberFormat("en-IN");

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return s ? `${m} min ${s} s` : `${m} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${m % 60} min`;
}

function shortDate(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
}

function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

const STATUS: Record<ResolutionStatus, { label: string; icon: typeof CheckCircle2; badge: string; tile: string }> = {
  resolved: { label: "Resolved", icon: CheckCircle2, badge: "bg-success-soft text-success", tile: "border-success/40" },
  unresolved: { label: "Unresolved", icon: XCircle, badge: "bg-danger-soft text-danger", tile: "border-danger/40" },
  unconfirmed: { label: "No feedback", icon: CircleHelp, badge: "bg-band text-ink-muted", tile: "border-line" },
};

/* --------------------------------------------------------------- components */

function Panel({ title, icon: Icon, children, className, action }: {
  title: string; icon: typeof BarChart3; children: React.ReactNode; className?: string; action?: React.ReactNode;
}) {
  const id = `panel-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section aria-labelledby={id} className={cn("dashboard-panel rounded-2xl border border-line-soft bg-surface shadow-card", className)}>
      <div className="flex items-center justify-between gap-3 border-b border-line-soft px-5 py-3">
        <h2 id={id} className="flex items-center gap-2 text-[1.05rem] font-semibold text-heading">
          <Icon aria-hidden="true" className="h-5 w-5 text-accent" />
          {title}
        </h2>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p role="status" className="rounded border border-dashed border-line px-4 py-6 text-center text-sm text-ink-muted">
      {children}
    </p>
  );
}

function MetricCard({ label, value, hint, icon: Icon, empty }: {
  label: string; value: string; hint: string; icon: typeof BarChart3; empty?: boolean;
}) {
  return (
    <div className="metric-card flex flex-col rounded-2xl border border-line-soft bg-surface p-6 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-ink-muted">{label}</p>
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-soft text-brand">
          <Icon aria-hidden="true" className="h-5 w-5" />
        </span>
      </div>
      <p className={cn("mt-2 font-semibold tabular-nums text-heading", empty ? "text-2xl text-ink-soft" : "text-[2rem] leading-tight")}>
        {value}
      </p>
      <p className="mt-1 text-xs leading-snug text-ink-soft">{hint}</p>
    </div>
  );
}

function TopTopics({ data }: { data: AnalyticsReport["top_topics"] }) {
  if (data.length === 0) return <Empty>No questions in this period yet.</Empty>;
  const max = Math.max(...data.map((d) => d.count));
  return (
    <ol className="space-y-3">
      {data.map((t, i) => (
        <li key={t.topic}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
            <span className="text-ink">
              <span className="mr-2 font-semibold text-ink-soft">{i + 1}.</span>
              {t.label}
            </span>
            <span className="font-semibold tabular-nums text-ink">{nf.format(t.count)}</span>
          </div>
          <div className="h-2.5 rounded-full bg-band" aria-hidden="true">
            <div className="h-2.5 rounded-full bg-brand" style={{ width: `${Math.max(4, (t.count / max) * 100)}%` }} />
          </div>
        </li>
      ))}
    </ol>
  );
}

function ResolutionStatusPanel({ r }: { r: AnalyticsReport["resolution"] }) {
  const total = r.resolved + r.unresolved + r.unconfirmed;
  return (
    <>
      <ul className="grid grid-cols-3 gap-3">
        {(["resolved", "unresolved", "unconfirmed"] as const).map((k) => {
          const s = STATUS[k];
          return (
            <li key={k} className={cn("rounded-md border bg-surface p-3 text-center", s.tile)}>
              <s.icon aria-hidden="true" className={cn("mx-auto h-6 w-6", s.badge.split(" ")[1])} />
              <p className="mt-1 text-2xl font-semibold tabular-nums text-heading">{nf.format(r[k])}</p>
              <p className="text-xs font-medium text-ink-muted">{s.label}</p>
            </li>
          );
        })}
      </ul>
      {total > 0 ? (
        <div className="mt-4 flex h-3 gap-[2px] overflow-hidden rounded-full" aria-hidden="true">
          {r.resolved > 0 && <div className="bg-success" style={{ flexGrow: r.resolved }} />}
          {r.unresolved > 0 && <div className="bg-danger" style={{ flexGrow: r.unresolved }} />}
          {r.unconfirmed > 0 && <div className="bg-line" style={{ flexGrow: r.unconfirmed }} />}
        </div>
      ) : null}
      <p className="mt-4 text-xs leading-relaxed text-ink-soft">
        Resolution is counted only when a passenger answers “Did this resolve your issue?”. Rate = Resolved ÷ (Resolved +
        Unresolved). Conversations without feedback are shown separately and never counted as resolved.
      </p>
    </>
  );
}

function bar(x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h} Z`;
}

function DailyChart({ data }: { data: AnalyticsReport["daily"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const total = data.reduce((a, d) => a + d.conversations, 0);
  const max = Math.max(1, ...data.map((d) => d.conversations));
  const W = 720;
  const H = 220;
  const pad = { l: 34, r: 8, t: 14, b: 26 };
  const plotW = W - pad.l - pad.r;
  const plotH = H - pad.t - pad.b;
  const step = plotW / data.length;
  const bw = Math.max(4, step - 2);
  const ticks = max <= 4 ? Array.from({ length: max + 1 }, (_, i) => i) : [0, Math.round(max / 2), max];
  const peak = data.reduce((best, d, i) => (d.conversations > (data[best]?.conversations ?? -1) ? i : best), 0);
  const labelEvery = data.length > 14 ? 5 : 1;

  const toggle = (
    <button
      type="button"
      onClick={() => setAsTable((v) => !v)}
      aria-pressed={asTable}
      className="flex items-center gap-1 rounded border border-line px-2 py-1 text-xs text-brand hover:bg-brand-soft"
    >
      {asTable ? <BarChart3 aria-hidden="true" className="h-3.5 w-3.5" /> : <Table2 aria-hidden="true" className="h-3.5 w-3.5" />}
      {asTable ? "Show chart" : "Show table"}
    </button>
  );

  return (
    <Panel title="Daily conversation activity" icon={BarChart3} action={toggle}>
      {total === 0 && !asTable ? (
        <Empty>No conversations in this period yet. Activity will appear here as passengers use the chatbot.</Empty>
      ) : asTable ? (
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Conversations and questions per day</caption>
            <thead className="sticky top-0 bg-band text-xs uppercase text-ink-muted">
              <tr>
                <th scope="col" className="px-3 py-2">Date</th>
                <th scope="col" className="px-3 py-2 text-right">Conversations</th>
                <th scope="col" className="px-3 py-2 text-right">Questions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.date} className="border-b border-line-soft">
                  <th scope="row" className="px-3 py-1.5 font-normal text-ink">{shortDate(d.date)}</th>
                  <td className="px-3 py-1.5 text-right tabular-nums">{d.conversations}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{d.questions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="h-auto w-full"
            role="img"
            aria-label={`Conversations per day. ${nf.format(total)} in total; busiest day ${shortDate(data[peak]!.date)} with ${data[peak]!.conversations}.`}
            onMouseLeave={() => setHover(null)}
          >
            {ticks.map((t) => {
              const y = pad.t + plotH - (t / max) * plotH;
              return (
                <g key={t}>
                  <line x1={pad.l} x2={W - pad.r} y1={y} y2={y} stroke="var(--line-soft)" strokeWidth={1} />
                  <text x={pad.l - 6} y={y + 4} textAnchor="end" fontSize="11" fill="var(--ink-soft)">{t}</text>
                </g>
              );
            })}
            {data.map((d, i) => {
              const h = (d.conversations / max) * plotH;
              const x = pad.l + i * step + (step - bw) / 2;
              return (
                <g key={d.date} onMouseEnter={() => setHover(i)}>
                  <rect x={pad.l + i * step} y={pad.t} width={step} height={plotH} fill="transparent" />
                  {d.conversations > 0 && (
                    <path d={bar(x, pad.t + plotH - h, bw, h, 4)} fill="var(--brand)" opacity={hover === null || hover === i ? 1 : 0.55} />
                  )}
                  {i === peak && d.conversations > 0 && (
                    <text x={x + bw / 2} y={pad.t + plotH - h - 4} textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--ink)">
                      {d.conversations}
                    </text>
                  )}
                  {(i % labelEvery === 0 || i === data.length - 1) && (
                    <text x={pad.l + i * step + step / 2} y={H - 8} textAnchor="middle" fontSize="10.5" fill="var(--ink-soft)">
                      {shortDate(d.date)}
                    </text>
                  )}
                </g>
              );
            })}
            <line x1={pad.l} x2={W - pad.r} y1={pad.t + plotH} y2={pad.t + plotH} stroke="var(--line)" strokeWidth={1} />
          </svg>
          {hover !== null && data[hover] ? (
            <div
              className="pointer-events-none absolute top-0 rounded border border-line bg-surface px-3 py-2 text-xs shadow-float"
              style={{ left: `clamp(0px, calc(${((pad.l + hover * step + step / 2) / W) * 100}% - 70px), calc(100% - 140px))` }}
            >
              <p className="font-semibold text-ink">{shortDate(data[hover].date)}</p>
              <p className="text-ink-muted">{data[hover].conversations} conversations</p>
              <p className="text-ink-muted">{data[hover].questions} questions</p>
            </div>
          ) : null}
        </div>
      )}
    </Panel>
  );
}

function Unanswered({ data, outOfScope }: { data: AnalyticsReport["unanswered"]; outOfScope: number }) {
  return (
    <>
      {data.length === 0 ? (
        <Empty>Every question in this period was answered from the knowledge base.</Empty>
      ) : (
        <ul className="divide-y divide-line-soft">
          {data.map((u) => (
            <li key={u.topic} className="flex items-start justify-between gap-3 py-2.5 first:pt-0">
              <div>
                <p className="text-sm font-medium text-ink">{u.label}</p>
                {u.keywords.length > 0 && (
                  <p className="mt-1 flex flex-wrap gap-1">
                    {u.keywords.map((k) => (
                      <span key={k} className="rounded bg-band px-1.5 py-0.5 text-[0.7rem] text-ink-muted">{k}</span>
                    ))}
                  </p>
                )}
              </div>
              <span className="shrink-0 rounded-full bg-warning-soft px-2.5 py-0.5 text-sm font-semibold tabular-nums text-warning">
                {nf.format(u.count)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-ink-soft">
        Questions the assistant could not answer from approved information, grouped by category. Off-topic (non-Digi
        Yatra) questions in this period: <strong className="text-ink">{nf.format(outOfScope)}</strong>.
      </p>
    </>
  );
}

function RecentTable({ rows }: { rows: AnalyticsReport["recent"] }) {
  if (rows.length === 0) return <Empty>No conversations in this period yet.</Empty>;
  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <caption className="sr-only">Most recent conversations (anonymous)</caption>
        <thead className="bg-band text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th scope="col" className="px-5 py-2.5">Conversation</th>
            <th scope="col" className="px-3 py-2.5">Category</th>
            <th scope="col" className="px-3 py-2.5 text-right">Questions</th>
            <th scope="col" className="px-3 py-2.5">Status</th>
            <th scope="col" className="px-3 py-2.5">Started</th>
            <th scope="col" className="px-5 py-2.5 text-right">Time to resolve</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const s = STATUS[r.status];
            return (
              <tr key={r.conversation} className="border-b border-line-soft last:border-0">
                <th scope="row" className="px-5 py-2.5 font-mono text-xs font-medium text-ink">{r.conversation}</th>
                <td className="px-3 py-2.5 text-ink">{r.topic_label}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{r.questions}</td>
                <td className="px-3 py-2.5">
                  <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", s.badge)}>
                    <s.icon aria-hidden="true" className="h-3.5 w-3.5" /> {s.label}
                  </span>
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-ink-muted">{dateTime(r.started_at)}</td>
                <td className="px-5 py-2.5 text-right tabular-nums text-ink-muted">{formatDuration(r.resolution_seconds)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AIUsagePanel({ usage }: { usage: NonNullable<AnalyticsReport["ai_usage"]> }) {
  const money = (value: number) => `$${value.toFixed(6)}`;
  return <Panel title="AI Usage & Costs" icon={BarChart3}>
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {usage.providers.map((p) => <div key={p.provider}><p className="text-sm text-ink-muted">{p.provider === "novita" ? "Novita requests" : p.provider === "sarvam" ? "Sarvam requests" : "Anthropic requests"}</p><p className="text-2xl font-semibold text-heading">{nf.format(p.requests)}</p><p className="text-xs text-ink-soft">{p.model} · {p.cache_hits} FAQ cache hits · {p.errors} errors</p></div>)}
      <div><p className="text-sm text-ink-muted">Total estimated AI cost</p><p className="text-2xl font-semibold text-heading">{money(usage.total_estimated_usd)}</p></div>
      <div><p className="text-sm text-ink-muted">Average cost per AI response</p><p className="text-2xl font-semibold text-heading">{money(usage.average_usd)}</p></div>
    </div>
    <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-xs" aria-label="AI token usage by provider"><thead><tr>{["Provider", "Input tokens", "Output tokens", "Cache read / write", "Average tokens", "Estimated USD"].map(h => <th key={h} className="border-b border-line px-2 py-2 font-semibold text-heading">{h}</th>)}</tr></thead><tbody>{usage.providers.map(p => <tr key={p.provider}><td className="px-2 py-2">{p.provider}</td><td>{nf.format(p.input_tokens)}</td><td>{nf.format(p.output_tokens)}</td><td>{nf.format(p.cache_read_tokens)} / {nf.format(p.cache_write_tokens)}</td><td>{Math.round(p.average_tokens)}</td><td>{money(p.estimated_usd)}</td></tr>)}</tbody></table></div>
    <details className="mt-4 text-sm"><summary className="cursor-pointer text-brand">Token usage trends</summary><div className="mt-2 max-h-60 overflow-auto"><table className="w-full text-left text-xs" aria-label="Daily AI token usage"><thead><tr><th>Date</th><th>Input tokens</th><th>Output tokens</th><th>Estimated USD</th></tr></thead><tbody>{usage.daily.map(d => <tr key={d.date}><td className="py-1">{d.date}</td><td>{nf.format(d.input_tokens)}</td><td>{nf.format(d.output_tokens)}</td><td>{money(d.estimated_usd)}</td></tr>)}</tbody></table></div></details>
    <p className="mt-3 text-xs text-ink-soft">{usage.note} Token counts missing from the provider are estimates.</p>
  </Panel>;
}

/* ---------------------------------------------------------------- the view */

export function DashboardView() {
  const [days, setDays] = useState<RangeDays>(7);
  const [data, setData] = useState<AnalyticsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updated, setUpdated] = useState<Date | null>(null);

  const load = useCallback(async (range: RangeDays, signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const report = await fetchAnalytics(range, signal);
      setData(report);
      setUpdated(new Date());
    } catch (e) {
      if (signal?.aborted) return;
      if (e instanceof AdminApiError && e.status === 401) {
        window.location.assign("/admin/login?next=/admin/dashboard");
        return;
      }
      setError(e instanceof Error ? e.message : "Analytics could not be loaded.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    void load(days, ctrl.signal);
    return () => ctrl.abort();
  }, [days, load]);

  const r = data?.resolution;
  const cards = useMemo(() => {
    if (!data || !r) return null;
    return [
      { label: "Total Conversations", icon: MessagesSquare, value: nf.format(data.totals.conversations),
        hint: "Chat sessions with at least one question" },
      { label: "Total Questions", icon: HelpCircle, value: nf.format(data.totals.questions),
        hint: "Questions asked (greetings excluded)" },
      r.rate_percent === null
        ? { label: "Confirmed Resolution Rate", icon: Target, value: "No feedback yet", empty: true,
            hint: "Shown once passengers answer Yes or No" }
        : { label: "Confirmed Resolution Rate", icon: Target, value: `${r.rate_percent}%`,
            hint: `${r.resolved} resolved of ${r.confirmed} with feedback` },
      r.avg_resolution_seconds === null
        ? { label: "Average Resolution Time", icon: Clock3, value: "No resolved chats", empty: true,
            hint: "From first question to the passenger’s “Yes”" }
        : { label: "Average Resolution Time", icon: Clock3, value: formatDuration(r.avg_resolution_seconds),
            hint: `First question → “Yes”, across ${r.resolved} resolved` },
    ];
  }, [data, r]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[1.75rem] font-medium leading-tight text-heading">Chatbot Dashboard</h1>
          <span aria-hidden="true" className="mt-2 block h-[3px] w-14 rounded bg-accent" />
          <p className="mt-2 text-sm text-ink-muted">
            Usage and issue resolution for the Digi Yatra Assistant
            {updated ? <> · updated {updated.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</> : null}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div role="group" aria-label="Reporting period" className="inline-flex rounded border border-line bg-surface p-0.5">
            {([7, 30] as const).map((d) => (
              <button
                key={d}
                type="button"
                aria-pressed={days === d}
                onClick={() => setDays(d)}
                className={cn(
                  "rounded px-3.5 py-1.5 text-sm font-medium transition-colors",
                  days === d ? "bg-panel text-white [html[data-contrast=high]_&]:text-black" : "text-brand hover:bg-brand-soft",
                )}
              >
                Last {d} days
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => void load(days)}
            disabled={loading}
            aria-label="Refresh data"
            className="flex h-9 w-9 items-center justify-center rounded border border-line bg-surface text-brand hover:bg-brand-soft disabled:opacity-60"
          >
            <RefreshCw aria-hidden="true" className={cn("h-4 w-4", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {error ? (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-danger/40 bg-danger-soft p-4 text-sm text-ink">
          <span className="flex items-center gap-2">
            <AlertCircle aria-hidden="true" className="h-5 w-5 text-danger" /> {error}
          </span>
          <button type="button" onClick={() => void load(days)} className="rounded border border-danger/50 px-3 py-1 font-medium text-danger">
            Retry
          </button>
        </div>
      ) : null}

      {!data && loading ? (
        <div className="flex items-center justify-center gap-2 rounded-md bg-surface p-16 text-ink-muted shadow-card" role="status">
          <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin" /> Loading analytics…
        </div>
      ) : null}

      {data && cards ? (
        <div className={cn("space-y-6 transition-opacity", loading && "opacity-60")} aria-busy={loading}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map((c) => (
              <MetricCard key={c.label} {...c} />
            ))}
          </div>

          {data.ai_usage ? <AIUsagePanel usage={data.ai_usage} /> : null}

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Most frequently asked topics" icon={BarChart3}>
              <TopTopics data={data.top_topics} />
            </Panel>
            <Panel title="Resolution status" icon={CheckCircle2}>
              <ResolutionStatusPanel r={data.resolution} />
            </Panel>
          </div>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <DailyChart data={data.daily} />
            <Panel title="Unanswered question categories" icon={AlertCircle}>
              <Unanswered data={data.unanswered} outOfScope={data.out_of_scope_count} />
            </Panel>
          </div>

          <Panel title="Recent activity" icon={MessagesSquare}>
            <RecentTable rows={data.recent} />
          </Panel>

          <p className="flex items-start gap-2 text-xs leading-relaxed text-ink-soft">
            <ShieldCheck aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            Privacy: no chat messages or passenger details are stored. Conversations are anonymous identifiers, and questions
            are recorded only as a category and a few standard keywords. All times are measured from the passenger’s first
            question.
          </p>
        </div>
      ) : null}
    </div>
  );
}
