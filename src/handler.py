import base64
import hashlib
import hmac
import json
import os
import time

_cached_secret = None


def _b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _secret():
    global _cached_secret
    if _cached_secret is None:
        import boto3

        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=os.environ["AUTH_SECRET_ID"])
        _cached_secret = json.loads(response["SecretString"])
    return _cached_secret


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
        config = _secret()
        valid_login = hmac.compare_digest(str(body.get("login", "")), config["adminLogin"])
        valid_password = hmac.compare_digest(str(body.get("senha", "")), config["adminPassword"])
        if not (valid_login and valid_password):
            return _response(401, {"message": "Usuario ou senha invalidos."})
        token = create_token(config["adminId"], "ADMINISTRADOR", config["jwtSecret"], int(os.getenv("JWT_EXPIRATION_SECONDS", "3600")))
        return _response(200, {"token": token})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _response(400, {"message": "Requisicao invalida."})


def authorizer(event, _context):
    try:
        authorization = event.get("headers", {}).get("authorization", "")
        if not authorization.startswith("Bearer "):
            return {"isAuthorized": False}
        claims = validate_token(authorization[7:], _secret()["jwtSecret"])
        return {"isAuthorized": True, "context": {"subject": claims["sub"], "role": claims["papel"]}}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"isAuthorized": False}
