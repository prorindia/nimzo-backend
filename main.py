from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ✅ CORS CONFIGURATION
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",              # Local frontend
        "https://nimzo-frontend.vercel.app",  # Vercel frontend (future)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ TEST ROUTE
@app.get("/")
def root():
    return {"status": "NIMZO backend running"}

# ✅ SAMPLE API (example)
@app.get("/api/categories")
def get_categories():
    return [
        {"id": 1, "name": "Groceries"},
        {"id": 2, "name": "Fruits"},
        {"id": 3, "name": "Vegetables"},
    ]

@app.get("/api/products")
def get_products(limit: int = 20):
    return [
        {"id": 1, "name": "Aashirvaad Atta 5kg", "price": 350},
        {"id": 2, "name": "Amul Milk 500ml", "price": 28},
    ][:limit]
