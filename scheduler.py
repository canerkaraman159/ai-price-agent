import time
import subprocess
import sys
from datetime import datetime

# ==================================================
# OTOMATİK ZAMANLAYICI MOTORU
# ==================================================

CHECK_INTERVAL_SECONDS = 30 * 60  # 30 Dakika

def run_price_pipeline():
    while True:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("\n" + "=" * 50)
        print(f"🔄 [{now_str}] FİYAT KONTROL DÖNGÜSÜ BAŞLIYOR")
        print("=" * 50)

        # 1. Güncel Fiyatları Çek ve SQL'e İşle
        print("\n1️⃣ Adım: Güncel fiyatlar çekiliyor (update_prices.py)...")
        try:
            subprocess.run([sys.executable, "update_prices.py"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ update_prices.py çalışırken hata oluştu: {e}")

        # 2. Fiyat Düşüşlerini ve Hedefleri Kontrol Et, Bildirim Gönder
        print("\n2️⃣ Adım: Düşüşler kontrol ediliyor ve bildirim gönderiliyor (price_check.py)...")
        try:
            subprocess.run([sys.executable, "price_check.py"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ price_check.py çalışırken hata oluştu: {e}")

        # 3. Bekleme Süresi
        print("\n✅ Döngü tamamlandı.")
        print(f"⏳ Bir sonraki kontrole kadar {CHECK_INTERVAL_SECONDS // 60} dakika bekleniyor...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        run_price_pipeline()
    except KeyboardInterrupt:
        print("\n🛑 Zamanlayıcı kullanıcı tarafından durduruldu.")