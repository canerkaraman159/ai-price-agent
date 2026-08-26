import time
import subprocess
import sys


# ==================================================
# OTOMATİK FİYAT TAKİP SİSTEMİ
# ==================================================

while True:

    print("\n" + "=" * 50)
    print("🔄 FİYAT KONTROLÜ BAŞLIYOR")
    print("=" * 50)


    # ==================================================
    # 1. GÜNCEL FİYATLARI ÇEK
    # ==================================================

    print("\n🔎 Güncel fiyatlar çekiliyor...")

    subprocess.run(
        [sys.executable, "update_prices.py"]
    )


    # ==================================================
    # 2. FİYAT KONTROLÜ
    # ==================================================

    print("\n📊 Fiyat değişimleri kontrol ediliyor...")

    subprocess.run(
        [sys.executable, "price_check.py"]
    )


    # ==================================================
    # 3. BEKLE
    # ==================================================

    print("\n✅ Kontrol tamamlandı.")
    print("\n⏳ 30 dakika bekleniyor...")

    time.sleep(1800)