from app.utils.text_cleanup import clean_bio, remove_emojis, truncate_text


class TestTextCleanup:
    def test_clean_bio_removes_emojis(self):
        bio = "We help businesses grow 🚀 | Marketing Agency 💼"
        result = clean_bio(bio)
        assert "🚀" not in result
        assert "💼" not in result
        assert "Marketing Agency" in result

    def test_clean_bio_normalizes_whitespace(self):
        bio = "Line 1\nLine 2\n\nLine 3"
        result = clean_bio(bio)
        assert "\n" not in result
        assert "  " not in result

    def test_clean_bio_handles_none(self):
        assert clean_bio(None) == ""

    def test_clean_bio_handles_empty(self):
        assert clean_bio("") == ""

    def test_remove_emojis(self):
        text = "Hello 👋 World 🌍"
        result = remove_emojis(text)
        assert "👋" not in result
        assert "🌍" not in result
        assert "Hello" in result
        assert "World" in result

    def test_truncate_text_short(self):
        text = "Short text"
        assert truncate_text(text, 100) == "Short text"

    def test_truncate_text_long(self):
        text = "A" * 600
        result = truncate_text(text, 500)
        assert len(result) == 500
        assert result.endswith("...")

    def test_truncate_text_exact_length(self):
        text = "A" * 500
        assert truncate_text(text, 500) == text
