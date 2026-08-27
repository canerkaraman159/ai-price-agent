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
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=CANER;"
    "DATABASE=AIPriceAgent;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
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


print("📦 Takip edilen ürün sayısı:", len(tracked_products))


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
    # ÜRÜNÜN SON 2 FİYATINI AL
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


    # Henüz yeterli fiyat geçmişi yoksa geç
    if len(prices) < 2:

        print(
            f"⚠️ Ürün ID {product_id} için "
            f"yeterli fiyat geçmişi yok."
        )

        continue


    new_price = prices[0].price
    old_price = prices[1].price


    print("------------------------------")
    print(f"Ürün ID: {product_id}")
    print(f"Eski fiyat: {old_price:,} TL")
    print(f"Yeni fiyat: {new_price:,} TL")
    print(f"Hedef fiyat: {target_price:,} TL")
    print(f"Son bildirim fiyatı: {last_notified_price}")


    # ==================================================
    # FİYAT DÜŞTÜ MÜ?
    # ==================================================

    if new_price < old_price:

        drop = old_price - new_price

        print("📉 FİYAT DÜŞTÜ!")
        print(f"Düşüş: {drop:,} TL")


        # ==================================================
        # HEDEF FİYATA ULAŞILDI MI?
        # ==================================================

        if new_price <= target_price:

            print("🎯 HEDEF FİYATA ULAŞILDI!")


            # ==================================================
            # AYNI FİYAT İÇİN TEKRAR BİLDİRİM GÖNDERME
            # ==================================================

            if last_notified_price == new_price:

                print(
                    "⚠️ Bu fiyat için bildirim zaten gönderilmiş."
                )

                continue


            # ==================================================
            # TELEGRAM MESAJI
            # ==================================================

            message = (
                "🚨 FİYAT ALARMI!\n\n"
                f"Ürün ID: {product_id}\n\n"
                f"📉 Eski fiyat: {old_price:,} TL\n"
                f"💰 Yeni fiyat: {new_price:,} TL\n"
                f"🎯 Hedef fiyat: {target_price:,} TL\n\n"
                f"💵 Tasarruf: {drop:,} TL"
            )


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


            print(
                "✅ Son bildirim fiyatı SQL'e kaydedildi."
            )


        else:

            print(
                "ℹ️ Fiyat düştü fakat henüz hedef fiyata ulaşmadı."
            )


    else:

        print("➡️ Fiyat düşmedi.")


# ==================================================
# BAĞLANTILARI KAPAT
# ==================================================

cursor.close()
connection.close()


print("\n✅ Fiyat kontrolü tamamlandı.")