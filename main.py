import os
import json
import pyodbc

from dotenv import load_dotenv
from google import genai


# .env dosyasını yükle
load_dotenv()


# Gemini bağlantısı
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


# SQL Server bağlantısı
connection = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=CANER;"
    "DATABASE=AIPriceAgent;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

print("SQL Server bağlantısı başarılı!")


# SQL sorguları için cursor
cursor = connection.cursor()


# SQL Server'daki products tablosunu test et
cursor.execute("""
    SELECT *
    FROM products
""")

rows = cursor.fetchall()

for row in rows:
    print(row)


# Ürün arama tool'u
def search_products(max_price: int, gpu: str):

    print(f"🔎 Ürün aranıyor: {gpu}, maksimum fiyat: {max_price}")

    cursor.execute("""
        SELECT
            id,
            name,
            price,
            url,
            gpu,
            ram,
            storage
        FROM products
        WHERE price <= ?
        AND gpu = ?
    """, (max_price, gpu))

    rows = cursor.fetchall()

    products = []

    for row in rows:
        products.append({
            "id": row.id,
            "name": row.name,
            "price": row.price,
            "url": row.url,
            "gpu": row.gpu,
            "ram": row.ram,
            "storage": row.storage
        })

    return {
        "products": products
    }


# Gemini'ye tool'u tanıtıyoruz
search_products_tool = {
    "type": "function",
    "name": "search_products",
    "description": "Gaming laptop ve diğer ürünleri veritabanında arar.",
    "parameters": {
        "type": "object",
        "properties": {
            "gpu": {
                "type": "string",
                "description": "Aranan ekran kartı. Örneğin RTX 4060."
            },
            "max_price": {
                "type": "integer",
                "description": "Ürünün aşmaması gereken maksimum fiyat."
            }
        },
        "required": ["gpu", "max_price"]
    }
}


# Kullanıcı isteği
user_message = "50 bin TL altında RTX 4060 gaming laptop bul."


# Gemini ile etkileşim
interaction = client.interactions.create(
    model="gemini-3.6-flash",
    input=user_message,
    tools=[search_products_tool]
)


# Gemini'nin tool çağrısını kontrol et
for step in interaction.steps:

    if step.type == "function_call":

        print("🤖 Gemini şu tool'u çağırmak istedi:")
        print(step.name)

        print("📦 Gönderdiği parametreler:")
        print(step.arguments)

        # Gemini'nin gönderdiği parametreleri al
        max_price = step.arguments["max_price"]
        gpu = step.arguments["gpu"]

        # SQL Server'dan ürünleri getir
        result = search_products(max_price, gpu)

        print("🔧 Tool çalıştı!")

        print("📦 Tool sonucu:")
        print(result)

        # Tool sonucunu Gemini'ye geri gönder
        final_interaction = client.interactions.create(
            model="gemini-3.6-flash",
            previous_interaction_id=interaction.id,
            input=[
                {
                    "type": "function_result",
                    "name": step.name,
                    "call_id": step.id,
                    "result": result
                }
            ]
        )

        print("\n🤖 Gemini'nin son cevabı:")
        print(final_interaction.output_text)