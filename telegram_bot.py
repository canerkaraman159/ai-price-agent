import os
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
# YARDIMCI FONKSİYON: EN UYGUN LİNKİ VE MAĞAZAYI ÇIKAR
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

# ==================================================
# SERPAPI + SQL CANLI ARAMA VE KAYIT FONKSİYONU
# ==================================================

def fetch_and_save_products(query: str = None, gpu: str = None, ram: str = None, min_price: int = None, max_price: int = None, limit: int = 10):
    conn = get_db_connection()
    cursor = conn.cursor()

    search_keywords = []
    if query and query.lower().strip() not in ["laptop", "gaming laptop", "bilgisayar"]:
        search_keywords.append(query)
    if gpu:
        search_keywords.append(gpu)
    if ram:
        search_keywords.append(ram)
    
    serp_query = " ".join(search_keywords) if search_keywords else "gaming laptop"
    if "laptop" not in serp_query.lower():
        serp_query += " laptop"

    # Kullanıcı daha fazla ürün istiyorsa SerpApi num değerini de artırıyoruz
    serp_num = max(25, limit * 2)
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

    # 2. Ürünleri SQL Server'a Kaydetme / Güncelleme
    for item in shopping_results:
        title = item.get("title")
        price = item.get("extracted_price")
        store_name, link = extract_store_info(item)

        if not title or price is None:
            continue

        extracted_gpu = None
        for g in ["5090", "5080", "5070", "5060", "5050", "4090", "4080", "4070", "4060", "4050", "3050", "3060", "2050"]:
            if f"rtx {g}" in title.lower() or f"rtx{g}" in title.lower() or g in title:
                extracted_gpu = f"RTX {g}"
                break

        extracted_ram = None
        for r in ["8 gb", "16 gb", "32 gb", "64 gb", "8gb", "16gb", "32gb", "64gb"]:
            if r in title.lower():
                extracted_ram = r.upper().replace("GB", " GB")
                break

        cursor.execute("SELECT id FROM products WHERE name = ?", (title,))
        existing = cursor.fetchone()

        if existing:
            product_id = existing[0]
            cursor.execute("UPDATE products SET price = ?, url = ? WHERE id = ?", (price, link, product_id))
        else:
            try:
                cursor.execute("""
                    INSERT INTO products (name, price, url, gpu, ram, storage)
                    OUTPUT INSERTED.id
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (title, price, link, extracted_gpu, extracted_ram, None))
                product_id = cursor.fetchone()[0]
            except Exception:
                cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM products")
                next_id = cursor.fetchone()[0]
                cursor.execute("""
                    INSERT INTO products (id, name, price, url, gpu, ram, storage)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (next_id, title, price, link, extracted_gpu, extracted_ram, None))
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

    # 3. İstenen Kriterlere ve Limite Göre Veritabanından Sonuçları Çekme
    final_limit = limit if limit and limit > 0 else 10
    sql = f"SELECT TOP {final_limit} id, name, price, url, gpu, ram FROM products WHERE 1=1"
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

    if query and query.lower().strip() not in ["laptop", "gaming laptop", "bilgisayar"]:
        words = query.strip().split()
        for word in words:
            if word.lower() not in ["laptop", "gaming"]:
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
            "ram": row.ram or "Belirtilmemiş"
        })

    cursor.close()
    conn.close()

    return {
        "searched_criteria": {
            "min_price": min_price,
            "max_price": max_price,
            "gpu": gpu,
            "ram": ram,
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
# SYSTEM INSTRUCTION & TOOLS
# ==================================================

SYSTEM_INSTRUCTION = """
Sen akıllı bir AI Fiyat Takip ve Alışveriş Danışmanısın.

Kullanıcının isteğini analiz et ve kriterleri search_products tool'una aktar.

FİYAT KURALLARI:
- "50k", "50 bin", "50.000 TL" = 50000 TL
- "50k altı" = max_price: 50000
- "30-55 bin arası" = min_price: 30000, max_price: 55000
- "55 bin civarı" = min_price: 50000, max_price: 60000

DONANIM KURALLARI:
- "RTX 4060" -> gpu: "RTX 4060"
- "RTX 5050" -> gpu: "RTX 5050"
- "16 GB RAM" -> ram: "16 GB"

SONUÇ SAYISI / LİMİT:
- Kullanıcı "10 tane göster", "daha fazla listele", "15 sonuç getir" gibi adet belirtirse limit parametresini ayarla. Belirtilmezse varsayılan 10'dur.

CEVAP VE LİNK BİÇİMLENDİRME KURALLARI:
1. Gelen bütün ürünleri eksiksiz listele.
2. Her ürünün linkini [Ürünü İncele](URL) formatında tıklanabilir olarak ekle.
3. Fiyatları Türkçe para birimi formatında sun (Örn: 40.999 TL).
4. Liste maddelerinde Ürün Adı, Fiyat, GPU, RAM ve İnceleme Linki yer alsın.
"""

search_products_tool = {
    "type": "function",
    "name": "search_products",
    "description": "Google Shopping üzerinde canlı ürün araması yapar, veritabanına kaydeder ve kriterlere uyanları listeler.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Model, marka veya genel arama adı (örn: Lenovo LOQ, MSI)."
            },
            "gpu": {
                "type": "string",
                "description": "Ekran kartı modeli (örn: RTX 4060, RTX 5050)."
            },
            "ram": {
                "type": "string",
                "description": "RAM miktarı (örn: 16 GB, 32 GB)."
            },
            "min_price": {
                "type": "integer",
                "description": "Minimum bütçe (TL)."
            },
            "max_price": {
                "type": "integer",
                "description": "Maksimum bütçe (TL)."
            },
            "limit": {
                "type": "integer",
                "description": "Listelenecek maksimum ürün sayısı (varsayılan: 10)."
            }
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
            "product_name": {
                "type": "string",
                "description": "Takip edilecek ürünün adı veya modeli."
            },
            "target_price": {
                "type": "integer",
                "description": "Hedef fiyat (TL)."
            }
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
            "product_name": {
                "type": "string",
                "description": "Takipten çıkarılacak ürünün adı."
            }
        },
        "required": ["product_name"]
    }
}

ALL_TOOLS = [
    search_products_tool,
    track_product_tool,
    get_tracked_products_tool,
    untrack_product_tool
]

# ==================================================
# TELEGRAM BOT HANDLERS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    welcome_text = (
        "🤖 **AI Canlı Fiyat Takip Botu Hazır!**\n\n"
        f"📍 Chat ID: `{chat_id}`\n\n"
        "Örnek komutlar:\n"
        "• *30-55 bin arası RTX 5050 laptop bul (10 tane)*\n"
        "• *55 bin civarı 16 GB RAM RTX 4060 MSI laptop bul*\n"
        "• *Acer Nitro modelini 39.000 TL olunca takip et*\n"
        "• *Takip ettiğim ürünleri göster*"
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

                if tool_name == "search_products":
                    result = fetch_and_save_products(
                        query=args.get("query"),
                        gpu=args.get("gpu"),
                        ram=args.get("ram"),
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

                final_text = final_interaction.output_text or "Sonuçlar listelendi."
                try:
                    await update.message.reply_text(final_text, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(final_text)
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

if __name__ == "__main__":
    print("🤖 Canlı SerpApi + Gemini Telegram Botu Başlatıldı...")
    app.run_polling()