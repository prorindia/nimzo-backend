from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

app = FastAPI(title="Nimzo Backend API")

# ======================
# CORS CONFIG
# ======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
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
    {
        "id": 1,
        "name": "Aashirvaad Atta 5kg",
        "price": 320,
        "category": "Groceries",
        "image": "https://via.placeholder.com/150",
        "in_stock": True,
    },
    {
        "id": 2,
        "name": "Amul Milk 500ml",
        "price": 28,
        "category": "Groceries",
        "image": "https://via.placeholder.com/150",
        "in_stock": True,
    },
    {
        "id": 3,
        "name": "Apple (1kg)",
        "price": 140,
        "category": "Fruits",
        "image": "https://via.placeholder.com/150",
        "in_stock": True,
    },
    {
        "id": 4,
        "name": "Tomato (1kg)",
        "price": 40,
        "category": "Vegetables",
        "image": "https://via.placeholder.com/150",
        "in_stock": False,
    },
]

# ======================
# HEALTH CHECK
# ======================
@app.get("/")
def root():
    return {"status": "Nimzo backend running 🚀"}

# ======================
# CATEGORIES API
# ======================
@app.get("/api/categories")
def get_categories():
    return CATEGORIES

# ======================
# PRODUCTS API
# ======================
@app.get("/api/products")
def get_products(
    category: Optional[str] = None,
    limit: int = 20
):
    data = PRODUCTS

    if category:
        data = [p for p in data if p["category"].lower() == category.lower()]

    return data[:limit]

# ======================
# PRODUCT DETAIL API
# ======================
@app.get("/api/products/{product_id}")
def get_product_by_id(product_id: int):
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    raise HTTPException(status_code=404, detail="Product not found")
