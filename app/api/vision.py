from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import requests
import os
from pathlib import Path
import uuid

from app.auth.dependencies import verify_firebase_token
from app.services.detect_cat import detect_cat
from app.services.analysis_cat import analyze_cat
from app.db.database import get_db_pool  
router = APIRouter()

# ============================================
# REQUEST SCHEMA
# ============================================
class AnalyzeCatRequest(BaseModel):
    """Schema สำหรับ request วิเคราะห์แมว"""
    image_url: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "image_url": "https://res.cloudinary.com/.../cat.jpg"
            }
        }



# ============================================
# ANALYZE CAT ENDPOINT
# ============================================
@router.post("/vision/analyze-cat", response_model=dict)
async def analyze_cat_endpoint(
    request: AnalyzeCatRequest,
    user: dict = Depends(verify_firebase_token)
):
    """
    🐱 **วิเคราะห์แมวจากรูปภาพและบันทึกลง DB**
    """
    
    try:
        # 🔐 ดึง firebase_uid จาก token
        firebase_uid = user.get("firebase_uid")
        
        if not firebase_uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Firebase token"
            )
        
        print(f"\n🔍 Starting analysis for user: {firebase_uid[:8]}***")
        print(f"📸 Image URL: {request.image_url}")
        
        # ========================================
        # STEP 1: Download Image
        # ========================================
        print("\n--- STEP 1: Downloading Image ---")
        
        try:
            response = requests.get(request.image_url, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to download image: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot download image: {str(e)}"
            )
        
        # สร้าง temp directory
        temp_dir = Path("/tmp/cat_images")
        temp_dir.mkdir(exist_ok=True)
        
        # สร้างชื่อไฟล์ชั่วคราว
        temp_filename = f"cat_{uuid.uuid4()}.jpg"
        temp_path = temp_dir / temp_filename
        
        # บันทึกรูปภาพ
        with open(temp_path, "wb") as f:
            f.write(response.content)
        
        print(f"✅ Image saved to: {temp_path}")
        print(f"📦 Image size: {len(response.content) / 1024:.2f} KB")
        
        try:
            # ========================================
            # STEP 2: Detect Cat (YOLO)
            # ========================================
            print("\n--- STEP 2: Detecting Cat with YOLO ---")
            
            detect_result = detect_cat(str(temp_path))
            
            print(f"🔍 Detection Result:")
            print(f"   - is_cat: {detect_result.get('is_cat')}")
            print(f"   - confidence: {detect_result.get('confidence')}")
            print(f"   - bounding_box: {detect_result.get('bounding_box')}")
            
            # ❌ ถ้าไม่พบแมว → หยุดทันที
            if not detect_result.get("is_cat"):
                print("❌ No cat detected in image")
                return {
                    "is_cat": False,
                    "confidence": detect_result.get("confidence", 0.0),
                    "message": "😿 ไม่พบแมวในภาพ กรุณาถ่ายรูปใหม่"
                }
            
            print("✅ Cat detected!")
            
            # ========================================
            # STEP 3: Analyze Cat Size
            # ========================================
            print("\n--- STEP 3: Analyzing Cat Size ---")
            
            bounding_box = detect_result["bounding_box"]
            
            analysis_result = analyze_cat(
                image_path=str(temp_path),
                bounding_box=bounding_box,
                firebase_uid=firebase_uid,
                cat_color=None,
                breed="unknown",
                age_category="adult"
            )
            
            print(f"📊 Analysis Result:")
            print(f"   - cat_color: {analysis_result.get('cat_color')}")
            print(f"   - weight_kg: {analysis_result.get('weight_kg')}")
            print(f"   - size_category: {analysis_result.get('size_category')}")
            
            # ========================================
            # 🔥 STEP 4: Save to Database (asyncpg)
            # ========================================
            print("\n--- STEP 4: Saving to Database ---")
            
            measurements = analysis_result.get('measurements', {})
            
            # Get DB pool
            pool = await get_db_pool()
            
            # Insert to database
            async with pool.acquire() as conn:
                cat_id = await conn.fetchval(
                    """
                    INSERT INTO cat (
                        firebase_uid, cat_color, breed, age,
                        weight, size_category,
                        chest_cm, neck_cm, waist_cm, 
                        body_length_cm, back_length_cm, leg_length_cm,
                        body_condition_score, body_condition, body_condition_description,
                        bmi, confidence, bounding_box,
                        posture, quality_flag,
                        image_url, thumbnail_url,
                        analysis_version, analysis_method,
                        detected_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27
                    ) RETURNING id
                    """,
                    firebase_uid,
                    analysis_result.get("cat_color", "Unknown"),  # name
                    analysis_result.get("breed"),  # breed
                    None,  # age
                    float(analysis_result.get("weight_kg", 0.0)),  # weight
                    analysis_result.get("size_category", "Unknown"),  # size_category
                    float(measurements.get("chest_cm", 0.0)),  # chest_cm
                    float(measurements.get("neck_cm")) if measurements.get("neck_cm") else None,  # neck_cm
                    float(measurements.get("waist_cm")) if measurements.get("waist_cm") else None,  # waist_cm
                    float(measurements.get("body_length_cm")) if measurements.get("body_length_cm") else None,  # body_length_cm
                    float(measurements.get("back_length_cm")) if measurements.get("back_length_cm") else None,  # back_length_cm
                    float(measurements.get("leg_length_cm")) if measurements.get("leg_length_cm") else None,  # leg_length_cm
                    analysis_result.get("body_condition_score"),  # body_condition_score
                    analysis_result.get("body_condition"),  # body_condition
                    analysis_result.get("body_condition_description"),  # body_condition_description
                    analysis_result.get("bmi"),  # bmi
                    float(detect_result.get("confidence", 0.0)),  # confidence
                    bounding_box,  # bounding_box (list)
                    analysis_result.get("posture"),  # posture
                    analysis_result.get("quality_flag"),  # quality_flag
                    request.image_url,  # image_url
                    None,  # thumbnail_url
                    analysis_result.get("analysis_version"),  # analysis_version
                    analysis_result.get("analysis_method"),  # analysis_method
                    datetime.utcnow(),  # detected_at
                    datetime.utcnow()   # updated_at
                )
            
            print(f"✅ Saved to database with ID: {cat_id}")
            
            # ========================================
            # STEP 5: Format Response for Flutter
            # ========================================
            print("\n--- STEP 5: Formatting Response ---")
            
            response_data = {
                # Detection info
                "is_cat": True,
                "confidence": float(detect_result.get("confidence", 0.0)),
                "message": "✅ พบแมวในภาพแล้ว!",
                
                # CatData fields
                "id": cat_id,  # 🔥 ID จาก DB
                "cat_color": analysis_result.get("cat_color", "Unknown"),
                "breed": analysis_result.get("breed"),
                "age": None,
                "weight": float(analysis_result.get("weight_kg", 0.0)),
                "size_category": analysis_result.get("size_category", "Unknown"),
                
                # Measurements
                "chest_cm": float(measurements.get("chest_cm", 0.0)),
                "neck_cm": float(measurements.get("neck_cm")) if measurements.get("neck_cm") else None,
                "body_length_cm": float(measurements.get("body_length_cm")) if measurements.get("body_length_cm") else None,
                
                # Additional info
                "bounding_box": bounding_box,
                "image_url": request.image_url,
                "thumbnail_url": None,
                "detected_at": datetime.utcnow().isoformat() + "Z",
                
                # Extra details
                "analysis_details": {
                    "posture": analysis_result.get("posture"),
                    "quality_flag": analysis_result.get("quality_flag"),
                    "body_condition": analysis_result.get("body_condition"),
                    "body_condition_score": analysis_result.get("body_condition_score"),
                    "bmi": analysis_result.get("bmi"),
                    "size_recommendation": analysis_result.get("size_recommendation"),
                    "all_measurements": measurements
                }
            }
            
            print("✅ Response formatted successfully")
            print(f"\n🎉 Analysis completed for user {firebase_uid[:8]}***")
            
            return response_data
            
        finally:
            # CLEANUP: ลบไฟล์ชั่วคราว
            if temp_path.exists():
                temp_path.unlink()
                print(f"🗑️ Cleaned up temp file: {temp_path}")
    
    except HTTPException:
        raise
    
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )