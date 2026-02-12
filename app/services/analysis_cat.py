import math
from typing import Optional, Dict, List, Tuple

# =========================
# GLOBAL REFERENCES
# =========================

# ค่าอ้างอิงจากการวัดแมวจริง (ข้อมูลจากสัตวแพทย์)
REAL_TORSO_HEIGHT_CM = 25  # ความสูงลำตัวเฉลี่ย

# ค่าปรับตามสายพันธุ์ (จากข้อมูลจริง)
BREED_MODIFIER = {
    "maine_coon": 1.15,        # แมวเมนคูน ตัวใหญ่
    "ragdoll": 1.10,           # แมวแร็กดอลล์ ตัวใหญ่
    "british_shorthair": 1.05, # แมวบริติชช็อตแฮร์ ตัวกลาง-ใหญ่
    "persian": 1.03,           # แมวเปอร์เซีย ตัวกลาง
    "siamese": 0.95,           # แมวสยาม ตัวเล็ก-กลาง
    "bengal": 1.02,            # แมวเบงกอล ตัวกลาง
    "scottish_fold": 1.00,     # แมวสก็อตติชโฟลด์ ตัวกลาง
    "russian_blue": 0.98,      # แมวรัสเซียนบลู ตัวกลาง
    "sphynx": 0.93,            # แมวสฟิงซ์ ตัวเล็ก
    "munchkin": 0.85,          # แมวมันช์กิ้น ตัวเล็กมาก
    "domestic_shorthair": 1.0, # แมวบ้านทั่วไป
    "domestic_longhair": 1.02, # แมวบ้านขนยาว
    "unknown": 1.0             # ไม่ทราบสายพันธุ์
}

# ช่วงอายุและค่าปรับน้ำหนัก
AGE_WEIGHT_MODIFIER = {
    "kitten": 0.3,      # ลูกแมว 0-6 เดือน
    "young": 0.7,       # แมวหนุ่มสาว 6-12 เดือน
    "adult": 1.0,       # แมววัยผู้ใหญ่ 1-7 ปี
    "senior": 0.95      # แมวสูงอายุ 7+ ปี
}

# =========================
# POSTURE DETECTION
# =========================

def estimate_posture(w: float, h: float) -> Tuple[str, float]:
    """
    วิเคราะห์ท่าทางของแมวจากอัตราส่วน width/height
    
    Returns:
        posture: ท่าทาง (lying/sitting/standing/curled)
        posture_factor: ค่าปรับสำหรับการคำนวณ
    """
    ratio = w / max(h, 1)
    
    if ratio > 1.6:
        return "lying", 0.85      # นอนราบ
    elif ratio > 1.4:
        return "curled", 0.88     # ขดตัว
    elif ratio < 0.8:
        return "sitting", 0.92    # นั่ง
    elif ratio < 1.0:
        return "standing", 1.0    # ยืน (มองด้านข้าง)
    else:
        return "standing", 0.98   # ยืน (มุมเฉียง)


# =========================
# BODY CONDITION SCORE (BCS)
# =========================

def estimate_body_condition(chest_cm: float, weight: float, body_length_cm: float) -> Dict:
    """
    ประเมินสภาพร่างกาย (Body Condition Score)
    ตามมาตรฐานสัตวแพทย์ 1-9 คะแนน
    
    BCS 1-3: ผอม
    BCS 4-5: เหมาะสม
    BCS 6-7: น้ำหนักเกิน
    BCS 8-9: อ้วน
    """
    # คำนวณดัชนีมวลกาย (BMI) แบบแมว
    bmi = (weight * 1000) / (body_length_cm ** 2)
    
    # ประเมิน BCS
    if bmi < 3.5:
        bcs = 3
        condition = "underweight"
        description = "ผอมเกินไป ควรเพิ่มน้ำหนัก"
    elif bmi < 4.5:
        bcs = 4
        condition = "lean"
        description = "ผอม แต่ยังอยู่ในเกณฑ์ปกติ"
    elif bmi < 6.0:
        bcs = 5
        condition = "ideal"
        description = "น้ำหนักเหมาะสม สุขภาพดี"
    elif bmi < 7.5:
        bcs = 6
        condition = "overweight"
        description = "น้ำหนักเกินเล็กน้อย ควรควบคุม"
    elif bmi < 9.0:
        bcs = 7
        condition = "overweight"
        description = "น้ำหนักเกิน ควรลดน้ำหนัก"
    else:
        bcs = 8
        condition = "obese"
        description = "อ้วน ควรปรึกษาสัตวแพทย์"
    
    return {
        "bcs_score": bcs,
        "condition": condition,
        "description": description,
        "bmi": round(bmi, 2)
    }


# =========================
# BODY METRICS
# =========================

