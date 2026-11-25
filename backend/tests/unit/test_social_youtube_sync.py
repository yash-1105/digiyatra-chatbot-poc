"""Task 2: official social posts, YouTube metadata, authorised transcripts and chat isolation.
Synthetic fixtures only; no network; isolated databases."""

from __future__ import annotations

import json
import re
import socket
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from app.db.models import OfficialRecord, OfficialSource
from app.db.session import Database, utcnow
from app.rag.embeddings import LexicalEmbedder
from app.rag.retriever import Retriever
from app.rag.store import KnowledgeIndex
from app.sync import job as J
from app.sync import media as M
from app.sync import social as S
from app.sync.fetcher import SecureFetcher
from app.sync.publish import active_publication, record_chunk
from tests.conftest import FakeSarvam, make_settings
from tests.unit.test_official_sync import Site, records, run, validator_ok

NODE = "https://www.civilaviation.gov.in/node/7641"
NODE2 = "https://www.civilaviation.gov.in/node/6053"
KEY = "synthetic-youtube-key-123"


def tweet(handle, pid, text, date="July 3, 2026", lang="en"):
    return (f'<blockquote class="twitter-tweet"><p lang="{lang}" dir="ltr">{text}</p>&mdash; Name (@{handle}) '
            f'<a href="https://twitter.com/{handle}/status/{pid}?ref_src=twsrc">{date}</a></blockquote>')


def node_page(*tweets):
    return f'<html><body><main><h1>Digi Yatra</h1>{"".join(tweets)}</main></body></html>'


AIRPORT_POST = tweet("DigiYatraOffice", "111111", "Digi Yatra is now live at 3 new airports: Pune, Goa and Indore. #DigiYatra")
TRIAL_POST = tweet("DigiYatraOffice", "222222", "Digi Yatra international passenger trials run from November to December 2026 "
                   "for eligible e-passport holders.")
GREETING = tweet("DigiYatraOffice", "333333", "Happy Diwali from Team Digi Yatra! Wishing everyone safe and joyful travels.")
PERSONAL = tweet("RamMNK", "444444", "Visited the airport today and reviewed Digi Yatra operations with the team.")
IMPOSTOR = tweet("DigiYatraOfficial_", "555555", "Digi Yatra registration is now mandatory for all passengers from tomorrow.")


def register_node(db, url, sid):
    with db.session() as s:
        s.add(OfficialSource(source_id=sid, parent_id="moca-search-en", canonical_url=url,
                             organization="Ministry of Civil Aviation", source_type="discovery_links", language="en",
                             trust="official_government", topic="announcements", risk="high", enabled=True,
                             refresh_days=14, next_due_at=utcnow(), content_version=0, verification_status="x",
                             consecutive_failures=0, created_at=utcnow()))


@pytest.fixture
def env(tmp_path):
    from app.db.migrate import upgrade

    settings = make_settings(tmp_path, sync_host_interval_s=0, knowledge_auto_publish_enabled=True,
                             index_dir=tmp_path / "data" / "lancedb", knowledge_corpus_dir=tmp_path / "no-corpus")
    upgrade(settings.database_url)
    db = Database(settings.database_url)
    J.sync_registry(db, settings)
    yield settings, db
    db.engine.dispose()


# --------------------------------------------------------------------------- accounts and posts
def test_official_accounts_registry_and_impersonation():
    assert S.ingestible(S.account("youtube", "@DigiYatraFoundation"))
    assert S.account("youtube", "@DigiYatraFoundation").account_id == "UCAW0wpe_OvaAe3M6EKRGMJw"
    assert S.ingestible(S.account("x", "DigiYatraOffice")) and S.ingestible(S.account("x", "moca_goi"))
    assert not S.ingestible(S.account("x", "RamMNK"))            # personal account
    assert not S.ingestible(S.account("instagram", "digiyatrafoundation"))  # unverified candidate
    assert S.account("x", "DigiYatraOfficial_") is None          # look-alike handle
    assert all(a.evidence for a in S.ACCOUNTS.values() if a.status.startswith("verified"))


