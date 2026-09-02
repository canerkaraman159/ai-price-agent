import os
import re
import json
import pyodbc
from dotenv import load_dotenv
from google import genai
import serpapi

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes
)

# Analiz ve Grafik Motoru
from analysis import analyze_by_name, generate_price_chart

# ==================================================
# ENV & API BAĞLANTILARI
# ==================================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
serp_client = serpapi.Client(api_key=SERPAPI_KEY)

# ==================================================
# SQL SERVER BAĞLANTISI
# ==================================================

def get_db_connection():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=CANER;"
        "DATABASE=AIPriceAgent;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

# ==================================================
# YARDIMCI FONKSİYONLAR: ÖZELLİK ÇIKARIMI & LİNK
# ==================================================

def extract_store_info(item: dict):
    store_name = item.get("source") or "Google Shopping"
    
    direct_link = item.get("link")
    if direct_link and not direct_link.startswith("https://www.google.com"):
        return store_name, direct_link

    merchant = item.get("merchant") or {}
    if isinstance(merchant, dict):
        merchant_link = merchant.get("link")
        if merchant_link and not merchant_link.startswith("https://www.google.com"):
            return merchant.get("name", store_name), merchant_link

    prod_link = item.get("product_link")
    return store_name, (prod_link or direct_link or "")


def parse_laptop_specs(title: str):
    title_lower = title.lower()
    
    # 1. GPU
    extracted_gpu = None
    gpu_models = ["5090", "5080", "5070", "5060", "5050", "4090", "4080", "4070", "4060", "4050", "3050", "3060", "2050"]
    for g in gpu_models:
        if f"rtx {g}" in title_lower or f"rtx{g}" in title_lower:
            extracted_gpu = f"RTX {g}"
            break

    # 2. RAM
    extracted_ram = None
    ram_match = re.search(r'\b(8|16|24|32|64)\s*gb\b(?!\s*ssd|\s*m\.2)', title_lower)
    if ram_match:
        extracted_ram = f"{ram_match.group(1)} GB"

    # 3. Storage (SSD / HDD)
    extracted_storage = None
    storage_match = re.search(r'\b(256\s*gb|512\s*gb|1\s*tb|2\s*tb)\s*(?:ssd|m\.2|nvme)?\b', title_lower)
    if storage_match:
        val = storage_match.group(1).upper().replace(" ", "")
        extracted_storage = f"{val[:-2]} {val[-2:]}"

    # 4. CPU
    extracted_cpu = None
    cpu_intel = re.search(r'\b(i[3579]-?\d{4,5}[a-z]{0,2}|ultra\s*[579]\s*\d{3}[a-z]?)\b', title_lower)
    cpu_amd = re.search(r'\b(ryzen\s*[3579]\s*\d{4}[a-z]{0,2})\b', title_lower)
    if cpu_intel:
        extracted_cpu = cpu_intel.group(0).upper().replace("I", "i", 1)
    elif cpu_amd:
        extracted_cpu = cpu_amd.group(0).title()

    # 5. Refresh Rate (Hz)
    extracted_hz = None
    hz_match = re.search(r'\b(60|120|144|165|240|300|360)\s*hz\b', title_lower)
    if hz_match:
        extracted_hz = int(hz_match.group(1))

    # 6. Screen Size
    extracted_screen = None
    screen_match = re.search(r'\b(13\.3|14|15\.6|16|16\.1|17|17\.3)\s*(?:\'\'|\"|\s*in[cç]|\s*fhd|\s*qhd)?\b', title_lower)
    if screen_match:
        extracted_screen = f"{screen_match.group(1)}\""

    return {
        "gpu": extracted_gpu,
        "ram": extracted_ram,
        "storage": extracted_storage,
        "cpu": extracted_cpu,
        "refresh_rate": extracted_hz,
        "screen_size": extracted_screen
    }

# ==================================================
# SERPAPI + SQL CANLI ARAMA VE KAYIT FONKSİYONU
# ==================================================

