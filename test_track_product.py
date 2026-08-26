import pyodbc


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
# TAKİP BİLGİLERİ
# ==================================================

product_id = 17
target_price = 35000
chat_id = "2004172459"


# ==================================================
# DAHA ÖNCE TAKİP EDİLİYOR MU?
# ==================================================

cursor.execute("""
    SELECT id
    FROM tracked_products
    WHERE product_id = ?
      AND chat_id = ?
      AND active = 1
""",
    product_id,
    chat_id
)

existing_tracking = cursor.fetchone()


# ==================================================
# ZATEN TAKİP EDİLİYORSA
# ==================================================

if existing_tracking:

    print("⚠️ Bu ürün zaten takip ediliyor!")


# ==================================================
# TAKİP EDİLMİYORSA EKLE
# ==================================================

else:

    cursor.execute("""
        INSERT INTO tracked_products
        (
            product_id,
            target_price,
            chat_id,
            active
        )
        VALUES (?, ?, ?, ?)
    """,
        product_id,
        target_price,
        chat_id,
        1
    )

    connection.commit()

    print("✅ Ürün takip listesine eklendi!")


# ==================================================
# KONTROL
# ==================================================

cursor.execute("""
    SELECT
        id,
        product_id,
        target_price,
        chat_id,
        active
    FROM tracked_products
    WHERE product_id = ?
      AND chat_id = ?
""",
    product_id,
    chat_id
)

result = cursor.fetchall()


print("\n📦 Takip kaydı:")

for row in result:
    print(row)


# ==================================================
# BAĞLANTIYI KAPAT
# ==================================================

cursor.close()
connection.close()