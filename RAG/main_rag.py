import os
import time
import json
import sys

from dotenv import load_dotenv

# --- YAPILANDIRMA & GÜVENLİK ---
# .env dosyasını yükle
load_dotenv()

# Anahtarı işletim sistemi ortam değişkenlerinden çekiyoruz.
# .env dosyanızda GOOGLE_API_KEY=anahtar_buraya şeklinde olmalı.
api_key = os.getenv("GOOGLE_API_KEY")
os.environ["GOOGLE_API_KEY"] = api_key

# --- KÜTÜPHANE İÇE AKTARIMLARI ---
# ChatGoogleGenerativeAI: LLM bileşeni (Gemini Flash).
# BM25Retriever: Anahtar kelime tabanlı arama algoritması (Geleneksel Arama).
# EnsembleRetriever: Anlamsal (FAISS) ve Anahtar Kelime (BM25) aramayı birleştiren sistem.
# PromptTemplate: Yapay zekaya katı talimatlar (Rol Yapma) vermek için kullanılır.
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain.schema import Document
from langchain.prompts import PromptTemplate
from langchain.schema.output_parser import StrOutputParser

# --------------------------------------------------------------------------------
# ADIM 1: BAŞLATMA & MODEL YAPILANDIRMASI
# --------------------------------------------------------------------------------
print("⚙️ Sistem başlatılıyor...")
# 1.1 LLM SEÇİMİ
# Hızı ve yüksek token limiti bağlam penceresi nedeniyle 'gemini-flash-latest' kullanıyoruz.
# Akademik görevlerde deterministik, olgusal cevaplar sağlamak için Temperature=0 KRİTİKTİR.
llm = ChatGoogleGenerativeAI(model="models/gemini-flash-latest", temperature=0)

# 1.2 EMBEDDING MODELİ
# 'create_db_gemini.py' dosyasında kullanılan modelle eşleşmelidir.
embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")


# --------------------------------------------------------------------------------
# ADIM 2: GERİ GETİRİCİ KURULUMU (HİBRİT ARAMA MİMARİSİ)
# --------------------------------------------------------------------------------
# Hedef: Yapay zekanın "anlama" yeteneğini (FAISS) anahtar kelimelerin "kesinliği" (BM25) ile birleştirmek.

# 2.1 VEKTÖR DEPOSUNU YÜKLEME (ANLAMSAL ARAMA)
if os.path.exists("faiss_index_gemini"):
    # Önceden hesaplanmış embedding'leri diskten yükle.
    vector_db = FAISS.load_local("faiss_index_gemini", embeddings, allow_dangerous_deserialization=True)
    # k=400: Başlangıçta geniş bir belge havuzu getiriyoruz, ardından Python mantığı kullanarak bunları filtreliyoruz.
    faiss_retriever = vector_db.as_retriever(search_kwargs={"k": 400})
else:
    print("❌ HATA: 'faiss_index_gemini' klasörü bulunamadı. Lütfen önce veritabanını oluşturun.")
    sys.exit()

# 2.2 BM25 İNDEKSİ OLUŞTURMA (ANAHTAR KELİME ARAMASI)
# "SE 305" veya "MATH 101" gibi tam eşleşmeleri yakalamak için bellek içi bir anahtar kelime indeksi oluşturuyoruz.
try:
    with open("ieu_courses_v17_stable.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"✅ JSON yüklendi: {len(data)} ders verisi var.")

    bm25_docs = []
    for item in data:
        dept_str = ", ".join(item.get('departments', []))

        # İÇERİK ENJEKSİYONU: BM25 eşleşmesi için AKTS ve Bölümleri metnin içine açıkça koyuyoruz.
        text_content = (
            f"Code: {item.get('course_code')} | "
            f"Name: {item.get('course_name')} | "
            f"ECTS: {item.get('ects')} | "
            f"Depts: {dept_str}"
        )

        # Meta veriler daha sonra filtreleme yapmak için korunur.
        metadata = {"code": item.get("course_code"), "dept_info": dept_str}
        bm25_docs.append(Document(page_content=text_content, metadata=metadata))

    bm25_retriever = BM25Retriever.from_documents(bm25_docs)
    bm25_retriever.k = 400

    # 2.3 TOPLULUK (HİBRİT) GERİ GETİRİCİ
    # Anlamsal Aramayı (0.6), Anahtar Kelime Aramasından (0.4) biraz daha yüksek ağırlıklandırıyoruz.
    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, faiss_retriever],
        weights=[0.4, 0.6]
    )
