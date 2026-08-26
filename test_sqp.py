import pyodbc

connection = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=CANER;"
    "DATABASE=AIPriceAgent;"
    "Trusted_Connection=yes;"
)

cursor = connection.cursor()

cursor.execute("""
    INSERT INTO products
    (id, name, price, url, gpu, ram, storage)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""",
    4,
    "TEST ÜRÜNÜ",
    99999,
    "https://example.com",
    "RTX 4060",
    "16 GB",
    "512 GB SSD"
)

connection.commit()

print("Ürün SQL Server'a eklendi!")

cursor.close()
connection.close()