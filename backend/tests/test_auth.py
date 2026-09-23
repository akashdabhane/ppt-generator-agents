from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth as auth_api
from app.api.v1.deps import get_db


def _client(api_env):
    app = FastAPI()
    app.include_router(auth_api.router)
    app.dependency_overrides[get_db] = api_env["client"].app.dependency_overrides[get_db]
    return TestClient(app)


def test_register_then_login_with_form_data(api_env):
    client = _client(api_env)
    reg = client.post("/auth/register", json={"email": "new@example.com", "password": "secret123"})
    assert reg.status_code == 200

    # The frontend sends the OAuth2 password form: username=<email>
    res = client.post("/auth/login", data={"username": "new@example.com", "password": "secret123"})
    assert res.status_code == 200
    assert res.json()["user"]["email"] == "new@example.com"
    assert res.json()["access_token"]


def test_login_rejects_json_body(api_env):
    client = _client(api_env)
    client.post("/auth/register", json={"email": "new@example.com", "password": "secret123"})
    res = client.post("/auth/login", json={"email": "new@example.com", "password": "secret123"})
    assert res.status_code == 422


def test_login_wrong_password(api_env):
    client = _client(api_env)
    client.post("/auth/register", json={"email": "new@example.com", "password": "secret123"})
    res = client.post("/auth/login", data={"username": "new@example.com", "password": "nope"})
    assert res.status_code == 400
