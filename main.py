from fastapi import FastAPI
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

# ✅ ROOT CHECK
@app.get("/")
def root():
    return {"status": "Nimzo backend running"}

# ✅ CATEGORIES API
@app.get("/api/categories")
def get_categories():
    return [
        {"id": 1, "name": "Vegetables"},
        {"id": 2, "name": "Fruits"},
        {"id": 3, "name": "Dairy"}
    ]

# ✅ PRODUCTS API
@app.get("/api/products")
def get_products(limit: int = 20):
    products = [
        {"id": 1, "name": "Aashirvaad Atta 5kg", "price": 350},
        {"id": 2, "name": "Amul Milk 500ml", "price": 30},
        {"id": 3, "name": "Tata Salt 1kg", "price": 28},
        {"id": 4, "name": "Fortune Oil 1L", "price": 160},
    ]
    return products[:limit]
