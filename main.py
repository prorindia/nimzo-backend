from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from uuid import uuid4

app = FastAPI(title="Nimzo Backend API")

# ======================
# ✅ CORS CONFIG (FIXED)
# ======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",        # ✅ ADDED
        "http://127.0.0.1:3001",        # ✅ ADDED
        "https://nimzo-frontend.vercel.app"
    ],
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

DEMO_USER = "demo_user_1"

# ======================
# HEALTH CHECK
# ======================
@app.get("/")
def root():
    return {"status": "Nimzo backend running 🚀"}

# ======================
# AUTH (OTP MOCK)
# ======================
@app.post("/api/auth/send-otp")
def send_otp(payload: dict):
    phone = payload.get("phone")
    if not phone:
        raise HTTPException(status_code=400, detail="Phone required")

    otp = "123456"
    OTP_STORE[phone] = otp
    return {"success": True, "message": "OTP sent (mock)", "otp": otp}

@app.post("/api/auth/verify-otp")
def verify_otp(payload: dict):
    phone = payload.get("phone")
    otp = payload.get("otp")

    if OTP_STORE.get(phone) != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    user_id = f"user_{phone}"
    USERS[user_id] = {"user_id": user_id, "phone": phone}
    return {"success": True, "user": USERS[user_id]}

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
# CART APIs (DEMO USER)
# ======================
@app.get("/api/cart")
def get_cart():
    cart = CARTS.setdefault(DEMO_USER, {"items": []})
    total = sum(i["price"] * i["quantity"] for i in cart["items"])
    item_count = sum(i["quantity"] for i in cart["items"])
    return {"items": cart["items"], "total": total, "item_count": item_count, "savings": 0}

@app.post("/api/cart/add")
def add_to_cart(payload: dict):
    product_id = payload.get("product_id")
    quantity = payload.get("quantity", 1)

    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    cart = CARTS.setdefault(DEMO_USER, {"items": []})
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
def update_cart(payload: dict):
    cart = CARTS.setdefault(DEMO_USER, {"items": []})
    for item in cart["items"]:
        if item["product_id"] == payload.get("product_id"):
            item["quantity"] = payload.get("quantity")
            return {"success": True}
    return {"success": True}

@app.delete("/api/cart/remove/{product_id}")
def remove_cart_item(product_id: int):
    cart = CARTS.setdefault(DEMO_USER, {"items": []})
    cart["items"] = [i for i in cart["items"] if i["product_id"] != product_id]
    return {"success": True}

@app.delete("/api/cart/clear")
def clear_cart():
    CARTS[DEMO_USER] = {"items": []}
    return {"success": True}

# ======================
# ORDER APIs
# ======================
@app.post("/api/orders/place")
def place_order(payload: dict):
    cart = CARTS.get(DEMO_USER)
    if not cart or not cart["items"]:
        raise HTTPException(status_code=400, detail="Cart is empty")

    if not payload.get("name") or not payload.get("phone") or not payload.get("address"):
        raise HTTPException(status_code=400, detail="Missing order details")

    order_id = str(uuid4())[:8]

    order = {
        "order_id": order_id,
        "user_id": DEMO_USER,
        "name": payload["name"],
        "phone": payload["phone"],
        "address": payload["address"],
        "items": cart["items"],
        "total": sum(i["price"] * i["quantity"] for i in cart["items"]),
        "payment_mode": "COD",
        "status": "PLACED"
    }

    ORDERS.append(order)
    CARTS[DEMO_USER] = {"items": []}
    return {"success": True, "order_id": order_id}

@app.get("/api/orders")
def get_orders():
    return [o for o in ORDERS if o["user_id"] == DEMO_USER]

# ======================
# ADMIN APIs
# ======================
@app.get("/api/admin/products")
def admin_get_products():
    return PRODUCTS

@app.get("/api/admin/orders")
def admin_get_orders():
    return ORDERS

VALID_ORDER_STATUSES = ["PLACED", "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED"]

@app.put("/api/admin/orders/{order_id}/status")
def admin_update_order_status(order_id: str, payload: dict):
    status = payload.get("status")
    if status not in VALID_ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    for order in ORDERS:
        if order["order_id"] == order_id:
            order["status"] = status
            return {"success": True, "order_id": order_id, "status": status}

    raise HTTPException(status_code=404, detail="Order not found")
