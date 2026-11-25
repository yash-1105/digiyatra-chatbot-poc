"""Task 2 processing inside the single scheduled job: social posts, YouTube, transcripts, accounts.

All functions run in Pipeline A (``SyncJob``) and persist through ``SyncJob._persist`` so records
get the same versioning, review, withdrawal, publication and index rules as Task 1 content.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import select

from app.db.models import OfficialRecord, OfficialSource
from app.db.session import utcnow
from app.security.guardrails import assess_input
from app.sync import policy as P
from app.sync import social as S
from app.sync.extract import language_of
from app.sync.fetcher import FetchError

ACTIVE = ("verified", "pending_review", "conflict", "historical")
SOCIAL_FLAG = "social post: confirm consequential claims against formal official documentation"
PLATFORM_LABEL = {"youtube": "YouTube", "x": "X (Twitter)", "linkedin": "LinkedIn", "instagram": "Instagram",
                  "facebook": "Facebook"}


def _post_candidate(source_id: str, post: S.Post, acc: S.Account, since: str) -> P.Candidate | None:
    if post.published_on and post.published_on < since:
        return None
    text, _ = P.strip_statistics(post.text)
    if S.excluded_reason(text) or assess_input(text).injection:
        return None
    topic, risk, claim = S.classify(text)
    flags = [SOCIAL_FLAG] if risk == "high" else []
    if claim in {"pilot", "future", "proposed"}:
        flags.append(f"claim type: {claim} (not confirmed operational functionality)")
    starts, ends = P.trial_window(text)
    label = PLATFORM_LABEL.get(post.platform, post.platform)
    cand = P.Candidate(
        P.key_for(source_id, "social", f"{post.platform}:{post.post_id}"), "social_post",
        f"{acc.name} on {label}" + (f" ({post.published_on})" if post.published_on else ""), claim, None, text, None,
        post.language if post.language in ("en", "hi") else language_of(text), post.published_on,
        (post.media or {}).get("modified"), starts, ends, flags, url=post.permalink,
        extra={"source_kind": "social_post", "platform": post.platform, "external_id": post.post_id,
               "account_id": acc.account_id, "account_name": acc.name, "topic": topic, "risk": risk,
               "organization": acc.owner, "authority": "official_social", "claim_type": claim,
               "referenced_urls": post.referenced_urls, "historical_after_days": 365},
    )
    return cand


def persist_embedded_posts(job, row: OfficialSource, spec, html: str) -> int:
    """Official posts embedded on an official government page already being crawled."""
    cands = []
    for post in S.embedded_posts(html)[: job.s.sync_max_social_posts]:
        acc = S.account(post.platform, post.handle)
        if not S.ingestible(acc):
            job.stats.failures["social_account_not_verified"] = job.stats.failures.get("social_account_not_verified", 0) + 1
            continue
        if c := _post_candidate(row.source_id, post, acc, job.s.sync_social_since):
            c.extra["embedded_on"] = row.canonical_url
            cands.append(c)
    job.stats.social_posts_seen += len(cands)
    if cands:
        job._persist(row, spec, cands, row.content_hash or "", None, None)
    return len(cands)


def process(job, fetcher, row: OfficialSource, spec) -> None:
    if spec.source_type == "account_registry":
        _accounts(job, row, spec)
    elif spec.source_type == "youtube_channel":
        _youtube(job, fetcher, row, spec)
    else:  # transcripts / social imports change only through authorised operator imports
        job._unchanged(row, row.http_status or 200, row.etag, row.last_modified)


# --------------------------------------------------------------------------- accounts
def _accounts(job, row: OfficialSource, spec) -> None:
    cands = []
    for acc in S.ACCOUNTS.values():
        if not S.ingestible(acc):
            continue
        label = PLATFORM_LABEL[acc.platform]
        kind = "official government account" if acc.status == "verified_government" else "official channel"
        body = (f"{acc.name} ({acc.handle}) is the {kind} of {acc.owner} on {label}: {acc.profile_url}. "
                f"Follow it for official Digi Yatra announcements and updates. Collection: {acc.automated}.")
        cands.append(P.Candidate(
            P.key_for(row.source_id, "account", f"{acc.platform}:{acc.account_id}"), "account_profile",
            f"Official {label} — {acc.name}", "Official channels", None, body, None, "en", None, None, None, None,
            url=acc.profile_url,
            extra={"source_kind": "account_profile", "platform": acc.platform, "external_id": acc.account_id,
                   "account_id": acc.account_id, "account_name": acc.name, "evidence": list(acc.evidence),
                   "verification": acc.status, "organization": acc.owner}))
    digest = hashlib.sha256(json.dumps([c.content_hash for c in cands]).encode()).hexdigest()
    if digest == row.content_hash:
        job._unchanged(row, 200, None, None)
        return
    job._persist(row, spec, cands, digest, None, None)


# --------------------------------------------------------------------------- YouTube
def _known_video_ids(job, row: OfficialSource) -> dict[str, str]:
    """Video IDs with provenance: approved corpus links and previously verified/imported videos."""
    from ingestion.corpus import load_corpus

    ids: dict[str, str] = {}
    try:
        chunks, _ = load_corpus(job.s.knowledge_corpus_dir)
        for c in chunks:
            for vid in S.video_ids(c["text"] + " " + " ".join(c.get("urls") or [])):
                ids.setdefault(vid, f"approved corpus `{c['source_file']}`")
    except (FileNotFoundError, ValueError):
        pass
    with job.db.session() as s:
        for rec in s.scalars(select(OfficialRecord).where(OfficialRecord.source_id == row.source_id,
                                                          OfficialRecord.record_type == "video",
                                                          OfficialRecord.status.in_(ACTIVE))):
            ids.setdefault(rec.external_id, (rec.media or {}).get("discovered_via", "previous synchronisation"))
    return ids


def _existing_videos(job, row) -> dict[str, OfficialRecord]:
    with job.db.session() as s:
        return {r.external_id: r for r in s.scalars(select(OfficialRecord).where(
            OfficialRecord.source_id == row.source_id, OfficialRecord.record_type == "video",
            OfficialRecord.status.in_(ACTIVE)))}


def _video_candidate(row, vid: str, title: str, *, description: str = "", published: str | None = None,
                     media: dict | None = None) -> P.Candidate:
    body = f'Official Digi Yatra Foundation YouTube video: "{title}".'
    if description:
        body += "\n" + description
    topic = S.classify(title + " " + description)[0]
    extra = {"source_kind": "video", "platform": "youtube", "external_id": vid, "account_id": S.YOUTUBE_CHANNEL_ID,
             "account_name": "Digi Yatra Foundation", "topic": topic, "risk": "low", "authority": "official_social",
             "organization": "Digi Yatra Foundation", **(media or {})}
    return P.Candidate(P.key_for(row.source_id, "video", vid), "video", title[:300], "YouTube video", None, body, None,
                       language_of(title + " " + description), published, None, None, None, url=S.watch_url(vid),
                       extra=extra)


def verify_videos(job, fetcher, row, ids: dict[str, str]) -> tuple[list[P.Candidate], set[str]]:
    """oEmbed ownership/availability check of known IDs (no API key needed). Returns candidates and
    keys to keep unchanged after transient errors."""
    cands, keep = [], set()
    existing = _existing_videos(job, row)
    for vid, via in list(ids.items())[: job.s.sync_youtube_max_videos]:
        url = "https://www.youtube.com/oembed?" + urlencode({"format": "json", "url": S.watch_url(vid)})
        try:
            data = json.loads(fetcher.get(url, "json").body)
        except FetchError as exc:
            if exc.status != 404 and vid in existing:
                keep.add(existing[vid].record_key)  # transient/limited: keep last verified metadata
            job.stats.failures[f"youtube_oembed_{exc.reason}"] = job.stats.failures.get(f"youtube_oembed_{exc.reason}", 0) + 1
            continue
        except ValueError:
            continue
        author = str(data.get("author_url", "")).rstrip("/").lower()
        if author not in {S.YOUTUBE_HANDLE_URL.lower(), f"https://www.youtube.com/channel/{S.YOUTUBE_CHANNEL_ID}".lower()}:
            job.stats.failures["youtube_not_official_channel"] = job.stats.failures.get("youtube_not_official_channel", 0) + 1
            continue
        title = " ".join(str(data.get("title", "")).split())[:300]
        if not title:
            continue
        prior = existing.get(vid)
        cands.append(_video_candidate(row, vid, title, published=prior.published_on if prior else None, media={
            "discovered_via": via, "transcript_status": "metadata_only",
            "transcript_reason": "caption download needs channel-owner authorisation; no authorised transcript supplied",
            **({k: v for k, v in (prior.media or {}).items() if k in ("duration_s", "playlists", "languages")} if prior else {}),
        }))
    return cands, keep


def _api(fetcher, path: str, params: dict, key: str, quota: list[int], cost: int):
    """YouTube Data API v3 call. The key is sent as a query parameter (documented) and is never logged,
    stored or returned; only reason codes leave this function on failure."""
    url = f"https://www.googleapis.com/youtube/v3/{path}?" + urlencode({**params, "key": key})
    quota[0] += cost
    return json.loads(fetcher.get(url, "json", respect_robots=False).body)


def _youtube(job, fetcher, row: OfficialSource, spec) -> None:
    key = job.s.youtube_api_key.get_secret_value() if job.s.youtube_api_key else None
    if not key:
        ids = _known_video_ids(job, row)
        cands, keep = verify_videos(job, fetcher, row, ids)
        _store_videos(job, row, spec, cands, keep, quota_note="YOUTUBE_API_KEY not configured: known official video IDs "
                      "verified via oEmbed only (no upload/playlist discovery, no descriptions or durations)")
        return
    quota = [0]
    try:
        ch = _api(fetcher, "channels", {"part": "contentDetails,snippet", "id": S.YOUTUBE_CHANNEL_ID}, key, quota, 1)
        uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        since = max(job.s.sync_social_since, row.cursor or "")[:10] if row.cursor else job.s.sync_social_since
        found: dict[str, dict] = {}
        token = None
        for _ in range(job.s.sync_youtube_max_pages):
            page = _api(fetcher, "playlistItems", {"part": "contentDetails", "playlistId": uploads, "maxResults": 50,
                                                   **({"pageToken": token} if token else {})}, key, quota, 1)
            for it in page.get("items", []):
                vid, pub = it["contentDetails"]["videoId"], it["contentDetails"].get("videoPublishedAt", "")[:10]
                if pub and pub < job.s.sync_social_since:
                    continue
                found.setdefault(vid, {"discovered_via": "channel uploads (YouTube Data API)"})
            token = page.get("nextPageToken")
            oldest = min((i["contentDetails"].get("videoPublishedAt", "9")[:10] for i in page.get("items", [])), default="9")
            if not token or (row.cursor and oldest < since) or len(found) >= job.s.sync_youtube_max_videos:
                break
        playlists = _api(fetcher, "playlists", {"part": "snippet", "channelId": S.YOUTUBE_CHANNEL_ID, "maxResults": 50},
                         key, quota, 1).get("items", [])[:10]
        for pl in playlists:
            items = _api(fetcher, "playlistItems", {"part": "contentDetails", "playlistId": pl["id"], "maxResults": 50},
                         key, quota, 1).get("items", [])
            for it in items:
                found.setdefault(it["contentDetails"]["videoId"], {"discovered_via": "official playlist (YouTube Data API)"}) \
                    .setdefault("playlists", []).append(pl["snippet"]["title"][:120])
        existing = _existing_videos(job, row)
        ids = list(dict.fromkeys([*found, *existing]))[: job.s.sync_youtube_max_videos]
        cands, newest, caption_checks = [], row.cursor or "", 0
        for i in range(0, len(ids), 50):
            batch = _api(fetcher, "videos", {"part": "snippet,contentDetails,status", "id": ",".join(ids[i:i + 50])},
                         key, quota, 1).get("items", [])
            for v in batch:
                vid, sn, cd = v["id"], v["snippet"], v["contentDetails"]
                if sn.get("channelId") != S.YOUTUBE_CHANNEL_ID or v.get("status", {}).get("privacyStatus") != "public":
                    continue
                pub = sn.get("publishedAt", "")[:10] or None
                newest = max(newest, pub or "")
                media = {**found.get(vid, {"discovered_via": "previous synchronisation"}),
                         "duration_s": S.iso_duration(cd.get("duration")),
                         "languages": sorted({x for x in (sn.get("defaultLanguage"), sn.get("defaultAudioLanguage")) if x}),
                         "captions_flag": cd.get("caption") == "true", "transcript_status": "metadata_only",
                         "transcript_reason": "caption download needs channel-owner authorisation"}
                prior = existing.get(vid)
                if cd.get("caption") == "true" and caption_checks < job.s.sync_youtube_caption_checks and (
                        prior is None or (prior.media or {}).get("captions_flag") is not True):
                    caption_checks += 1
                    tracks = _api(fetcher, "captions", {"part": "snippet", "videoId": vid}, key, quota, 50).get("items", [])
                    media["caption_tracks"] = sorted({f"{t['snippet'].get('language')}:{'auto' if t['snippet'].get('trackKind') == 'asr' else 'human'}"
                                                      for t in tracks})
                    media["transcript_status"] = "available_owner_authorisation_required" if tracks else "metadata_only"
                elif prior and (prior.media or {}).get("caption_tracks"):
                    media["caption_tracks"] = prior.media["caption_tracks"]
                    media["transcript_status"] = prior.media.get("transcript_status", "metadata_only")
                cands.append(_video_candidate(row, vid, sn.get("title", "")[:300],
                                              description=S.relevant_description(sn.get("description", "")),
                                              published=pub, media=media))
        _store_videos(job, row, spec, cands, set(), cursor=newest or row.cursor,
                      quota_note=f"YouTube Data API units used last run: {quota[0]} (free daily quota "
                                 f"{job.s.sync_youtube_daily_quota})")
    except (KeyError, IndexError, ValueError) as exc:
        raise FetchError(f"youtube_api_unexpected_response:{type(exc).__name__}", 200) from exc


def _store_videos(job, row, spec, cands, keep, quota_note: str, cursor: str | None = None) -> None:
    job.stats.videos_seen += len(cands)
    digest = hashlib.sha256(json.dumps(sorted(c.content_hash for c in cands)).encode()).hexdigest()
    if not cands and not keep:
        raise FetchError("no_official_videos_verified", 200)
    if digest == row.content_hash and not keep:
        job._unchanged(row, 200, None, None)
    else:
        job._persist(row, spec, cands, digest, None, None, keep_keys=keep)
    with job.db.session() as s:
        r = s.get(OfficialSource, row.source_id)
        r.platform, r.account_id, r.quota_note = "youtube", S.YOUTUBE_CHANNEL_ID, quota_note[:160]
        r.cursor = cursor or r.cursor
        r.ownership_evidence = {"status": "verified", "evidence": list(S.ACCOUNTS["youtube:digiyatrafoundation"].evidence)}


def import_videos(job, fetcher, urls: list[str]) -> dict:
    """Operator-supplied official video URLs (e.g. a YouTube Studio export); verified via oEmbed."""
    from app.sync.job import spec_for

    row = job._row("yt-channel-digiyatrafoundation")
    ids = {vid: "operator video list" for u in urls for vid in S.video_ids(u)}
    if not ids:
        raise ValueError("No YouTube video URLs found")
    known = _known_video_ids(job, row)
    cands, keep = verify_videos(job, fetcher, row, {**known, **ids})
    verified = sum(1 for c in cands if c.extra["external_id"] in ids)
    try:
        _store_videos(job, row, spec_for(row), cands, keep, quota_note="operator video list verified via oEmbed")
    except FetchError as exc:  # nothing verified: report, never delete existing records
        return {"requested": len(ids), "verified_official": 0, "reason": exc.reason}
    return {"requested": len(ids), "verified_official": verified}


# --------------------------------------------------------------------------- transcripts
def import_transcript(job, video_id: str, data: bytes, kind: str, language: str | None = None) -> dict:
    """Organisation-supplied caption file (.vtt/.srt) for a verified official video.
    Reprocessed only when the file changes; every passage requires review."""
    from app.sync.job import spec_for

    if kind not in {"human", "auto"}:
        raise ValueError("kind must be human or auto")
    with job.db.session() as s:
        video = s.scalar(select(OfficialRecord).where(OfficialRecord.platform == "youtube",
                                                      OfficialRecord.external_id == video_id,
                                                      OfficialRecord.record_type == "video",
                                                      OfficialRecord.status.in_(ACTIVE)))
    if video is None:
        raise ValueError("Unknown video: import/verify the official video first")
    segments = S.group_segments(S.parse_captions(data))
    if not segments:
        raise ValueError("No caption cues found (expected WebVTT or SRT)")
    lang = language or language_of(" ".join(g.text for g in segments))
    sid = f"yt-transcript:{video_id}:{lang}:{kind}"
    digest = hashlib.sha256(data).hexdigest()
    now = utcnow()
    with job.db.session() as s:
        if s.get(OfficialSource, sid) is None:
            s.add(OfficialSource(
                source_id=sid, parent_id="yt-channel-digiyatrafoundation", canonical_url=f"{S.watch_url(video_id)}#captions-{lang}-{kind}",
                organization="Digi Yatra Foundation", source_type="transcript", language=lang, trust="official_social",
                topic="video_resources", risk="high", enabled=True, refresh_days=job.s.sync_fortnightly_days,
                next_due_at=now + timedelta(days=job.s.sync_fortnightly_days), content_version=0,
                verification_status="operator_capture", consecutive_failures=0, created_at=now, platform="youtube",
                account_id=S.YOUTUBE_CHANNEL_ID))
    row = job._row(sid)
    if row.content_hash == digest:
        return {"source_id": sid, "unchanged": True, "passages": 0}
    flags = [f"operator-supplied {kind} captions"]
    if kind == "auto":
        flags.append("automatic captions: verify airport names, technical terms and numbers against written documentation")
    if video.published_on and video.published_on < (now.date() - timedelta(days=730)).isoformat():
        flags.append("video older than two years: app demonstration may be outdated")
    cands = []
    for g in segments:
        text, _ = P.strip_statistics(g.text)
        if len(text) < 25 or assess_input(text).injection:
            continue
        topic, risk, claim = S.classify(text)
        cands.append(P.Candidate(
            P.key_for(sid, "transcript", str(g.start)), "transcript", video.title, f"{g.start // 60}:{g.start % 60:02d}",
            None, text, f"t={g.start}", lang, video.published_on, None, None, None, list(flags),
            url=S.watch_url(video_id, g.start),
            extra={"source_kind": "transcript", "platform": "youtube", "external_id": video_id,
                   "account_id": S.YOUTUBE_CHANNEL_ID, "account_name": "Digi Yatra Foundation", "start_s": g.start,
                   "end_s": g.end, "transcript_type": kind, "topic": topic, "risk": "high" if kind == "auto" else risk,
                   "claim_type": claim, "organization": "Digi Yatra Foundation", "authority": "official_social"}))
    job._persist(row, spec_for(row), cands, digest, None, None, operator_capture=True, replace_missing=True)
    with job.db.session() as s:  # mark the video as having an authorised transcript
        v = s.get(OfficialRecord, video.id)
        v.media = {**(v.media or {}), "transcript_status": f"authorised_{kind}_transcript_imported",
                   "transcript_languages": sorted({*(v.media or {}).get("transcript_languages", []), lang})}
    return {"source_id": sid, "unchanged": False, "passages": len(cands)}


# --------------------------------------------------------------------------- social exports
def import_social(job, platform: str, data: bytes, handle: str | None = None) -> dict:
    """Organisation-provided export for platforms that block automated access (X, LinkedIn, …)."""
    from app.sync.job import spec_for

    posts = S.parse_social_export(platform, data, handle)
    raw = json.loads(data) if data.lstrip().startswith(b"[") else []
    withdrawn_ids = {S.SOCIAL_URL[platform].match(str(r.get("url", ""))).groups()[-1]
                     for r in raw if isinstance(r, dict) and r.get("withdrawn") and S.SOCIAL_URL[platform].match(str(r.get("url", "")))}
    acc = S.account(platform, posts[0].handle) if posts else None
    if acc is None:
        raise ValueError("Export contains no posts")
    sid = f"social-import:{platform}:{acc.account_id.lower()}"
    now = utcnow()
    with job.db.session() as s:
        if s.get(OfficialSource, sid) is None:
            s.add(OfficialSource(
                source_id=sid, parent_id="official-accounts", canonical_url=acc.profile_url, organization=acc.owner,
                source_type="social_import", language="en", trust="official_social", topic="announcements", risk="high",
                enabled=True, refresh_days=job.s.sync_weekly_days, next_due_at=now + timedelta(days=job.s.sync_weekly_days),
                content_version=0, verification_status="operator_capture", consecutive_failures=0, created_at=now,
                platform=platform, account_id=acc.account_id, ownership_evidence={"status": acc.status, "evidence": list(acc.evidence)}))
    row = job._row(sid)
    cands = [c for p in posts if p.post_id not in withdrawn_ids and (c := _post_candidate(sid, p, acc, job.s.sync_social_since))]
    for c in cands:
        c.flags.append("organisation-provided export")
    job._persist(row, spec_for(row), cands, hashlib.sha256(data).hexdigest(), None, None, operator_capture=True)
    withdrawn = 0
    if withdrawn_ids:
        from sqlalchemy import update

        with job.db.session() as s:
            withdrawn = s.execute(update(OfficialRecord).where(
                OfficialRecord.platform == platform, OfficialRecord.external_id.in_(withdrawn_ids),
                OfficialRecord.status.in_(ACTIVE)).values(status="withdrawn",
                                                          review_reason="withdrawn by the official account")).rowcount or 0
    newest = max((p.published_on or "" for p in posts), default="")
    with job.db.session() as s:
        r = s.get(OfficialSource, sid)
        r.cursor = max(r.cursor or "", newest) or None
    return {"source_id": sid, "posts": len(posts), "ingestible": len(cands), "withdrawn": withdrawn,
            "excluded": len(posts) - len(cands) - len(withdrawn_ids)}