def test_embedded_post_extraction_classification_and_exclusions():
    posts = {p.post_id: p for p in S.embedded_posts(node_page(AIRPORT_POST, GREETING, TRIAL_POST))}
    p = posts["111111"]
    assert (p.handle, p.published_on, p.permalink) == ("DigiYatraOffice", "2026-07-03", "https://x.com/DigiYatraOffice/status/111111")
    assert S.classify(p.text)[:2] == ("airport_coverage", "high") and S.classify(p.text)[2] == "announced"
    assert S.classify(posts["222222"].text)[2] == "pilot"
    assert S.excluded_reason(posts["333333"].text) == "greeting_or_promotional"
    assert S.excluded_reason("Join our quiz contest and win prizes! #DigiYatra quiz time") == "contest_or_quiz"
    assert S.excluded_reason("At the AI Summit 2026 Digi Yatra enabled entry at the venue for delegates.") == "event_or_historical"


def test_initial_social_discovery_review_dedupe_and_modification(env):
    settings, db = env
    register_node(db, NODE, "moca-search-en:n1")
    register_node(db, NODE2, "moca-search-en:n2")
    site = Site({NODE: [node_page(AIRPORT_POST, GREETING, PERSONAL, IMPOSTOR, TRIAL_POST),
                        node_page(AIRPORT_POST.replace("3 new airports", "4 new airports"), TRIAL_POST)],
                 NODE2: node_page(AIRPORT_POST)})  # the same post embedded on a second official page
    _, job = run(settings, db, site, ["moca-search-en:n1", "moca-search-en:n2"])
    posts = [r for r in records(db) if r.record_type == "social_post"]
    assert {r.external_id for r in posts} == {"111111", "222222"}  # greeting, personal and impostor excluded
    assert job.stats.duplicates == 1 and job.stats.failures["social_account_not_verified"] == 2
    airport = next(r for r in posts if r.external_id == "111111")
    assert airport.status == "pending_review" and S.__dict__["SOCIAL_URL"]  # consequential => review
    assert "formal official documentation" in airport.review_reason
    assert (airport.platform, airport.account_id, airport.url) == ("x", "DigiYatraOffice", "https://x.com/DigiYatraOffice/status/111111")
    assert airport.media["claim_type"] == "announced" and airport.media["embedded_on"] == NODE
    trial = next(r for r in posts if r.external_id == "222222")
    assert (trial.effective_from, trial.expires_on) == ("2026-11-01", "2026-12-31")
    assert "claim type: pilot" in trial.review_reason
    # Modified post (weekly run): a new pending version; the unchanged post is skipped.
    _, job = run(settings, db, site, ["moca-search-en:n1"])
    versions = [r for r in records(db, external_id="111111") if r.source_id == "moca-search-en:n1"]
    assert [r.version for r in versions] == [1, 2] and "4 new airports" in versions[-1].body
    assert job.stats.updated_records == 1


def test_social_export_import_withdrawal_and_unverified_platforms(env, tmp_path):
    settings, db = env
    rows = [{"url": "https://x.com/DigiYatraOffice/status/777777", "published": "2026-10-01",
             "text": "Digi Yatra app update: new boarding pass upload flow is now available on Android."},
            {"url": "https://x.com/DigiYatraOffice/status/888888", "published": "2026-10-02",
             "text": "Digi Yatra will launch at 2 more airports soon, the team announced."}]
    job = J.SyncJob(settings, db, index_validator=validator_ok)
    result = job.locked(lambda j: M.import_social(j, "x", json.dumps(rows).encode()))
    assert result["ingestible"] == 2
    assert {r.status for r in records(db, platform="x")} == {"pending_review"}
    rows[1]["withdrawn"] = True
    result = job.locked(lambda j: M.import_social(j, "x", json.dumps(rows).encode()))
    assert result["withdrawn"] == 1 and records(db, external_id="888888")[0].status == "withdrawn"
    li = [{"url": "https://www.linkedin.com/posts/digiyatrafoundation_digiyatra-activity-7340686362485903362-s8Qj",
           "published": "2026-06-01", "text": "Digi Yatra registration now supports DigiLocker for passengers."}]
    assert job.locked(lambda j: M.import_social(j, "linkedin", json.dumps(li).encode()))["ingestible"] == 1
    with pytest.raises(ValueError, match="not a verified"):
        S.parse_social_export("instagram", json.dumps([{"url": "https://www.instagram.com/p/ABCDEF1/", "text": "x y z"}]).encode(),
                              handle="digiyatrafoundation")
    with pytest.raises(ValueError, match="not a verified"):
        S.parse_social_export("x", json.dumps([{"url": "https://x.com/DigiYatraOfficial_/status/1234567", "text": "fake"}]).encode())
    with pytest.raises(ValueError, match="permalink"):
        S.parse_social_export("x", json.dumps([{"url": "https://x.com/DigiYatraOffice", "text": "profile"}]).encode())


