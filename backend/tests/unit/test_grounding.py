"""Sentence-level citation grounding."""

from __future__ import annotations

from app.security.grounding import ground_answer

EV = [
    "Q: Is Digi Yatra mandatory?\nA: No, using Digi Yatra is purely voluntary for air passengers. Data is collected only with their consent.",
    "Q: How long will the biometric data be stored? A: The airport systems purge biometric data within 24 hours of the flight's departure.",
    "Q: Can I register without Aadhaar? A: Currently, Aadhaar is mandatory for verification and creating your Digi Yatra ID.",
]


def test_supported_sentences_keep_citations():
    r = ground_answer("Using Digi Yatra is purely voluntary for air passengers [1]. Biometric data is purged within 24 hours of departure [2].",
                      {1: 0, 2: 1}, EV)
    assert r.dropped == 0 and r.cited_hits == [0, 1]
    assert r.text == "Using Digi Yatra is purely voluntary for air passengers [1]. Biometric data is purged within 24 hours of departure [2]."


def test_misattributed_citation_is_reattributed():
    r = ground_answer("Aadhaar is mandatory for verification and creating your Digi Yatra ID [1].", {1: 0}, EV)
    assert r.reattributed == 1 and r.cited_hits == [2] and r.text.endswith("[1].")


def test_unsupported_factual_sentence_dropped():
    r = ground_answer("Digi Yatra is voluntary [1]. Passengers receive cashback rewards and lounge upgrades every month [1].",
                      {1: 0}, EV)
    assert r.dropped == 1 and "cashback" not in r.text and "voluntary" in r.text


def test_invented_number_dropped():
    r = ground_answer("The airport systems purge biometric data within 48 hours of the flight's departure [2].", {2: 1}, EV)
    assert r.dropped == 1 and r.cited_hits == []


def test_uncited_supported_sentence_gets_citation_and_advice_kept():
    r = ground_answer("The airport systems purge biometric data within 24 hours of departure. Please check the official website.",
                      {}, EV)
    assert r.cited_hits == [1] and "[1]" in r.text and "Please check the official website." in r.text


def test_marker_after_full_stop_and_paragraphs():
    r = ground_answer("Using Digi Yatra is purely voluntary for air passengers. [1]\n\nAadhaar is mandatory for verification and creating your Digi Yatra ID. [2]",
                      {1: 0, 2: 2}, EV)
    assert r.text == ("Using Digi Yatra is purely voluntary for air passengers [1].\n\n"
                      "Aadhaar is mandatory for verification and creating your Digi Yatra ID [2].")


def test_declines_are_not_treated_as_claims():
    r = ground_answer("No customer care phone number is listed in the sources; you can email support instead [1].", {1: 0}, EV)
    assert r.dropped == 0 and r.cited_hits == [0]
