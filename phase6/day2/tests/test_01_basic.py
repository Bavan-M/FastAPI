import pytest

# ============================================================
# HEALTH CHECK TESTS
# ============================================================
#mark = A label/tag you attach to a test to give it special behavior or metadata.
# Run test with async event loop

@pytest.mark.asyncio
async def test_health_check(client):
    """Simplest possible test — verify app is running"""
    # Act
    response=await client.get("/health")

    #Assert
    assert response.status_code==200
    assert response.json()=={"status":"ok"}


# ============================================================
# AUTH TESTS
# ============================================================
@pytest.mark.asyncio
async def test_register_success(client):
    """Happy path — register a new user"""

    #Arrage
    payload={
        "username":"bavan",
        "email":"bavan@gmail.com",
        "password":"pass@1234567"
    }

    # Act
    response=await client.post("/api/v1/auth/register",json=payload)

    #Assert
    assert response.status_code==201
    data=response.json()
    assert data["username"]=="bavan"
    assert data["email"]=="bavan@gmail.com"
    assert data["role"]=="user"
    assert "id" in data
    assert "password" not in data

@pytest.mark.asyncio
async def test_register_duplicate_username(client):
    """Register same username twice — should fail"""
    payload={"username":"alice","email":"new@test.com","password":"pass@1234567"}
    response=await client.post("/api/v1/auth/register",json=payload)
    assert response.status_code==409
    assert "already taken" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_register_invalid_email(client):
    """Invalid email format — Pydantic validation should catch it"""
    payload = {
        "username": "testuser",
        "email":    "not-an-email",
        "password": "pass12345"
    }

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422   # Pydantic validation error

@pytest.mark.asyncio
async def test_register_short_password(client):
    """Password too short — should fail validation"""
    payload = {
        "username": "testuser",
        "email":    "test@test.com",
        "password": "short"          # less than 8 chars
    }

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_me_authenticated(auth_client): # auth_client = Always sends valid token (can't change it)
    """Authenticated user can get their profile"""
    response = await auth_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "alice"
    assert data["role"]     == "admin"

@pytest.mark.asyncio
async def test_get_me_unauthenticated(client): # client = Sends nothing (you can add ANY token - valid, invalid, or none)
    """No token — should return 401"""
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_me_invalid_token(client):
    """Invalid token — should return 401"""
    response=await client.get("/api/v1/auth/me",
                        headers={"Authorization":"Bearer invalid-token"})
    assert response.status_code==401


# ============================================================
# ITEM TESTS
# ============================================================
@pytest.mark.asyncio
async def test_create_item_success(auth_client): # since this api requires token and is hardcoded in auth_client
    """Create item as authenticated user"""
    payload={
        "title":"Test Item",
        "description":"A test item",
        "price":29.99
    }
    response=await auth_client.post("/api/v1/items",json=payload)
    assert response.status_code==201
    data=response.json()
    assert data["title"]    == "Test Item"
    assert data["price"]    == 29.99
    assert data["owner_id"] == 1   # alice's ID

@pytest.mark.asyncio
async def test_create_item_unauthenticated(client):
    """Create item without auth — should fail"""
    response = await client.post(
        "/api/v1/items",
        json={"title": "Item", "price": 10.0}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_item_negative_price(auth_client):
    """Negative price — should fail validation"""
    response = await auth_client.post(
        "/api/v1/items",
        json={"title": "Item", "price": -5.0}
    )

    assert response.status_code == 422

@pytest.mark.asyncio
async def test_list_items_only_own(auth_client, user_client):
    """Users can only see their own items"""
    # Alice creates an item
    await auth_client.post(
        "/api/v1/items",
        json={"title": "Alice Item", "price": 10.0}
    )

    # Bob creates an item
    await user_client.post(
        "/api/v1/items",
        json={"title": "Bob Item", "price": 20.0}
    )

    # Alice should only see her item
    response = await auth_client.get("/api/v1/items")
    items = response.json()
    assert len(items) == 1
    assert items[0]["title"] == "Alice Item"

    # Bob should only see his item
    response = await user_client.get("/api/v1/items")
    items = response.json()
    assert len(items) == 1
    assert items[0]["title"] == "Bob Item"

@pytest.mark.asyncio
async def test_get_item_not_found(auth_client):
    """Get non-existent item — should return 404"""
    response = await auth_client.get("/api/v1/items/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_delete_item_success(auth_client):
    """Create then delete an item"""
    # Create
    create_res = await auth_client.post(
        "/api/v1/items",
        json={"title": "To Delete", "price": 5.0}
    )
    item_id = create_res.json()["id"]

    # Delete
    delete_res = await auth_client.delete(f"/api/v1/items/{item_id}")
    assert delete_res.status_code == 204

    # Verify gone
    get_res = await auth_client.get(f"/api/v1/items/{item_id}")
    assert get_res.status_code == 404

@pytest.mark.asyncio
async def test_admin_can_see_all_users(admin_client):
    """Admin endpoint accessible by admin"""
    response = await admin_client.get("/api/v1/admin/users")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_user_cannot_access_admin(user_client):
    """Regular user cannot access admin endpoint"""
    response = await user_client.get("/api/v1/admin/users")
    assert response.status_code == 403
    