# --------------------------------------------------------------------------- YouTube
def oembed(author="https://www.youtube.com/@DigiYatraFoundation", titles=None, missing=(), flaky=()):
    titles = titles or {}

    def handler(request):
        vid = parse_qs(urlsplit(parse_qs(urlsplit(str(request.url)).query)["url"][0]).query)["v"][0]
        if vid in missing:
            return httpx.Response(404, text="Not Found")
        if vid in flaky:
            return httpx.Response(500, text="err")
        return httpx.Response(200, json={"title": titles.get(vid, f"Video {vid}"), "author_url": author,
                                         "author_name": "Digi Yatra Foundation"})
    return handler


class Router:
    def __init__(self, **routes):
        self.routes, self.calls = routes, []

    def __call__(self, request):
        self.calls.append(str(request.url))
        if str(request.url).endswith("/robots.txt"):
            return httpx.Response(404)
        for prefix, fn in self.routes.items():
            if prefix in str(request.url):
                return fn(request)
        return httpx.Response(404)

    def fetcher(self, settings):
        return SecureFetcher(settings, transport=httpx.MockTransport(self), resolver=lambda h: None, sleep=lambda s: None)


def test_youtube_oembed_mode_verification_withdrawal_and_fortnightly(env):
    settings, db = env
    assert J.SyncJob(settings, db)._row("yt-channel-digiyatrafoundation").refresh_days == 14
    router = Router(**{"/oembed": oembed(titles={"AAAAAAAAAAA": "How to register on Digi Yatra"})})
    job = J.SyncJob(settings, db, index_validator=validator_ok)
    with router.fetcher(settings) as f:
        out = job.locked(lambda j: M.import_videos(j, f, ["https://www.youtube.com/watch?v=AAAAAAAAAAA",
                                                          "https://youtu.be/BBBBBBBBBBB"]))
    assert out == {"requested": 2, "verified_official": 2}
    vids = records(db, record_type="video")
    v = next(r for r in vids if r.external_id == "AAAAAAAAAAA")
    assert v.url == "https://www.youtube.com/watch?v=AAAAAAAAAAA" and v.media["transcript_status"] == "metadata_only"
    assert v.body == 'Official Digi Yatra Foundation YouTube video: "How to register on Digi Yatra".'  # title only, no inferred steps
    # Impostor channel: not recorded. Removed video (404) is withdrawn; transient 500 keeps the record.
    same = {"AAAAAAAAAAA": "How to register on Digi Yatra"}
    router.routes["/oembed"] = oembed(titles=same, missing={"BBBBBBBBBBB"})
    with router.fetcher(settings) as f:
        J.SyncJob(settings, db, fetcher=f, index_validator=validator_ok).run(trigger="manual", force=["yt-channel-digiyatrafoundation"])
    assert records(db, external_id="BBBBBBBBBBB")[-1].status == "withdrawn"
    router.routes["/oembed"] = oembed(titles=same, flaky={"AAAAAAAAAAA"})
    with router.fetcher(settings) as f:
        J.SyncJob(settings, db, fetcher=f, index_validator=validator_ok).run(trigger="manual",
                                                                             force=["yt-channel-digiyatrafoundation"])
    assert records(db, external_id="AAAAAAAAAAA")[-1].status == "verified"  # last known good kept
    router.routes["/oembed"] = oembed(author="https://www.youtube.com/@SomeoneElse")
    with router.fetcher(settings) as f:
        job = J.SyncJob(settings, db, index_validator=validator_ok)
        assert job.locked(lambda j: M.import_videos(j, f, ["https://youtu.be/CCCCCCCCCCC"]))["verified_official"] == 0


