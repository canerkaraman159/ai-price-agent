# AI Laptop Price Tracker & Advisor

Telegram üzerinden çalışan, Google Shopping verilerini SerpApi ile çekip donanım özelliklerine göre filtreleyen ve fiyat geçmişini takip eden bir bot projesi. 

Kullanıcının doğal dilde yazdığı istekleri Gemini Function Calling ile ayrıştırır, SQL Server üzerinde saklar ve fiyat değişimlerini analiz eder.

## Ne İşe Yarar?

- **Doğal Dil Filtreleme:** "50k altına 32 GB RAM'li 4060 laptop" gibi mesajlardan bütçe ve donanım kriterlerini ayıklar.
- **Donanım Ayrıştırma:** İlan başlıklarından GPU, CPU, RAM, SSD ve ekran yenileme hızı (Hz) gibi teknik detayları regex ile çeker.
- **Fiyat Geçmişi & Grafik:** Ürünün zaman içindeki fiyat hareketlerini Pandas ile analiz eder, Matplotlib ile çizilen grafiği diske kaydetmeden bellek üzerinden Telegram'a yollar.
- **Arka Plan Takibi:** Takip listesine alınan ürünlerin fiyatını Telegram JobQueue ile periyodik kontrol edip hedef fiyata düştüğünde uyarı mesajı atar.
- **Model Kıyaslama:** İki farklı laptop sorulduğunda donanım ve fiyat farklarını yan yana getirerek özet bir değerlendirme sunar.

## Kullanılan Teknolojiler

- Python 3.11+
- Google Gemini API (Function Calling)
- Microsoft SQL Server (`pyodbc`)
- SerpApi (Google Shopping)
- python-telegram-bot
- Pandas & Matplotlib
