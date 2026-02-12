import os
import firebase_admin
from firebase_admin import credentials


def init_firebase() -> None:
    """Initialize Firebase Admin SDK"""
    
    # กัน init ซ้ำ
    if firebase_admin._apps:
        print("✅ Firebase already initialized")
        return

    print("🔍 Reading Firebase credentials from environment...")
    
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
    private_key = os.getenv("FIREBASE_PRIVATE_KEY")

    # 🔍 Debug: แสดงว่ามีตัวแปรอะไรบ้าง
    print(f"   - FIREBASE_PROJECT_ID: {'✅' if project_id else '❌ MISSING'}")
    print(f"   - FIREBASE_CLIENT_EMAIL: {'✅' if client_email else '❌ MISSING'}")
    print(f"   - FIREBASE_PRIVATE_KEY: {'✅' if private_key else '❌ MISSING'}")

    if not all([project_id, client_email, private_key]):
        missing = []
        if not project_id:
            missing.append("FIREBASE_PROJECT_ID")
        if not client_email:
            missing.append("FIREBASE_CLIENT_EMAIL")
        if not private_key:
            missing.append("FIREBASE_PRIVATE_KEY")
        
        error_msg = f"Missing Firebase ENV variables: {', '.join(missing)}"
        print(f"❌ {error_msg}")
        
        print("\n💡 How to fix:")
        print("   1. Go to Render Dashboard → Your Service → Environment")
        print("   2. Add these environment variables:")
        print("      - FIREBASE_PROJECT_ID")
        print("      - FIREBASE_CLIENT_EMAIL")
        print("      - FIREBASE_PRIVATE_KEY")
        print("   3. Get values from Firebase Console:")
        print("      https://console.firebase.google.com/")
        print("      → Project Settings → Service Accounts → Generate new private key")
        
        raise RuntimeError(error_msg)

    try:
        # ทำความสะอาด private_key
        cleaned_private_key = private_key.replace("\\n", "\n").strip('"').strip("'")
        
        print("🔍 Creating Firebase credentials...")
        
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": project_id,
            "client_email": client_email,
            "private_key": cleaned_private_key,
            "token_uri": "https://oauth2.googleapis.com/token",
        })

        print("🔍 Initializing Firebase Admin SDK...")
        firebase_admin.initialize_app(cred)
        
        print(f"✅ Firebase initialized successfully for project: {project_id}")
        
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        raise