from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'flashmart-secret-key-2024')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Security
security = HTTPBearer()

app = FastAPI(title="FlashMart API")
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    is_admin: bool = False

class AddressCreate(BaseModel):
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = ""
    city: str
    state: str
    pincode: str
    is_default: bool = False

class AddressResponse(AddressCreate):
    id: str

class ProductCreate(BaseModel):
    name: str
    description: str
    price: float
    mrp: float
    unit: str
    category_id: str
    image_url: str
    stock: int = 100
    is_available: bool = True

class ProductResponse(BaseModel):
    id: str
    name: str
    description: str
    price: float
    mrp: float
    unit: str
    category_id: str
    category_name: Optional[str] = ""
    image_url: str
    stock: int
    is_available: bool
    discount_percent: int = 0

class CategoryCreate(BaseModel):
    name: str
    image_url: str
    display_order: int = 0

class CategoryResponse(BaseModel):
    id: str
    name: str
    image_url: str
    display_order: int

class CartItemAdd(BaseModel):
    product_id: str
    quantity: int = 1

class CartItemResponse(BaseModel):
    product_id: str
    name: str
    price: float
    mrp: float
    unit: str
    image_url: str
    quantity: int
    subtotal: float

class CartResponse(BaseModel):
    items: List[CartItemResponse]
    total: float
    item_count: int
    savings: float

class OrderCreate(BaseModel):
    address_id: str
    payment_method: str = "COD"

class OrderItemResponse(BaseModel):
    product_id: str
    name: str
    price: float
    quantity: int
    subtotal: float

class OrderResponse(BaseModel):
    id: str
    user_id: str
    items: List[OrderItemResponse]
    address: dict
    total: float
    status: str
    payment_method: str
    created_at: str
    estimated_delivery: str

class PincodeCheck(BaseModel):
    pincode: str

class PincodeResponse(BaseModel):
    pincode: str
    is_serviceable: bool
    delivery_time: str = ""
    message: str = ""

# ==================== AUTH HELPERS ====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str, is_admin: bool = False) -> str:
    payload = {
        "user_id": user_id,
        "is_admin": is_admin,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/register")
async def register(user_data: UserCreate):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    user_doc = {
        "id": user_id,
        "name": user_data.name,
        "email": user_data.email,
        "phone": user_data.phone,
        "password": hash_password(user_data.password),
        "is_admin": False,
        "addresses": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user_doc)
    
    # Create empty cart
    await db.carts.insert_one({"user_id": user_id, "items": []})
    
    token = create_token(user_id)
    return {
        "token": token,
        "user": UserResponse(id=user_id, name=user_data.name, email=user_data.email, phone=user_data.phone)
    }

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["id"], user.get("is_admin", False))
    return {
        "token": token,
        "user": UserResponse(
            id=user["id"],
            name=user["name"],
            email=user["email"],
            phone=user["phone"],
            is_admin=user.get("is_admin", False)
        )
    }

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        phone=user["phone"],
        is_admin=user.get("is_admin", False)
    )

# ==================== ADDRESS ROUTES ====================

@api_router.get("/addresses", response_model=List[AddressResponse])
async def get_addresses(user: dict = Depends(get_current_user)):
    return user.get("addresses", [])

@api_router.post("/addresses", response_model=AddressResponse)
async def add_address(address: AddressCreate, user: dict = Depends(get_current_user)):
    address_id = str(uuid.uuid4())
    address_doc = {**address.model_dump(), "id": address_id}
    
    # If this is the first address or marked as default, set others to non-default
    if address.is_default or len(user.get("addresses", [])) == 0:
        address_doc["is_default"] = True
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"addresses.$[].is_default": False}}
        )
    
    await db.users.update_one(
        {"id": user["id"]},
        {"$push": {"addresses": address_doc}}
    )
    return AddressResponse(**address_doc)

@api_router.delete("/addresses/{address_id}")
async def delete_address(address_id: str, user: dict = Depends(get_current_user)):
    await db.users.update_one(
        {"id": user["id"]},
        {"$pull": {"addresses": {"id": address_id}}}
    )
    return {"message": "Address deleted"}

# ==================== CATEGORY ROUTES ====================

