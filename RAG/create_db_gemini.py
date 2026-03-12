import json
import os
import sys
import time
from dotenv import load_dotenv

# --- YAPILANDIRMA & GÜVENLİK ---
# .env dosyasını yükle
load_dotenv()

# Anahtarı işletim sistemi ortam değişkenlerinden çekiyoruz.
# .env dosyanızda GOOGLE_API_KEY=anahtar_buraya şeklinde olmalı.
api_key = os.getenv("GOOGLE_API_KEY")
os.environ["GOOGLE_API_KEY"] = api_key

# --- KÜTÜPHANE İÇE AKTARIMLARI ---
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema import Document

print("⚙️ Veritabanı düzeltme işlemi başlıyor...")

# --------------------------------------------------------------------------------
# ADIM 1: MODEL SEÇİMİ (PROJE GEREKSİNİMİ 3.3)
# --------------------------------------------------------------------------------
# İstediğin model: text-embedding-004
embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")

# --------------------------------------------------------------------------------
# ADIM 2: VERİ YÜKLEME (PROJE GEREKSİNİMİ 3.2)
# --------------------------------------------------------------------------------
json_file = "ieu_courses_v17_stable.json"
try:
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"✅ {len(data)} ders yüklendi.")
except FileNotFoundError:
    print("❌ JSON dosyası bulunamadı!")
    sys.exit()

# --------------------------------------------------------------------------------
# ADIM 3: BELGE HAZIRLIĞI & META VERİ ZENGİNLEŞTİRME
# --------------------------------------------------------------------------------
documents = []
for item in data:
    dept_str = ", ".join(item.get('departments', []))

    text_content = f"""
    Course Code: {item.get('course_code')}
    Course Name: {item.get('course_name')}
    Departments: {dept_str}
    ECTS: {item.get('ects')}
    Weekly Topics: {', '.join(item.get('weekly_topics', []))}
    """

    metadata = {
        "code": item.get("course_code"),
        "name": item.get("course_name"),
        "dept_info": dept_str
    }

    documents.append(Document(page_content=text_content, metadata=metadata))

# --------------------------------------------------------------------------------
# ADIM 4: VEKTÖR VERİTABANI OLUŞTURMA (FAISS)
# --------------------------------------------------------------------------------
print("⏳ Vektör veritabanı yeniden oluşturuluyor...")

try:
    batch_size = 50
    vector_db = None

    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        print(f"   İşleniyor: {i} - {i + len(batch)} arası...")

        if vector_db is None:
            vector_db = FAISS.from_documents(batch, embeddings)
        else:
            vector_db.add_documents(batch)

        time.sleep(1)

    vector_db.save_local("faiss_index_gemini")

    print("\n🎉 TEBRİKLER! Veritabanı 'dept_info' ile güncellendi.")
    print("Artık 'main_rag.py' dosyasını çalıştırırsan eksik dersler (FAISS sonuçları) gelecektir.")

except Exception as e:
    print(f"❌ HATA: {e}")