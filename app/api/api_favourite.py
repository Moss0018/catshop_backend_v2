from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
import asyncpg
from uuid import UUID

from app.db.database import get_db_pool

router = APIRouter()

# ============================================================================
# Pydantic Models
# ============================================================================

class FavouriteItem(BaseModel):
    user_id: int  # person_login_catshop.id
    clothing_uuid: str  # UUID as string

class PaginationRequest(BaseModel):
    user_id: int
    page: int = 1
    limit: int = 10

# ============================================================================
# GET: ดึงรายการโปรดทั้งหมดของ User
# ============================================================================

@router.get("/get/person-favourite/{user_id}")
async def get_person_favourite(user_id: int):
    """
    Get favourite list for a specific user
    
    Returns:
    - List of favourite items with full product details from cat_clothing
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as connection:
            query = """
                SELECT 
                    uf.id as favourite_id,
                    uf.user_id,
                    uf.clothing_uuid,
                    uf.created_at,
                    c.uuid,
                    c.clothing_name,
                    c.price,
                    c.discount_price,
                    c.stock,
                    c.image_url,
                    c.category,
                    c.size_category,
                    c.gender,
                    c.breed,
                    c.cat_color,
                    c.description,
                    c.images
                FROM user_favorites uf
                INNER JOIN cat_clothing c ON uf.clothing_uuid = c.uuid
                WHERE uf.user_id = $1
                ORDER BY uf.created_at DESC
            """
            rows = await connection.fetch(query, user_id)
            
            if not rows:
                return []
            
            result = []
            for row in rows:
                item = dict(row)
                # แปลง UUID เป็น string
                if item.get('uuid'):
                    item['uuid'] = str(item['uuid'])
                if item.get('clothing_uuid'):
                    item['clothing_uuid'] = str(item['clothing_uuid'])
                result.append(item)
            
            return result
            
    except asyncpg.PostgresError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ============================================================================
# GET: ดึงจำนวนรายการโปรดทั้งหมด
# ============================================================================

@router.get("/get/person-favourite/count/{user_id}")
async def get_favourite_count(user_id: int):
    """
    Get total count of favourite items for a user
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as connection:
            query = """
                SELECT COUNT(*) as total
                FROM user_favorites
                WHERE user_id = $1
            """
            result = await connection.fetchval(query, user_id)
            
            return {"user_id": user_id, "total": result}
            
    except asyncpg.PostgresError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ============================================================================
# POST: เพิ่มสินค้าเข้ารายการโปรด
# ============================================================================

@router.post("/post/person-favourite")
async def post_person_favourite(data: FavouriteItem):
    """
    Add an item to user's favourites
    
    Request Body:
    - user_id: int (person_login_catshop.id)
    - clothing_uuid: str (UUID from cat_clothing)
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as connection:
            # ตรวจสอบว่ามีอยู่แล้วหรือไม่
            check_query = """
                SELECT id FROM user_favorites
                WHERE user_id = $1 AND clothing_uuid = $2
            """
            existing = await connection.fetchval(
                check_query, 
                data.user_id, 
                UUID(data.clothing_uuid)
            )
            
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Item already in favourites"
                )
            
            # เพิ่มรายการใหม่
            insert_query = """
                INSERT INTO user_favorites (user_id, clothing_uuid)
                VALUES ($1, $2)
                RETURNING id, user_id, clothing_uuid, created_at
            """
            result = await connection.fetchrow(
                insert_query, 
                data.user_id, 
                UUID(data.clothing_uuid)
            )
            
            response = dict(result)
            # แปลง UUID เป็น string
            if response.get('clothing_uuid'):
                response['clothing_uuid'] = str(response['clothing_uuid'])
            
            return {
                "message": "Added to favourites successfully",
                "data": response
            }
            
    except HTTPException:
        raise
    except asyncpg.PostgresError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ============================================================================
# POST: ดึงรายการโปรดแบบ Pagination
# ============================================================================

@router.post("/post/page-favourite")
async def post_pagination_favourite(data: PaginationRequest):
    """
    Get paginated favourite list
    
    Request Body:
    - user_id: int
    - page: int (default: 1)
    - limit: int (default: 10)
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as connection:
            offset = (data.page - 1) * data.limit
            
            # ดึงข้อมูล
            query = """
                SELECT 
                    uf.id as favourite_id,
                    uf.user_id,
                    uf.clothing_uuid,
                    uf.created_at,
                    c.uuid,
                    c.clothing_name,
                    c.price,
                    c.discount_price,
                    c.stock,
                    c.image_url,
                    c.category,
                    c.size_category,
                    c.gender,
                    c.breed,
                    c.description
                FROM user_favorites uf
                INNER JOIN cat_clothing c ON uf.clothing_uuid = c.uuid
                WHERE uf.user_id = $1
                ORDER BY uf.created_at DESC
                LIMIT $2 OFFSET $3
            """
            rows = await connection.fetch(
                query, 
                data.user_id, 
                data.limit, 
                offset
            )
            
            # นับจำนวนทั้งหมด
            count_query = """
                SELECT COUNT(*) FROM user_favorites
                WHERE user_id = $1
            """
            total = await connection.fetchval(count_query, data.user_id)
            
            result = []
            for row in rows:
                item = dict(row)
                # แปลง UUID เป็น string
                if item.get('uuid'):
                    item['uuid'] = str(item['uuid'])
                if item.get('clothing_uuid'):
                    item['clothing_uuid'] = str(item['clothing_uuid'])
                result.append(item)
            
            return {
                "data": result,
                "pagination": {
                    "page": data.page,
                    "limit": data.limit,
                    "total": total,
                    "total_pages": (total + data.limit - 1) // data.limit
                }
            }
            
    except asyncpg.PostgresError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ============================================================================
# DELETE: ลบสินค้าออกจากรายการโปรด
# ============================================================================

@router.delete("/del/person-favourite")
async def del_person_favourite(
    user_id: int = Body(...), 
    clothing_uuid: str = Body(...)
):
    """
    Remove an item from user's favourites
    
    Request Body:
    - user_id: int
    - clothing_uuid: str (UUID)
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as connection:
            delete_query = """
                DELETE FROM user_favorites
                WHERE user_id = $1 AND clothing_uuid = $2
                RETURNING id
            """
            deleted_id = await connection.fetchval(
                delete_query, 
                user_id, 
                UUID(clothing_uuid)
            )
            
            if not deleted_id:
                raise HTTPException(
                    status_code=404,
                    detail="Favourite item not found"
                )
            
            return {
                "message": "Removed from favourites successfully",
                "deleted_id": deleted_id
            }
            
    except HTTPException:
        raise
    except asyncpg.PostgresError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ============================================================================
# GET: ตรวจสอบว่าสินค้าอยู่ใน Favourite หรือไม่
# ============================================================================

@router.get("/get/check-favourite/{user_id}/{clothing_uuid}")
async def check_favourite(user_id: int, clothing_uuid: str):
    """
    Check if an item is in user's favourites
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as connection:
            query = """
                SELECT id FROM user_favorites
                WHERE user_id = $1 AND clothing_uuid = $2
            """
            result = await connection.fetchval(query, user_id, UUID(clothing_uuid))
            
            return {
                "user_id": user_id,
                "clothing_uuid": clothing_uuid,
                "is_favourite": result is not None
            }
            
    except asyncpg.PostgresError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )