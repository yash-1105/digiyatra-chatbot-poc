"""Retrieval relevance on 30 representative passenger questions (real index, lexical vectors)."""

from __future__ import annotations

import pytest

# (question, acceptable source files — at least one must appear in the top 5)
CASES = [
    ("How do I register for Digi Yatra?", {"registration_details.md", "end_to_end_process.md", "general_02_how_it_works.md"}),
    ("What documents do I need to enrol?", {"registration_details.md", "general_02_how_it_works.md", "support_02_registration_profile.md", "end_to_end_process.md"}),
    ("Can I register without Aadhaar?", {"support_02_registration_profile.md"}),
    ("Is Digi Yatra mandatory?", {"general_01_introduction.md"}),
    ("Who operates Digi Yatra?", {"general_01_introduction.md", "linkedin_about_us.md", "privacy_policy.csv"}),
    ("When was Digi Yatra launched?", {"general_01_introduction.md"}),
    ("Which airports support Digi Yatra?", {"available_airports.md"}),
    ("Is Digi Yatra available at Chandigarh airport?", {"available_airports.md"}),
    ("Can I use Digi Yatra for international flights?", {"support_04_general_information.md"}),
    ("Can foreign citizens use Digi Yatra?", {"general_04_app_eligibility.md"}),
    ("Where is my data stored?", {"general_03_data_privacy_security.md", "support_02_registration_profile.md"}),
    ("How long does the airport keep my biometric data?", {"airport_data_sharing.md", "general_03_data_privacy_security.md"}),
    ("Does Digi Yatra track my travel history?", {"general_03_data_privacy_security.md"}),
    ("How do I delete my Digi Yatra account?", {"delete_digiyatra.md", "general_03_data_privacy_security.md"}),
    ("Can I add my child to my account?", {"general_04_app_eligibility.md", "support_02_registration_profile.md", "allowed_passengers.md"}),
    ("Can my infant travel using Digi Yatra?", {"allowed_passengers.md", "support_05_usage_eligibility.md"}),
    ("My wife and I are on the same PNR, can I add her?", {"support_02_registration_profile.md"}),
    ("I am not receiving the OTP", {"support_01_app_troubleshooting.md"}),
    ("I get a Forbidden error when I log in", {"support_01_app_troubleshooting.md"}),
    ("My boarding pass upload keeps failing", {"support_01_app_troubleshooting.md", "support_02_registration_profile.md"}),
    ("The name on my boarding pass doesn't match my Aadhaar", {"support_02_registration_profile.md"}),
    ("How do I share my boarding pass PDF with the app?", {"share_data_with_app.md"}),
    ("What happens at the airport entry gate?", {"airport_guide.md", "end_to_end_process.md", "general_02_how_it_works.md"}),
    ("What should I do at the boarding gate?", {"airport_guide.md", "end_to_end_process.md"}),
    ("What if the Digi Yatra system is down?", {"general_02_how_it_works.md"}),
    ("I changed my phone, what now?", {"general_04_app_eligibility.md"}),
    ("Does wearing a turban affect face matching?", {"general_04_app_eligibility.md"}),
    ("Is the app available in Hindi?", {"available_languages.md"}),
    ("How do I contact customer care?", {"contact_us.md", "general_05_troubleshooting_support.md"}),
    ("Why was I asked for my boarding pass even after using Digi Yatra?", {"support_03_airport_availability.md"}),
    ("How do I change my app passcode?", {"support_04_general_information.md"}),
    ("When should I share my credentials with the airport?", {"general_02_how_it_works.md", "end_to_end_process.md"}),
]


@pytest.mark.parametrize("question,expected", CASES, ids=[c[0][:40] for c in CASES])
def test_relevant_source_in_top_5(retriever, question, expected):
    hits = retriever.search(question, top_k=5)
    files = [h.source_file for h in hits]
    assert expected & set(files), f"{question!r} -> {files}"


def test_case_count():
    assert len(CASES) >= 25


@pytest.mark.parametrize(
    "question",
    ["What is the capital of France?", "Write me a poem about cricket", "Best biryani recipe", "Explain quantum entanglement"],
)
def test_off_topic_questions_find_no_strong_evidence(retriever, question):
    hits = retriever.search(question, top_k=5)
    assert not hits or hits[0].score < 0.35


def test_results_are_scored_ranked_deduplicated_and_capped(retriever):
    hits = retriever.search("How is my data stored and deleted?", top_k=8)
    assert hits == sorted(hits, key=lambda h: h.score, reverse=True)
    assert len({h.chunk_id for h in hits}) == len(hits)
    per_file: dict[str, int] = {}
    for h in hits:
        per_file[h.source_file] = per_file.get(h.source_file, 0) + 1
        assert 0 < h.score <= 1
    assert max(per_file.values()) <= retriever.max_per_source


def test_configurable_top_k(retriever):
    assert len(retriever.search("Digi Yatra registration Aadhaar selfie", top_k=2)) == 2
    assert len(retriever.search("Digi Yatra registration Aadhaar selfie", top_k=6)) <= 6


def test_draft_international_trial_never_retrieved(retriever):
    for q in ("Can I use my ePassport for an international flight?", "DY-IPT trial airlines and routes",
              "Which international routes does IndiGo support with Digi Yatra?"):
        for h in retriever.search(q, top_k=10):
            assert "IPT" not in h.source_file and "ePassport" not in h.text


def test_citation_lookup_only_resolves_indexed_chunks(retriever):
    hit = retriever.search("Is Digi Yatra mandatory?", 1)[0]
    assert retriever.lookup(hit.chunk_id)["source_file"] == hit.source_file
    assert retriever.lookup("fake-chunk-id") is None
