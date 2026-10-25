import pytest
from fastapi.testclient import TestClient
from backend.app import create_app, User


@pytest.fixture
def app(tmp_path):
    return create_app(f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def register(client, email="buyer@example.com"):
    return client.post("/api/auth/register", json={
        "email": email,
        "password": "StrongPass123!"
    })


def login(client, email="buyer@example.com"):
    response = client.post("/api/auth/login", json={
        "email": email,
        "password": "StrongPass123!"
    })
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def buyer(client):
    assert register(client).status_code == 201
    return login(client)


@pytest.fixture
def admin(client, app):
    assert register(client, "admin@example.com").status_code == 201
    with app.state.session_factory() as session:
        user = session.query(User).filter_by(email="admin@example.com").one()
        user.role = "admin"
        session.commit()
    return login(client, "admin@example.com")


def add_vehicle(client, admin, **overrides):
    data = {
        "make": "Toyota",
        "model": "Corolla",
        "category": "Sedan",
        "price": 20000,
        "quantity": 2
    }
    data.update(overrides)
    response = client.post("/api/vehicles", headers=admin, json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_and_login(client):
    response = register(client)
    assert response.status_code == 201
    assert "password" not in response.json()
    assert "password_hash" not in response.json()
    assert login(client)["Authorization"].startswith("Bearer ")


def test_duplicate_registration(client):
    register(client)
    assert register(client).status_code == 409


def test_wrong_password(client):
    register(client)
    response = client.post("/api/auth/login", json={
        "email": "buyer@example.com", "password": "WrongPassword!"
    })
    assert response.status_code == 401


@pytest.mark.parametrize("payload", [
    {"email": "invalid", "password": "StrongPass123!"},
    {"email": "buyer@example.com", "password": "short"},
])
def test_registration_validation(client, payload):
    assert client.post("/api/auth/register", json=payload).status_code == 422


def test_registration_cannot_grant_admin(client):
    response = client.post("/api/auth/register", json={
        "email": "attacker@example.com",
        "password": "StrongPass123!",
        "role": "admin"
    })
    assert response.status_code in (201, 422)
    if response.status_code == 201:
        headers = login(client, "attacker@example.com")
        assert client.post(
            "/api/vehicles/1/restock", headers=headers, json={"quantity": 1}
        ).status_code == 403


def test_authentication_required(client):
    assert client.get("/api/vehicles").status_code == 401
    assert client.get("/api/vehicles", headers={
        "Authorization": "Bearer invalid"
    }).status_code == 401


def test_create_list_update_delete(client, admin, buyer):
    vehicle = add_vehicle(client, admin)
    vehicle_id = vehicle["id"]
    response = client.get("/api/vehicles", headers=buyer)
    assert response.status_code == 200
    assert any(item["id"] == vehicle_id for item in response.json())

    response = client.put(
        f"/api/vehicles/{vehicle_id}", headers=admin,
        json={"price": 18000, "quantity": 3}
    )
    assert response.status_code == 200
    assert response.json()["price"] == 18000
    assert response.json()["quantity"] == 3

    assert client.delete(
        f"/api/vehicles/{vehicle_id}", headers=admin
    ).status_code == 204
    assert client.get("/api/vehicles", headers=buyer).json() == []


def test_search_filters(client, admin, buyer):
    add_vehicle(client, admin)
    add_vehicle(client, admin, make="Ford", model="Explorer",
                category="SUV", price=40000)
    filters = [
        {"make": "toy"},
        {"model": "roll"},
        {"category": "sedan"},
        {"min_price": 15000, "max_price": 25000}
    ]
    for params in filters:
        response = client.get(
            "/api/vehicles/search", headers=buyer, params=params
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["make"] == "Toyota"


def test_purchase_and_out_of_stock(client, admin, buyer):
    vehicle = add_vehicle(client, admin, quantity=1)
    url = f"/api/vehicles/{vehicle['id']}/purchase"
    response = client.post(url, headers=buyer)
    assert response.status_code == 200
    assert response.json()["quantity"] == 0
    assert client.post(url, headers=buyer).status_code == 409


def test_restock_and_admin_permissions(client, admin, buyer):
    vehicle = add_vehicle(client, admin)
    url = f"/api/vehicles/{vehicle['id']}"
    assert client.delete(url, headers=buyer).status_code == 403
    assert client.post(
        url + "/restock", headers=buyer, json={"quantity": 5}
    ).status_code == 403
    response = client.post(
        url + "/restock", headers=admin, json={"quantity": 5}
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 7


@pytest.mark.parametrize("change", [
    {"price": -1}, {"quantity": -1}, {"quantity": 1.5},
    {"make": ""}, {"model": ""}, {"category": ""}
])
def test_invalid_vehicle_rejected(client, admin, change):
    data = dict(make="Toyota", model="Corolla", category="Sedan",
                price=20000, quantity=2)
    data.update(change)
    assert client.post(
        "/api/vehicles", headers=admin, json=data
    ).status_code == 422


def test_invalid_restock_and_missing_vehicle(client, admin, buyer):
    vehicle = add_vehicle(client, admin)
    for quantity in (0, -1, 1.5):
        assert client.post(
            f"/api/vehicles/{vehicle['id']}/restock",
            headers=admin, json={"quantity": quantity}
        ).status_code == 422
    assert client.post(
        "/api/vehicles/99999/purchase", headers=buyer
    ).status_code == 404


def test_database_persists_between_app_instances(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'persistent.db'}"
    with TestClient(create_app(database_url)) as first:
        assert register(first).status_code == 201
    with TestClient(create_app(database_url)) as second:
        assert login(second)["Authorization"].startswith("Bearer ")
