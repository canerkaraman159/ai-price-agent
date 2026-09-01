import io
import warnings
import pyodbc
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Arka planda başsız (headless) çizim motoru
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=UserWarning)

def get_db_connection():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=CANER;"
        "DATABASE=AIPriceAgent;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

def analyze_product_price(product_id: int):
    """
    Belirtilen ürünün fiyat geçmişini pandas ile çeker;
    min, max, ortalama ve yüzdelik değişimi hesaplar.
    """
    conn = get_db_connection()
    
    query = """
        SELECT price, checked_at 
        FROM price_history 
        WHERE product_id = ? 
        ORDER BY checked_at ASC
    """
    
    df = pd.read_sql(query, conn, params=[product_id])
    conn.close()

    if df.empty:
        return {"success": False, "message": "Fiyat geçmişi bulunamadı."}

    df["price"] = df["price"].astype(float)
    
    first_price = float(df["price"].iloc[0])
    latest_price = float(df["price"].iloc[-1])
    min_price = float(df["price"].min())
    max_price = float(df["price"].max())
    avg_price = float(df["price"].mean())
    
    price_change_pct = float(((latest_price - first_price) / first_price) * 100) if first_price > 0 else 0.0

    return {
        "success": True,
        "product_id": product_id,
        "record_count": int(len(df)),
        "first_price": round(first_price, 2),
        "latest_price": round(latest_price, 2),
        "min_price": round(min_price, 2),
        "max_price": round(max_price, 2),
        "avg_price": round(avg_price, 2),
        "change_percentage": round(price_change_pct, 2)
    }

def analyze_by_name(product_name: str):
    """
    Ürün adından eşleşen ürünü bulup fiyat analizini döndürür.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    words = product_name.strip().split()
    sql = "SELECT TOP 1 id, name FROM products WHERE 1=1"
    params = []
    for word in words:
        if len(word) > 2:
            sql += " AND name LIKE ?"
            params.append(f"%{word}%")
            
    cursor.execute(sql, params)
    product = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not product:
        return {"success": False, "message": f"'{product_name}' adında bir ürün bulunamadı."}
        
    analysis = analyze_product_price(product[0])
    analysis["product_name"] = product[1]
    return analysis

def generate_price_chart(product_id: int):
    """
    Ürünün zaman serisi fiyat grafiğini çizer ve RAM üzerindeki BytesIO nesnesi olarak döner.
    """
    conn = get_db_connection()
    query = """
        SELECT price, checked_at 
        FROM price_history 
        WHERE product_id = ? 
        ORDER BY checked_at ASC
    """
    df = pd.read_sql(query, conn, params=[product_id])
    
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    prod_row = cursor.fetchone()
    conn.close()

    if df.empty:
        return None

    product_name = prod_row[0] if prod_row else "Ürün"
    short_title = product_name[:40] + "..." if len(product_name) > 40 else product_name

    df["price"] = df["price"].astype(float)
    df["checked_at"] = pd.to_datetime(df["checked_at"])

    # Modern Dark Tema Çizimi
    fig, ax = plt.subplots(figsize=(9, 4.5), facecolor="#1e1e2e")
    ax.set_facecolor("#1e1e2e")

    ax.plot(
        df["checked_at"], 
        df["price"], 
        marker="o", 
        color="#89b4fa", 
        linewidth=2.5, 
        markersize=6,
        label="Fiyat (TL)"
    )

    ax.set_title(f"Fiyat Geçmişi: {short_title}", color="#cdd6f4", fontsize=13, pad=15, fontweight="bold")
    ax.tick_params(colors="#a6adc8", labelsize=9)
    ax.grid(True, linestyle="--", alpha=0.25, color="#6c7086")

    for spine in ax.spines.values():
        spine.set_color("#45475a")

    plt.xticks(rotation=20)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    plt.close(fig)

    return buf

def generate_chart_by_name(product_name: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    words = product_name.strip().split()
    sql = "SELECT TOP 1 id FROM products WHERE 1=1"
    params = []
    for word in words:
        if len(word) > 2:
            sql += " AND name LIKE ?"
            params.append(f"%{word}%")
            
    cursor.execute(sql, params)
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return None
    return generate_price_chart(row[0])