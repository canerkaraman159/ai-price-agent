import os
import pyodbc
import serpapi
from dotenv import load_dotenv

# ==================================================
# ENV & API BAĞLANTILARI
# ==================================================

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

client = serpapi.Client(
    api_key=SERPAPI_KEY
)

# ==================================================
# SQL SERVER BAĞLANTISI
# ==================================================

connection = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=CANER;"
    "DATABASE=AIPriceAgent;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

cursor = connection.cursor()

print("SQL Server bağlantısı başarılı!")

# ==================================================
# TAKİP EDİLEN ÜRÜNLERİ AL
# ==================================================

cursor.execute("""
    SELECT DISTINCT
        p.id,
        p.name,
        p.price,
        p.gpu
    FROM products p
    INNER JOIN tracked_products tp
        ON p.id = tp.product_id
    WHERE tp.active = 1
""")

products = cursor.fetchall()
print(f"📦 Güncellenecek aktif takip edilen ürün sayısı: {len(products)}")

# ==================================================
# ÜRÜNLERİ GÜNCELLE
# ==================================================

for product in products:

    product_id = product.id
    product_name = product.name
    current_price = product.price
    gpu = product.gpu

    print("\n------------------------------")
    print("Ürün ID:", product_id)
    print("Ürün:", product_name)
    print("Mevcut Fiyat:", current_price)
    print("GPU:", gpu)

    # ==================================================
    # SERPAPI ARAMASI
    # ==================================================

    query = product_name

    print("🔎 SerpApi aranıyor:", query)

    try:
        results = client.search({
            "engine": "google_shopping",
            "q": query,
            "hl": "tr",
            "gl": "tr",
            "num": 10
        })

        shopping_results = results.get("shopping_results", [])

    except Exception as e:
        print(f"❌ SerpApi Hatası: {e}")
        continue

    if not shopping_results:
        print("❌ SerpApi'de ürün bulunamadı.")
        continue

    # ==================================================
    # DOĞRU ÜRÜNÜ BUL (KELİME EŞLEŞTİRME FİLTRESİ)
    # ==================================================

    new_price = None
    normalized_product_name = product_name.lower()
    words = [w for w in normalized_product_name.split() if len(w) >= 4]

    for result in shopping_results:

        title = result.get("title")

        if not title:
            continue

        normalized_title = title.lower()

        # Ürün adındaki 4 harf ve üzeri önemli kelimeleri say
        match_count = 0
        for word in words:
            if word in normalized_title:
                match_count += 1

        # En az 3 kelime uyuşuyorsa veya kelime sayısı azsa çoğunluğu eşleşiyorsa kabul et
        required_matches = min(3, len(words))
        if match_count >= required_matches:

            price = result.get("extracted_price")

            if price is not None:
                new_price = price
                print("✅ Eşleşen Ürün:", title)
                print("💰 Yeni Fiyat:", new_price)
                break

    # ==================================================
    # UYGUN ÜRÜN BULUNAMADI
    # ==================================================

    if new_price is None:
        print("❌ Uygun ürün eşleşmesi bulunamadı.")
        continue

    # ==================================================
    # PRICE HISTORY (GEÇMİŞE EKLE)
    # ==================================================

    try:
        cursor.execute("""
            INSERT INTO price_history
            (
                product_id,
                price,
                checked_at
            )
            VALUES (?, ?, GETDATE())
        """,
            product_id,
            float(new_price)
        )
    except Exception:
        cursor.execute("SELECT ISNULL(MAX(id), 0) + 1 FROM price_history")
        history_id = cursor.fetchone()[0]
        cursor.execute("""
            INSERT INTO price_history
            (
                id,
                product_id,
                price,
                checked_at
            )
            VALUES (?, ?, ?, GETDATE())
        """,
            history_id,
            product_id,
            float(new_price)
        )

    # ==================================================
    # PRODUCTS TABLOSUNDAKİ FİYATI GÜNCELLE
    # ==================================================

    cursor.execute("""
        UPDATE products
        SET price = ?
        WHERE id = ?
    """,
        float(new_price),
        product_id
    )

    # ==================================================
    # KAYDET
    # ==================================================

    connection.commit()

    print("✅ Fiyat SQL Server'a kaydedildi!")


# ==================================================
# KAPAT
# ==================================================

cursor.close()
connection.close()

print("\n🏁 Tüm aktif ürünlerin fiyat güncellemesi tamamlandı.")