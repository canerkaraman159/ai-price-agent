import os
from dotenv import load_dotenv
import serpapi


load_dotenv()

api_key = os.getenv("SERPAPI_KEY")

client = serpapi.Client(api_key=api_key)

results = client.search({
    "engine": "google_shopping",
    "q": "RTX 4060 gaming laptop",
    "hl": "tr",
    "gl": "tr"
})

products = results.get("shopping_results", [])

for product in products[:10]:
    print("Ürün:", product.get("title"))
    print("Fiyat:", product.get("extracted_price"))
    print("Mağaza:", product.get("source"))
    print("Link:", product.get("product_link"))
    print("-" * 50)