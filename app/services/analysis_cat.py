import os
import json
import requests
import base64
from dotenv import load_dotenv
from google import genai
from google.genai import types
import time

load_dotenv()

client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
MODEL = "models/gemini-2.0-flash"

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
  "gender": <0=ไม่ทราบ, 1=ผู้, 2=เมีย>,
  "weight_kg": <น้ำหนักโดยประมาณ เป็น float เช่น 4.5>,
  "size_category": "<XS|S|M|L|XL>",
  "chest_cm": <รอบอกโดยประมาณ เป็น float>,
  "neck_cm": <รอบคอโดยประมาณ เป็น float หรือ null>,
  "waist_cm": <รอบเอวโดยประมาณ เป็น float หรือ null>,
  "body_length_cm": <ความยาวลำตัว เป็น float หรือ null>,
  "back_length_cm": <ความยาวหลัง เป็น float หรือ null>,
  "leg_length_cm": <ความยาวขาหน้า เป็น float หรือ null>,
  "age_category": "<kitten|junior|adult|senior>",
  "body_condition_score": <integer 1-9>,
  "body_condition": "<underweight|ideal|overweight>",
  "body_condition_description": "<ประเมินสภาพร่างกาย 1-2 ประโยค>",
  "posture": "<standing|sitting|lying|other>",
  "size_recommendation": "<ขนาดเสื้อที่แนะนำพร้อมเหตุผล>",
  "size_ranges": {
    "chest_min": <float>, "chest_max": <float>,
    "neck_min": <float>, "neck_max": <float>,
    "back_length_min": <float>, "back_length_max": <float>
  },
  "quality_flag": "<good|blurry|partial|unclear>",
  "confidence": <0.0-1.0>,
  "analysis_version": "2.0",
  "analysis_method": "gemini_2.0_flash_vision"
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
"""


def _calc_bmi(weight_kg, body_length_cm):
    if not weight_kg or not body_length_cm or body_length_cm <= 0:
        return None
    length_m = body_length_cm / 100.0
    return round(weight_kg / (length_m ** 2), 2)


def analyze_cat(image_cat: str) -> dict:
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

    # ── 2. เรียก Gemini + Retry ──────────────────────────────
    print(f"🤖 Calling {MODEL}...")
    response = None
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    types.Part.from_text(text=CAT_ANALYSIS_PROMPT),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1500,
                ),
            )
            break  # ✅ สำเร็จออกจาก loop

        except Exception as e:
            error_str = str(e)
            print(f"❌ Gemini API error (attempt {attempt+1}): {e}")
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if "limit: 0" in error_str or "PerDay" in error_str:
                    raise RuntimeError("วันนี้ใช้ quota หมดแล้ว กรุณาลองใหม่พรุ่งนี้")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                    print(f"⏳ Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError("Gemini rate limit exceeded. Please try again later.")
            raise RuntimeError(f"Gemini Vision failed: {e}")

    # ── 3. Parse JSON ────────────────────────────────────────
    raw_text = response.text.strip()
    print(f"📝 Gemini raw response:\n{raw_text[:300]}...")

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

    # ── 4. ถ้าไม่ใช่แมว ─────────────────────────────────────
    if not ai_data.get("is_cat", True):
        return {
            "is_cat": False,
            "message": ai_data.get("message", "ไม่พบแมวในภาพ"),
        }

    # ── 5. คำนวณ BMI ─────────────────────────────────────────
    bmi = _calc_bmi(ai_data.get("weight_kg"), ai_data.get("body_length_cm"))

    # ── 6. Return dict ───────────────────────────────────────
    result = {
        "is_cat": True,
        "message": "ok",
        "cat_color": ai_data.get("cat_color", "Unknown"),
        "breed":     ai_data.get("breed"),
        "age":       ai_data.get("age"),
        "gender":    ai_data.get("gender", 0),
        "weight_kg": ai_data.get("weight_kg"),
        "size_category": ai_data.get("size_category", "M"),
        "bounding_box":  ai_data.get("bounding_box", []),
        "confidence":    ai_data.get("confidence", 0.90),
        "measurements": {
            "chest_cm":       ai_data.get("chest_cm"),
            "neck_cm":        ai_data.get("neck_cm"),
            "waist_cm":       ai_data.get("waist_cm"),
            "body_length_cm": ai_data.get("body_length_cm"),
            "back_length_cm": ai_data.get("back_length_cm"),
            "leg_length_cm":  ai_data.get("leg_length_cm"),
        },
        "age_category":               ai_data.get("age_category", "adult"),
        "body_condition_score":       ai_data.get("body_condition_score"),
        "body_condition":             ai_data.get("body_condition"),
        "body_condition_description": ai_data.get("body_condition_description"),
        "bmi":                        bmi,
        "posture":                    ai_data.get("posture", "unknown"),
        "size_recommendation":        ai_data.get("size_recommendation"),
        "size_ranges":                ai_data.get("size_ranges"),
        "quality_flag":               ai_data.get("quality_flag", "good"),
        "analysis_version":           ai_data.get("analysis_version", "2.0"),
        "analysis_method":            ai_data.get("analysis_method", "gemini_2.0_flash_vision"),
    }

    print(
        f"✅ Done: {result['cat_color']} | {result['size_category']} "
        f"| chest={result['measurements']['chest_cm']}cm | bmi={bmi}"
    )
    return result