def fetch_and_save_products(
    query: str = None, 
    gpu: str = None, 
    ram: str = None, 
    storage: str = None, 
    cpu: str = None, 
    refresh_rate: int = None, 
    screen_size: str = None, 
    min_price: int = None, 
    max_price: int = None, 
    limit: int = 10
):
    conn = get_db_connection()
    cursor = conn.cursor()

    search_keywords = []
    if query and query.lower().strip() not in ["laptop", "gaming laptop", "bilgisayar"]:
        search_keywords.append(query)
    if cpu:
        search_keywords.append(cpu)
    if gpu:
        search_keywords.append(gpu)
    if ram:
        search_keywords.append(ram)
    if storage:
        search_keywords.append(storage)
    if refresh_rate:
        search_keywords.append(f"{refresh_rate}Hz")

    serp_query = " ".join(search_keywords) if search_keywords else "gaming laptop"
    if "laptop" not in serp_query.lower() and "notebook" not in serp_query.lower():
        serp_query += " laptop"

    serp_num = max(40, limit * 4)
    print(f"🌐 SerpApi Google Shopping aranıyor: '{serp_query}' | Limit: {limit}")

    serp_params = {
        "engine": "google_shopping",
        "q": serp_query,
        "hl": "tr",
        "gl": "tr",
        "num": serp_num
    }

    try:
        results = serp_client.search(serp_params)
        shopping_results = results.get("shopping_results", [])
    except Exception as e:
        print(f"❌ SerpApi Hatası: {e}")
        shopping_results = []

    BANNED_SOURCES = [
        "amerikasepetim", "gshopper", "aliexpress", "temu", "ubuy", 
        "fruugo", "desertcart", "tiendamia", "fishpond", "ebay",
        "ciceksepeti", "çiçeksepeti", "easycep", "getmobil", "yenilenmis",
        "sahibinden", "letgo", "dolap", "gardrops"
    ]

    BLACKLIST_WORDS = [
        "ikinci el", "2. el", "2.el", "2.el.", "yenilenmiş", "refurbished", "outlet",
        "teşhir", "kullanılmış", "revizyon", "tamirli",
        "masaüstü", "kasa", "toplama", "hazır sistem", "monitör", "sıvı soğutma",
        "çanta", "adaptör", "klavye", "kulaklık", "stand", "soğutucu"
    ]

    for item in shopping_results:
        title = item.get("title", "")
        price = item.get("extracted_price")
        source = item.get("source", "").lower()
        store_name, link = extract_store_info(item)

        if not title or price is None:
            continue

        if any(banned in source for banned in BANNED_SOURCES) or any(banned in link.lower() for banned in BANNED_SOURCES):
            continue

        if "alternative_price" in item and item["alternative_price"].get("currency") in ["$", "€", "£"]:
            continue

        title_lower = title.lower()
        if any(bad_word in title_lower for bad_word in BLACKLIST_WORDS):
            continue

        specs = parse_laptop_specs(title)

        cursor.execute("SELECT id FROM products WHERE name = ?", (title,))
        existing = cursor.fetchone()

        if existing:
            product_id = existing[0]
            cursor.execute("""
                UPDATE products 
                SET price = ?, url = ?, gpu = ?, ram = ?, storage = ?, cpu = ?, refresh_rate = ?, screen_size = ?
                WHERE id = ?
            """, (price, link, specs["gpu"], specs["ram"], specs["storage"], specs["cpu"], specs["refresh_rate"], specs["screen_size"], product_id))
        else:
            try:
                cursor.execute("""
                    INSERT INTO products (name, price, url, gpu, ram, storage, cpu, refresh_rate, screen_size)
                    OUTPUT INSERTED.id
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (title, price, link, specs["gpu"], specs["ram"], specs["storage"], specs["cpu"], specs["refresh_rate"], specs["screen_size"]))
                product_id = cursor.fetchone()[0]
            except Exception:
                cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM products")
                next_id = cursor.fetchone()[0]
                cursor.execute("""
                    INSERT INTO products (id, name, price, url, gpu, ram, storage, cpu, refresh_rate, screen_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (next_id, title, price, link, specs["gpu"], specs["ram"], specs["storage"], specs["cpu"], specs["refresh_rate"], specs["screen_size"]))
                product_id = next_id

        try:
            cursor.execute("""
                INSERT INTO price_history (product_id, price, checked_at)
                VALUES (?, ?, GETDATE())
            """, (product_id, price))
        except Exception:
            cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM price_history")
            history_id = cursor.fetchone()[0]
            cursor.execute("""
                INSERT INTO price_history (id, product_id, price, checked_at)
                VALUES (?, ?, ?, GETDATE())
            """, (history_id, product_id, price))

    conn.commit()

    final_limit = limit if limit and limit > 0 else 10
    sql = f"""
        SELECT TOP {final_limit} 
            id, name, price, url, gpu, ram, storage, cpu, refresh_rate, screen_size 
        FROM products 
        WHERE 1=1
    """
    params = []

    if min_price is not None:
        sql += " AND price >= ?"
        params.append(min_price)

    if max_price is not None:
        sql += " AND price <= ?"
        params.append(max_price)

    if gpu:
        sql += " AND (gpu LIKE ? OR name LIKE ?)"
        params.extend([f"%{gpu}%", f"%{gpu}%"])

    if ram:
        sql += " AND (ram LIKE ? OR name LIKE ?)"
        params.extend([f"%{ram}%", f"%{ram}%"])

    if storage:
        sql += " AND (storage LIKE ? OR name LIKE ?)"
        params.extend([f"%{storage}%", f"%{storage}%"])

    if cpu:
        sql += " AND (cpu LIKE ? OR name LIKE ?)"
        params.extend([f"%{cpu}%", f"%{cpu}%"])

    if refresh_rate:
        sql += " AND refresh_rate >= ?"
        params.append(refresh_rate)

    if screen_size:
        sql += " AND (screen_size LIKE ? OR name LIKE ?)"
        params.extend([f"%{screen_size}%", f"%{screen_size}%"])

    if query and query.lower().strip() not in ["laptop", "gaming laptop", "bilgisayar"]:
        words = query.strip().split()
        for word in words:
            if word.lower() not in ["laptop", "gaming", "notebook"]:
                sql += " AND name LIKE ?"
                params.append(f"%{word}%")

    sql += " ORDER BY price ASC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    filtered_products = []
    for row in rows:
        filtered_products.append({
            "id": row.id,
            "name": row.name,
            "price": row.price,
            "url": row.url or "",
            "gpu": row.gpu or "Belirtilmemiş",
            "ram": row.ram or "Belirtilmemiş",
            "storage": row.storage or "Belirtilmemiş",
            "cpu": row.cpu or "Belirtilmemiş",
            "refresh_rate": f"{row.refresh_rate} Hz" if row.refresh_rate else "Belirtilmemiş",
            "screen_size": row.screen_size or "Belirtilmemiş"
        })

    cursor.close()
    conn.close()

    return {
        "searched_criteria": {
            "min_price": min_price,
            "max_price": max_price,
            "gpu": gpu,
            "ram": ram,
            "storage": storage,
            "cpu": cpu,
            "refresh_rate": refresh_rate,
            "screen_size": screen_size,
            "limit": final_limit
        },
        "products": filtered_products
    }


def db_track_product(product_name: str, target_price: int, chat_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    words = product_name.strip().split()
    sql = "SELECT TOP 1 id, name, price FROM products WHERE 1=1"
    params = []
    for word in words:
        if len(word) > 2:
            sql += " AND name LIKE ?"
            params.append(f"%{word}%")

    cursor.execute(sql, params)
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        return {
            "success": False,
            "message": f"'{product_name}' kriterine uygun ürün bulunamadı. Lütfen önce arama yapın."
        }

    product_id = product.id
    product_title = product.name
    current_price = product.price

    cursor.execute("""
        SELECT id FROM tracked_products
        WHERE product_id = ? AND chat_id = ? AND active = 1
    """, (product_id, chat_id))
    
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return {"success": False, "message": f"'{product_title}' zaten aktif takip listenizde bulunuyor."}

    try:
        cursor.execute("""
            INSERT INTO tracked_products (product_id, target_price, chat_id, active)
            VALUES (?, ?, ?, 1)
        """, (product_id, target_price, chat_id))
    except Exception:
        cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM tracked_products")
        track_id = cursor.fetchone()[0]
        cursor.execute("""
            INSERT INTO tracked_products (id, product_id, target_price, chat_id, active)
            VALUES (?, ?, ?, ?, 1)
        """, (track_id, product_id, target_price, chat_id))
    
    conn.commit()
    cursor.close()
    conn.close()

    return {
        "success": True,
        "product_id": product_id,
        "product_name": product_title,
        "current_price": current_price,
        "target_price": target_price
    }


def db_get_tracked_products(chat_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT tp.product_id, p.name, p.price, tp.target_price, p.url
        FROM tracked_products tp
        JOIN products p ON tp.product_id = p.id
        WHERE tp.chat_id = ? AND tp.active = 1
    """, (chat_id,))

    rows = cursor.fetchall()
    tracked = []
    for row in rows:
        tracked.append({
            "product_id": row.product_id,
            "name": row.name,
            "price": row.price,
            "target_price": row.target_price,
            "url": row.url or ""
        })

    cursor.close()
    conn.close()
    return {"products": tracked}


def db_untrack_product(product_name: str, chat_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT tp.id, p.id AS product_id, p.name
        FROM tracked_products tp
        JOIN products p ON tp.product_id = p.id
        WHERE tp.chat_id = ? AND tp.active = 1
    """, (chat_id,))

    all_tracked = cursor.fetchall()
    target_item = None

    search_term = product_name.lower().strip()
    for row in all_tracked:
        if search_term in row.name.lower():
            target_item = row
            break

    if not target_item:
        cursor.close()
        conn.close()
        return {
            "success": False, 
            "message": f"'{product_name}' adında aktif bir takip kaydınız bulunamadı."
        }

    cursor.execute("""
        UPDATE tracked_products
        SET active = 0
        WHERE id = ? AND chat_id = ?
    """, (target_item.id, chat_id))

    conn.commit()
    cursor.close()
    conn.close()

    return {
        "success": True,
        "product_name": target_item.name,
        "product_id": target_item.product_id
    }


# ==================================================
# 5. GÜN: İKİ ÜRÜNÜ KARŞILAŞTIRMA FONKSİYONU
# ==================================================

def db_compare_products(product_1: str, product_2: str):
    """
    Veritabanından iki farklı modelin donanım ve fiyat bilgilerini çeker.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    def find_one(p_name):
        words = p_name.strip().split()
        sql = "SELECT TOP 1 id, name, price, gpu, cpu, ram, storage, refresh_rate, screen_size, url FROM products WHERE 1=1"
        params = []
        for word in words:
            if len(word) > 2:
                sql += " AND name LIKE ?"
                params.append(f"%{word}%")
        cursor.execute(sql, params)
        return cursor.fetchone()

    p1_row = find_one(product_1)
    p2_row = find_one(product_2)

    cursor.close()
    conn.close()

    if not p1_row:
        return {"success": False, "message": f"'{product_1}' veritabanında bulunamadı. Lütfen önce aratın."}
    if not p2_row:
        return {"success": False, "message": f"'{product_2}' veritabanında bulunamadı. Lütfen önce aratın."}

    def format_prod(r):
        return {
            "id": r.id,
            "name": r.name,
            "price": r.price,
            "gpu": r.gpu or "Belirtilmemiş",
            "cpu": r.cpu or "Belirtilmemiş",
            "ram": r.ram or "Belirtilmemiş",
            "storage": r.storage or "Belirtilmemiş",
            "refresh_rate": f"{r.refresh_rate} Hz" if r.refresh_rate else "Belirtilmemiş",
            "screen_size": r.screen_size or "Belirtilmemiş",
            "url": r.url or ""
        }

    return {
        "success": True,
        "product_1": format_prod(p1_row),
        "product_2": format_prod(p2_row)
    }

# ==================================================
# SYSTEM INSTRUCTION & TOOLS
# ==================================================

SYSTEM_INSTRUCTION = """
Sen akıllı bir AI Donanım ve Fiyat Takip Danışmanısın.

Kullanıcının isteğini analiz et ve kriterleri uygun tool'lara aktar.

PARAMETRE KURALLARI:
- Fiyatlar: "50k altı" -> max_price: 50000, "30-55k arası" -> min_price: 30000, max_price: 55000
- GPU: "RTX 4060", "RTX 5050"
- RAM: "16 GB", "32 GB"
- Storage: "512 GB", "1 TB"
- CPU: "i7-13700H", "Ryzen 7 8845HS", "i5"
- Refresh Rate: "144 Hz" -> refresh_rate: 144, "165 Hz" -> refresh_rate: 165

KARŞILAŞTIRMA (compare_products) KURALLARI:
- compare_products çağrıldığında iki ürünü yan yana koyup teknik donanımlarını (İşlemci gücü, Ekran kartı, RAM, Hz ve Ekran boyutu) ve Fiyatlarını kıyasla.
- Hangisinin işlemcisinin/ekran kartının daha üstün olduğunu belirt.
- Fiyat farkına değip değmeyeceğini analiz et ve net bir "🏆 Hangisi Tercih Edilmeli?" sonucu ver.
- Her iki ürünün de satın alma linklerini ekle.

FİYAT ANALİZİ (analyze_price) KURALLARI:
- analyze_price çağrıldığında ilk fiyat, güncel fiyat, dip, tepe, ortalama ve % değişim değerlerini sunup mantıklı bir alışveriş tavsiyesi ver.

CEVAP BİÇİMLENDİRME:
- Linkleri [Ürünü İncele](URL) formatında tıklanabilir yap.
- Fiyatları Türkçe para birimi formatında sun (Örn: 42.500 TL).
"""

search_products_tool = {
    "type": "function",
    "name": "search_products",
    "description": "Google Shopping üzerinde detaylı kriterlerle canlı sıfır ürün araması yapar.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Model, marka veya genel arama adı."},
            "gpu": {"type": "string", "description": "Ekran kartı modeli."},
            "ram": {"type": "string", "description": "RAM miktarı."},
            "storage": {"type": "string", "description": "Depolama alanı."},
            "cpu": {"type": "string", "description": "İşlemci modeli veya serisi."},
            "refresh_rate": {"type": "integer", "description": "Minimum ekran yenileme hızı (Hz)."},
            "screen_size": {"type": "string", "description": "Ekran boyutu."},
            "min_price": {"type": "integer", "description": "Minimum bütçe (TL)."},
            "max_price": {"type": "integer", "description": "Maksimum bütçe (TL)."},
            "limit": {"type": "integer", "description": "Listelenecek maksimum ürün sayısı."}
        },
        "required": []
    }
}

track_product_tool = {
    "type": "function",
    "name": "track_product",
    "description": "Belirtilen ürünü hedef fiyata düştüğünde bildirim almak için takip listesine ekler.",
    "parameters": {
        "type": "object",
        "properties": {
            "product_name": {"type": "string", "description": "Takip edilecek ürünün adı veya modeli."},
            "target_price": {"type": "integer", "description": "Hedef fiyat (TL)."}
        },
        "required": ["product_name", "target_price"]
    }
}

get_tracked_products_tool = {
    "type": "function",
    "name": "get_tracked_products",
    "description": "Kullanıcının aktif takip listesindeki ürünleri listeler.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

untrack_product_tool = {
    "type": "function",
    "name": "untrack_product",
    "description": "Kullanıcının takip ettiği bir ürünü takipten çıkarır.",
    "parameters": {
        "type": "object",
        "properties": {
            "product_name": {"type": "string", "description": "Takipten çıkarılacak ürünün adı."}
        },
        "required": ["product_name"]
    }
}

analyze_price_tool = {
    "type": "function",
    "name": "analyze_price",
    "description": "Veritabanındaki bir ürünün geçmiş fiyat hareketlerini, min/max/ortalama fiyatlarını analiz eder.",
    "parameters": {
        "type": "object",
        "properties": {
            "product_name": {"type": "string", "description": "Fiyat geçmişi analiz edilecek ürünün adı veya modeli."}
        },
        "required": ["product_name"]
    }
}

compare_products_tool = {
    "type": "function",
    "name": "compare_products",
    "description": "Kullanıcının karşılaştırmak istediği iki farklı laptop modelini donanım özellikleri ve fiyatları açısından kıyaslar.",
    "parameters": {
        "type": "object",
        "properties": {
            "product_1": {"type": "string", "description": "Birinci laptop modelinin adı veya anahtar kelimesi."},
            "product_2": {"type": "string", "description": "İkinci laptop modelinin adı veya anahtar kelimesi."}
        },
        "required": ["product_1", "product_2"]
    }
}

ALL_TOOLS = [
    search_products_tool,
    track_product_tool,
    get_tracked_products_tool,
    untrack_product_tool,
    analyze_price_tool,
    compare_products_tool
]

# ==================================================
# OTOMATİK ARKA PLAN FİYAT KONTROL GÖREVİ (JOBQUEUE)
# ==================================================

async def auto_price_check(context: ContextTypes.DEFAULT_TYPE):
    print("\n⏰ [Zamanlayıcı] Takip edilen ürünler internette canlı taranıyor...")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT tp.id, tp.chat_id, tp.target_price, p.id, p.name, p.price, p.url
            FROM tracked_products tp
            JOIN products p ON tp.product_id = p.id
            WHERE tp.active = 1
        """)
        tracked_items = cursor.fetchall()

        if not tracked_items:
            print("ℹ️ Aktif takip edilen ürün bulunmuyor.")
            return

        for item in tracked_items:
            track_id = item[0]
            chat_id = item[1]
            target_price = item[2]
            product_id = item[3]
            product_name = item[4]
            old_price = item[5]
            current_url = item[6]

            print(f"🔍 Canlı taranıyor: {product_name[:35]}... (Mevcut DB: {old_price:,.0f} TL)")

            try:
                search_query = product_name[:60]
                serp_params = {
                    "engine": "google_shopping",
                    "q": search_query,
                    "hl": "tr",
                    "gl": "tr",
                    "num": 5
                }
                res = serp_client.search(serp_params)
                shopping_results = res.get("shopping_results", [])
            except Exception as e:
                print(f"❌ SerpApi canlı tarama hatası: {e}")
                continue

            live_price = None
            live_url = current_url

            for prod in shopping_results:
                price = prod.get("extracted_price")
                source = prod.get("source", "").lower()
                _, link = extract_store_info(prod)

                if price and price > 5000:
                    live_price = price
                    if link:
                        live_url = link
                    break

            if live_price:
                print(f"💰 Bulunan Canlı Fiyat: {live_price:,.0f} TL")
                
                cursor.execute("""
                    UPDATE products 
                    SET price = ?, url = ?
                    WHERE id = ?
                """, (live_price, live_url, product_id))

                try:
                    cursor.execute("""
                        INSERT INTO price_history (product_id, price, checked_at)
                        VALUES (?, ?, GETDATE())
                    """, (product_id, live_price))
                except Exception:
                    cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM price_history")
                    new_hist_id = cursor.fetchone()[0]
                    cursor.execute("""
                        INSERT INTO price_history (id, product_id, price, checked_at)
                        VALUES (?, ?, ?, GETDATE())
                    """, (new_hist_id, product_id, live_price))

                conn.commit()

                if live_price <= target_price:
                    alert_text = (
                        f"🔥 **FİYAT ALARMI! HEDEF FİYATA ULAŞILDI!**\n\n"
                        f"💻 **Ürün:** {product_name}\n"
                        f"🎯 **Hedef Fiyatınız:** {target_price:,.0f} TL\n"
                        f"📉 **Yeni Canlı Fiyat:** {live_price:,.0f} TL\n\n"
                        f"🔗 [Hemen Satın Al]({live_url})"
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=alert_text,
                            parse_mode="Markdown"
                        )
                        print(f"🔔 Kullanıcıya fiyat alarmı iletildi! ({chat_id})")
                    except Exception as e:
                        print(f"❌ Telegram bildirim hatası: {e}")

    except Exception as e:
        print(f"❌ Zamanlayıcı SQL hatası: {e}")
    finally:
        cursor.close()
        conn.close()

# ==================================================
# TELEGRAM BOT HANDLERS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    welcome_text = (
        "🤖 **Gelişmiş AI Laptop Danışmanı & Fiyat Takipçisi Hazır!**\n\n"
        "Neler yapabilirim?\n"
        "• *32 GB RAM, RTX 4060 laptop bul*\n"
        "• *Acer Nitro ile ERAZER modelini karşılaştır*\n"
        "• *Acer Nitro fiyat analizini göster*\n"
        "• *ERAZER modelini 33.000 TL olunca takip et*"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id

    print(f"\n📩 Gelen Mesaj ({chat_id}): {user_message}")

    try:
        interaction = gemini_client.interactions.create(
            model="gemini-3.6-flash",
            input=user_message,
            tools=ALL_TOOLS,
            system_instruction=SYSTEM_INSTRUCTION
        )

        has_tool_call = False

        for step in interaction.steps:
            if step.type == "function_call":
                has_tool_call = True
                tool_name = step.name
                args = step.arguments or {}

                print(f"🤖 Tool: {tool_name} | Parametreler: {args}")

                result = {}
                chart_product_id = None

                if tool_name == "search_products":
                    result = fetch_and_save_products(
                        query=args.get("query"),
                        gpu=args.get("gpu"),
                        ram=args.get("ram"),
                        storage=args.get("storage"),
                        cpu=args.get("cpu"),
                        refresh_rate=args.get("refresh_rate"),
                        screen_size=args.get("screen_size"),
                        min_price=args.get("min_price"),
                        max_price=args.get("max_price"),
                        limit=args.get("limit", 10)
                    )

                elif tool_name == "track_product":
                    result = db_track_product(
                        product_name=args.get("product_name", ""),
                        target_price=args.get("target_price", 0),
                        chat_id=chat_id
                    )

                elif tool_name == "get_tracked_products":
                    result = db_get_tracked_products(chat_id=chat_id)

                elif tool_name == "untrack_product":
                    result = db_untrack_product(
                        product_name=args.get("product_name", ""),
                        chat_id=chat_id
                    )

                elif tool_name == "analyze_price":
                    result = analyze_by_name(
                        product_name=args.get("product_name", "")
                    )
                    if result.get("success") and "product_id" in result:
                        chart_product_id = result["product_id"]

                elif tool_name == "compare_products":
                    result = db_compare_products(
                        product_1=args.get("product_1", ""),
                        product_2=args.get("product_2", "")
                    )

                final_interaction = gemini_client.interactions.create(
                    model="gemini-3.6-flash",
                    previous_interaction_id=interaction.id,
                    input=[
                        {
                            "type": "function_result",
                            "name": step.name,
                            "call_id": step.id,
                            "result": result
                        }
                    ],
                    system_instruction=SYSTEM_INSTRUCTION
                )

                final_text = final_interaction.output_text or "İşlem tamamlandı."
                try:
                    await update.message.reply_text(final_text, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(final_text)

                if chart_product_id:
                    try:
                        chart_buf = generate_price_chart(chart_product_id)
                        if chart_buf:
                            await update.message.reply_photo(
                                photo=chart_buf,
                                caption="📈 Fiyat Trend Grafiği"
                            )
                    except Exception as e:
                        print(f"❌ Grafik gönderme hatası: {e}")

                return

        if not has_tool_call:
            reply_text = interaction.output_text or "Nasıl yardımcı olabilirim?"
            await update.message.reply_text(reply_text)

    except Exception as e:
        print(f"❌ İşlem Hatası: {e}")
        await update.message.reply_text("İsteğiniz işlenirken bir sorun oluştu. Lütfen tekrar deneyin.")

# ==================================================
# BOTU ÇALIŞTIR
# ==================================================

app = Application.builder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

job_queue = app.job_queue
job_queue.run_repeating(auto_price_check, interval=1800, first=10)

if __name__ == "__main__":
    print("🤖 Gelişmiş Donanım Destekli Telegram Botu ve Zamanlayıcı Başlatıldı...")
    app.run_polling()