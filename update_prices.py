import os
import pyodbc
import serpapi

from dotenv import load_dotenv


# ==================================================
# ENV
# ==================================================

load_dotenv()

api_key = os.getenv("SERPAPI_KEY")

client = serpapi.Client(
    api_key=api_key
)


# ==================================================
# SQL SERVER
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
        p.gpu
    FROM products p
    INNER JOIN tracked_products tp
        ON p.id = tp.product_id
    WHERE tp.active = 1
""")

products = cursor.fetchall()


# ==================================================
# ÜRÜNLERİ GÜNCELLE
# ==================================================

for product in products:

    product_id = product.id
    product_name = product.name
    gpu = product.gpu

    print("------------------------------")
    print("Ürün ID:", product_id)
    print("Ürün:", product_name)
    print("GPU:", gpu)


    # ==================================================
    # SERPAPI ARAMASI
    # ==================================================

    query = product_name

    print("🔎 SerpApi aranıyor:", query)

    results = client.search({
        "engine": "google_shopping",
        "q": query,
        "hl": "tr",
        "gl": "tr"
    })


    shopping_results = results.get(
        "shopping_results",
        []
    )


    if not shopping_results:

        print("❌ Ürün bulunamadı.")
        continue


    # ==================================================
    # DOĞRU ÜRÜNÜ BUL
    # ==================================================

    new_price = None

    normalized_product_name = product_name.lower()

    for result in shopping_results:

        title = result.get("title")

        if not title:
            continue


        normalized_title = title.lower()

        print("Bulunan ürün:", title)


        # --------------------------------------------------
        # ÜRÜN ADINDAKİ ÖNEMLİ KELİMELERİ KONTROL ET
        # --------------------------------------------------

        words = normalized_product_name.split()

        match_count = 0

        for word in words:

            if len(word) >= 4 and word in normalized_title:

                match_count += 1


        # --------------------------------------------------
        # YETERLİ EŞLEŞME VARSA ÜRÜNÜ KABUL ET
        # --------------------------------------------------

        if match_count >= 3:

            price = result.get("extracted_price")

            if price is not None:

                new_price = price

                print("✅ Ürün eşleşti!")
                print("Yeni fiyat:", new_price)

                break


    # ==================================================
    # UYGUN ÜRÜN BULUNAMADI
    # ==================================================

    if new_price is None:

        print("❌ Uygun ürün eşleşmesi bulunamadı.")
        continue


    # ==================================================
    # PRICE HISTORY
    # ==================================================

    cursor.execute("""
        INSERT INTO price_history
        (
            product_id,
            price
        )
        VALUES (?, ?)
    """,
        product_id,
        int(new_price)
    )


    # ==================================================
    # PRODUCTS TABLOSUNDAKİ FİYATI GÜNCELLE
    # ==================================================

    cursor.execute("""
        UPDATE products
        SET price = ?
        WHERE id = ?
    """,
        int(new_price),
        product_id
    )


    # ==================================================
    # KAYDET
    # ==================================================

    connection.commit()


    print("✅ Fiyat güncellendi!")
    print("Ürün ID:", product_id)
    print("Yeni fiyat:", int(new_price))


# ==================================================
# KAPAT
# ==================================================

cursor.close()
connection.close()

print("\n✅ Tüm fiyatlar güncellendi.")