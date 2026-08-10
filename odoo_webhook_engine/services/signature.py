# -*- coding: utf-8 -*-
"""
HMAC-SHA256 signature generation for outgoing webhook payloads.
External receivers can verify payload integrity using the shared secret.
"""

import hashlib
import hmac


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """
    Compute HMAC-SHA256 signature.

    :param payload_bytes: raw request body bytes
    :param secret: shared secret key string
    :return: hex-encoded HMAC-SHA256 digest
    """
    return hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def verify_signature(payload_bytes: bytes, secret: str, signature: str) -> bool:
    """
    Verify that a received signature matches the expected HMAC-SHA256.

    :param payload_bytes: raw request body bytes
    :param secret: shared secret key string
    :param signature: hex-encoded signature from request header
    :return: True if valid
    """
    expected = compute_signature(payload_bytes, secret)
    return hmac.compare_digest(expected, signature)
