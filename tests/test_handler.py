import json
import os
import sys
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from handler import create_token, login, validate_cpf, validate_token


class JwtTest(unittest.TestCase):
    def test_round_trip(self):
        token = create_token("00000000-0000-0000-0000-000000000001", "ADMINISTRADOR", "x" * 32)
        claims = validate_token(token, "x" * 32)
        self.assertEqual("ADMINISTRADOR", claims["papel"])

    def test_rejects_wrong_secret(self):
        token = create_token("id", "ADMINISTRADOR", "x" * 32)
        with self.assertRaises(ValueError):
            validate_token(token, "y" * 32)


class CpfLoginTest(unittest.TestCase):
    VALID_CPF = "00361937040"
    CLIENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

    @staticmethod
    def event(cpf):
        return {"body": json.dumps({"cpf": cpf})}

    def test_rejects_invalid_cpf(self):
        with patch("handler._find_client") as find_client:
            response = login(self.event("00361937041"), None)

        self.assertEqual(400, response["statusCode"])
        self.assertEqual({"message": "CPF invalido."}, json.loads(response["body"]))
        find_client.assert_not_called()

    def test_returns_not_found_for_unknown_client(self):
        with patch("handler._find_client", return_value=None):
            response = login(self.event(self.VALID_CPF), None)

        self.assertEqual(404, response["statusCode"])

    def test_rejects_inactive_client(self):
        with patch("handler._find_client", return_value=(self.CLIENT_ID, False)):
            response = login(self.event(self.VALID_CPF), None)

        self.assertEqual(403, response["statusCode"])

    def test_issues_client_token_for_active_client(self):
        with (
            patch("handler._find_client", return_value=(self.CLIENT_ID, True)),
            patch("handler._auth_secret", return_value={"jwtSecret": "x" * 32}),
        ):
            response = login(self.event("003.619.370-40"), None)

        self.assertEqual(200, response["statusCode"])
        token = json.loads(response["body"])["token"]
        claims = validate_token(token, "x" * 32)
        self.assertEqual({"sub", "papel", "iat", "exp"}, set(claims))
        self.assertEqual(str(self.CLIENT_ID), claims["sub"])
        self.assertEqual("CLIENTE", claims["papel"])

    def test_normalizes_valid_formatted_cpf(self):
        self.assertEqual(self.VALID_CPF, validate_cpf("003.619.370-40"))


if __name__ == "__main__":
    unittest.main()