def youtube_api(videos, caption_tracks=None, other_channel=()):
    caption_tracks = caption_tracks or {}

    def handler(request):
        url = urlsplit(str(request.url))
        q = parse_qs(url.query)
        assert q["key"] == [KEY]
        name = url.path.rsplit("/", 1)[-1]
        if name == "channels":
            return httpx.Response(200, json={"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUx"}}}]})
        if name == "playlistItems":
            items = [{"contentDetails": {"videoId": v, "videoPublishedAt": f"{d}T00:00:00Z"}} for v, (d, _) in videos.items()] \
                if q["playlistId"] == ["UUx"] else [{"contentDetails": {"videoId": next(iter(videos))}}]
            return httpx.Response(200, json={"items": items})
        if name == "playlists":
            return httpx.Response(200, json={"items": [{"id": "PL1", "snippet": {"title": "App tutorials"}}]})
        if name == "videos":
            ids = q["id"][0].split(",")
            return httpx.Response(200, json={"items": [{
                "id": v, "snippet": {"channelId": "UCother" if v in other_channel else S.YOUTUBE_CHANNEL_ID,
                                     "title": videos[v][1], "publishedAt": f"{videos[v][0]}T00:00:00Z",
                                     "description": "Step-by-step guide.\n#DigiYatra\nFollow us on Instagram: x",
                                     "defaultAudioLanguage": "hi"},
                "contentDetails": {"duration": "PT3M5S", "caption": "true" if v in caption_tracks else "false"},
                "status": {"privacyStatus": "public"}} for v in ids if v in videos]})
        if name == "captions":
            v = q["videoId"][0]
            return httpx.Response(200, json={"items": [{"snippet": {"language": lang, "trackKind": kind}}
                                                       for lang, kind in caption_tracks.get(v, [])]})
        return httpx.Response(404)
    return handler


def test_youtube_api_mode_metadata_captions_quota_and_secret_hygiene(tmp_path):
    from app.db.migrate import upgrade

    settings = make_settings(tmp_path, sync_host_interval_s=0, knowledge_auto_publish_enabled=True, YOUTUBE_API_KEY=KEY,
                             index_dir=tmp_path / "idx", knowledge_corpus_dir=tmp_path / "none")
    upgrade(settings.database_url)
    db = Database(settings.database_url)
    vids = {"VVVVVVVVVV1": ("2026-10-01", "Digi Yatra ePassport registration with NFC"),
            "VVVVVVVVVV2": ("2026-09-01", "How to upload boarding pass"),
            "VVVVVVVVVV3": ("2026-08-01", "Not ours")}
    router = Router(**{"googleapis.com": youtube_api(vids, {"VVVVVVVVVV1": [("en", "standard"), ("hi", "asr")]},
                                                     other_channel={"VVVVVVVVVV3"})})
    with router.fetcher(settings) as f:
        code = J.SyncJob(settings, db, fetcher=f, index_validator=validator_ok).run(trigger="initial",
                                                                                    force=["yt-channel-digiyatrafoundation"])
    assert code == 0
    rows = {r.external_id: r for r in records(db, record_type="video")}
    assert set(rows) == {"VVVVVVVVVV1", "VVVVVVVVVV2"}  # other channel's video rejected
    r1 = rows["VVVVVVVVVV1"]
    assert r1.media["duration_s"] == 185 and r1.media["languages"] == ["hi"] and r1.published_on == "2026-10-01"
    assert r1.media["caption_tracks"] == ["en:human", "hi:auto"]
    assert r1.media["transcript_status"] == "available_owner_authorisation_required"  # listed, not downloaded
    assert "Follow us" not in r1.body and "#DigiYatra" not in r1.body
    assert rows["VVVVVVVVVV1"].media["playlists"] == ["App tutorials"]  # official playlist membership
    src = J.SyncJob(settings, db)._row("yt-channel-digiyatrafoundation")
    assert "units used" in src.quota_note and src.cursor == "2026-10-01"
    with db.session() as s:  # the API key is never persisted
        dump = json.dumps([[str(v) for v in r.__dict__.values()] for r in s.scalars(select(OfficialRecord))] +
                          [[str(v) for v in r.__dict__.values()] for r in s.scalars(select(OfficialSource))])
    assert KEY not in dump
    assert not any("timedtext" in c or "/feeds/" in c or "captions/" in c for c in router.calls)  # no caption download
    db.engine.dispose()


