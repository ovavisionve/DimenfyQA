"""Tests for bio keyword filtering in the scraping pipeline."""

import pytest


def filter_by_bio_keywords(profiles: list[dict], bio_keywords: list[str]) -> list[dict]:
    """Replicate the bio keyword filter logic from scraping_tasks.py."""
    if not bio_keywords:
        return profiles
    kw_lower = [kw.lower().strip() for kw in bio_keywords if kw.strip()]
    return [
        p for p in profiles
        if any(kw in (p.get("biography") or "").lower() for kw in kw_lower)
    ]


class TestBioKeywordFilter:
    """Tests for pre-scraping bio keyword filtering."""

    def test_no_keywords_returns_all(self):
        profiles = [
            {"username": "user1", "biography": "Marketing guru"},
            {"username": "user2", "biography": "Coach de vida"},
        ]
        result = filter_by_bio_keywords(profiles, [])
        assert len(result) == 2

    def test_filters_by_single_keyword(self):
        profiles = [
            {"username": "user1", "biography": "Marketing guru | DMs open"},
            {"username": "user2", "biography": "Coach de vida y negocios"},
            {"username": "user3", "biography": "Just vibing"},
        ]
        result = filter_by_bio_keywords(profiles, ["coach"])
        assert len(result) == 1
        assert result[0]["username"] == "user2"

    def test_filters_by_multiple_keywords(self):
        profiles = [
            {"username": "user1", "biography": "Marketing agency owner"},
            {"username": "user2", "biography": "Life coach | Entrepreneur"},
            {"username": "user3", "biography": "Just vibing"},
            {"username": "user4", "biography": "Agency digital"},
        ]
        result = filter_by_bio_keywords(profiles, ["coach", "agency"])
        assert len(result) == 3
        usernames = [p["username"] for p in result]
        assert "user1" in usernames
        assert "user2" in usernames
        assert "user4" in usernames

    def test_case_insensitive(self):
        profiles = [
            {"username": "user1", "biography": "MARKETING AGENCY"},
            {"username": "user2", "biography": "marketing agency"},
        ]
        result = filter_by_bio_keywords(profiles, ["Marketing"])
        assert len(result) == 2

    def test_handles_empty_bio(self):
        profiles = [
            {"username": "user1", "biography": None},
            {"username": "user2", "biography": ""},
            {"username": "user3", "biography": "Coach profesional"},
        ]
        result = filter_by_bio_keywords(profiles, ["coach"])
        assert len(result) == 1
        assert result[0]["username"] == "user3"

    def test_handles_empty_keyword_strings(self):
        profiles = [
            {"username": "user1", "biography": "Coach de vida"},
        ]
        result = filter_by_bio_keywords(profiles, ["", " ", "coach"])
        assert len(result) == 1

    def test_partial_match(self):
        """Keywords match as substrings — 'market' matches 'marketing'."""
        profiles = [
            {"username": "user1", "biography": "Digital marketing expert"},
        ]
        result = filter_by_bio_keywords(profiles, ["market"])
        assert len(result) == 1

    def test_spanish_keywords(self):
        profiles = [
            {"username": "user1", "biography": "Agencia de marketing digital"},
            {"username": "user2", "biography": "Emprendedor y coach"},
            {"username": "user3", "biography": "Fotografo profesional"},
        ]
        result = filter_by_bio_keywords(profiles, ["agencia", "coach"])
        assert len(result) == 2

    def test_all_filtered_out(self):
        profiles = [
            {"username": "user1", "biography": "Just a regular person"},
            {"username": "user2", "biography": "Love food and travel"},
        ]
        result = filter_by_bio_keywords(profiles, ["agency", "coach"])
        assert len(result) == 0

    def test_no_profiles(self):
        result = filter_by_bio_keywords([], ["coach"])
        assert len(result) == 0
