"""Provider usage and clearly labelled cost estimates. No passenger data is accepted."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.config import Settings
from app.db.models import AIUsage
from app.db.session import Database, utcnow


def estimate_tokens(text: str) -> int:
    """Conservative UTF-8 byte budget, not an exact multilingual provider tokenizer."""
    return (len(text.encode("utf-8")) + 2) // 3


def usage_values(provider: str, usage: dict, settings: Settings, fallback_input: int = 0) -> dict:
    def integer(value):
        return max(0, int(value or 0))

    if provider == "anthropic":
        estimated = "input_tokens" not in usage or "output_tokens" not in usage
        fresh = integer(usage.get("input_tokens", fallback_input))
        output = integer(usage.get("output_tokens"))
        read = integer(usage.get("cache_read_input_tokens"))
        write = integer(usage.get("cache_creation_input_tokens"))
        total = fresh + read + write
        cost = (
            fresh * settings.anthropic_input_usd_million
            + output * settings.anthropic_output_usd_million
            + read * settings.anthropic_cache_read_usd_million
            + write * settings.anthropic_cache_write_usd_million
        ) / 1e6
    else:
        estimated = "prompt_tokens" not in usage or "completion_tokens" not in usage
        total = integer(usage.get("prompt_tokens", fallback_input))
        output = integer(usage.get("completion_tokens"))
        read = min(total, integer((usage.get("prompt_tokens_details") or {}).get("cached_tokens")))
        write = 0
        cost = (
            (
                (total - read) * settings.sarvam_input_inr_million
                + read * settings.sarvam_cached_inr_million
                + output * settings.sarvam_output_inr_million
            )
            / settings.usd_inr_estimate
            / 1e6
        )
    return dict(
        input_tokens=total,
        output_tokens=output,
        cache_read_tokens=read,
        cache_write_tokens=write,
        tokens_estimated=estimated,
        estimated_usd=cost,
    )


class UsageService:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def record(self, provider: str, model: str, usage: dict, *, status: str, latency_ms: int, fallback_input: int = 0):
        values = usage_values(provider, usage, self.settings, fallback_input)
        if status == "cache":
            values = dict(
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                tokens_estimated=False,
                estimated_usd=0,
            )
        with self.db.session() as s:
            s.add(
                AIUsage(
                    occurred_at=utcnow(), provider=provider, model=model, status=status, latency_ms=latency_ms, **values
                )
            )

    def report(self, days: int) -> dict:
        # ponytail: bounded reporting window, SQL aggregates if volume outgrows this small POC.
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
        with self.db.session() as s:
            rows = list(s.scalars(select(AIUsage).where(AIUsage.occurred_at >= start)))
        providers = []
        for provider, model in [("sarvam", "sarvam-105b"), ("anthropic", "claude-haiku-5-5")]:
            group = [r for r in rows if r.provider == provider]
            upstream = [r for r in group if r.status != "cache"]
            tokens = sum(r.input_tokens + r.output_tokens for r in upstream)
            cost = sum(r.estimated_usd for r in group)
            providers.append(
                dict(
                    provider=provider,
                    model=model,
                    requests=len(upstream),
                    cache_hits=sum(r.status == "cache" for r in group),
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
            daily=daily,
            total_estimated_usd=total,
            average_usd=total / requests if requests else 0,
            costs_are_estimates=True,
            usd_inr_estimate=self.settings.usd_inr_estimate,
            note="Estimated API cost, not an invoice. Provider-reported tokens where available; failed calls may have unreported usage. Sarvam INR uses the configured USD/INR estimate.",
        )