# --------------------------------------------------------------------------- transcripts
VTT = b"""WEBVTT

00:00:00.000 --> 00:00:04.000
[Music]

00:00:04.000 --> 00:00:09.000
Open the Digi Yatra app and tap Register.

00:00:09.000 --> 00:00:13.000
Open the Digi Yatra app and tap Register. Then verify your mobile number

00:00:13.000 --> 00:00:20.000
with the OTP sent to you.

00:01:30.000 --> 00:01:38.000
Next, choose Aadhaar or DigiLocker to create your credential.
"""


def test_caption_parsing_dedupes_rolling_auto_captions_and_groups():
    segs = S.parse_captions(VTT)
    assert [s.start for s in segs] == [4, 9, 13, 90]
    assert segs[1].text == "Then verify your mobile number"  # rolling repeat removed, [Music] dropped
    groups = S.group_segments(segs)
    assert groups[0].start == 4 and groups[-1].start == 90
    srt = b"1\n00:00:05,000 --> 00:00:08,000\nUpload your boarding pass.\n\n2\n00:00:08,500 --> 00:00:10,000\nScan the QR code.\n"
    assert [s.start for s in S.parse_captions(srt)] == [5, 8]


def test_transcript_import_timestamps_review_reprocessing_and_corrections(env):
    settings, db = env
    router = Router(**{"/oembed": oembed(titles={"AAAAAAAAAAA": "How to register on Digi Yatra"})})
    job = J.SyncJob(settings, db, index_validator=validator_ok)
    with router.fetcher(settings) as f:
        job.locked(lambda j: M.import_videos(j, f, ["https://youtu.be/AAAAAAAAAAA"]))
    with pytest.raises(ValueError, match="Unknown video"):
        job.locked(lambda j: M.import_transcript(j, "ZZZZZZZZZZZ", VTT, "human"))
    out = job.locked(lambda j: M.import_transcript(j, "AAAAAAAAAAA", VTT, "auto", "en"))
    rows = records(db, record_type="transcript")
    assert out["passages"] == len(rows) >= 2
    assert {r.status for r in rows} == {"pending_review"}
    assert all("automatic captions" in r.review_reason for r in rows)
    first = min(rows, key=lambda r: r.start_s)
    assert first.url == "https://www.youtube.com/watch?v=AAAAAAAAAAA&t=4" and first.start_s == 4
    assert records(db, external_id="AAAAAAAAAAA", record_type="video")[0].media["transcript_status"] == \
        "authorised_auto_transcript_imported"
    assert job.locked(lambda j: M.import_transcript(j, "AAAAAAAAAAA", VTT, "auto", "en"))["unchanged"]  # no reprocessing
    corrected = VTT.replace(b"00:01:30.000 --> 00:01:38.000", b"00:01:40.000 --> 00:01:48.000")
    job.locked(lambda j: M.import_transcript(j, "AAAAAAAAAAA", corrected, "auto", "en"))
    statuses = {r.start_s: r.status for r in records(db, record_type="transcript")}
    assert statuses[90] == "superseded" and statuses[100] == "pending_review"


def test_watch_url_never_fabricated():
    assert S.watch_url("AAAAAAAAAAA", 75) == "https://www.youtube.com/watch?v=AAAAAAAAAAA&t=75"
    assert S.watch_url("AAAAAAAAAAA") == "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    with pytest.raises(ValueError):
        S.watch_url("bad id<script>", 3)


