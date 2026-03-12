import os
import time
import json
import requests
import re
import sys
from bs4 import BeautifulSoup

# --- 1. PROJE YAPILANDIRMASI ---
# [cite_start]Hedef: Proje tanımında belirtilen hedef mühendislik bölümlerini tanımla[cite: 13].
# Anahtarlar yerel HTML dosya adlarına, değerler ise JSON çıktısında meta veri
# etiketleme için kullanılan resmi bölüm adlarına karşılık gelir.
FILES_MAP = {

"yazilim_muh_ders.html": "Software Engineering",  # [cite: 15]

"bilgisayar_muh_ders.html": "Computer Engineering",  # [cite: 16]

"elektrik_muh_ders.html": "Electrical and Electronics Engineering",  # [cite: 17]

"endustri_muh_ders.html": "Industrial Engineering"  # [cite: 18]
}

# Ağ Yapılandırması: Üniversite web sitesine erişirken hataları önlemek için SSL uyarılarını devre dışı bırak.
requests.packages.urllib3.disable_warnings()
# User-Agent başlığı, sunucu tarafından engellenmemek için gerçek bir tarayıcıyı simüle eder.
HEADERS = {"User-Agent": "Mozilla/5.0"}

# --- 2. KÜRESEL VERİ DEPOLAMA ---
# 'unique_courses', işlenen ders nesnelerini depolamak için ana veritabanıdır (Sözlük).
# Anahtar olarak 'course_code' kullanan bir sözlük kullanmak, mükerrer girişleri önler.
unique_courses = {}

# 'dept_semester_map' müfredat yapısını takip eder.
# Her bölüm için belirli yuvaların (HAVUZ veya SEÇMELİ gibi) hangi dönemde göründüğünü kaydeder.
# Örnek: Yazılım Mühendisliği -> 5. Dönem -> POOL 004
dept_semester_map = {dept: {"ELEC": []} for dept in FILES_MAP.values()}

# İlk yerel dosya ayrıştırması sırasında bulunan URL'leri depolamak için geçici kümeler.
found_pool_urls = set()
found_sfl_url = None

# --- 3. VERİ TEMİZLEME FİLTRELERİ ---
# [cite_start]Hedef: Veri İşleme ve Yapılandırma - Gereksiz metinlerin kaldırılması [cite: 33-34].
# Bazı web sayfaları gerçek ders adları yerine genel başlıklar döndürür.
# Bu liste, düşük kaliteli verileri filtrelemek için bir 'Kara Liste' görevi görür.
GENERIC_TITLES = [
    "COURSE INTRODUCTION AND APPLICATION INFORMATION",
    "DERS TANITIM VE UYGULAMA BİLGİLERİ",
    "COURSE INTRODUCTION",
    "DERS TANITIM BILGILERI",
    "NO DESCRIPTION",
    "NONE"
]


