import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from handler import create_token, validate_token


class JwtTest(unittest.TestCase):
    def test_round_trip(self):
        token = create_token("00000000-0000-0000-0000-000000000001", "ADMINISTRADOR", "x" * 32)
        claims = validate_token(token, "x" * 32)
        self.assertEqual("ADMINISTRADOR", claims["papel"])

    def test_rejects_wrong_secret(self):
        token = create_token("id", "ADMINISTRADOR", "x" * 32)
        with self.assertRaises(ValueError):
            validate_token(token, "y" * 32)


if __name__ == "__main__":
    unittest.main()
