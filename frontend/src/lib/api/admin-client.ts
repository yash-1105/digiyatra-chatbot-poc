/** Typed client for the protected analytics endpoint. */
import { publicConfig } from "@/lib/config";

export type RangeDays = 7 | 30;
export type ResolutionStatus = "resolved" | "unresolved" | "unconfirmed";

export interface AIUsageReport {
  providers: { provider: string; model: string; requests: number; cache_hits: number; errors: number;
    input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number;
    estimated_usd: number; average_tokens: number; average_usd: number; estimated_token_requests: number }[];
  daily: { date: string; input_tokens: number; output_tokens: number; estimated_usd: number }[];
  total_estimated_usd: number; average_usd: number; note: string; costs_are_estimates: boolean;
}
export interface AnalyticsReport {
  ai_usage?: AIUsageReport;
  range: { days: number; start: string; end: string };
  totals: { conversations: number; questions: number };
  resolution: {
    resolved: number;
    unresolved: number;
    unconfirmed: number;
    confirmed: number;
    rate_percent: number | null;
    avg_resolution_seconds: number | null;
  };
  top_topics: { topic: string; label: string; count: number }[];
  unanswered: { topic: string; label: string; count: number; keywords: string[] }[];
  out_of_scope_count: number;
  daily: { date: string; conversations: number; questions: number }[];
  recent: {
    conversation: string;
    topic: string | null;
    topic_label: string;
    questions: number;
    status: ResolutionStatus;
    started_at: string;
    resolution_seconds: number | null;
  }[];
}

export class AdminApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function fetchAnalytics(days: RangeDays, signal?: AbortSignal): Promise<AnalyticsReport> {
  const res = await fetch(`${publicConfig.apiBaseUrl}/api/v1/admin/analytics?days=${days}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!res.ok) {
    throw new AdminApiError(
      res.status === 401 ? "Your session has expired. Please sign in again." : "Analytics could not be loaded.",
      res.status,
    );
  }
  return (await res.json()) as AnalyticsReport;
}
