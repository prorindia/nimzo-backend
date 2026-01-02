from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from uuid import uuid4
from datetime import datetime, timedelta
from jose import jwt, JWTError

app = FastAPI(title="Nimzo Backend API")

# ======================
# JWT CONFIG
# ======================
SECRET_KEY = "nimzo-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ======================
# CORS CONFIG (DEBUG MODE)
# ======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # DEBUG ONLY
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# DUMMY DATA
# ======================
CATEGORIES = [
    {"id": 1, "name": "Groceries"},
    {"id": 2, "name": "Fruits"},
    {"id": 3, "name": "Vegetables"},
]

PRODUCTS = [
    {"id": 1, "name": "Aashirvaad Atta 5kg", "price": 320, "category": "Groceries", "image": "https://via.placeholder.com/150", "in_stock": True},
    {"id": 2, "name": "Amul Milk 500ml", "price": 28, "category": "Groceries", "image": "https://via.placeholder.com/150", "in_stock": True},
    {"id": 3, "name": "Apple (1kg)", "price": 140, "category": "Fruits", "image": "https://via.placeholder.com/150", "in_stock": True},
    {"id": 4, "name": "Tomato (1kg)", "price": 40, "category": "Vegetables", "image": "https://via.placeholder.com/150", "in_stock": False},
]

# ======================
# IN-MEMORY STORES
# ======================
CARTS = {}
ORDERS = []
USERS = {}
OTP_STORE = {}

# ======================
# JWT HELPERS
# ======================
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ✅ FIXED AUTH HEADER (ONLY REAL CHANGE)
def get_current_user(authorization: str = Header(None, alias="Authorization")):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization missing")
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"user_id": user_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ======================
# HEALTH
# ======================
@app.get("/")
def root():
    return {"status": "Nimzo backend running 🚀"}

@app.get("/ping")
def ping():
    return {"pong": True}

# ======================
# AUTH (OTP MOCK + JWT)
# ======================
@app.post("/api/auth/send-otp")
def send_otp(payload: dict):
    phone = payload.get("phone")
    if not phone:
        raise HTTPException(status_code=400, detail="Phone required")
    OTP_STORE[phone] = "123456"
    return {"success": True, "otp": "123456"}

@app.post("/api/auth/verify-otp")
def verify_otp(payload: dict):
    phone = payload.get("phone")
    otp = payload.get("otp")

    if OTP_STORE.get(phone) != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    USERS[phone] = {"user_id": phone, "phone": phone}
    token = create_access_token({"user_id": phone})

    return {"success": True, "access_token": token}

# ======================
# CATEGORIES & PRODUCTS
# ======================
@app.get("/api/categories")
def get_categories():
    return CATEGORIES

@app.get("/api/products")
def get_products(category: Optional[str] = None, limit: int = 20):
    data = PRODUCTS
    if category:
        data = [p for p in data if p["category"].lower() == category.lower()]
    return data[:limit]

@app.get("/api/products/{product_id}")
def get_product_by_id(product_id: int):
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    raise HTTPException(status_code=404, detail="Product not found")

# ======================
# CART APIs
# ======================
@app.get("/api/cart")
def get_cart(user=Depends(get_current_user)):
    user_id = user["user_id"]
    cart = CARTS.setdefault(user_id, {"items": []})
    total = sum(i["price"] * i["quantity"] for i in cart["items"])
    item_count = sum(i["quantity"] for i in cart["items"])
    return {"items": cart["items"], "total": total, "item_count": item_count, "savings": 0}

@app.post("/api/cart/add")
def add_to_cart(payload: dict, user=Depends(get_current_user)):
    user_id = user["user_id"]
    product_id = payload.get("product_id")
    quantity = payload.get("quantity", 1)

    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    cart = CARTS.setdefault(user_id, {"items": []})
    for item in cart["items"]:
        if item["product_id"] == product_id:
            item["quantity"] += quantity
            return {"success": True}

    cart["items"].append({
        "product_id": product_id,
        "name": product["name"],
        "price": product["price"],
        "image": product["image"],
        "quantity": quantity
    })
    return {"success": True}

@app.put("/api/cart/update")
def update_cart(payload: dict, user=Depends(get_current_user)):
    cart = CARTS.setdefault(user["user_id"], {"items": []})
    for item in cart["items"]:
        if item["product_id"] == payload.get("product_id"):
            item["quantity"] = payload.get("quantity")
    return {"success": True}

@app.delete("/api/cart/remove/{product_id}")
def remove_cart_item(product_id: int, user=Depends(get_current_user)):
    cart = CARTS.setdefault(user["user_id"], {"items": []})
    cart["items"] = [i for i in cart["items"] if i["product_id"] != product_id]
    return {"success": True}

@app.delete("/api/cart/clear")
def clear_cart(user=Depends(get_current_user)):
    CARTS[user["user_id"]] = {"items": []}
    return {"success": True}

# ======================
# ORDER APIs
# ======================
@app.post("/api/orders/place")
def place_order(payload: dict, user=Depends(get_current_user)):
    cart = CARTS.get(user["user_id"])
    if not cart or not cart["items"]:
        raise HTTPException(status_code=400, detail="Cart is empty")

    order_id = str(uuid4())[:8]
    order = {
        "order_id": order_id,
        "user_id": user["user_id"],
        "name": payload.get("name"),
        "phone": payload.get("phone"),
        "address": payload.get("address"),
        "items": cart["items"],
        "total": sum(i["price"] * i["quantity"] for i in cart["items"]),
        "status": "PLACED"
    }

    ORDERS.append(order)
    CARTS[user["user_id"]] = {"items": []}
    return {"success": True, "order_id": order_id}

@app.get("/api/orders")
def get_orders(user=Depends(get_current_user)):
    return [o for o in ORDERS if o["user_id"] == user["user_id"]]

# ======================
# ADMIN APIs
# ======================
@app.get("/api/admin/products")
def admin_get_products():
    return PRODUCTS

@app.get("/api/admin/orders")
def admin_get_orders():
    return ORDERS

@app.put("/api/admin/orders/{order_id}/status")
def admin_update_order_status(order_id: str, payload: dict):
    for order in ORDERS:
        if order["order_id"] == order_id:
            order["status"] = payload.get("status")
            return {"success": True}
    raise HTTPException(status_code=404, detail="Order not found")
