# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.callback_flutter import router as callback_router
from app.api.search_flutter import router as search_router
from app.api.vision import router as vision_router
from app.auth.login import router as login_router
from app.auth.register import router as sign_up_router
from app.db.database import create_db_pool, close_db_pool
from app.core.firebase import init_firebase

from app.api.api_favourite import router as api_favourite
from app.api.api_basket import router as api_basket

@asynccontextmanager
async def lifespan(app: FastAPI):

    # --- DB ---
    try:
        await create_db_pool()
    except Exception as e:
        print(f"⚠️ Database not ready, continue without DB: {e}")

    # --- Firebase ---
    try:
        init_firebase()
        print("✅ Firebase initialized")
    except Exception as e:
        print(f"⚠️ Firebase skipped: {e}")

   

    print("🚀 App startup complete")
    yield

    # --- Shutdown ---
    try:
        await close_db_pool()
        print("🧹 Database pool closed")
    except Exception:
        pass

    print("🧹 App shutdown complete")


app = FastAPI(
    title="ABC SHOP API",
    version="1.5.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(callback_router, prefix="/api", tags=["Callback"])
app.include_router(search_router, prefix="/api", tags=["Search"])
app.include_router(login_router, prefix="/api", tags=["LogIn"])
app.include_router(sign_up_router, prefix="/api", tags=["SignUp"])
app.include_router(vision_router, prefix="/api", tags=["Vision"])
app.include_router(api_favourite, prefix="/api", tags=["Favourites"])
app.include_router(api_basket, prefix="/api", tags=["Baskets"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "Cat Shop API is running"}