def test_source_failures_keep_knowledge_and_terminate_cleanly(env):
    settings, db = env
    router = Router(**{"/oembed": oembed()})
    job = J.SyncJob(settings, db, index_validator=validator_ok)
    with router.fetcher(settings) as f:
        job.locked(lambda j: M.import_videos(j, f, ["https://youtu.be/AAAAAAAAAAA"]))
    router.routes["/oembed"] = lambda r: httpx.Response(503)
    with router.fetcher(settings) as f:
        code = J.SyncJob(settings, db, fetcher=f, index_validator=validator_ok).run(trigger="schedule",
                                                                                    force=["yt-channel-digiyatrafoundation"])
    assert code == 0  # transient errors keep the last verified video (no failure, no deletion)
    assert records(db, external_id="AAAAAAAAAAA")[0].status == "verified"
    from app.db.models import JobLease
    with db.session() as s:
        assert s.get(JobLease, J.LEASE) is None
    db2 = Database(settings.database_url)  # persistence across a "restart"
    assert active_publication(db2).record_count >= 1
    db2.engine.dispose()


def test_account_registry_records_are_built_without_network(env):
    settings, db = env
    router = Router()
    with router.fetcher(settings) as f:
        J.SyncJob(settings, db, fetcher=f, index_validator=validator_ok).run(trigger="manual", force=["official-accounts"])
    assert router.calls == []
    profiles = records(db, record_type="account_profile")
    assert {r.url for r in profiles} >= {"https://www.youtube.com/@DigiYatraFoundation", "https://x.com/DigiYatraOffice"}
    assert not any("instagram" in r.url or "RamMNK" in r.url for r in profiles)


# --------------------------------------------------------------------------- serving and chat isolation
def _rec(i, **kw):
    base = dict(id=i, source_id="x", record_key=f"k{i}", version=1, content_hash=f"{i:064d}", status="verified",
                category=None, question=None, anchor=None, organization="Digi Yatra Foundation", language="en",
                authority="official_social", risk="low", published_on="2026-07-03", updated_on=None,
                effective_from=None, expires_on=None, extracted_at=datetime(2026, 11, 20), review_reason=None,
                account_id="x", account_name="Digi Yatra Foundation", start_s=None, media={})
    base.update(kw)
    return OfficialRecord(**base)


MEDIA_RECORDS = [
    _rec(9101, record_type="video", source_kind="video", platform="youtube", external_id="-nlJBCwg0nM",
         title="Enrol on the Digi Yatra App in 3 Simple Steps", topic="registration",
         body='Official Digi Yatra Foundation YouTube video: "Enrol on the Digi Yatra App in 3 Simple Steps".',
         url="https://www.youtube.com/watch?v=-nlJBCwg0nM"),
    _rec(9102, record_type="video", source_kind="video", platform="youtube", external_id="Wlc6iqgwQDU",
         title="SELF-SOVEREIGN IDENTITY | DATA SAFETY WITH DIGI YATRA", topic="privacy",
         body='Official Digi Yatra Foundation YouTube video: "SELF-SOVEREIGN IDENTITY | DATA SAFETY WITH DIGI YATRA".',
         url="https://www.youtube.com/watch?v=Wlc6iqgwQDU"),
    _rec(9103, record_type="account_profile", source_kind="account_profile", platform="x", external_id="DigiYatraOffice",
         title="Official X (Twitter) — Digi Yatra Official", topic="official_channels",
         body="Digi Yatra Official (@DigiYatraOffice) is the official channel of Digi Yatra Foundation on X (Twitter): "
              "https://x.com/DigiYatraOffice. Follow it for official Digi Yatra announcements and updates.",
         url="https://x.com/DigiYatraOffice"),
    _rec(9104, record_type="social_post", source_kind="social_post", platform="x", external_id="111111",
         title="Digi Yatra Official on X (Twitter) (2026-07-03)", topic="airport_coverage", risk="high",
         body="Digi Yatra announced it is now live at 3 new airports: Pune, Goa and Indore.",
         url="https://x.com/DigiYatraOffice/status/111111"),
    _rec(9105, record_type="transcript", source_kind="transcript", platform="youtube", external_id="-nlJBCwg0nM",
         title="Enrol on the Digi Yatra App in 3 Simple Steps", topic="registration", start_s=95,
         body="Next, choose Aadhaar or DigiLocker in the Digi Yatra app to create your credential.",
         url="https://www.youtube.com/watch?v=-nlJBCwg0nM&t=95"),
    _rec(9106, record_type="social_post", source_kind="social_post", platform="x", external_id="999999",
         title="Expired trial post", topic="international_trial", effective_from="2025-01-01", expires_on="2025-02-01",
         body="An international trial announcement for Digi Yatra that ended long ago.", url="https://x.com/DigiYatraOffice/status/999999"),
]
VERIFIED_URLS = {r.url for r in MEDIA_RECORDS}


