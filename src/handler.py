import base64
import hashlib
import hmac
import json
import logging
import os
import re
import ssl
import time

_cached_auth_secret = None
_cached_database_secret = None

LOGGER = logging.getLogger(__name__)
CPF_PATTERN = re.compile(r"^(?:\d{11}|\d{3}\.\d{3}\.\d{3}-\d{2})$")


def _b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _read_secret(secret_id):
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    return json.loads(response["SecretString"])


def _auth_secret():
    global _cached_auth_secret
    if _cached_auth_secret is None:
        _cached_auth_secret = _read_secret(os.environ["AUTH_SECRET_ID"])
    return _cached_auth_secret


def _database_secret():
    global _cached_database_secret
    if _cached_database_secret is None:
        _cached_database_secret = _read_secret(os.environ["DB_SECRET_ARN"])
    return _cached_database_secret


def validate_cpf(value):
    if not isinstance(value, str) or not CPF_PATTERN.fullmatch(value.strip()):
        return None

    cpf = re.sub(r"\D", "", value)
    if len(set(cpf)) == 1:
        return None

    for position in (9, 10):
        weight = position + 1
        total = sum(int(cpf[index]) * (weight - index) for index in range(position))
        digit = (total * 10 % 11) % 10
        if digit != int(cpf[position]):
            return None

    return cpf


def _find_client(cpf):
    import pg8000.dbapi

    credentials = _database_secret()
    connection = pg8000.dbapi.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
        user=credentials["username"],
        password=credentials["password"],
        timeout=int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5")),
        ssl_context=ssl.create_default_context(),
    )
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT id, ativo FROM cliente WHERE cpf_cnpj = %s",
                (cpf,),
            )
            return cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()


def create_token(subject, role, secret, expiration_seconds=3600):
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({"sub": subject, "papel": role, "iat": now, "exp": now + expiration_seconds}, separators=(",", ":")).encode())
    signature = _b64url(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def validate_token(token, secret):
    header, payload, signature = token.split(".")
    expected = _b64url(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise ValueError("invalid signature")
    claims = json.loads(_decode(payload))
    if int(claims["exp"]) <= int(time.time()):
        raise ValueError("expired token")
    return claims


def _response(status, body):
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def login(event, _context):
    try:
        body = json.loads(event.get("body") or "{}")
        cpf = validate_cpf(body.get("cpf"))
        if cpf is None:
            return _response(400, {"message": "CPF invalido."})

        client = _find_client(cpf)
        if client is None:
            return _response(404, {"message": "Cliente nao encontrado."})

        client_id, active = client
        if not active:
            return _response(403, {"message": "Cliente inativo."})

        config = _auth_secret()
        token = create_token(
            str(client_id),
            "CLIENTE",
            config["jwtSecret"],
            int(os.getenv("JWT_EXPIRATION_SECONDS", "3600")),
        )
        return _response(200, {"token": token})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _response(400, {"message": "Requisicao invalida."})
    except Exception:
        LOGGER.exception("Falha ao autenticar cliente por CPF")
        return _response(500, {"message": "Falha interna na autenticacao."})


def authorizer(event, _context):
    try:
        headers = event.get("headers") or {}
        authorization = headers.get("authorization") or headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return {"isAuthorized": False}
        claims = validate_token(authorization[7:], _auth_secret()["jwtSecret"])
        return {"isAuthorized": True, "context": {"subject": claims["sub"], "role": claims["papel"]}}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"isAuthorized": False}