except Exception as e:
    print(f"⚠️ BM25 Hatası: {e}")
    ensemble_retriever = faiss_retriever


# --------------------------------------------------------------------------------
# ADIM 3: AKILLI FİLTRELEME & GENİŞLETME ALGORİTMASI (TEMEL MANTIK)
# --------------------------------------------------------------------------------
# Bu fonksiyon "Müfredat Yapısı Sorunu"nu çözer.
# "İskelet" (Zorunlu) dersleri "Genişletme" (Seçmeli Havuz) derslerinden ayırır.

def retrieve_and_filter(query):
    print(f"\n📡 Veritabanından geniş tarama yapılıyor (k=400)...")
    # 3.1 GENİŞ KAPSAMLI GERİ GETİRME
    # Hibrit Geri Getiriciyi kullanarak en iyi 400 potansiyel eşleşmeyi getir.
    raw_docs = ensemble_retriever.invoke(query)

    # 3.2 NİYET ANALİZİ (SORGU ANLAMA)
    # Kullanıcının belirli bir Yıl veya Dönem hakkında soru sorup sormadığını tespit etmek için sezgisel kurallar kullanıyoruz.
    target_year = ""
    q_lower = query.lower()

    if "second year" in q_lower or "2nd year" in q_lower or "2. year" in q_lower:
        target_year = "2. Year"
    elif "first year" in q_lower or "1st year" in q_lower:
        target_year = "1. Year"
    elif "third year" in q_lower or "3rd year" in q_lower:
        target_year = "3. Year"
    elif "fourth year" in q_lower or "4th year" in q_lower or "final year" in q_lower:
        target_year = "4. Year"

    target_term = ""
    if "fall" in q_lower:
        target_term = "Fall"
    elif "spring" in q_lower:
        target_term = "Spring"

    print(f"🔍 ANALİZ: Hedef Yıl='{target_year}', Hedef Dönem='{target_term}'")

    # 3.3 İSKELET İNŞASI (ZORUNLU DERSLER)
    # Hedef yıl/dönem ile KESİN eşleşen dersleri bulmak için ham belgeler üzerinde geziniyoruz.
    skeleton_docs = []
    active_slots = set()  # "Yer Tutucu" dersleri (POOL, ELEC, SFL) takip etmek için

    for doc in raw_docs:
        dept_info = doc.metadata.get("dept_info", "")
        code = doc.metadata.get("code", "")

        # A. Yıl Filtreleme (Katı)
        if target_year and target_year not in dept_info:
            continue

        # B. Dönem Filtreleme (Bağlam-Duyarlı)
        # Esnek derslerin (her iki dönem) veya Seçmeli derslerin geçmesine izin veriyoruz.
        if target_term:
            is_flexible = "Fall" in dept_info and "Spring" in dept_info
            is_elective = "Elective" in dept_info
            has_target = target_term in dept_info
            if not (has_target or is_flexible or is_elective):
                continue

        # C. İskelet Listesine Ekle
        skeleton_docs.append(doc)

        # D. Slot Tespit Mantığı
        # Eğer "POOL 004" görürsek, "POOL"u aktif olarak işaretliyoruz.
        if code.startswith("SFL"): active_slots.add("SFL")
        if code.startswith("ELEC"): active_slots.add("ELEC")
        if code.startswith("POOL"): active_slots.add("POOL")

    print(f"   🦴 İskelet Kuruldu: {len(skeleton_docs)} ders. Tespit Edilen Slotlar: {active_slots}")

    # 3.4 DİNAMİK GENİŞLETME (YER TUTUCULARI ÇÖZÜMLEME)
    # İskelette bir slot (yuva) bulunduysa (örn: POOL), ham belgelere geri dönüp
    # o slot için TÜM mevcut seçenekleri getiriyoruz.
    expansion_docs = []

    if active_slots:
        print("   🚀 Slotlar Genişletiliyor...")

        for doc in raw_docs:
            code = doc.metadata.get("code", "")
            dept_info = doc.metadata.get("dept_info", "")

            # Halihazırda iskelette olan dersleri eklemekten kaçın
            if any(d.metadata["code"] == code for d in skeleton_docs):
                continue

            # KURAL 1: SFL GENİŞLETME (Yabancı Diller)
            # Eğer SFL slotu aktifse; Almanca, İtalyanca, Rusça vb. getir.
            if "SFL" in active_slots:
                if code.startswith(("GER", "ITL", "RUS", "FRA", "GRE", "SPA", "CHN", "JPN")):
                    expansion_docs.append(doc)
                    continue

            # KURAL 2: ELEC GENİŞLETME (Teknik Seçmeliler)
            # Eğer ELEC slotu aktifse, "Elective" olarak işaretlenmiş herhangi bir dersi getir.
            if "ELEC" in active_slots:
                if "Elective" in dept_info and "Electives" in dept_info:
                    expansion_docs.append(doc)
                    continue

            # KURAL 3: POOL GENİŞLETME (Genel Eğitim)
            # Eğer POOL slotu aktifse, "Pool" veya "GED" olarak işaretlenmiş dersleri getir.
            if "POOL" in active_slots:
                if "Pool" in dept_info or "GED" in dept_info:
                    expansion_docs.append(doc)
                    continue

    # 3.5 SON BİRLEŞTİRME & TEKİLLEŞTİRME
    # Zorunlu İskelet + Seçmeli Genişletme seçeneklerini birleştir.
    final_docs = skeleton_docs + expansion_docs

    unique_docs = []
    seen_codes = set()
    for d in final_docs:
        c = d.metadata.get("code")
        if c not in seen_codes:
            unique_docs.append(d)
            seen_codes.add(c)

    print(f"✨ Final Liste: {len(unique_docs)} ders (İskelet + Genişletilmiş Seçenekler).\n")
    return unique_docs


