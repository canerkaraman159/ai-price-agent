from search_tool import search_products


results = search_products(
    max_price=50000,
    gpu="RTX 4060"
)

print("\nSONUÇLAR:")

for product in results["products"]:

    print("------------------------------")
    print("Ürün:", product["name"])
    print("Fiyat:", product["price"])
    print("Mağaza:", product["source"])
    print("Link:", product["url"])