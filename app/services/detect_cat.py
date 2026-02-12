"""Cat Detect Service - Optimized for FastAPI + Flutter"""
from ultralytics import YOLO
import cv2
import numpy as np
from typing import Dict, Optional
from pathlib import Path


class CatDetector:
    """
    🐱 Cat Detector using YOLOv8
    
    Features:
    - Image quality validation
    - Multiple cat detection
    - Confidence threshold filtering
    - Singleton pattern for performance
    """
    
    def __init__(self, model_path: str = "yolov8n.pt"):
        """
        Initialize YOLO model
        
        Args:
            model_path: Path to YOLO weights (default: yolov8n.pt)
        """
        print(f"🔥 Loading YOLO model: {model_path}")
        try:
            self.model = YOLO(model_path)
            print("✅ YOLO model loaded successfully")
        except Exception as e:
            print(f"❌ Failed to load YOLO: {e}")
            raise RuntimeError(f"YOLO model initialization failed: {e}")
        
        # COCO dataset: class 15 = cat
        self.cat_class_id = 15
        
        # Default thresholds
        self.min_confidence = 0.5
        self.min_image_size = 100
        self.min_sharpness = 50  # Laplacian variance threshold
        self.min_brightness = 30
        self.max_brightness = 225

    def check_image_quality(self, image: np.ndarray) -> Dict:
        """
        ตรวจสอบคุณภาพรูปภาพ
        
        Args:
            image: OpenCV image (BGR format)
            
        Returns:
            {
                "is_valid": bool,
                "reason": str or None,
                "details": dict  # 🔥 เพิ่มรายละเอียด
            }
        """
        h, w = image.shape[:2]
        
        # 1. ตรวจสอบขนาด
        if w < self.min_image_size or h < self.min_image_size:
            return {
                "is_valid": False,
                "reason": f"รูปเล็กเกินไป (ขนาด: {w}x{h}, ต้องการอย่างน้อย {self.min_image_size}x{self.min_image_size})",
                "details": {"width": w, "height": h}
            }
        
        # 2. ตรวจสอบความคมชัด (Blur detection)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        if laplacian_var < self.min_sharpness:
            return {
                "is_valid": False,
                "reason": f"รูปเบลอ (ความคมชัด: {laplacian_var:.2f}, ต้องการ > {self.min_sharpness})",
                "details": {"sharpness": laplacian_var}
            }
        
        # 3. ตรวจสอบความสว่าง
        mean_brightness = np.mean(gray)
        
        if mean_brightness < self.min_brightness:
            return {
                "is_valid": False,
                "reason": f"รูปมืดเกินไป (ความสว่าง: {mean_brightness:.1f}, ต้องการ > {self.min_brightness})",
                "details": {"brightness": mean_brightness}
            }
        
        if mean_brightness > self.max_brightness:
            return {
                "is_valid": False,
                "reason": f"รูปสว่างเกินไป (ความสว่าง: {mean_brightness:.1f}, ต้องการ < {self.max_brightness})",
                "details": {"brightness": mean_brightness}
            }
        
        # ✅ รูปผ่านการตรวจสอบ
        return {
            "is_valid": True,
            "reason": None,
            "details": {
                "width": w,
                "height": h,
                "sharpness": laplacian_var,
                "brightness": mean_brightness
            }
        }

    def detect_cat(
        self, 
        image_path: str, 
        confidence_threshold: Optional[float] = None,
        return_all_cats: bool = False
    ) -> Dict:
        """
        ตรวจจับแมวในรูปภาพ
        
        Args:
            image_path: Path to image file
            confidence_threshold: Minimum confidence (default: 0.5)
            return_all_cats: If True, return all detected cats (default: False)
            
        Returns:
            {
                "is_cat": bool,
                "confidence": float,
                "bounding_box": [x1, y1, x2, y2] or None,
                "total_cats_detected": int,
                "all_cats": list (if return_all_cats=True),
                "image_quality": dict,
                "error": str or None
            }
        """
        
        if confidence_threshold is None:
            confidence_threshold = self.min_confidence
        
        try:
            # ========================================
            # STEP 1: Read Image
            # ========================================
            print(f"📸 Reading image: {image_path}")
            
            # ตรวจสอบว่าไฟล์มีอยู่จริง
            if not Path(image_path).exists():
                return {
                    "is_cat": False,
                    "confidence": 0.0,
                    "bounding_box": None,
                    "total_cats_detected": 0,
                    "error": f"ไม่พบไฟล์: {image_path}"
                }
            
            image = cv2.imread(image_path)
            
            if image is None:
                return {
                    "is_cat": False,
                    "confidence": 0.0,
                    "bounding_box": None,
                    "total_cats_detected": 0,
                    "error": "โหลดภาพไม่ได้ (ไฟล์อาจเสียหายหรือรูปแบบไม่ถูกต้อง)"
                }
            
            # ========================================
            # STEP 2: Check Image Quality
            # ========================================
            print("🔍 Checking image quality...")
            quality = self.check_image_quality(image)
            
            if not quality["is_valid"]:
                print(f"⚠️ Image quality issue: {quality['reason']}")
                return {
                    "is_cat": False,
                    "confidence": 0.0,
                    "bounding_box": None,
                    "total_cats_detected": 0,
                    "image_quality": quality,
                    "error": quality["reason"]
                }
            
            print(f"✅ Image quality OK: {quality['details']}")
            
            # ========================================
            # STEP 3: YOLO Detection
            # ========================================
            print(f"🤖 Running YOLO detection (confidence > {confidence_threshold})...")
            
            results = self.model(
                image, 
                conf=confidence_threshold, 
                verbose=False
            )
            
            # ========================================
            # STEP 4: Extract Cat Detections
            # ========================================
            cats = []
            
            for result in results:
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    
                    # Filter only cats
                    if class_id == self.cat_class_id:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        confidence = float(box.conf[0])
                        
                        cats.append({
                            "confidence": confidence,
                            "bbox": [int(x1), int(y1), int(x2), int(y2)],
                            "area": int((x2 - x1) * (y2 - y1))
                        })
            
            print(f"🐱 Found {len(cats)} cat(s)")
            
            # ========================================
            # STEP 5: Process Results
            # ========================================
            if not cats:
                return {
                    "is_cat": False,
                    "confidence": 0.0,
                    "bounding_box": None,
                    "total_cats_detected": 0,
                    "image_quality": quality,
                    "error": "ไม่พบแมวในรูปภาพ"
                }
            
            # เลือกแมวที่มี confidence สูงสุด
            best_cat = max(cats, key=lambda x: x["confidence"])
            
            print(f"✅ Best cat detected:")
            print(f"   - Confidence: {best_cat['confidence']:.2%}")
            print(f"   - Bounding box: {best_cat['bbox']}")
            print(f"   - Area: {best_cat['area']} pixels")
            
            result = {
                "is_cat": True,
                "confidence": round(best_cat["confidence"], 4),  # 🔥 4 ตำแหน่งทศนิยม
                "bounding_box": best_cat["bbox"],
                "total_cats_detected": len(cats),
                "image_quality": quality,
                "error": None
            }
            
            # ถ้าต้องการข้อมูลแมวทั้งหมด
            if return_all_cats and len(cats) > 1:
                result["all_cats"] = [
                    {
                        "confidence": round(cat["confidence"], 4),
                        "bounding_box": cat["bbox"],
                        "area": cat["area"]
                    }
                    for cat in sorted(cats, key=lambda x: x["confidence"], reverse=True)
                ]
            
            return result
        
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            
            print(f"❌ detect_cat error: {e}")
            print(error_trace)
            
            return {
                "is_cat": False,
                "confidence": 0.0,
                "bounding_box": None,
                "total_cats_detected": 0,
                "error": f"เกิดข้อผิดพลาดในการตรวจจับ: {str(e)}"
            }


# ========================================
# Singleton Instance (Performance Optimization)
# ========================================
_detector_instance: Optional[CatDetector] = None

def get_detector() -> CatDetector:
    """
    Get or create CatDetector singleton instance
    
    Returns:
        CatDetector instance
    """
    global _detector_instance
    
    if _detector_instance is None:
        print("🏗️ Creating CatDetector singleton instance...")
        _detector_instance = CatDetector()
    
    return _detector_instance


def detect_cat(
    image_path: str, 
    confidence_threshold: Optional[float] = None,
    return_all_cats: bool = False
) -> Dict:
    """
    🐱 Convenience function to detect cats
    
    Args:
        image_path: Path to image file
        confidence_threshold: Minimum confidence (default: 0.5)
        return_all_cats: Return all detected cats (default: False)
        
    Returns:
        Detection result dictionary
    """
    detector = get_detector()
    return detector.detect_cat(
        image_path, 
        confidence_threshold=confidence_threshold,
        return_all_cats=return_all_cats
    )


# ========================================
# Reset Function (for testing)
# ========================================
def reset_detector():
    """Reset the singleton instance (useful for testing)"""
    global _detector_instance
    _detector_instance = None
    print("♻️ CatDetector instance reset")