@api_router.get("/categories", response_model=List[CategoryResponse])
async def get_categories():
    categories = await db.categories.find({}, {"_id": 0}).sort("display_order", 1).to_list(100)
    return categories

@api_router.post("/admin/categories", response_model=CategoryResponse)
async def create_category(category: CategoryCreate, user: dict = Depends(get_admin_user)):
    category_id = str(uuid.uuid4())
    category_doc = {**category.model_dump(), "id": category_id}
    await db.categories.insert_one(category_doc)
    return CategoryResponse(**category_doc)

# ==================== PRODUCT ROUTES ====================

@api_router.get("/products", response_model=List[ProductResponse])
async def get_products(
    category_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50
):
    query = {"is_available": True}
    if category_id:
        query["category_id"] = category_id
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    
    products = await db.products.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    # Add category names
    categories = {c["id"]: c["name"] for c in await db.categories.find({}, {"_id": 0}).to_list(100)}
    
    result = []
    for p in products:
        discount = int(((p["mrp"] - p["price"]) / p["mrp"]) * 100) if p["mrp"] > p["price"] else 0
        result.append(ProductResponse(
            **p,
            category_name=categories.get(p["category_id"], ""),
            discount_percent=discount
        ))
    return result

@api_router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    category = await db.categories.find_one({"id": product["category_id"]}, {"_id": 0})
    discount = int(((product["mrp"] - product["price"]) / product["mrp"]) * 100) if product["mrp"] > product["price"] else 0
    
    return ProductResponse(
        **product,
        category_name=category["name"] if category else "",
        discount_percent=discount
    )

@api_router.post("/admin/products", response_model=ProductResponse)
async def create_product(product: ProductCreate, user: dict = Depends(get_admin_user)):
    product_id = str(uuid.uuid4())
    product_doc = {**product.model_dump(), "id": product_id}
    await db.products.insert_one(product_doc)
    
    category = await db.categories.find_one({"id": product.category_id}, {"_id": 0})
    discount = int(((product.mrp - product.price) / product.mrp) * 100) if product.mrp > product.price else 0
    
    return ProductResponse(
        **product_doc,
        category_name=category["name"] if category else "",
        discount_percent=discount
    )