def get_course_details_from_web(url):
    """
    [cite_start]MODÜL: Web Kazıma Mantığı [cite: 21]

    İşlevsellik:
    1. Bir dersin belirli URL'sini ziyaret eder.
    2. İngilizce Ders Adını çıkarır (tutarsızlıkları ele alarak).
    3. Haftalık Konuları çıkarır (RAG bağlamı için kritik).
    4. Ders Açıklamasını çıkarır.
    """
    try:
        # Sayfanın İngilizce sürümünü yüklemek için URL'yi zorla.
        if "lang=en" not in url: url += "&lang=en"

        # Takılmayı önlemek için zaman aşımı ile HTTP GET isteği gönder.
        response = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if response.status_code != 200: return "Connection Error", "None", [], None

        soup = BeautifulSoup(response.content, "html.parser")
        english_name = None

        # --- STRATEJİ 1: Meta Veri Tablosundan İsim Çıkarma ---
        # "Course Name" içeren bir tablo hücresi ara. Bu genellikle en doğru kaynaktır.
        label_td = soup.find("td", string=re.compile(r"Course Name|Dersin Adı", re.IGNORECASE))
        if label_td:
            value_td = label_td.find_next_sibling("td")  # Bir sonraki hücredeki değeri al
            if value_td:
                candidate = value_td.get_text(strip=True)
                if len(candidate) > 2:
                    english_name = candidate

        # --- STRATEJİ 2: Başlığa (H1) Geri Dönüş ---
        # Tablo yöntemi başarısız olursa, ana sayfa başlığını (H1) ara.
        if not english_name:
            h1 = soup.find("h1")
            if h1:
                t = h1.get_text(strip=True)
                # Sadece ismi almak için "SE 302 - Software Engineering" ifadesini böl.
                candidate = t.split("-", 1)[1].strip() if "-" in t else t
                english_name = candidate

        # --- VERİ DOĞRULAMA ---
        # Çıkarılan ismin GENERIC_TITLES kara listesinde olup olmadığını kontrol et.
        # Eğer jenerik ise, müfredattaki orijinal ismi korumak için bunu at (None döndür).
        if english_name:
            clean_name = english_name.upper().strip()
            if any(g in clean_name for g in GENERIC_TITLES) or len(clean_name) < 3:
                english_name = None

                # --- İÇERİK ÇIKARMA: Açıklama ---
        # [cite_start]Ders açıklamasını/hedeflerini çıkar[cite: 26].
        full_desc = "No description."
        c_div = soup.find("div", class_="content")
        if c_div:
            # Anlamlı cümleler olacak kadar uzun paragrafları birleştir.
            ps = [p.get_text(strip=True) for p in c_div.find_all("p") if len(p.get_text(strip=True)) > 20]
            if ps: full_desc = "\n".join(ps)

        # --- İÇERİK ÇIKARMA: Haftalık Konular ---
        # [cite_start]Haftalık programı çıkar[cite: 29]. Bu, "Sinyal işlemeyi hangi ders kapsıyor?"
        # gibi soruları yanıtlamak için çok önemlidir (Konu Bazlı Arama).
        w_topics = []
        for tbl in soup.find_all("table"):
            rows = tbl.find_all("tr")
            if len(rows) > 10:  # Sezgisel Yöntem: Program tablosu genellikle uzundur (>10 satır).
                for r in rows[1:]:
                    cs = r.find_all("td")
                    if len(cs) >= 2:
                        week_num = cs[0].get_text(strip=True)
                        topic = cs[1].get_text(strip=True)
                        if topic and len(topic) > 2:
                            w_topics.append(f"Week {week_num}: {topic}")
                if w_topics: break

        return full_desc, "None", w_topics, english_name

    except Exception as e:
        return "Fetch Error", "None", [], None


