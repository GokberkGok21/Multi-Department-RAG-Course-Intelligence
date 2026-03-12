# 🎓 Multi-Department RAG-Based Course Intelligence System

Bu proje, üniversite bünyesindeki farklı bölümlere ait ders bilgilerini doğal dil işleme (NLP) teknikleri kullanarak sorgulayan bir **RAG (Retrieval-Augmented Generation)** sistemidir. Kullanıcılar, ders içerikleri hakkında doğal dilde sorular sorabilir ve sistem en alakalı dersleri bularak akıllı cevaplar üretir.

## 🚀 Öne Çıkan Özellikler
- **Anlamsal Arama (Semantic Search):** Basit anahtar kelime eşleşmesi yerine, kullanıcının niyetini anlayan vektör tabanlı arama.
- **Vektör Veritabanı (FAISS):** Ders verilerini yüksek boyutlu vektör uzayında saklayarak saniyeler içinde en alakalı sonuçları getirme.
- **Google Gemini Entegrasyonu:** `text-embedding-004` modeli ile verileri anlamlandırma ve `Gemini-Flash` ile kullanıcıya doğal dilde cevap verme.
- **Çoklu Bölüm Desteği:** Meta veri etiketleme sayesinde bölümler arası karşılaştırma ve filtreleme yeteneği.

## 🛠 Kullanılan Teknolojiler
- **Dil:** Python
- **LLM & Embeddings:** Google Gemini AI
- **Vector Store:** FAISS (Facebook AI Similarity Search)
- **Framework:** LangChain
- **Veri Formatı:** JSON (Düzleştirilmiş ve normalize edilmiş ders verileri)

## 📦 Kurulum ve Çalıştırma

1. **Depoyu klonlayın:**
   ```bash
   git clone https://github.com/GokberkGok21/Multi-Department-RAG-Course-Intelligence
 2. Gerekli kütüphaneleri yükleyin:
    ```bash
    pip install -r requirements.txt
3. API Anahtarınızı ayarlayın:
   Proje dizininde bir .env dosyası oluşturun ve anahtarınızı ekleyin:
   GOOGLE_API_KEY=your_api_key_here
4. Vektör Veritabanını oluşturun:
   ```bash
   python create_db_gemini.py
5. Sistemi çalıştırın:
   ```bash
   python main_rag.py
