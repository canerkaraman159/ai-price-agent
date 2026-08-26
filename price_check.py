import os
import asyncio
import pyodbc

from dotenv import load_dotenv
from telegram import Bot


# ==================================================
# ENV
# ==================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = Bot(token=TELEGRAM_BOT_TOKEN)


# ==================================================
# SQL SERVER BAĞLANTISI
# ==================================================

connection = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=CANER;"
    "DATABASE=AIPriceAgent;"
    "Trusted_Connection=yes;"
)

cursor = connection.cursor()


# ==================================================
# TELEGRAM BİLDİRİM FONKSİYONU
# ==================================================

async def send_notification(chat_id, message):

    await bot.send_message(
        chat_id=chat_id,
        text=message
    )


# ==================================================
# TAKİP EDİLEN ÜRÜNLERİ GETİR
# ==================================================

cursor.execute("""
    SELECT
        id,
        product_id,
        target_price,
        chat_id,
        active,
        last_notified_price
    FROM tracked_products
    WHERE active = 1
""")

tracked_products = cursor.fetchall()

print(tracked_products)


# ==================================================
# ÜRÜNLERİ KONTROL ET
# ==================================================

for tracked in tracked_products:

    tracking_id = tracked.id
    product_id = tracked.product_id
    target_price = tracked.target_price
    chat_id = tracked.chat_id
    last_notified_price = tracked.last_notified_price


    # ==================================================
    # ÜRÜNÜN ESKİ VE YENİ FİYATINI AL
    # ==================================================

    cursor.execute("""
        SELECT TOP 2
            price,
            checked_at
        FROM price_history
        WHERE product_id = ?
        ORDER BY checked_at DESC
    """, product_id)

    prices = cursor.fetchall()


    if len(prices) < 2:
        continue


    new_price = prices[0].price
    old_price = prices[1].price


    print("------------------------------")
    print(f"Ürün ID: {product_id}")
    print(f"Eski fiyat: {old_price}")
    print(f"Yeni fiyat: {new_price}")
    print(f"Hedef fiyat: {target_price}")
    print(f"Son bildirim fiyatı: {last_notified_price}")
    print(f"Chat ID: {chat_id}")


    # ==================================================
    # FİYAT DÜŞTÜ MÜ?
    # ==================================================

    if new_price < old_price:

        drop = old_price - new_price

        print("FİYAT DÜŞTÜ!")
        print(f"Düşüş: {drop}")


        # ==================================================
        # HEDEF FİYATA ULAŞILDI MI?
        # ==================================================

        if new_price <= target_price:

            print("HEDEF FİYATA ULAŞILDI!")


            # ==================================================
            # AYNI FİYAT İÇİN TEKRAR BİLDİRİM GÖNDERME
            # ==================================================

            if last_notified_price == new_price:

                print("⚠️ Bu fiyat için bildirim zaten gönderilmiş.")
                print("📭 Yeni bildirim gönderilmeyecek.")

                continue


            # ==================================================
            # TELEGRAM MESAJI
            # ==================================================

            message = f"""
📉 FİYAT DÜŞTÜ!

Ürün ID: {product_id}

Eski fiyat: {old_price:,} TL
Yeni fiyat: {new_price:,} TL
Hedef fiyat: {target_price:,} TL

💰 Tasarruf: {old_price - new_price:,} TL
"""


            # ==================================================
            # TELEGRAM BİLDİRİMİ
            # ==================================================

            asyncio.run(
                send_notification(
                    chat_id,
                    message
                )
            )


            print("📩 Telegram bildirimi gönderildi!")


            # ==================================================
            # SON BİLDİRİM FİYATINI KAYDET
            # ==================================================

            cursor.execute("""
                UPDATE tracked_products
                SET last_notified_price = ?
                WHERE id = ?
            """,
                new_price,
                tracking_id
            )

            connection.commit()

            print("✅ Son bildirim fiyatı SQL'e kaydedildi.")


# ==================================================
# BAĞLANTILARI KAPAT
# ==================================================

cursor.close()
connection.close()

print("✅ Fiyat kontrolü tamamlandı.")