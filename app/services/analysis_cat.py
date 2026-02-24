"""
app/services/analysis_cat.py

ส่ง image_cat → Gemini 1.5 Flash → return dict ตรงกับ column ใน table cat ทุก field

เปลี่ยนจาก OpenAI → Google Gemini 1.5 Flash (Free Tier)
- ไม่ต้องผูกบัตร
- 15 RPM / 1,500 RPD
- รองรับ multimodal (ภาพ + ข้อความ)
"""

import os
import json
import base64
import requests
import google.generativeai as genai

# ── Configure Gemini ──────────────────────────────────────────────────────────
genai.configure(api_key=os.environ["GOOGLE_API_KEY_CATSHOP"])
model = genai.GenerativeModel("gemini-1.5-flash")

# ─────────────────────────────────────────────────────────────────────────────
#  PROMPT — บอก Gemini ให้คืน JSON ตรงกับ DB schema
# ─────────────────────────────────────────────────────────────────────────────
CAT_ANALYSIS_PROMPT = """
สมมุติให้คุณเชี่ยวชาญด้านการดูแลสัตว์เลี้ยงโดยเฉพาะแมว

ช่วยวิเคราะห์แมวในภาพนี้ แล้วตอบกลับเป็น JSON เท่านั้น
ห้ามมีข้อความอื่น ห้ามมี markdown ห้ามมี code block — raw JSON เท่านั้น

ถ้าไม่มีแมวในภาพ ให้ตอบ:
{"is_cat": false, "message": "ไม่พบแมวในภาพ"}

ถ้ามีแมว ให้วิเคราะห์และตอบ JSON ครบทุก field ดังนี้:
{
  "is_cat": true,
  "cat_color": "<สีหลัก/ลาย เช่น orange tabby, black, white, calico, bicolor>",
  "breed": "<สายพันธุ์ที่ประเมินได้ เช่น Domestic Shorthair, Persian, Siamese>",
  "age": <อายุโดยประมาณ เป็น integer (ปี) หรือ null>,
  "gender": <0=ไม่ทราบ, 1=ผู้, 2=เมีย — ประเมินจากรูปร่างหน้าตา>,
  "weight_kg": <น้ำหนักโดยประมาณ เป็น float เช่น 4.5>,
  "size_category": "<XS|S|M|L|XL>",
  "chest_cm": <รอบอกโดยประมาณ เป็น float>,
  "neck_cm": <รอบคอโดยประมาณ เป็น float หรือ null>,
  "waist_cm": <รอบเอวโดยประมาณ เป็น float หรือ null>,
  "body_length_cm": <ความยาวลำตัว (จมูก-โคนหาง) เป็น float หรือ null>,
  "back_length_cm": <ความยาวหลัง เป็น float หรือ null>,
  "leg_length_cm": <ความยาวขาหน้า เป็น float หรือ null>,
  "age_category": "<kitten|junior|adult|senior>",
  "body_condition_score": <integer 1-9, 1=ผอมมาก 5=สมส่วน 9=อ้วนมาก>,
  "body_condition": "<underweight|ideal|overweight>",
  "body_condition_description": "<ประเมินสภาพร่างกาย 1-2 ประโยค>",
  "posture": "<standing|sitting|lying|other>",
  "size_recommendation": "<ขนาดเสื้อที่แนะนำพร้อมเหตุผล เช่น S — ตัวเล็ก รอบอกแคบ>",
  "size_ranges": {
    "chest_min": <float>,
    "chest_max": <float>,
    "neck_min": <float>,
    "neck_max": <float>,
    "back_length_min": <float>,
    "back_length_max": <float>
  },
  "quality_flag": "<good|blurry|partial|unclear>",
  "confidence": <ความมั่นใจในการวิเคราะห์ 0.0-1.0>,
  "analysis_version": "2.0",
  "analysis_method": "gemini_1.5_flash_vision"
}

กฎขนาด (อ้างอิงจาก chest_cm):
  XS: chest < 28 cm
  S : chest 28-32 cm
  M : chest 32-36 cm
  L : chest 36-40 cm
  XL: chest > 40 cm

กฎ age_category:
  kitten : age < 1
  junior : age 1-2
  adult  : age 3-10
  senior : age > 10

หากภาพไม่ชัดหรือวิเคราะห์ได้ไม่ครบ ให้ตอบ JSON ครบทุก field
แต่ใส่ null สำหรับ field ที่ไม่แน่ใจ และ quality_flag = "blurry" หรือ "unclear"
"""


# ─────────────────────────────────────────────────────────────────────────────
#  BMI helper
# ─────────────────────────────────────────────────────────────────────────────
def _calc_bmi(weight_kg: float | None, body_length_cm: float | None) -> float | None:
    if not weight_kg or not body_length_cm or body_length_cm <= 0:
        return None
    length_m = body_length_cm / 100.0
    return round(weight_kg / (length_m ** 2), 2)


