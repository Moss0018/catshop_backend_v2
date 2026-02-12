# search_api.py - Backend API for Search System

from fastapi import APIRouter, HTTPException, Query
import asyncpg
from typing import Optional, List
from pydantic import BaseModel
from app.db.database import get_db_pool

from fastapi import APIRouter

router = APIRouter()



# ============================================================================
# Models
# ============================================================================

class SearchCategoryResponse(BaseModel):
    id: int
    name_en: str
    name_th: str
    category_type: str

class ClothingItemResponse(BaseModel):
    id: int
    image_url: str
    images: dict
    clothing_name: str
    description: str
    category: int
    category_name_en: Optional[str] = None
    category_name_th: Optional[str] = None
    size_category: str
    price: float
    discount_price: Optional[float] = None
    discount_percent: Optional[int] = None
    gender: int
    stock: int
    breed: str
    created_at: str

class PaginatedResponse(BaseModel):
    items: List[ClothingItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================================
# API Endpoints
# ============================================================================



@router.get("/search/autocomplete")
async def search_autocomplete(
    query: str = Query(..., min_length=1, description="Search query (minimum 1 characters)")
):
    """
    Autocomplete search suggestions from search_category table
    Returns matching categories based on name_en or name_th
    """
    try:
        pool = await get_db_pool()
        async with pool.acquire() as connection:
            sql = """
            SELECT 
                id,
                name_category,
                category_type
                FROM search_category
            WHERE 
            LOWER(name_category) LIKE LOWER($1)
            ORDER BY 
            CASE
                WHEN category_type = 'all' THEN 0
                WHEN category_type = 'season' THEN 1
                WHEN category_type = 'festival' THEN 2
                WHEN category_type = 'style' THEN 3
            ELSE 4
            END,
                name_category
                LIMIT 10;
            """
            
            search_pattern = f"%{query}%"
            rows = await connection.fetch(sql, search_pattern)
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/search/btn/outfit/{category_id}")
async def search_btn_outfit(
    category_id: int,
    gender: Optional[int] = Query(None, description="Gender filter (0=Unisex, 1=Male, 2=Female, 3=Kitten, None=All)")
):
    """
    Get clothing items by category_id and optional gender filter
    
    Parameters:
    - category_id: ID from search_category table (0-10)
    - gender: Optional filter (0=Unisex, 1=Male, 2=Female, 3=Kitten)
    
    Returns list of matching clothing items
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as connection:
    
            where_conditions = ["category_id = $1", "is_active = true"]
            params = [category_id]
            
            if gender is not None:
                where_conditions.append(f"gender = ${len(params) + 1}")
                params.append(gender)
            
            where_clause = " AND ".join(where_conditions)
            

            query = f"""
                SELECT 
                    id,
                    image_url,
                    images,
                    clothing_name,
                    description,
                    category,
                    size_category,
                    price,
                    discount_price,
                    CASE 
                        WHEN discount_price IS NOT NULL AND discount_price < price 
                        THEN ROUND(((price - discount_price) / price) * 100, 0)
                        ELSE NULL
                    END as discount_percent,
                    gender,
                    clothing_like,
                    clothing_seller,
                    stock,
                    breed,
                    category_id,
                    created_at
                FROM cat_clothing
                WHERE {where_clause}
                ORDER BY 
                    CASE 
                        WHEN gender = 0 THEN 0  -- Unisex first
                        WHEN gender = 1 THEN 1  -- Male
                        WHEN gender = 2 THEN 2  -- Female
                        WHEN gender = 3 THEN 3  -- Kitten
                        ELSE 4
                    END,
                    created_at DESC
            """
            
           
            rows = await connection.fetch(query, *params)
            print(f"✅ Found {len(rows)} items")
            
            if not rows:
                print("⚠️ Warning: No items found in database!")
                return []
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/search/clothing", response_model=PaginatedResponse)
async def search_clothing_page(
    category_id: Optional[int] = Query(None, description="Category ID from search_category"),
    gender: Optional[int] = Query(None, description="Gender filter (0=Unisex, 1=Male, 2=Female, 3=Kitten)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page")
):
    """
    Search clothing items with filtering and pagination
    - If category_id is provided: filter by category
    - If gender is provided: filter by gender
    - If both provided: combine filters
    - If neither: show all items
    """
    try:
        pool = await get_db_pool()
        async with pool.acquire() as connection:
            
            
            where_conditions = ["c.is_active = true"]
            params = []
            param_count = 1
            
            if category_id is not None:
                where_conditions.append(f"c.category_id = ${param_count}")
                params.append(category_id)
                param_count += 1
            
            if gender is not None:
                where_conditions.append(f"c.gender = ${param_count}")
                params.append(gender)
                param_count += 1
            
            where_clause = " AND ".join(where_conditions)
            
            count_sql = f"""
                SELECT COUNT(*) 
                FROM cat_clothing c
                WHERE {where_clause}
            """
            
            total_count = await connection.fetchval(count_sql, *params)
   
            offset = (page - 1) * page_size
            total_pages = (total_count + page_size - 1) // page_size
            
            items_sql = f"""
            SELECT 
                c.id,
                c.image_url,
                c.images,
                c.clothing_name,
                c.description,
                c.category_id,
                sc.name_en as category_name_en,
                sc.name_th as category_name_th,
                c.size_category,
                c.price,
                c.discount_price,
                CASE 
            WHEN c.discount_price IS NOT NULL AND c.discount_price < c.price 
            THEN ROUND(((c.price - c.discount_price) / c.price) * 100, 0)
            ELSE NULL
            END as discount_percent,
                c.gender,
                c.stock,
                c.breed,
                c.created_at
            FROM cat_clothing c
            LEFT JOIN search_category sc ON c.category_id = sc.id
            WHERE {where_clause}
            ORDER BY c.created_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
            """
            
            params.extend([page_size, offset])
            rows = await connection.fetch(items_sql, *params)
            
            items = [dict(row) for row in rows]
            
            return {
                "items": items,
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")