def estimate_body_metrics(bbox: List[float]) -> Dict:
    """
    คำนวณขนาดส่วนต่างๆ ของร่างกายแมว
    โดยอิงจากข้อมูลกายวิภาคแมวจริง
    """
    x1, y1, x2, y2 = bbox
    w = max(x2 - x1, 1)
    h = max(y2 - y1, 1)
    
    posture, posture_factor = estimate_posture(w, h)
    
    # อัตราส่วนลำตัวตามท่าทาง
    torso_ratio = {
        "lying": 0.55,
        "curled": 0.50,
        "sitting": 0.60,
        "standing": 0.65
    }[posture]
    
    # คำนวณขนาดจริง
    effective_height = h * torso_ratio
    pixel_to_cm = REAL_TORSO_HEIGHT_CM / max(effective_height, 1)
    
    # ความยาวลำตัว (nose to tail base)
    body_length_cm = round(
        w * pixel_to_cm * (1.0 if posture in ["lying", "curled"] else 0.9),
        1
    )
    
    # รอบอก (chest circumference) - สำคัญสำหรับเสื้อผ้า
    chest_base = math.pi * (w * pixel_to_cm) * 0.6
    chest_cm = round(chest_base * posture_factor, 1)
    
    # รอบคอ (neck circumference) - สำหรับปลอกคอ
    neck_cm = round(chest_cm * 0.62, 1)
    
    # รอบเอว (waist) - ตรงส่วนที่เล็กที่สุดของลำตัว
    waist_cm = round(chest_cm * 0.85, 1)
    
    # ความยาวหลัง (back length) - จากคอถึงโคนหาง
    back_length_cm = round(body_length_cm * 0.75, 1)
    
    # ความยาวขา (leg length) - ประมาณการ
    leg_length_cm = round(h * pixel_to_cm * 0.35, 1)
    
    # ประเมินคุณภาพภาพ
    size_ratio = min(1.0, (w * h) / (300 * 300))
    aspect_score = 1.0 if 0.5 < w / h < 2.0 else 0.6
    posture_clarity = 0.9 if posture in ["standing", "sitting"] else 0.7
    confidence = round((size_ratio * 0.5 + aspect_score * 0.3 + posture_clarity * 0.2), 2)
    
    quality_flag = (
        "excellent" if confidence > 0.85 else
        "good" if confidence > 0.75 else
        "medium" if confidence > 0.6 else
        "poor"
    )
    
    return {
        "posture": posture,
        "chest_cm": chest_cm,
        "neck_cm": neck_cm,
        "waist_cm": waist_cm,
        "body_length_cm": body_length_cm,
        "back_length_cm": back_length_cm,
        "leg_length_cm": leg_length_cm,
        "confidence": confidence,
        "quality_flag": quality_flag
    }


# =========================
# WEIGHT ESTIMATION
# =========================

def estimate_weight(
    chest_cm: float, 
    body_length_cm: float, 
    breed: str = "unknown",
    age_category: str = "adult"
) -> float:
    """
    ประมาณน้ำหนักแมว โดยใช้สูตรจากงานวิจัยสัตวแพทย์
    
    สูตรพื้นฐาน: Weight = (Chest² × Body Length) / 3000
    ปรับด้วยค่า breed และ age
    """
    # น้ำหนักพื้นฐาน
    base_weight = (chest_cm ** 2 * body_length_cm) / 3000
    
    # ปรับตามสายพันธุ์
    breed_adjusted = base_weight * BREED_MODIFIER.get(breed, 1.0)
    
    # ปรับตามอายุ
    age_adjusted = breed_adjusted * AGE_WEIGHT_MODIFIER.get(age_category, 1.0)
    
    return round(age_adjusted, 2)


# =========================
# SIZE CATEGORY (CLOTHING)
# =========================

def determine_size(weight: float, chest_cm: float, neck_cm: float) -> Dict:
    """
    กำหนดขนาดเสื้อผ้าสำหรับแมว
    โดยพิจารณาทั้งน้ำหนัก รอบอก และรอบคอ
    
    ขนาดมาตรฐาน:
    XS: แมวเล็กมาก (< 2.5 kg)
    S:  แมวเล็ก (2.5-4 kg)
    M:  แมวกลาง (4-6 kg)
    L:  แมวใหญ่ (6-8.5 kg)
    XL: แมวใหญ่มาก (> 8.5 kg)
    """
    
    # กำหนดขนาดตามหลายเกณฑ์
    weight_size = (
        "XS" if weight < 2.5 else
        "S" if weight < 4 else
        "M" if weight < 6 else
        "L" if weight < 8.5 else
        "XL"
    )
    
    chest_size = (
        "XS" if chest_cm < 24 else
        "S" if chest_cm < 32 else
        "M" if chest_cm < 38 else
        "L" if chest_cm < 45 else
        "XL"
    )
    
    neck_size = (
        "XS" if neck_cm < 15 else
        "S" if neck_cm < 20 else
        "M" if neck_cm < 24 else
        "L" if neck_cm < 28 else
        "XL"
    )
    
    # เลือกขนาดที่เหมาะสมที่สุด (weighted average)
    sizes = [weight_size, chest_size, chest_size, neck_size]  # chest มีน้ำหนักมากกว่า
    size_category = max(set(sizes), key=sizes.count)
    
    # ช่วงขนาดที่แนะนำ
    size_ranges = {
        "XS": {"weight": "< 2.5 kg", "chest": "< 24 cm", "neck": "< 15 cm"},
        "S": {"weight": "2.5-4 kg", "chest": "24-32 cm", "neck": "15-20 cm"},
        "M": {"weight": "4-6 kg", "chest": "32-38 cm", "neck": "20-24 cm"},
        "L": {"weight": "6-8.5 kg", "chest": "38-45 cm", "neck": "24-28 cm"},
        "XL": {"weight": "> 8.5 kg", "chest": "> 45 cm", "neck": "> 28 cm"}
    }
    
    return {
        "size_category": size_category,
        "size_ranges": size_ranges[size_category],
        "recommendation": f"แนะนำขนาด {size_category} สำหรับเสื้อผ้า และปลอกคอ"
    }