# ─────────────────────────────────────────────────────────────────────────────
#  Main function
# ─────────────────────────────────────────────────────────────────────────────
def analyze_cat(image_cat: str) -> dict:
    """
    ดาวน์โหลด image_cat → encode base64 → ส่ง Gemini 1.5 Flash
    คืน dict พร้อม INSERT เข้า table cat

    ML Kit ทำ detect บน Flutter แล้ว — ฝั่งนี้วิเคราะห์ขนาด/สี/สายพันธุ์อย่างเดียว
    """

    # ── 1. Download image ────────────────────────────────────
    print(f"⬇️  Downloading image: {image_cat}")
    try:
        resp = requests.get(image_cat, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Cannot download image: {e}")

    image_bytes = resp.content
    mime_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
    print(f"✅ Downloaded ({len(image_bytes)/1024:.1f} KB) | mime={mime_type}")

    # ── 2. เรียก Gemini 1.5 Flash ───────────────────────────
    print("🤖 Calling Gemini 1.5 Flash...")
    try:
        image_part = {
            "mime_type": mime_type,
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        }

        response = model.generate_content(
            contents=[
                {"role": "user", "parts": [image_part, {"text": CAT_ANALYSIS_PROMPT}]}
            ],
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=1500,
            ),
        )
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        raise RuntimeError(f"Gemini Vision failed: {e}")

    # ── 3. Parse JSON response ───────────────────────────────
    raw_text = response.text.strip()
    print(f"📝 Gemini raw response:\n{raw_text[:300]}...")

    # ลบ markdown code block ถ้า Gemini แนบมาด้วย
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        ai_data: dict = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}\nRaw: {raw_text}")
        raise RuntimeError(f"Gemini returned invalid JSON: {e}")

    # ── 4. ถ้าไม่ใช่แมว คืนเลย ──────────────────────────────
    if not ai_data.get("is_cat", True):
        return {
            "is_cat": False,
            "message": ai_data.get("message", "ไม่พบแมวในภาพ"),
        }

    # ── 5. คำนวณ BMI ────────────────────────────────────────
    weight_kg = ai_data.get("weight_kg")
    body_length_cm = ai_data.get("body_length_cm")
    bmi = _calc_bmi(weight_kg, body_length_cm)

    # ── 6. Build result dict (ตรงกับ DB column) ─────────────
    result = {
        # ── meta ────────────────────────────────────────────
        "is_cat":  True,
        "message": "ok",

        # ── ข้อมูลแมว ──────────────────────────────────────
        "cat_color": ai_data.get("cat_color", "Unknown"),
        "breed":     ai_data.get("breed"),
        "age":       ai_data.get("age"),
        "gender":    ai_data.get("gender", 0),
        "weight_kg": weight_kg,

        # ── ขนาด ───────────────────────────────────────────
        "size_category": ai_data.get("size_category", "M"),
        "bounding_box":  ai_data.get("bounding_box", []),
        "confidence":    ai_data.get("confidence", 0.90),

        # ── การวัด nested (vision.py จะ .get("measurements")) ──
        "measurements": {
            "chest_cm":       ai_data.get("chest_cm"),
            "neck_cm":        ai_data.get("neck_cm"),
            "waist_cm":       ai_data.get("waist_cm"),
            "body_length_cm": ai_data.get("body_length_cm"),
            "back_length_cm": ai_data.get("back_length_cm"),
            "leg_length_cm":  ai_data.get("leg_length_cm"),
        },

        # ── สุขภาพ ─────────────────────────────────────────
        "age_category":               ai_data.get("age_category", "adult"),
        "body_condition_score":       ai_data.get("body_condition_score"),
        "body_condition":             ai_data.get("body_condition"),
        "body_condition_description": ai_data.get("body_condition_description"),
        "bmi":                        bmi,

        # ── ท่าทาง / คำแนะนำ ───────────────────────────────
        "posture":             ai_data.get("posture", "unknown"),
        "size_recommendation": ai_data.get("size_recommendation"),
        "size_ranges":         ai_data.get("size_ranges"),
        "quality_flag":        ai_data.get("quality_flag", "good"),

        # ── Meta ────────────────────────────────────────────
        "analysis_version": ai_data.get("analysis_version", "2.0"),
        "analysis_method":  ai_data.get("analysis_method", "gemini_1.5_flash_vision"),
    }

    print(
        f"✅ Done: {result['cat_color']} | {result['size_category']} "
        f"| chest={result['measurements']['chest_cm']}cm | bmi={bmi}"
    )
    return result