# --------------------------------------------------------------------------------
# ADIM 4: PROMPT MÜHENDİSLİĞİ (DOĞRULAMA ZİNCİRİ)
# --------------------------------------------------------------------------------
# LLM'i bir "Akademik Denetçi" olarak hareket etmeye zorlayan sağlam bir Prompt Şablonu oluşturuyoruz.
# Halüsinasyonları önlemek için 4 Adımlı Algoritmik Talimat seti içerir.

prompt_template = """
Sen, İzmir Ekonomi Üniversitesi Mühendislik Fakültesi için çalışan, veri odaklı, objektif ve matematiksel kesinlik arayan bir Akademik Denetçisin.
Görevin, sana sağlanan ham veri parçalarını (Bağlam) bir **BİLGİSAYAR ALGORİTMASI** gibi işleyerek öğrencinin sorusunu yanıtlamaktır.

Cevabını oluştururken aşağıdaki **4 ADIMLI ALGORİTMAYI** sırasıyla çalıştır:

--- ADIM 1: VERİ SEÇİMİ VE SAHİPLİK (KİMİN DERSİ?) ---
* **KURAL:** Bir dersin bağlamda bulunması, o dersin sorulan bölüm (Örn: Yazılım Müh.) için geçerli olduğu anlamına gelmez.
* **YÖNTEM:** Her dersin "Departments" satırını tara.
    * **EĞER** sorulan bölümün adı (Örn: "Software Engineering") satırda **AÇIKÇA (STRING OLARAK)** geçmiyorsa -> **BU DERSİ YOK SAY.** (Dersin kodu MATH, PHYS veya EEE olsa bile alma).
    * *Not:* Asla tahmin yürütme. Sadece yazılı beyana güven.

--- ADIM 2: STATÜ KONTROLÜ (ZORUNLU MU?) ---
* **KURAL:** Soru "Zorunlu" (Core/Mandatory) dersleri istiyorsa; statüsü "Elective" olan dersleri ele.
    * *Örnek:* Dersin açıklamasında "Software Eng : Elective" yazıyorsa ve soru "Zorunlu dersler neler?" ise, bu dersi listeye alma.
    * *İstisna:* `ELEC 00X`, `POOL 00X`, `SFL` gibi kodlar "Zorunlu Seçmeli Havuz" olduğu için bunları **DAHİL ET.**

--- ADIM 3: HESAPLAMA VE "ALTIN KURAL" SAĞLAMASI ---
* **DEĞER ATAMA (OVERRIDE):** Bir dersin genel ECTS değeri ile "Depts" satırındaki parantez içi değer (Örn: `... (6 ECTS)`) farklıysa, **HER ZAMAN PARANTEZ İÇİNDEKİ DEĞERİ KULLAN.**
* **ALTIN KURAL (SANITY CHECK):**
    * Mühendislik Fakültesinde standart şudur: **Her dönem = 30 ECTS**, **Toplam Program = 240 ECTS.**
    * **HESAPLAMA:** Seçtiğin dersleri topla.
        * **Eğer Toplam ≠ 30 ise (Örn: 26 veya 34):** DUR VE KONTROL ET! Muhtemelen bir `POOL`/`ELEC` dersini unuttun ya da bir dersin Override (6 yerine 5 ECTS) kuralını görmedin. Listeyi tekrar tara.
        * **Eğer veri yoksa:** Eksiği uydurma, sadece "Veri eksikliği nedeniyle toplam X ECTS bulundu" de.

--- ADIM 4: CEVAP FORMATI ---
* **Liste Soruları:** (Örn: "2. sınıf dersleri neler?")
    * Sadece ders Kodu, Adı ve ECTS bilgisini içeren temiz bir tablo oluştur.
* **Hesaplama Soruları:** (Örn: "En yoğun yıl hangisi?")
    * İşlem hatası olmadığını kanıtlamak için; hesapladığın yılların derslerini kısaca listele, altına **TOPLAM** puanı yaz ve (30 ECTS ile uyumlu olup olmadığını) parantez içinde belirt.

BAĞLAM (Veritabanından Gelen Ham Veri):
{context}

SORU:
{question}

CEVAP:
"""

prompt = PromptTemplate(template=prompt_template, input_variables=["context", "question"])


# --------------------------------------------------------------------------------
# ADIM 5: RAG ZİNCİRİ YÜRÜTME
# --------------------------------------------------------------------------------
def run_rag(query):
    # 1. Getir & Filtrele (Python Mantığı)
    relevant_docs = retrieve_and_filter(query)

    # 2. Bağlam İnşası (Zenginleştirme)
    context_text = "\n\n".join([d.page_content for d in relevant_docs])

    # 3. Üretim (LLM)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"context": context_text, "question": query})


# --------------------------------------------------------------------------------
# ADIM 6: KULLANICI ARAYÜZÜ DÖNGÜSÜ
# --------------------------------------------------------------------------------
print("\n🤖 AKADEMİK ASİSTAN HAZIR (Çıkmak için 'q')")
while True:
    q = input("\nSoru Sor: ")
    if q.lower() == 'q': break
    try:
        print("⏳ Düşünüyor...")
        res = run_rag(q)
        print(f"\n📢 Cevap:\n{res}")
        print("-" * 50)
    except Exception as e:
        print(f"Hata: {e}")