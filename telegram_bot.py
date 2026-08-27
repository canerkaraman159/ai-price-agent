import os
import pyodbc

from dotenv import load_dotenv
from google import genai

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes
)

from search.search_tool import search_products


# ==================================================
# ENV
# ==================================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ==================================================
# GEMINI
# ==================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
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

print("SQL Server bağlantısı başarılı!")

cursor = connection.cursor()


# ==================================================
# SEARCH PRODUCTS TOOL
# ==================================================

search_products_tool = {
    "type": "function",
    "name": "search_products",
    "description": "Gaming laptop ve diğer ürünleri internet üzerinde arar.",
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
        "required": [
            "gpu",
            "max_price"
        ]
    }
}


# ==================================================
# TRACK PRODUCT TOOL
# ==================================================

track_product_tool = {
    "type": "function",
    "name": "track_product",
    "description": "Belirtilen ürünü hedef fiyatın altına düştüğünde haber vermek için takip listesine ekler.",
    "parameters": {
        "type": "object",
        "properties": {

            "product_name": {
                "type": "string",
                "description": "Takip edilmek istenen ürünün adı."
            },

            "target_price": {
                "type": "integer",
                "description": "Ürünün altına düştüğünde haber verilecek hedef fiyat."
            }

        },
        "required": [
            "product_name",
            "target_price"
        ]
    }
}


# ==================================================
# GET TRACKED PRODUCTS TOOL
# ==================================================

