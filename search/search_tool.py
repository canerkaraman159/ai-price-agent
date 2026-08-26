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


# ==================================================
# ÜRÜN ARAMA
# ==================================================

def search_products(max_price: int, gpu: str):

    query = f"{gpu} gaming laptop"

    print(f"🔎 SerpApi aranıyor: {query}")
    print(f"💰 Maksimum fiyat: {max_price}")


    # ==================================================
    # SERPAPI
    # ==================================================

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


    products = []


    # ==================================================
    # ÜRÜNLERİ İŞLE
    # ==================================================

    for product in shopping_results:

        price = product.get("extracted_price")

        if price is None:
            continue

        if price > max_price:
            continue


        name = product.get("title")

        print("ÜRÜN ADI:", name)
        print("ARAMANAN GPU:", gpu)


        # ==================================================
        # GPU KONTROLÜ
        # ==================================================

        normalized_gpu = gpu.lower().replace(" ", "")
        normalized_name = name.lower().replace(" ", "")

        if normalized_gpu not in normalized_name:

            print("❌ GPU eşleşmedi, ürün atlandı.")

            continue


        # ==================================================
        # ÜRÜN BİLGİLERİ
        # ==================================================

        source = product.get("source")

        product_link = product.get("product_link")
        normal_link = product.get("link")
        merchant_link = product.get("merchant_link")


        print("------------------------------")
        print("SOURCE:", source)
        print("PRODUCT LINK:", product_link)
        print("LINK:", normal_link)
        print("MERCHANT LINK:", merchant_link)


        # ==================================================
        # URL SEÇ
        # ==================================================

        url = product_link


        # Eğer product_link yoksa
        # diğer link alanlarını dene

        if not url:
            url = merchant_link

        if not url:
            url = normal_link


        # ==================================================
        # SQL'DE ÜRÜN VAR MI?
        # ==================================================

        cursor.execute("""
            SELECT id
            FROM products
            WHERE name = ?
        """, (name,))


        existing_product = cursor.fetchone()


        # ==================================================
        # ÜRÜN ZATEN VARSA
        # ==================================================

        if existing_product:

            product_id = existing_product[0]

            print("------------------------------")
            print("Ürün zaten var.")
            print("ID:", product_id)
            print("Ürün:", name)


            # ------------------------------------------
            # URL BOŞSA GÜNCELLE
            # ------------------------------------------

            if url:

                cursor.execute("""
                    UPDATE products
                    SET url = ?
                    WHERE id = ?
                """,
                    url,
                    product_id
                )


        # ==================================================
        # YENİ ÜRÜN
        # ==================================================

        else:

            cursor.execute("""
                SELECT ISNULL(MAX(id), 0) + 1
                FROM products
            """)


            product_id = cursor.fetchone()[0]


            cursor.execute("""
                INSERT INTO products
                (
                    id,
                    name,
                    price,
                    url,
                    gpu,
                    ram,
                    storage
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                product_id,
                name,
                price,
                url,
                gpu,
                None,
                None
            )


            print("------------------------------")
            print("Yeni ürün SQL'e eklendi.")
            print("ID:", product_id)
            print("Ürün:", name)
            print("Fiyat:", price)
            print("URL:", url)


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
            price
        )


        # ==================================================
        # GEMINI'YE GÖNDERİLECEK VERİ
        # ==================================================

        products.append({
            "id": product_id,
            "name": name,
            "price": price,
            "source": source,
            "url": url
        })


    # ==================================================
    # SQL DEĞİŞİKLİKLERİNİ KAYDET
    # ==================================================

    connection.commit()


    # ==================================================
    # SONUÇ
    # ==================================================

    print("\n✅ Arama tamamlandı.")
    print(f"📦 {len(products)} ürün bulundu.")


    return {
        "products": products
    }