def process_local_files():
    """
    [cite_start]MODÜL: Müfredat Yapısı Ayrıştırma [cite: 23]

    İşlevsellik:
    1. Yerel HTML dosyalarını okur (üniversite web sitesinden kaydedilmiş).
    2. Müfredatın 'iskeletini' oluşturur: hangi dersler hangi dönemde zorunlu/seçmeli.
    3. AKTS çıkarımını yönetir ve 'Yuva' (Slot) derslerini (POOL, ELEC) tespit eder.
    """
    global found_sfl_url
    print("1. Parsing Local HTML Files (Building Curriculum Skeleton)...")

    for filename, dept_name in FILES_MAP.items():
        if not os.path.exists(filename): continue

        # Türkçe karakterleri işlemek için dosyayı UTF-8 kodlamasıyla oku.
        with open(filename, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Tüm müfredat tablolarını bul (Güz/Bahar dönemleri).
        tables = soup.find_all("table", class_="curr")
        for table in tables:
            # --- META VERİ ÇIKARMA ---
            # [cite_start]Dönemi ve Türü Belirle (Zorunlu vs Seçmeli)[cite: 27, 31].
            title_td = table.find("td", class_="title")
            raw_semester = title_td.get_text(strip=True) if title_td else "Unknown"

            is_table_elective = "Seçmeli" in raw_semester or "Elective" in raw_semester
            status_str = "Elective" if is_table_elective else "Mandatory"

            # Dönem adlarını normalleştir (örn: "3. Yıl Güz" -> "3. Year Fall").
            sem_en = raw_semester.replace("Yıl", "Year").replace("Dönemi", "").replace("Güz", "Fall").replace("Bahar",
                                                                                                              "Spring").replace(
                "Seçmeli Dersler", "Electives").strip()

            # Dönem tablosundaki dersler arasında gezin.
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 7:  # Satırın yeterli sütuna sahip olduğundan emin ol (Kod, İsim, AKTS, vb.)
                    code_col = cols[0].get_text(strip=True)
                    if code_col in ["Kodu", "Code"] or len(code_col) < 2: continue  # Başlıkları atla

                    # Ders izlencesi bağlantısını çıkar
                    link_tag = cols[0].find("a")
                    raw_link = link_tag["href"] if link_tag else ""
                    if raw_link and not raw_link.startswith("http"):
                        raw_link = "https://ects.ieu.edu.tr/new/" + raw_link

                    # Havuz ve SFL sayfaları için özel URL'leri tespit et
                    if "sid=pool" in raw_link:
                        found_pool_urls.add(raw_link.replace("&lang=tr", "").replace("&lang=en", ""))
                    if "sid=sfl" in raw_link:
                        found_sfl_url = raw_link

                    course_name = cols[2].get_text(strip=True)
                    ects = cols[6].get_text(strip=True)  # AKTS'yi çıkar [cite: 30]

                    # --- YUVA (SLOT) MANTIĞI ---
                    # POOL 004, ELEC veya SFL gibi yer tutucu kodları ele al.
                    topics = []
                    is_slot = False

                    if code_col.startswith("POOL"):
                        dept_semester_map[dept_name][code_col] = sem_en
                        topics = ["Pool Requirement."]
                        status_str = "Mandatory"  # Havuzlar doldurulması gereken zorunlu yuvalardır.
                        is_slot = True
                    elif code_col.startswith("SFL"):
                        dept_semester_map[dept_name][code_col] = sem_en
                        topics = ["Language Requirement."]
                        status_str = "Mandatory"
                        is_slot = True
                    elif code_col.startswith("ELEC"):
                        # Teknik seçmeli dönemlerini takip et.
                        if sem_en not in dept_semester_map[dept_name]["ELEC"]:
                            dept_semester_map[dept_name]["ELEC"].append(sem_en)
                        topics = ["Technical Elective Slot."]
                        status_str = "Mandatory"
                        is_slot = True

                    # Daha iyi RAG geri alımı için bağlam dizesine AKTS ekle.
                    # Örnek bağlam: "Software Engineering : Mandatory (3. Year Fall)(6 ECTS)"
                    ects_suffix = f"({ects} ECTS)" if is_slot else ""
                    rel_str = f"{dept_name} : {status_str} ({sem_en}){ects_suffix}"

                    # --- VERİ TOPLAMA ---
                    # Ders varsa, yeni bölüm bilgisini ekle. Yoksa, yeni giriş oluştur.
                    if code_col in unique_courses:
                        if rel_str not in unique_courses[code_col]["departments"]:
                            unique_courses[code_col]["departments"].append(rel_str)
                    else:
                        unique_courses[code_col] = {
                            "course_code": code_col,
                            "course_name": course_name,
                            "ects": ects,
                            "syllabus_link": raw_link,
                            "weekly_topics": topics,
                            "departments": [rel_str]  # Bu dersi alan tüm bölümlerin listesi.
                        }


def expand_pool_page():
    """
    MODÜL: Dinamik İçerik Genişletme (Havuzlar)

    İşlevsellik:
    1. Önceki adımda bulunan 'Havuz' URL'lerini ziyaret eder.
    2. O havuzda bulunan gerçek derslerin listesini kazır.
    3. Bu dersleri, o Havuz gereksinimine sahip bölümlerle eşleştirir.
    """
    if not found_pool_urls: return
    print(f"\n2. Expanding Pool Courses (Fetching actual electives)...")

    for base in found_pool_urls:
        try:
            url = base + "&lang=en"
            resp = requests.get(url, headers=HEADERS, verify=False)
            soup = BeautifulSoup(resp.content, "html.parser")
            tbl = soup.find("table", class_="table-bordered") or soup.find("table")
            if not tbl: continue

            rows = tbl.find_all("tr")
            curr_pool = None
            is_generic = False

            for row in rows:
                txt = row.get_text(strip=True).upper()
                # Havuz Başlığını Tespit Et (örn: "POOL 004")
                pm = re.search(r"POOL\s*0*(\d+)", txt)

                # Bu satırın bir başlık satırı olup olmadığını kontrol et
                if len(row.find_all("td")) < 5 and len(txt) > 3:
                    if pm:
                        curr_pool = f"POOL {pm.group(1).zfill(3)}";
                        is_generic = False
                    elif "ELECTIVE" in txt:
                        curr_pool = "GENERIC";  # Genel teknik seçmeli dersler
                        is_generic = True
                    continue

                # Başlık altındaki gerçek ders satırlarını işle
                if curr_pool:
                    cols = row.find_all("td")
                    if len(cols) < 5: continue
                    code = cols[0].get_text(strip=True)
                    if len(code) < 3 or "CODE" in code: continue

                    # İlişki dizesini oluştur (Bölüm + Dönem)
                    rels = []
                    for dept, info in dept_semester_map.items():
                        if not is_generic and curr_pool in info:
                            # Belirli Havuzu (örn: POOL 004) Bölümle eşleştir
                            rels.append(f"{dept} : Elective ({curr_pool}) ({info[curr_pool]})")
                        elif is_generic and info["ELEC"]:
                            # Genel teknik seçmeli dersleri eşleştir
                            rels.append(f"{dept} : Elective ({', '.join(info['ELEC'])})")

                    if not rels: continue

                    # Ders ayrıntılarını kaydet
                    if code in unique_courses:
                        for r in rels:
                            if r not in unique_courses[code]["departments"]:
                                unique_courses[code]["departments"].append(r)
                    else:
                        link = "https://ects.ieu.edu.tr/new/" + cols[0].find("a")["href"] if cols[0].find("a") else ""
                        unique_courses[code] = {
                            "course_code": code,
                            "course_name": cols[2].get_text(strip=True),
                            "ects": cols[6].get_text(strip=True),
                            "syllabus_link": link,
                            "weekly_topics": [],
                            "departments": rels
                        }
        except:
            pass


def expand_sfl_page():
    """
    MODÜL: Dinamik İçerik Genişletme (Diller)

    İşlevsellik:
    1. Genel 'İkinci Yabancı Dil' kodlarını belirli dil dersleriyle eşleştirir.
    2. Örnek: SFL 101 -> GER 103 (Almanca), ITL 103 (İtalyanca), vb.
    """
    print("\n3. Expanding SFL Courses (Mapping languages)...")
    langs = ["GER", "FR", "ITL", "RUS", "SPN", "JPN", "CHN"]
    # Genel kodları gerçek veritabanı kodlarıyla eşleştirme
    l_map = {"101": "SFL 1013", "102": "SFL 1024", "201": "SFL 201", "202": "SFL 202"}
    base = "https://ects.ieu.edu.tr/new/syllabus.php"

    for lng in langs:
        for lvl, par in l_map.items():
            # Farklı numaralandırma kullanan Fransızca/İtalyanca için kodları ayarla
            real = lvl
            if lng in ["FR", "ITL"]:
                if lvl == "101":
                    real = "103"
                elif lvl == "102":
                    real = "104"

            cc = f"{lng} {real}"
            uc = f"{lng}+{real}"
            sp = "1" if int(lvl[-1]) % 2 != 0 else "2"  # Dönemi tahmin et
            lnk = f"{base}?section=se.cs.ieu.edu.tr&course_code={uc}&cer=&sem={sp}&lang=en"

            rels = []
            for d, i in dept_semester_map.items():
                if par in i: rels.append(f"{d} : Elective ({par}) ({i[par]})")
            if not rels: continue

            if cc in unique_courses:
                for r in rels:
                    if r not in unique_courses[cc]["departments"]:
                        unique_courses[cc]["departments"].append(r)
            else:
                unique_courses[cc] = {
                    "course_code": cc, "course_name": f"Second Foreign Lang ({cc})",
                    "ects": "4", "syllabus_link": lnk,
                    "weekly_topics": ["Lang Skills"], "departments": rels
                }


def fetch_details():
    """
    MODÜL: Derinlemesine Tarama

    İşlevsellik:
    1. Toplanan tüm derslerin listesi üzerinde gezinir.
    2. Her ders için 'get_course_details_from_web' işlevini çağırır.
    3. 'weekly_topics' ve 'course_name' alanlarını canlı web verileriyle günceller.
    """
    print(f"\n4. Fetching Deep Details (Objectives & Topics) for {len(unique_courses)} courses...")
    c = 0
    for k, v in unique_courses.items():
        c += 1
        # Halihazırda işlenmiş bir yer tutucu ise atla
        if any(k.startswith(x) for x in ["POOL", "SFL", "ELEC"]) and v["weekly_topics"]: continue

        # İlerleme çubuğunu yazdır
        sys.stdout.write(f"\r{c}/{len(unique_courses)} - {k:<10}")

        if v["syllabus_link"].startswith("http"):
            # Web'den ayrıntıları getir
            _, _, t, n = get_course_details_from_web(v["syllabus_link"])

            if t:  # Konular bulunursa, güncelle
                v["weekly_topics"] = t

            # Web'de geçerli bir isim bulunursa (jenerik olmayan), güncelle.
            if n:
                v["course_name"] = n

        # Sunucuya nazik olmak için bekle (Hız Sınırlaması)
        time.sleep(0.01)


if __name__ == "__main__":
    # --- ANA BORU HATTI (PIPELINE) YÜRÜTME ---
    process_local_files()  # Adım 1: Yerel dosyalardan İskelet oluştur
    expand_pool_page()  # Adım 2: Havuz Seçmeli Derslerini Getir
    expand_sfl_page()  # Adım 3: Dil Seçeneklerini Getir
    fetch_details()  # Adım 4: Konular için Derinlemesine Tara

    # [cite_start]Nihai yapılandırılmış veriyi JSON'a kaydet[cite: 32].
    with open("ieu_courses_v17_stable.json", "w", encoding="utf-8") as f:
        json.dump(list(unique_courses.values()), f, indent=4)
    print("\n✅ Scraper Completed! Data saved to 'ieu_courses_v17_stable.json'.")