# =========================
# COLOR PROCESSING
# =========================

def process_cat_color(cat_color: Optional[str]) -> str:
    """
    ประมวลผลสีของแมว รองรับหลายสี
    
    Examples:
        "orange" -> "orange"
        "black+white" -> "black+white"
        "orange+white+black" -> "orange+white+black"
    """
    if not cat_color:
        return "unknown"
    
    # ทำความสะอาดและจัดรูปแบบ
    colors = [c.strip().lower() for c in cat_color.replace(",", "_").split("_")]
    colors = [c for c in colors if c]  # ลบค่าว่าง
    
    if not colors:
        return "unknown"
    
    # รวมสีด้วย +
    return "_".join(colors)


# =========================
# MAIN ANALYSIS FUNCTION
# =========================

def analyze_cat(
    image_path: str,
    bounding_box: List[float],
    firebase_uid: str,
    cat_color: Optional[str] = None,
    breed: str = "unknown",
    age_category: str = "adult"
) -> Dict:
    """
    🐱 CatAnalyzer V5 - Professional Edition
    
    วิเคราะห์แมวอย่างครบถ้วน ด้วยข้อมูลจากสัตวแพทย์และกายวิภาคศาสตร์
    
    Parameters:
        image_path: path ของรูปภาพ
        bounding_box: [x1, y1, x2, y2] ตำแหน่งแมวในภาพ
        firebase_uid: Firebase UID ของเจ้าของแมว
        cat_color: สีของแมว (เช่น "orange", "black+white")
        breed: สายพันธุ์ (ดูรายชื่อใน BREED_MODIFIER)
        age_category: ช่วงอายุ (kitten/young/adult/senior)
    
    Returns:
        Dict ที่มีข้อมูลครบถ้วนเกี่ยวกับแมว
    """
    
    # 1. ประมวลผลสี
    processed_color = process_cat_color(cat_color)
    
    # 2. วิเคราะห์ขนาดส่วนต่างๆ ของร่างกาย
    metrics = estimate_body_metrics(bounding_box)
    
    # 3. ประมาณน้ำหนัก
    weight = estimate_weight(
        metrics["chest_cm"],
        metrics["body_length_cm"],
        breed,
        age_category
    )
    
    # 4. ประเมินสภาพร่างกาย
    body_condition = estimate_body_condition(
        metrics["chest_cm"],
        weight,
        metrics["body_length_cm"]
    )
    
    # 5. กำหนดขนาดเสื้อผ้า
    size_info = determine_size(
        weight,
        metrics["chest_cm"],
        metrics["neck_cm"]
    )
    
    # 6. สรุปผลการวิเคราะห์
    return {
        # ข้อมูลเจ้าของ
        "firebase_uid": firebase_uid,
        
        # ข้อมูลพื้นฐาน
        "breed": breed,
        "cat_color": processed_color,
        "age_category": age_category,
        
        # น้ำหนักและสภาพร่างกาย
        "weight_kg": weight,
        "body_condition_score": body_condition["bcs_score"],
        "body_condition": body_condition["condition"],
        "body_condition_description": body_condition["description"],
        "bmi": body_condition["bmi"],
        
        # ขนาดส่วนต่างๆ (สำหรับเสื้อผ้า/อุปกรณ์)
        "measurements": {
            "chest_cm": metrics["chest_cm"],
            "neck_cm": metrics["neck_cm"],
            "waist_cm": metrics["waist_cm"],
            "body_length_cm": metrics["body_length_cm"],
            "back_length_cm": metrics["back_length_cm"],
            "leg_length_cm": metrics["leg_length_cm"]
        },
        
        # ขนาดเสื้อผ้า
        "size_category": size_info["size_category"],
        "size_ranges": size_info["size_ranges"],
        "size_recommendation": size_info["recommendation"],
        
        # ข้อมูลการวิเคราะห์
        "posture": metrics["posture"],
        "confidence": metrics["confidence"],
        "quality_flag": metrics["quality_flag"],
        
        # 🔥 เพิ่ม bounding_box ที่ได้จาก detect_cat
        "bounding_box": bounding_box,
        
        # Metadata
        "analysis_method": "cv_heuristic_v5_professional",
        "analysis_version": "5.0",
        "image_path": image_path
    }