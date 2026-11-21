"""Provider usage and clearly labelled cost estimates. No passenger data is accepted."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from math import ceil

from sqlalchemy import select

from app.clients.novita import NovitaChatClient
from app.config import Settings
from app.db.models import AIUsage, FAQUsage
from app.db.session import Database, utcnow


def estimate_tokens(text: str) -> int:
    """Conservative UTF-8 byte budget, not an exact multilingual provider tokenizer."""
    return (len(text.encode("utf-8")) + 2) // 3


def usage_values(provider: str, usage: dict, settings: Settings, fallback_input: int = 0) -> dict:
    def integer(value):
        return max(0, int(value or 0))

    reasoning, write_1h = None, None
    if provider == "anthropic":
        details = usage.get("output_tokens_details") or {}
        if "thinking_tokens" in details:
            reasoning = integer(details["thinking_tokens"])
        estimated = "input_tokens" not in usage or "output_tokens" not in usage
        fresh = integer(usage.get("input_tokens", fallback_input))
        output = integer(usage.get("output_tokens"))
        read = integer(usage.get("cache_read_input_tokens"))
        write = integer(usage.get("cache_creation_input_tokens"))
        breakdown = usage.get("cache_creation") or {}
        if "ephemeral_1h_input_tokens" in breakdown:
            write_1h = min(write, integer(breakdown["ephemeral_1h_input_tokens"]))
        total = fresh + read + write
        cost = (
            fresh * settings.anthropic_input_usd_million
            + output * settings.anthropic_output_usd_million
            + read * settings.anthropic_cache_read_usd_million
            + (write - (write_1h or 0)) * settings.anthropic_cache_write_usd_million
            + (write_1h or 0) * settings.anthropic_cache_write_1h_usd_million
        ) / 1e6
        native = cost
    else:
        estimated = "prompt_tokens" not in usage or "completion_tokens" not in usage
        total = integer(usage.get("prompt_tokens", fallback_input))
        output = integer(usage.get("completion_tokens"))
        read = min(total, integer((usage.get("prompt_tokens_details") or {}).get("cached_tokens")))
        write = 0
        details = usage.get("completion_tokens_details") or {}
        if "reasoning_tokens" in details:
            reasoning = integer(details["reasoning_tokens"])
        if provider == "novita":
            prompt_details = usage.get("prompt_tokens_details") or {}
            if not read:
                read = min(total, integer(prompt_details.get("cache_read_Prompt_tokens")))
            write = min(total - read, integer(prompt_details.get("cache_creation_Prompt_tokens")))
            native = cost = (
                (total - read - write) * settings.novita_input_usd_million
                + read * settings.novita_cached_usd_million
                + write * settings.novita_cache_write_usd_million
                + output * settings.novita_output_usd_million
            ) / 1e6
        else:
            native = ((total - read) * settings.sarvam_input_inr_million
                      + read * settings.sarvam_cached_inr_million
                      + output * settings.sarvam_output_inr_million) / 1e6
            cost = native / settings.usd_inr_estimate
    return dict(
        input_tokens=total,
        output_tokens=output,
        cache_read_tokens=read,
        cache_write_tokens=write,
        tokens_estimated=estimated,
        estimated_usd=cost,
        priced_amount=None if estimated else native,
        pricing_version=settings.novita_pricing_version if provider == "novita" else settings.api_pricing_version,
        reasoning_tokens=reasoning,
        cache_write_1h_tokens=write_1h,
    )


class UsageService:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def record(self, provider: str, model: str, usage: dict, *, status: str, latency_ms: int,
               fallback_input: int = 0, locale=None, error_kind=None, retrieval_tokens_estimated=None,
               optimized_context=None):
        values = usage_values(provider, usage, self.settings, fallback_input)
        with self.db.session() as s:
            s.add(AIUsage(
                occurred_at=utcnow(), provider=provider, model=model, status=status, latency_ms=latency_ms,
                locale=locale, error_kind=error_kind, optimized_context=optimized_context,
                retrieval_tokens_estimated=retrieval_tokens_estimated, **values,
            ))

    def record_faq(self, provider, locale, outcome, latency_ms):
        with self.db.session() as s:
            s.add(FAQUsage(occurred_at=utcnow(), provider=provider, locale=locale,
                           outcome=outcome, latency_ms=latency_ms))

    def report(self, days: int) -> dict:
        # ponytail: bounded reporting window, SQL aggregates if volume outgrows this small POC.
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
        with self.db.session() as s:
            rows = list(s.scalars(select(AIUsage).where(AIUsage.occurred_at >= start)))
            faqs = list(s.scalars(select(FAQUsage).where(FAQUsage.occurred_at >= start)))
        providers = []
        for provider, model in [("sarvam", "sarvam-105b"), ("anthropic", "claude-haiku-5-5"),
                                ("novita", NovitaChatClient.model)]:
            group = [r for r in rows if r.provider == provider]
            upstream = [r for r in group if r.status != "cache"]
            tokens = sum(r.input_tokens + r.output_tokens for r in upstream)
            cost = sum(r.estimated_usd for r in group)
            providers.append(
                dict(
                    provider=provider,
                    model=model,
                    requests=len(upstream),
                    cache_hits=sum(r.status == "cache" for r in group)
                    + sum(r.provider == provider and r.outcome == "hit" for r in faqs),
                    errors=sum(r.status == "error" for r in group),
                    input_tokens=sum(r.input_tokens for r in group),
                    output_tokens=sum(r.output_tokens for r in group),
                    cache_read_tokens=sum(r.cache_read_tokens for r in group),
                    cache_write_tokens=sum(r.cache_write_tokens for r in group),
                    estimated_usd=cost,
                    average_tokens=tokens / len(upstream) if upstream else 0,
                    average_usd=cost / len(upstream) if upstream else 0,
                    estimated_token_requests=sum(r.tokens_estimated for r in group),
                )
            )
        dimensions = []
        for provider, model, locale, optimized in sorted(
            {(r.provider, r.model, r.locale or "unknown", bool(r.optimized_context))
             for r in rows if r.status != "cache"}
        ):
            group = [r for r in rows if (r.provider, r.model, r.locale or "unknown", bool(r.optimized_context))
                     == (provider, model, locale, optimized) and r.status != "cache"]
            priced = [r for r in group if r.priced_amount is not None]
            latencies = sorted(r.latency_ms for r in group)
            dimensions.append(dict(
                provider=provider, model=model, locale=locale, optimized_context=optimized, requests=len(group),
                errors=sum(r.status == "error" for r in group),
                timeouts=sum(r.error_kind == "timeout" for r in group),
                p50_ms=latencies[ceil(.5 * len(latencies)) - 1],
                p95_ms=latencies[ceil(.95 * len(latencies)) - 1],
                reported_input_tokens=sum(r.input_tokens for r in group if not r.tokens_estimated),
                reported_output_tokens=sum(r.output_tokens for r in group if not r.tokens_estimated),
                estimated_input_tokens=sum(r.input_tokens for r in group if r.tokens_estimated),
                reasoning_tokens=sum(r.reasoning_tokens or 0 for r in group),
                reasoning_reported_requests=sum(r.reasoning_tokens is not None for r in group),
                retrieval_tokens_estimated=sum(r.retrieval_tokens_estimated or 0 for r in group),
                cache_read_tokens=sum(r.cache_read_tokens for r in group),
                cache_write_tokens=sum(r.cache_write_tokens for r in group),
                cache_write_1h_tokens=sum(r.cache_write_1h_tokens or 0 for r in group),
                currency="INR" if provider == "sarvam" else "USD",
                reported_usage_cost={version: sum(r.priced_amount for r in priced if r.pricing_version == version)
                                     for version in sorted({r.pricing_version for r in priced})},
                priced_requests=len(priced),
            ))
        faq_metrics = []
        for provider, locale in sorted({(r.provider, r.locale) for r in faqs}):
            group = [r for r in faqs if r.provider == provider and r.locale == locale]
            outcomes = Counter(r.outcome for r in group)
            hit_latencies = sorted(r.latency_ms for r in group if r.outcome == "hit")
            # Group averages are counterfactual proxies, not a matched or invoiced saving.
            comparable = [r for r in rows if r.provider == provider and r.locale == locale
                          and r.status == "ok" and r.priced_amount is not None]
            faq_metrics.append(dict(
                provider=provider, locale=locale, outcomes=dict(outcomes), calls_avoided=outcomes["hit"],
                hit_p95_ms=hit_latencies[ceil(.95 * len(hit_latencies)) - 1] if hit_latencies else None,
                estimated_cost_avoided=(outcomes["hit"] * sum(r.priced_amount for r in comparable) / len(comparable)
                                        if comparable else None),
                currency="INR" if provider == "sarvam" else "USD",
            ))
        daily = []
        for i in range(days):
            day = (start + timedelta(days=i)).date().isoformat()
            group = [r for r in rows if r.occurred_at.date().isoformat() == day]
            daily.append(
                dict(
                    date=day,
                    input_tokens=sum(r.input_tokens for r in group),
                    output_tokens=sum(r.output_tokens for r in group),
                    estimated_usd=sum(r.estimated_usd for r in group),
                )
            )
        requests = sum(p["requests"] for p in providers)
        total = sum(p["estimated_usd"] for p in providers)
        return dict(
            providers=providers,
            provider_language=dimensions,
            faq=faq_metrics,
            daily=daily,
            total_estimated_usd=total,
            average_usd=total / requests if requests else 0,
            costs_are_estimates=True,
            usd_inr_estimate=self.settings.usd_inr_estimate,
            note="Estimated API cost, not an invoice. Provider-reported tokens where available; failed calls may have unreported usage. Sarvam INR uses the configured USD/INR estimate.",
        )
