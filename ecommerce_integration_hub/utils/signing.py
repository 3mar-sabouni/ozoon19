import hashlib
import hmac
import json
import time


def serialize_payload(payload):
    """Return the exact compact UTF-8 JSON bytes that will be signed and sent."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def build_signature(secret, timestamp, raw_body):
    """Compute hex(HMAC_SHA256(secret, timestamp + '.' + raw_body))."""
    message = str(timestamp).encode("utf-8") + b"." + raw_body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_signature(secret, timestamp, raw_body, signature, max_age_seconds=300):
    """Validate timestamp freshness and HMAC signature."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > max_age_seconds:
        return False
    expected = build_signature(secret, str(ts), raw_body)
    return hmac.compare_digest(expected, str(signature or ""))
