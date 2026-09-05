import re
import unicodedata


def stable_slug(value, fallback):
    """Build an ASCII URL slug, keeping a stable fallback for non-Latin names."""
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or fallback
