import hashlib
import hmac
import unittest

from ..utils.signing import build_signature, serialize_payload
from ..utils.text import stable_slug


class TestConnectorUtilities(unittest.TestCase):
    def test_compact_json_and_signature_use_same_raw_bytes(self):
        payload = {"name": "هاتف", "quantity": 2}
        raw = serialize_payload(payload)
        self.assertEqual(raw, '{"name":"هاتف","quantity":2}'.encode("utf-8"))

        secret = "test-secret"
        timestamp = "1700000000"
        expected = hmac.new(
            secret.encode("utf-8"),
            timestamp.encode("utf-8") + b"." + raw,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(build_signature(secret, timestamp, raw), expected)

    def test_slug_falls_back_for_non_latin_only_name(self):
        self.assertEqual(stable_slug("الهواتف", "category-10"), "category-10")