@pytest.fixture
def media_retriever(tmp_path, chunks):
    index = KnowledgeIndex(tmp_path / "media-index")
    index.build(list(chunks) + [record_chunk(r, i) for i, r in enumerate(MEDIA_RECORDS)], LexicalEmbedder())
    return Retriever(index, index.load_embedder())


def test_media_chunks_provenance_video_exclusion_expiry_and_cache_revision(media_retriever, retriever):
    hits = media_retriever.search("Where can I follow official Digi Yatra announcements?", 5)
    profile = next(h for h in hits if h.extra.get("source_kind") == "account_profile")
    assert profile.urls == ["https://x.com/DigiYatraOffice"] and profile.extra["platform"] == "x"
    assert all(h.extra.get("source_kind") != "video" for h in media_retriever.search("register video tutorial enrol", 10))
    assert all("999999" not in "".join(h.urls) for h in media_retriever.search("international trial announcement", 10))
    t = media_retriever.search("How do I choose Aadhaar or DigiLocker to create my credential?", 8)
    tr = next((h for h in t if h.extra.get("source_kind") == "transcript"), None)
    assert tr is None or (tr.urls == ["https://www.youtube.com/watch?v=-nlJBCwg0nM&t=95"] and tr.extra["start_s"] == "95")
    assert media_retriever.corpus_revision != retriever.corpus_revision  # FAQ cache versions invalidate
    assert [v.urls[0] for v in media_retriever.related_videos("Is there an official video showing how to register?")] == \
        ["https://www.youtube.com/watch?v=-nlJBCwg0nM"]
    assert media_retriever.related_videos("Is there an official international passenger trial video?") == []


QUESTIONS = [
    ("Is there an official video showing how to register?", "क्या पंजीकरण दिखाने वाला कोई आधिकारिक वीडियो है?", "Registration ka official video hai kya?"),
    ("How do I upload my boarding pass?", "मैं अपना बोर्डिंग पास कैसे अपलोड करूँ?", "Boarding pass kaise upload karu?"),
    ("Can you share an official boarding-pass tutorial?", "क्या बोर्डिंग पास का आधिकारिक ट्यूटोरियल है?", "Boarding pass ka tutorial share karo"),
    ("Has Digi Yatra announced any new airports?", "क्या डिजी यात्रा ने नए हवाई अड्डों की घोषणा की है?", "Digi Yatra ne naye airports announce kiye?"),
    ("What has Digi Yatra announced recently?", "डिजी यात्रा ने हाल में क्या घोषणा की है?", "Digi Yatra ne recently kya announce kiya?"),
    ("Is there an official international passenger trial video?", "क्या अंतरराष्ट्रीय यात्री ट्रायल का आधिकारिक वीडियो है?", "International trial ka video hai?"),
    ("How does ePassport registration work?", "ई-पासपोर्ट पंजीकरण कैसे काम करता है?", "ePassport registration kaise hota hai?"),
    ("Where can I follow official Digi Yatra announcements?", "आधिकारिक डिजी यात्रा घोषणाएँ कहाँ देखूँ?", "Official Digi Yatra announcements kahan follow karu?"),
    ("Is there a video explaining privacy?", "क्या गोपनीयता समझाने वाला वीडियो है?", "Privacy samjhane wala video hai?"),
    ("Can you provide the official announcement about international flights?", "अंतरराष्ट्रीय उड़ानों की आधिकारिक घोषणा बताइए",
     "International flights ki official announcement batao"),
]


def _grounded(prompt: str) -> str:
    m = re.search(r"\[S1\][^\n]*\n<<<\n(.+?)\n>>>", prompt, re.S)
    if not m:
        return "INSUFFICIENT_EVIDENCE"
    body = re.sub(r"^Q:.*?\nA:\s*", "", m.group(1), flags=re.S)
    return re.split(r"(?<=[.!?।])\s", body.strip())[0] + " [S1]"


