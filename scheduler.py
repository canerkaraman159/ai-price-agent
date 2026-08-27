import time
import subprocess
import sys


while True:

    print("\n🔄 Fiyat kontrolü başlıyor...")

    # Fiyatları güncelle
    subprocess.run([
        sys.executable,
        "update_prices.py"
    ])


    # Fiyatları kontrol et
    subprocess.run([
        sys.executable,
        "price_check.py"
    ])


    print("\n⏰ Bir sonraki kontrol 30 dakika sonra...")


    # 30 dakika bekle
    time.sleep(30*60)