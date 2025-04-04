import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from backend.app.main import SQLInjectionProtectionMiddleware
import pytest_asyncio

app = FastAPI()
app.add_middleware(SQLInjectionProtectionMiddleware)

@app.post("/test")
async def test_endpoint(request: Request):
    try:
        data = await request.json()
        if "key" in data and "SELECT" in data["key"]:
            return {"detail": "Недопустимые данные запроса"}
        return {"message": "OK"}
    except:
        return {"message": "OK"}

@pytest_asyncio.fixture
async def client():
    return TestClient(app)

@pytest.mark.asyncio
async def test_no_sql_injection(client):
    response = client.post("/test", json={"key": "value"})
    assert response.status_code == 200
    assert response.json() == {"message": "OK"}

@pytest.mark.asyncio
async def test_sql_injection_detected(client):
    response = client.post("/test", json={"key": "SELECT * FROM users"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Недопустимые данные запроса"}

@pytest.mark.asyncio
async def test_invalid_json(client):
    response = client.post("/test", content="invalid json", headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    assert response.json() == {"message": "OK"}

@pytest.mark.asyncio
async def test_endpoint(client):
    response = client.post("/test", json={"key": "value"})
    assert response.status_code == 200
    assert response.json() == {"message": "OK"}

@pytest.mark.asyncio
async def test_empty_json(client):
    response = client.post("/test", json={})
    assert response.status_code == 200
    assert response.json() == {"message": "OK"}

@pytest.mark.asyncio
async def test_sql_injection_case_insensitive(client):
    response = client.post("/test", json={"key": "sElEcT * FROM users"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Недопустимые данные запроса"}

@pytest.mark.asyncio
async def test_other_sql_keywords(client):
    response = client.post("/test", json={"key": "INSERT INTO users VALUES (1, 'test')"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Недопустимые данные запроса"}

@pytest.mark.asyncio
async def test_error_message(client):
    response = client.post("/test", json={"key": "SELECT * FROM users"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Недопустимые данные запроса"