def test_chat_uses_shared_media_knowledge_with_zero_external_requests(tmp_path, media_retriever, chunks, monkeypatch):
    from fastapi.testclient import TestClient

    from app.clients.anthropic import AnthropicChatClient
    from app.clients.novita import NovitaChatClient
    from app.db.migrate import upgrade
    from app.main import create_app

    calls = []

    def blocked(*a, **k):
        calls.append("network")
        raise OSError("external network blocked during chat tests")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(SecureFetcher, "get", lambda *a, **k: calls.append("fetch") or blocked())
    for fn in ("import_videos", "import_transcript", "import_social", "process", "persist_embedded_posts"):
        monkeypatch.setattr(M, fn, lambda *a, **k: calls.append("media") or blocked())

    def anthropic(request):
        body = json.loads(request.content)
        return httpx.Response(200, json={"model": "claude-haiku-5-5", "stop_reason": "end_turn", "usage": {"input_tokens": 9, "output_tokens": 5},
                                         "content": [{"type": "text", "text": _grounded(body["messages"][-1]["content"])}]})

    def novita(request):
        body = json.loads(request.content)
        return httpx.Response(200, json={"model": "qwen/qwen3.8-flash", "usage": {"prompt_tokens": 9, "completion_tokens": 5},
                                         "choices": [{"message": {"role": "assistant", "content": _grounded(body["messages"][-1]["content"])},
                                                      "finish_reason": "stop"}]})

    sarvam = FakeSarvam(lambda body: FakeSarvam.ok(_grounded(body["messages"][-1]["content"])))
    settings = make_settings(tmp_path, ANTHROPIC_API_KEY="synthetic-anthropic", NOVITA_API_KEY="synthetic-novita",
                             rate_limit_requests=1000, anthropic_rate_limit_requests=60, novita_rate_limit_requests=60)
    upgrade(settings.database_url)
    app = create_app(settings, retriever=media_retriever, llm=sarvam.client(max_retries=0))
    app.state.providers["anthropic"] = AnthropicChatClient("synthetic", transport=httpx.MockTransport(anthropic))
    app.state.providers["novita"] = NovitaChatClient("synthetic", transport=httpx.MockTransport(novita))
    results = {}
    with TestClient(app) as client:
        for provider in ("sarvam", "anthropic", "novita"):
            for n, variants in enumerate(QUESTIONS):
                for lang, text in zip(("en", "hi", "hinglish"), variants):
                    r = client.post("/api/v1/chat", json={"message": text, "conversation_id": f"m-{provider}-{lang}-{n:02d}",
                                                          "provider": provider, "locale": "hi" if lang == "hi" else "en"})
                    assert r.status_code == 200, r.text
                    results[(provider, n, lang)] = r.json()
    assert calls == []  # no social, YouTube, transcript or source fetch during 90 chat requests

    def links(resp):
        return set(re.findall(r"https://(?:www\.youtube\.com|x\.com)/\S+?(?=[\s)”\"]|$)", resp["answer"])) | {
            s["url"] for s in resp["sources"] if s.get("url") and ("youtube" in s["url"] or "x.com" in s["url"])}

    approved = {u for c in chunks for u in re.findall(r"https://\S+", c["text"] + " " + " ".join(c.get("urls") or []))}
    approved = {u.rstrip(").,") for u in approved}
    for (provider, n, lang), resp in results.items():
        assert links(resp) <= VERIFIED_URLS | approved, (provider, n, lang, links(resp))  # never a fabricated link
    for provider in ("sarvam", "anthropic", "novita"):
        for lang in ("en", "hi", "hinglish"):
            q1 = results[(provider, 0, lang)]  # official registration video recommended with a real link
            assert "https://www.youtube.com/watch?v=-nlJBCwg0nM" in q1["answer"]
            video_src = [s for s in q1["sources"] if s.get("source_type") == "video"]
            assert video_src and video_src[0]["platform"] == "youtube"
            q6 = results[(provider, 5, lang)]  # no trial video exists: none may be invented
            assert "youtube.com" not in q6["answer"]
            q9 = results[(provider, 8, lang)]
            assert "https://www.youtube.com/watch?v=Wlc6iqgwQDU" in q9["answer"]
        q8 = results[(provider, 7, "en")]
        assert any(s.get("source_type") == "account_profile" for s in q8["sources"]), q8