@api_router.put("/admin/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: str, product: ProductCreate, user: dict = Depends(get_admin_user)):
    result = await db.products.update_one(
        {"id": product_id},
        {"$set": product.model_dump()}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    
    updated = await db.products.find_one({"id": product_id}, {"_id": 0})
    category = await db.categories.find_one({"id": updated["category_id"]}, {"_id": 0})
    discount = int(((updated["mrp"] - updated["price"]) / updated["mrp"]) * 100) if updated["mrp"] > updated["price"] else 0
    
    return ProductResponse(
        **updated,
        category_name=category["name"] if category else "",
        discount_percent=discount
    )

@api_router.delete("/admin/products/{product_id}")
async def delete_product(product_id: str, user: dict = Depends(get_admin_user)):
    await db.products.delete_one({"id": product_id})
    return {"message": "Product deleted"}

# ==================== CART ROUTES ====================

@api_router.get("/cart", response_model=CartResponse)
async def get_cart(user: dict = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": user["id"]}, {"_id": 0})
    if not cart:
        cart = {"user_id": user["id"], "items": []}
        await db.carts.insert_one(cart)
    
    items = []
    total = 0
    savings = 0
    
    for item in cart.get("items", []):
        product = await db.products.find_one({"id": item["product_id"]}, {"_id": 0})
        if product:
            subtotal = product["price"] * item["quantity"]
            mrp_total = product["mrp"] * item["quantity"]
            items.append(CartItemResponse(
                product_id=product["id"],
                name=product["name"],
                price=product["price"],
                mrp=product["mrp"],
                unit=product["unit"],
                image_url=product["image_url"],
                quantity=item["quantity"],
                subtotal=subtotal
            ))
            total += subtotal
            savings += (mrp_total - subtotal)
    
    return CartResponse(items=items, total=total, item_count=len(items), savings=savings)

@api_router.post("/cart/add")
async def add_to_cart(item: CartItemAdd, user: dict = Depends(get_current_user)):
    product = await db.products.find_one({"id": item.product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    cart = await db.carts.find_one({"user_id": user["id"]})
    if not cart:
        await db.carts.insert_one({"user_id": user["id"], "items": []})
    
    # Check if item already in cart
    existing = await db.carts.find_one({
        "user_id": user["id"],
        "items.product_id": item.product_id
    })
    
    if existing:
        await db.carts.update_one(
            {"user_id": user["id"], "items.product_id": item.product_id},
            {"$inc": {"items.$.quantity": item.quantity}}
        )
    else:
        await db.carts.update_one(
            {"user_id": user["id"]},
            {"$push": {"items": {"product_id": item.product_id, "quantity": item.quantity}}}
        )
    
    return {"message": "Added to cart"}

@api_router.put("/cart/update")
async def update_cart_item(item: CartItemAdd, user: dict = Depends(get_current_user)):
    if item.quantity <= 0:
        await db.carts.update_one(
            {"user_id": user["id"]},
            {"$pull": {"items": {"product_id": item.product_id}}}
        )
    else:
        await db.carts.update_one(
            {"user_id": user["id"], "items.product_id": item.product_id},
            {"$set": {"items.$.quantity": item.quantity}}
        )
    return {"message": "Cart updated"}

@api_router.delete("/cart/remove/{product_id}")
async def remove_from_cart(product_id: str, user: dict = Depends(get_current_user)):
    await db.carts.update_one(
        {"user_id": user["id"]},
        {"$pull": {"items": {"product_id": product_id}}}
    )
    return {"message": "Removed from cart"}

@api_router.delete("/cart/clear")
async def clear_cart(user: dict = Depends(get_current_user)):
    await db.carts.update_one(
        {"user_id": user["id"]},
        {"$set": {"items": []}}
    )
    return {"message": "Cart cleared"}

# ==================== ORDER ROUTES ====================

@api_router.post("/orders", response_model=OrderResponse)
async def create_order(order_data: OrderCreate, user: dict = Depends(get_current_user)):
    # Get cart
    cart = await db.carts.find_one({"user_id": user["id"]}, {"_id": 0})
    if not cart or not cart.get("items"):
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    # Get address
    address = None
    for addr in user.get("addresses", []):
        if addr["id"] == order_data.address_id:
            address = addr
            break
    
    if not address:
        raise HTTPException(status_code=400, detail="Address not found")
    
    # Build order items
    order_items = []
    total = 0
    
    for item in cart["items"]:
        product = await db.products.find_one({"id": item["product_id"]}, {"_id": 0})
        if product:
            subtotal = product["price"] * item["quantity"]
            order_items.append({
                "product_id": product["id"],
                "name": product["name"],
                "price": product["price"],
                "quantity": item["quantity"],
                "subtotal": subtotal
            })
            total += subtotal
    
    order_id = str(uuid.uuid4())[:8].upper()
    now = datetime.now(timezone.utc)
    estimated_delivery = now + timedelta(minutes=15)
    
    order_doc = {
        "id": order_id,
        "user_id": user["id"],
        "items": order_items,
        "address": {
            "full_name": address["full_name"],
            "phone": address["phone"],
            "address_line1": address["address_line1"],
            "address_line2": address.get("address_line2", ""),
            "city": address["city"],
            "state": address["state"],
            "pincode": address["pincode"]
        },
        "total": total,
        "status": "confirmed",
        "payment_method": order_data.payment_method,
        "created_at": now.isoformat(),
        "estimated_delivery": estimated_delivery.isoformat()
    }
    
    await db.orders.insert_one(order_doc)
    
    # Clear cart
    await db.carts.update_one({"user_id": user["id"]}, {"$set": {"items": []}})
    
    return OrderResponse(**order_doc)

@api_router.get("/orders", response_model=List[OrderResponse])
async def get_orders(user: dict = Depends(get_current_user)):
    orders = await db.orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return orders

@api_router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id, "user_id": user["id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

# ==================== ADMIN ORDER ROUTES ====================

@api_router.get("/admin/orders", response_model=List[OrderResponse])
async def get_all_orders(user: dict = Depends(get_admin_user)):
    orders = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return orders

@api_router.put("/admin/orders/{order_id}/status")
async def update_order_status(order_id: str, status: str, user: dict = Depends(get_admin_user)):
    valid_statuses = ["confirmed", "preparing", "out_for_delivery", "delivered", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    result = await db.orders.update_one({"id": order_id}, {"$set": {"status": status}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": f"Order status updated to {status}"}

# ==================== PINCODE ROUTES ====================

@api_router.post("/pincode/check", response_model=PincodeResponse)
async def check_pincode(data: PincodeCheck):
    pincode = await db.pincodes.find_one({"pincode": data.pincode}, {"_id": 0})
    if pincode and pincode.get("is_serviceable"):
        return PincodeResponse(
            pincode=data.pincode,
            is_serviceable=True,
            delivery_time="10-15 mins",
            message="Yay! We deliver to your area"
        )
    return PincodeResponse(
        pincode=data.pincode,
        is_serviceable=False,
        message="Sorry, we don't deliver to this pincode yet"
    )

# ==================== SEED DATA ROUTE ====================

@api_router.post("/admin/seed")
async def seed_database():
    # Check if already seeded
    existing_products = await db.products.count_documents({})
    if existing_products > 0:
        return {"message": "Database already seeded", "products": existing_products}
    
    # Create categories
    categories = [
        {"id": "cat-fruits", "name": "Fruits", "image_url": "https://images.pexels.com/photos/1300975/pexels-photo-1300975.jpeg", "display_order": 1},
        {"id": "cat-vegetables", "name": "Vegetables", "image_url": "https://images.pexels.com/photos/5429051/pexels-photo-5429051.png", "display_order": 2},
        {"id": "cat-dairy", "name": "Dairy & Bread", "image_url": "https://images.pexels.com/photos/5953674/pexels-photo-5953674.jpeg", "display_order": 3},
        {"id": "cat-staples", "name": "Staples", "image_url": "https://images.pexels.com/photos/6707559/pexels-photo-6707559.jpeg", "display_order": 4},
        {"id": "cat-snacks", "name": "Snacks", "image_url": "https://images.pexels.com/photos/8064390/pexels-photo-8064390.jpeg", "display_order": 5},
        {"id": "cat-beverages", "name": "Beverages", "image_url": "https://images.pexels.com/photos/1292294/pexels-photo-1292294.jpeg", "display_order": 6},
        {"id": "cat-personal", "name": "Personal Care", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "display_order": 7}
    ]
    
    await db.categories.insert_many(categories)
    
    # Create 100 products
    products = [
        # Fruits (15)
        {"id": str(uuid.uuid4()), "name": "Banana (Robusta)", "description": "Fresh yellow bananas", "price": 45, "mrp": 50, "unit": "12 pcs", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/1093038/pexels-photo-1093038.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Apple (Shimla)", "description": "Fresh red apples from Shimla", "price": 180, "mrp": 200, "unit": "1 kg", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/102104/pexels-photo-102104.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Orange (Nagpur)", "description": "Sweet Nagpur oranges", "price": 85, "mrp": 100, "unit": "1 kg", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/207085/pexels-photo-207085.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Pomegranate", "description": "Ruby red pomegranates", "price": 220, "mrp": 250, "unit": "1 kg", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/65256/pomegranate-open-cores-fruit-65256.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Grapes (Green)", "description": "Seedless green grapes", "price": 75, "mrp": 90, "unit": "500 g", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/708777/pexels-photo-708777.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Mango (Alphonso)", "description": "Premium Alphonso mangoes", "price": 450, "mrp": 500, "unit": "1 kg", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/918643/pexels-photo-918643.jpeg", "stock": 50, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Papaya", "description": "Fresh ripe papaya", "price": 55, "mrp": 65, "unit": "1 pc", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/5945569/pexels-photo-5945569.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Watermelon", "description": "Sweet and juicy watermelon", "price": 45, "mrp": 55, "unit": "1 kg", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/1313267/pexels-photo-1313267.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Guava", "description": "Fresh green guavas", "price": 60, "mrp": 70, "unit": "500 g", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/3746517/pexels-photo-3746517.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Pineapple", "description": "Ripe and sweet pineapple", "price": 65, "mrp": 80, "unit": "1 pc", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/947879/pexels-photo-947879.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Kiwi", "description": "Imported green kiwi", "price": 120, "mrp": 150, "unit": "3 pcs", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/51312/kiwi-fruit-vitamins-healthy-eating-51312.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Strawberry", "description": "Fresh strawberries", "price": 150, "mrp": 180, "unit": "200 g", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/46174/strawberries-berries-fruit-freshness-46174.jpeg", "stock": 60, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Chikoo (Sapota)", "description": "Sweet brown chikoo", "price": 80, "mrp": 95, "unit": "500 g", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/5945748/pexels-photo-5945748.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Sweet Lime (Mosambi)", "description": "Fresh mosambi", "price": 70, "mrp": 85, "unit": "1 kg", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/1414110/pexels-photo-1414110.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Pear", "description": "Green imported pears", "price": 160, "mrp": 190, "unit": "500 g", "category_id": "cat-fruits", "image_url": "https://images.pexels.com/photos/568471/pexels-photo-568471.jpeg", "stock": 80, "is_available": True},
        
        # Vegetables (20)
        {"id": str(uuid.uuid4()), "name": "Onion", "description": "Fresh red onions", "price": 35, "mrp": 40, "unit": "1 kg", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/175414/pexels-photo-175414.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Tomato", "description": "Fresh red tomatoes", "price": 40, "mrp": 45, "unit": "1 kg", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/1327838/pexels-photo-1327838.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Potato", "description": "Fresh potatoes", "price": 30, "mrp": 35, "unit": "1 kg", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/144248/potatoes-vegetables-erdfrucht-bio-144248.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Green Chilli", "description": "Fresh green chillies", "price": 25, "mrp": 30, "unit": "250 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/4198370/pexels-photo-4198370.jpeg", "stock": 150, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Coriander", "description": "Fresh coriander leaves", "price": 15, "mrp": 20, "unit": "100 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/6087521/pexels-photo-6087521.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Ginger", "description": "Fresh ginger", "price": 80, "mrp": 100, "unit": "250 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/161556/ginger-plant-asia-rhizome-161556.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Garlic", "description": "Fresh garlic bulbs", "price": 60, "mrp": 75, "unit": "250 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/1392585/pexels-photo-1392585.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Capsicum (Green)", "description": "Fresh green capsicum", "price": 45, "mrp": 55, "unit": "250 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/128536/pexels-photo-128536.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Carrot", "description": "Fresh orange carrots", "price": 50, "mrp": 60, "unit": "500 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/143133/pexels-photo-143133.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Cauliflower", "description": "Fresh cauliflower", "price": 40, "mrp": 50, "unit": "1 pc", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/6316515/pexels-photo-6316515.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Cabbage", "description": "Fresh green cabbage", "price": 35, "mrp": 45, "unit": "1 pc", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/2518893/pexels-photo-2518893.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Brinjal (Baingan)", "description": "Fresh purple brinjal", "price": 40, "mrp": 50, "unit": "500 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/5529576/pexels-photo-5529576.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Lady Finger (Bhindi)", "description": "Fresh okra", "price": 55, "mrp": 65, "unit": "500 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/3650647/pexels-photo-3650647.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Spinach (Palak)", "description": "Fresh spinach leaves", "price": 25, "mrp": 30, "unit": "250 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/2325843/pexels-photo-2325843.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Methi (Fenugreek)", "description": "Fresh fenugreek leaves", "price": 20, "mrp": 25, "unit": "250 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/6087522/pexels-photo-6087522.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Cucumber", "description": "Fresh green cucumber", "price": 30, "mrp": 40, "unit": "500 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/2329440/pexels-photo-2329440.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Bottle Gourd (Lauki)", "description": "Fresh bottle gourd", "price": 35, "mrp": 45, "unit": "1 pc", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/7195134/pexels-photo-7195134.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Bitter Gourd (Karela)", "description": "Fresh bitter gourd", "price": 45, "mrp": 55, "unit": "500 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/5945699/pexels-photo-5945699.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Peas (Matar)", "description": "Fresh green peas", "price": 80, "mrp": 100, "unit": "500 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/255469/pexels-photo-255469.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Lemon", "description": "Fresh lemons", "price": 45, "mrp": 55, "unit": "250 g", "category_id": "cat-vegetables", "image_url": "https://images.pexels.com/photos/1414110/pexels-photo-1414110.jpeg", "stock": 100, "is_available": True},
        
        # Dairy (15)
        {"id": str(uuid.uuid4()), "name": "Amul Toned Milk", "description": "Fresh toned milk", "price": 28, "mrp": 30, "unit": "500 ml", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/248412/pexels-photo-248412.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Amul Full Cream Milk", "description": "Rich full cream milk", "price": 35, "mrp": 38, "unit": "500 ml", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/248412/pexels-photo-248412.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Amul Butter", "description": "Creamy salted butter", "price": 58, "mrp": 62, "unit": "100 g", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/531334/pexels-photo-531334.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Paneer", "description": "Fresh cottage cheese", "price": 95, "mrp": 110, "unit": "200 g", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/4087607/pexels-photo-4087607.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Dahi (Curd)", "description": "Fresh set curd", "price": 35, "mrp": 40, "unit": "400 g", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/3742767/pexels-photo-3742767.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Cheese Slices", "description": "Processed cheese slices", "price": 85, "mrp": 95, "unit": "200 g", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/821365/pexels-photo-821365.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Fresh Cream", "description": "Amul fresh cream", "price": 45, "mrp": 50, "unit": "200 ml", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/3321585/pexels-photo-3321585.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Eggs (White)", "description": "Farm fresh white eggs", "price": 75, "mrp": 85, "unit": "6 pcs", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/162712/egg-white-food-protein-162712.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Brown Eggs", "description": "Premium brown eggs", "price": 95, "mrp": 110, "unit": "6 pcs", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/162712/egg-white-food-protein-162712.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "White Bread", "description": "Fresh white bread", "price": 40, "mrp": 45, "unit": "400 g", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/1775043/pexels-photo-1775043.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Brown Bread", "description": "Whole wheat bread", "price": 50, "mrp": 55, "unit": "400 g", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/1775043/pexels-photo-1775043.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Pav", "description": "Fresh soft pav", "price": 30, "mrp": 35, "unit": "8 pcs", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/1775043/pexels-photo-1775043.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Lassi (Sweet)", "description": "Amul sweet lassi", "price": 25, "mrp": 30, "unit": "200 ml", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/3742767/pexels-photo-3742767.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Buttermilk (Chaas)", "description": "Fresh buttermilk", "price": 20, "mrp": 25, "unit": "200 ml", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/3742767/pexels-photo-3742767.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Ghee", "description": "Pure desi ghee", "price": 280, "mrp": 320, "unit": "500 ml", "category_id": "cat-dairy", "image_url": "https://images.pexels.com/photos/5953674/pexels-photo-5953674.jpeg", "stock": 60, "is_available": True},
        
        # Staples (15)
        {"id": str(uuid.uuid4()), "name": "Basmati Rice", "description": "Premium basmati rice", "price": 180, "mrp": 210, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/4110251/pexels-photo-4110251.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Wheat Flour (Atta)", "description": "Whole wheat flour", "price": 55, "mrp": 65, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/6707559/pexels-photo-6707559.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Toor Dal", "description": "Split pigeon peas", "price": 140, "mrp": 160, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Chana Dal", "description": "Bengal gram dal", "price": 95, "mrp": 110, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Moong Dal", "description": "Yellow moong dal", "price": 130, "mrp": 150, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Masoor Dal", "description": "Red lentils", "price": 110, "mrp": 130, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Sugar", "description": "White refined sugar", "price": 48, "mrp": 55, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/2523650/pexels-photo-2523650.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Salt", "description": "Iodized table salt", "price": 22, "mrp": 25, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/2523650/pexels-photo-2523650.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Sunflower Oil", "description": "Refined sunflower oil", "price": 160, "mrp": 180, "unit": "1 L", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/33783/olive-oil-salad-dressing-cooking-olive.jpg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Mustard Oil", "description": "Pure mustard oil", "price": 180, "mrp": 200, "unit": "1 L", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/33783/olive-oil-salad-dressing-cooking-olive.jpg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Rajma", "description": "Red kidney beans", "price": 140, "mrp": 165, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Chickpeas (Chole)", "description": "White chickpeas", "price": 120, "mrp": 140, "unit": "1 kg", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/8438918/pexels-photo-8438918.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Poha", "description": "Flattened rice", "price": 45, "mrp": 55, "unit": "500 g", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/4110251/pexels-photo-4110251.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Besan", "description": "Gram flour", "price": 65, "mrp": 75, "unit": "500 g", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/6707559/pexels-photo-6707559.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Sooji (Semolina)", "description": "Fine semolina", "price": 40, "mrp": 50, "unit": "500 g", "category_id": "cat-staples", "image_url": "https://images.pexels.com/photos/6707559/pexels-photo-6707559.jpeg", "stock": 100, "is_available": True},
        
        # Snacks (15)
        {"id": str(uuid.uuid4()), "name": "Lay's Classic Salted", "description": "Crispy potato chips", "price": 20, "mrp": 20, "unit": "52 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/568805/pexels-photo-568805.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Kurkure Masala Munch", "description": "Crunchy corn puffs", "price": 20, "mrp": 20, "unit": "75 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/568805/pexels-photo-568805.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Haldiram Bhujia", "description": "Classic namkeen", "price": 65, "mrp": 75, "unit": "200 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/8064390/pexels-photo-8064390.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Hide & Seek", "description": "Chocolate chip cookies", "price": 30, "mrp": 35, "unit": "100 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/230325/pexels-photo-230325.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Parle-G", "description": "Glucose biscuits", "price": 10, "mrp": 10, "unit": "80 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/230325/pexels-photo-230325.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Oreo Vanilla", "description": "Cream filled cookies", "price": 30, "mrp": 35, "unit": "120 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/230325/pexels-photo-230325.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Monaco Salted", "description": "Salted crackers", "price": 30, "mrp": 35, "unit": "200 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/568805/pexels-photo-568805.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Maggi Noodles", "description": "2 minute noodles", "price": 14, "mrp": 14, "unit": "70 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/2347311/pexels-photo-2347311.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Yippee Noodles", "description": "Magic masala noodles", "price": 12, "mrp": 12, "unit": "70 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/2347311/pexels-photo-2347311.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Pringles Original", "description": "Stacked potato crisps", "price": 99, "mrp": 110, "unit": "107 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/568805/pexels-photo-568805.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Bourbon Biscuit", "description": "Chocolate cream biscuit", "price": 25, "mrp": 30, "unit": "150 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/230325/pexels-photo-230325.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Aloo Bhujia", "description": "Spicy potato sev", "price": 55, "mrp": 65, "unit": "200 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/8064390/pexels-photo-8064390.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Marie Gold", "description": "Light tea biscuits", "price": 25, "mrp": 28, "unit": "200 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/230325/pexels-photo-230325.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Jim Jam", "description": "Jam filled biscuits", "price": 20, "mrp": 25, "unit": "100 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/230325/pexels-photo-230325.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Dark Fantasy", "description": "Choco fills", "price": 40, "mrp": 45, "unit": "75 g", "category_id": "cat-snacks", "image_url": "https://images.pexels.com/photos/230325/pexels-photo-230325.jpeg", "stock": 100, "is_available": True},
        
        # Beverages (10)
        {"id": str(uuid.uuid4()), "name": "Coca-Cola", "description": "Carbonated soft drink", "price": 40, "mrp": 45, "unit": "750 ml", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/50593/coca-cola-cold-drink-soft-drink-coke-50593.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Pepsi", "description": "Carbonated soft drink", "price": 40, "mrp": 45, "unit": "750 ml", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/50593/coca-cola-cold-drink-soft-drink-coke-50593.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Sprite", "description": "Lemon lime soda", "price": 40, "mrp": 45, "unit": "750 ml", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/50593/coca-cola-cold-drink-soft-drink-coke-50593.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Thums Up", "description": "Strong cola drink", "price": 40, "mrp": 45, "unit": "750 ml", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/50593/coca-cola-cold-drink-soft-drink-coke-50593.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Real Mango Juice", "description": "100% mango juice", "price": 50, "mrp": 55, "unit": "200 ml", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/1292294/pexels-photo-1292294.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Tropicana Orange", "description": "Orange juice", "price": 50, "mrp": 55, "unit": "200 ml", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/1292294/pexels-photo-1292294.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Bisleri Water", "description": "Packaged drinking water", "price": 22, "mrp": 25, "unit": "1 L", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/327090/pexels-photo-327090.jpeg", "stock": 200, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Red Bull", "description": "Energy drink", "price": 115, "mrp": 125, "unit": "250 ml", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/1292294/pexels-photo-1292294.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Tata Tea Gold", "description": "Premium tea powder", "price": 180, "mrp": 200, "unit": "500 g", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/1417945/pexels-photo-1417945.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Nescafe Classic", "description": "Instant coffee", "price": 245, "mrp": 280, "unit": "100 g", "category_id": "cat-beverages", "image_url": "https://images.pexels.com/photos/312418/pexels-photo-312418.jpeg", "stock": 100, "is_available": True},
        
        # Personal Care (10)
        {"id": str(uuid.uuid4()), "name": "Colgate Toothpaste", "description": "Cavity protection", "price": 55, "mrp": 65, "unit": "100 g", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Dove Soap", "description": "Moisturizing soap", "price": 52, "mrp": 60, "unit": "100 g", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Dettol Handwash", "description": "Antibacterial handwash", "price": 75, "mrp": 85, "unit": "200 ml", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Head & Shoulders", "description": "Anti-dandruff shampoo", "price": 185, "mrp": 210, "unit": "180 ml", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Lifebuoy Soap", "description": "Germ protection soap", "price": 35, "mrp": 40, "unit": "100 g", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Nivea Body Lotion", "description": "Moisturizing lotion", "price": 180, "mrp": 210, "unit": "200 ml", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 80, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Whisper Ultra", "description": "Sanitary pads", "price": 135, "mrp": 150, "unit": "8 pcs", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Gillette Razor", "description": "Disposable razor", "price": 65, "mrp": 75, "unit": "2 pcs", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Parachute Coconut Oil", "description": "Pure coconut oil", "price": 95, "mrp": 110, "unit": "200 ml", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 100, "is_available": True},
        {"id": str(uuid.uuid4()), "name": "Vaseline Lotion", "description": "Intensive care lotion", "price": 160, "mrp": 185, "unit": "200 ml", "category_id": "cat-personal", "image_url": "https://images.pexels.com/photos/3735657/pexels-photo-3735657.jpeg", "stock": 80, "is_available": True},
    ]
    
    await db.products.insert_many(products)
    
    # Add serviceable pincodes (major Indian cities)
    pincodes = [
        {"pincode": "400001", "city": "Mumbai", "is_serviceable": True},
        {"pincode": "400002", "city": "Mumbai", "is_serviceable": True},
        {"pincode": "400050", "city": "Mumbai", "is_serviceable": True},
        {"pincode": "110001", "city": "Delhi", "is_serviceable": True},
        {"pincode": "110002", "city": "Delhi", "is_serviceable": True},
        {"pincode": "560001", "city": "Bangalore", "is_serviceable": True},
        {"pincode": "560034", "city": "Bangalore", "is_serviceable": True},
        {"pincode": "600001", "city": "Chennai", "is_serviceable": True},
        {"pincode": "500001", "city": "Hyderabad", "is_serviceable": True},
        {"pincode": "700001", "city": "Kolkata", "is_serviceable": True},
        {"pincode": "411001", "city": "Pune", "is_serviceable": True},
        {"pincode": "380001", "city": "Ahmedabad", "is_serviceable": True},
        {"pincode": "302001", "city": "Jaipur", "is_serviceable": True},
        {"pincode": "226001", "city": "Lucknow", "is_serviceable": True},
        {"pincode": "201301", "city": "Noida", "is_serviceable": True},
        {"pincode": "122001", "city": "Gurgaon", "is_serviceable": True},
    ]
    
    await db.pincodes.insert_many(pincodes)
    
    # Create admin user
    admin_id = str(uuid.uuid4())
    admin_doc = {
        "id": admin_id,
        "name": "Admin",
        "email": "admin@flashmart.com",
        "phone": "9999999999",
        "password": hash_password("admin123"),
        "is_admin": True,
        "addresses": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(admin_doc)
    await db.carts.insert_one({"user_id": admin_id, "items": []})
    
    return {"message": "Database seeded successfully", "products": len(products), "categories": len(categories)}

# ==================== MAIN APP ====================

@api_router.get("/")
async def root():
    return {"message": "FlashMart API", "version": "1.0"}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
