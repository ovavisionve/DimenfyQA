import re
import unicodedata


def clean_bio(bio: str | None) -> str:
    """Clean Instagram bio text: remove emojis, normalize whitespace, strip special chars."""
    if not bio:
        return ""

    # Remove emojis and special unicode characters
    text = remove_emojis(bio)

    # Normalize unicode (e.g., accented characters)
    text = unicodedata.normalize("NFKD", text)

    # Replace line breaks with spaces
    text = text.replace("\n", " ").replace("\r", " ")

    # Remove multiple spaces
    text = re.sub(r"\s+", " ", text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def remove_emojis(text: str) -> str:
    """Remove emoji characters from text."""
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U00002500-\U00002bef"  # chinese chars
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "\U0001f900-\U0001f9ff"  # supplemental symbols
        "\U0001fa00-\U0001fa6f"  # chess symbols
        "\U0001fa70-\U0001faff"  # symbols extended-A
        "\U00002702-\U000027b0"
        "\U0000fe00-\U0000fe0f"  # variation selectors
        "\U0000200d"  # zero width joiner
        "\U0000200c"  # zero width non-joiner
        "\U000020e3"  # combining enclosing keycap
        "\U0000231a-\U0000231b"  # watch, hourglass
        "\U00002934-\U00002935"  # arrows
        "\U000025aa-\U000025ab"  # squares
        "\U000025b6"
        "\U000025c0"
        "\U000025fb-\U000025fe"
        "\U00002600-\U000026ff"  # misc symbols
        "\U00002700-\U000027bf"  # dingbats
        "\U0000fe0f"
        "\U0001f000-\U0001f02f"  # mahjong tiles
        "\U0001f0a0-\U0001f0ff"  # playing cards
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text)


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to max_length, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
