from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://nimzo-frontend.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------
# MOCK DATA
# ------------------------

categories = [
    {"id": 1, "name": "Groceries"},
    {"id": 2, "name": "Fruits"},
    {"id": 3, "name": "Vegetables"},
]

products = [
    {
        "id": 1,
        "name": "Aashirvaad Atta 5kg",
        "price": 320,
        "category": "Groceries",
        "image": "https://via.placeholder.com/150",
        "in_stock": True
    },
    {
        "id": 2,
        "name": "Amul Milk 500ml",
        "price": 28,
        "category": "Groceries",
        "image": "https://via.placeholder.com/150",
        "in_stock": True
    },
    {
        "id": 3,
        "name": "Apple (1kg)",
        "price": 140,
        "category": "Fruits",
        "image": "https://via.placeholder.com/150",
        "in_stock": True
    },
    {
        "id": 4,
        "name": "Tomato (1kg)",
        "price": 40,
        "category": "Vegetables",
        "image": "https://via.placeholder.com/150",
        "in_stock": False
    },
]

# ------------------------
# APIs
# ------------------------

@app.get("/")
def root():
    return {"message": "Nimzo Backend is Live 🚀"}

@app.get("/api/categories")
def get_categories():
    return categories

@app.get("/api/products")
def get_products(category: str | None = None):
    if category:
        return [p for p in products if p["category"] == category]
    return products

@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    for product in products:
        if product["id"] == product_id:
            return product
    raise HTTPException(status_code=404, detail="Product not found")