get_tracked_products_tool = {
    "type": "function",
    "name": "get_tracked_products",
    "description": "Kullanıcının aktif olarak takip ettiği ürünleri getirir.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}


# ==================================================
# UNTRACK PRODUCT TOOL
# ==================================================

untrack_product_tool = {
    "type": "function",
    "name": "untrack_product",
    "description": "Kullanıcının takip ettiği bir ürünü takipten çıkarır.",
    "parameters": {
        "type": "object",
        "properties": {

            "product_name": {
                "type": "string",
                "description": "Takipten çıkarılmak istenen ürünün adı."
            }

        },
        "required": [
            "product_name"
        ]
    }
}


# ==================================================
# /START
# ==================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    chat_id = update.effective_chat.id

    print("CHAT ID:", chat_id)

    await update.message.reply_text(
        f"🤖 AI Price Agent hazır!\n\n"
        f"Chat ID: {chat_id}\n\n"
        f"Örnek:\n"
        f"50.000 TL altında RTX 4060 laptop bul."
    )


# ==================================================
# TELEGRAM MESAJI
# ==================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_message = update.message.text
    chat_id = update.effective_chat.id

    print("\n📩 Telegram mesajı:")
    print(user_message)


    # ==================================================
    # GEMINI
    # ==================================================

    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=user_message,
        tools=[
            search_products_tool,
            track_product_tool,
            get_tracked_products_tool,
            untrack_product_tool
        ]
    )


    # ==================================================
    # TOOL ÇAĞRISINI KONTROL ET
    # ==================================================

    for step in interaction.steps:

        if step.type != "function_call":
            continue


        print("\n🤖 Gemini tool çağırdı:")
        print(step.name)

        print("📦 Parametreler:")
        print(step.arguments)


        # ==================================================
        # SEARCH PRODUCTS
        # ==================================================

        if step.name == "search_products":

            max_price = step.arguments["max_price"]
            gpu = step.arguments["gpu"]

            result = search_products(
                max_price=max_price,
                gpu=gpu
            )

            print("🔧 Tool çalıştı!")

            print("📦 SerpApi sonucu:")
            print(result)


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


            final_answer = final_interaction.output_text


            if not final_answer:

                final_answer = (
                    "Ürün araması tamamlandı fakat sonuç oluşturulamadı."
                )


            print("\n🤖 Gemini:")
            print(final_answer)


            await update.message.reply_text(
                final_answer
            )

            return


        # ==================================================
        # TRACK PRODUCT
        # ==================================================

        elif step.name == "track_product":

            product_name = step.arguments["product_name"]
            target_price = step.arguments["target_price"]


            print("📌 Takip isteği:")
            print("Ürün:", product_name)
            print("Hedef fiyat:", target_price)


            # ------------------------------------------
            # KULLANICI İSTEĞİNİ ANALİZ ET
            # ------------------------------------------

            request_lower = product_name.lower()

            wants_msi = "msi" in request_lower
            wants_cyborg = "cyborg" in request_lower
            wants_4050 = "4050" in request_lower
            wants_4060 = "4060" in request_lower


            # ------------------------------------------
            # TÜM ÜRÜNLERİ SQL'DEN AL
            # ------------------------------------------

            cursor.execute("""
                SELECT
                    id,
                    name,
                    price,
                    gpu
                FROM products
            """)

            all_rows = cursor.fetchall()


            # ------------------------------------------
            # ÜRÜN ADAYLARINI FİLTRELE
            # ------------------------------------------

            rows = []


            for row in all_rows:

                name_lower = row.name.lower()
                gpu_lower = (row.gpu or "").lower()


                # MSI isteniyorsa MSI olmalı
                if wants_msi:

                    if "msi" not in name_lower:
                        continue


                # Cyborg isteniyorsa Cyborg olmalı
                if wants_cyborg:

                    if "cyborg" not in name_lower:
                        continue


                # RTX 4050 isteniyorsa 4050 olmalı
                if wants_4050:

                    if (
                        "4050" not in name_lower
                        and "4050" not in gpu_lower
                    ):
                        continue


                # RTX 4060 isteniyorsa 4060 olmalı
                if wants_4060:

                    if (
                        "4060" not in name_lower
                        and "4060" not in gpu_lower
                    ):
                        continue


                rows.append(row)


            print("🔎 SQL ürün adayları:")


            for row in rows:

                print(
                    row.id,
                    row.name,
                    row.price,
                    row.gpu
                )


            # ------------------------------------------
            # EN UYGUN ÜRÜNÜ SEÇ
            # ------------------------------------------

            product = None


            # MSI + Cyborg + RTX4050
            if (
                wants_msi
                and wants_cyborg
                and wants_4050
            ):

                for row in rows:

                    name_lower = row.name.lower()

                    if (
                        "msi" in name_lower
                        and "cyborg" in name_lower
                        and "4050" in name_lower
                    ):

                        product = {
                            "id": row.id,
                            "name": row.name,
                            "price": row.price
                        }

                        break


            # ------------------------------------------
            # MSI + RTX4060
            # ------------------------------------------

            if product is None:

                if wants_msi and wants_4060:

                    for row in rows:

                        name_lower = row.name.lower()

                        if (
                            "msi" in name_lower
                            and "4060" in name_lower
                        ):

                            product = {
                                "id": row.id,
                                "name": row.name,
                                "price": row.price
                            }

                            break


            # ------------------------------------------
            # GENEL MSI ÜRÜNÜ
            # ------------------------------------------

            if product is None:

                if wants_msi:

                    for row in rows:

                        name_lower = row.name.lower()

                        if "msi" in name_lower:

                            product = {
                                "id": row.id,
                                "name": row.name,
                                "price": row.price
                            }

                            break


            # ------------------------------------------
            # GENEL ÜRÜN
            # ------------------------------------------

            if product is None:

                if rows:

                    row = rows[0]

                    product = {
                        "id": row.id,
                        "name": row.name,
                        "price": row.price
                    }


            print("🔎 Seçilen ürün:")
            print(product)


            # ------------------------------------------
            # ÜRÜN BULUNAMADI
            # ------------------------------------------

            if product is None:

                result = {
                    "success": False,
                    "message": "Ürün veritabanında bulunamadı."
                }


            else:

                product_id = product["id"]


                # --------------------------------------
                # ZATEN TAKİP EDİLİYOR MU?
                # --------------------------------------

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


                if existing_tracking:

                    result = {
                        "success": False,
                        "message": "Bu ürün zaten takip ediliyor."
                    }


                else:

                    # ----------------------------------
                    # TAKİP LİSTESİNE EKLE
                    # ----------------------------------

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


                    result = {
                        "success": True,
                        "product_id": product_id,
                        "product_name": product["name"],
                        "current_price": product["price"],
                        "target_price": target_price
                    }


            # ------------------------------------------
            # GEMINI'YE SONUCU GÖNDER
            # ------------------------------------------

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


            final_answer = final_interaction.output_text


            # ------------------------------------------
            # GEMINI BOŞ DÖNERSE
            # ------------------------------------------

            if not final_answer:

                if result.get("success"):

                    final_answer = (
                        f"✅ {result['product_name']} "
                        f"takip listesine eklendi!\n\n"
                        f"💰 Mevcut fiyat: "
                        f"{result['current_price']:,} TL\n"
                        f"🎯 Hedef fiyat: "
                        f"{result['target_price']:,} TL"
                    )

                else:

                    final_answer = result["message"]


            print("\n🤖 Gemini:")
            print(final_answer)


            await update.message.reply_text(
                final_answer
            )

            return


        # ==================================================
        # GET TRACKED PRODUCTS
        # ==================================================

        elif step.name == "get_tracked_products":

            print("📦 Takip edilen ürünler getiriliyor...")


            cursor.execute("""
                SELECT
                    tp.product_id,
                    p.name,
                    p.price,
                    tp.target_price
                FROM tracked_products tp
                JOIN products p
                    ON tp.product_id = p.id
                WHERE tp.chat_id = ?
                AND tp.active = 1
            """,
                chat_id
            )


            rows = cursor.fetchall()


            tracked_products = []


            for row in rows:

                tracked_products.append({
                    "product_id": row.product_id,
                    "name": row.name,
                    "price": row.price,
                    "target_price": row.target_price
                })


            result = {
                "products": tracked_products
            }


            print("📦 SQL takip sonucu:")
            print(result)


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


            final_answer = final_interaction.output_text


            if not final_answer:

                if tracked_products:

                    final_answer = (
                        "📦 Takip ettiğiniz ürünler:\n\n"
                    )


                    for product in tracked_products:

                        final_answer += (
                            f"💻 {product['name']}\n"
                            f"💰 Mevcut fiyat: "
                            f"{product['price']:,} TL\n"
                            f"🎯 Hedef fiyat: "
                            f"{product['target_price']:,} TL\n\n"
                        )


                else:

                    final_answer = (
                        "Şu anda takip ettiğiniz ürün bulunmuyor."
                    )


            print("\n🤖 Gemini:")
            print(final_answer)


            await update.message.reply_text(
                final_answer
            )

            return


        # ==================================================
        # UNTRACK PRODUCT
        # ==================================================

        elif step.name == "untrack_product":

            product_name = step.arguments["product_name"]


            print("📌 Takipten çıkarma isteği:")
            print("Ürün:", product_name)


            # ------------------------------------------
            # TAKİP EDİLEN ÜRÜNÜ BUL
            # ------------------------------------------

            cursor.execute("""
                SELECT
                    p.id,
                    p.name
                FROM products p
                INNER JOIN tracked_products tp
                    ON p.id = tp.product_id
                WHERE
                    tp.chat_id = ?
                    AND tp.active = 1
                    AND p.name LIKE ?
            """,
                chat_id,
                f"%{product_name}%"
            )


            product = cursor.fetchone()


            print("🔎 Takip edilen ürünler arasındaki sonuç:")


            if product:

                print({
                    "id": product.id,
                    "name": product.name
                })

            else:

                print(None)


            # ------------------------------------------
            # ÜRÜN BULUNAMADI
            # ------------------------------------------

            if product is None:

                result = {
                    "success": False,
                    "message": "Bu ürün şu anda takip edilmiyor."
                }


            else:

                product_id = product.id


                # ------------------------------------------
                # TAKİP KAYDINI BUL
                # ------------------------------------------

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


                tracking = cursor.fetchone()


                # ------------------------------------------
                # TAKİP EDİLMİYORSA
                # ------------------------------------------

                if tracking is None:

                    result = {
                        "success": False,
                        "message": "Bu ürün şu anda takip edilmiyor."
                    }


                else:

                    # --------------------------------------
                    # ACTIVE = 0
                    # --------------------------------------

                    cursor.execute("""
                        UPDATE tracked_products
                        SET active = 0
                        WHERE product_id = ?
                        AND chat_id = ?
                        AND active = 1
                    """,
                        product_id,
                        chat_id
                    )


                    connection.commit()


                    print("✅ Ürün takipten çıkarıldı!")


                    result = {
                        "success": True,
                        "product_name": product.name,
                        "product_id": product_id
                    }


            # ------------------------------------------
            # GEMINI'YE SONUCU GÖNDER
            # ------------------------------------------

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


            final_answer = final_interaction.output_text


            # ------------------------------------------
            # GEMINI BOŞ DÖNERSE
            # ------------------------------------------

            if not final_answer:

                if result.get("success"):

                    final_answer = (
                        f"✅ {result['product_name']} "
                        f"takipten çıkarıldı."
                    )

                else:

                    final_answer = result["message"]


            print("\n🤖 Gemini:")
            print(final_answer)


            await update.message.reply_text(
                final_answer
            )

            return


# ==================================================
# TELEGRAM BOT
# ==================================================

app = Application.builder().token(
    TELEGRAM_TOKEN
).build()


# ==================================================
# /START
# ==================================================

app.add_handler(
    CommandHandler(
        "start",
        start
    )
)


# ==================================================
# NORMAL MESAJLAR
# ==================================================

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    )
)


# ==================================================
# BOTU BAŞLAT
# ==================================================

print("🤖 AI Price Agent Telegram bot çalışıyor...")


if __name__ == "__main__":

    app.run_polling()