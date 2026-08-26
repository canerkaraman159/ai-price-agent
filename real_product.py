import os
import pyodbc
import serpapi

from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# SERPAPI
# -----------------------------

api_key = os.getenv("SERPAPI_KEY")

client = serpapi.Client(api_key=api_key)


# -----------------------------
# SQL SERVER
# -----------------------------

connection = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=CANER;"
    "DATABASE=AIPriceAgent;"
    "Trusted_Connection=yes;"
)

cursor = connection.cursor()


# -----------------------------
# ÜRÜNLERİ SERPAPI'DEN AL
# -----------------------------

results = client.search({
    "engine": "google_shopping",
    "q": "RTX 4060 gaming laptop",
    "hl": "tr",
    "gl": "tr"
})

products = results.get("shopping_results", [])


# -----------------------------
# SQL'E EKLE
# -----------------------------

next_id = cursor.execute(
    "SELECT ISNULL(MAX(id), 0) + 1 FROM products"
).fetchone()[0]


for product in products[:5]:

    name = product.get("title")
    price = product.get("extracted_price")
    url = product.get("product_link")

    if not name or price is None:
        continue

    # Aynı ürün daha önce eklenmiş mi?
    cursor.execute(
        "SELECT id FROM products WHERE name = ?",
        name
    )

    existing_product = cursor.fetchone()

    if existing_product:

        product_id = existing_product[0]

        print("------------------------------")
        print("Ürün zaten var.")
        print("ID:", product_id)
        print("Ürün:", name)

    else:

        cursor.execute("""
            INSERT INTO products
            (id, name, price, url, gpu, ram, storage)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            next_id,
            name,
            price,
            url,
            None,
            None,
            None
        )

        product_id = next_id

        next_id += 1

        print("------------------------------")
        print("Yeni ürün eklendi.")
        print("ID:", product_id)
        print("Ürün:", name)
        print("Fiyat:", price)


    # -----------------------------
    # PRICE HISTORY
    # -----------------------------

    history_id = cursor.execute(
    "SELECT ISNULL(MAX(id), 0) + 1 FROM price_history"
).fetchone()[0]

cursor.execute("""
    INSERT INTO price_history
    (id, product_id, price, checked_at)
    VALUES (?, ?, ?, GETDATE())
""",
    history_id,
    product_id,
    price
)

connection.commit()

print("------------------------------")
print("İşlem tamamlandı!")

cursor.close()
connection.close()