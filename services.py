import re
from database import DB

CURRENT_USER_ID = None
PENDING_WARRANTY_ORDER = None
PENDING_WARRANTY_PRODUCTS = []


def set_current_user(user_id):
    global CURRENT_USER_ID
    CURRENT_USER_ID = user_id


def has_pending_warranty():
    return bool(PENDING_WARRANTY_ORDER) and bool(PENDING_WARRANTY_PRODUCTS)


def clear_pending_warranty():
    global PENDING_WARRANTY_ORDER, PENDING_WARRANTY_PRODUCTS
    PENDING_WARRANTY_ORDER = None
    PENDING_WARRANTY_PRODUCTS = []


def search_products(keyword):
    keyword = keyword.strip().lower()
    if not keyword:
        return []
    normalized = keyword.replace(" ", "")
    with DB.cursor() as cursor:
        cursor.execute(
            """SELECT item, name, price, stock_quantity
               FROM products
               WHERE LOWER(name) LIKE LOWER(%s)
                  OR LOWER(item) LIKE LOWER(%s)
                  OR REPLACE(LOWER(name), ' ', '') LIKE LOWER(%s)
               ORDER BY name""",
            (f"%{keyword}%", f"%{keyword}%", f"%{normalized}%"),
        )
        return cursor.fetchall()


def get_all_products():
    with DB.cursor() as cursor:
        cursor.execute("SELECT item, name, price, stock_quantity FROM products ORDER BY name")
        return cursor.fetchall()


def list_orders():
    if CURRENT_USER_ID is None:
        return []
    with DB.cursor() as cursor:
        cursor.execute(
            """SELECT order_number, status, placed_at
               FROM orders WHERE user_id = %s ORDER BY placed_at DESC""",
            (CURRENT_USER_ID,),
        )
        return cursor.fetchall()


def get_order_status(order_number):
    if CURRENT_USER_ID is None:
        return None
    with DB.cursor() as cursor:
        cursor.execute(
            """SELECT id, order_number, status, placed_at
               FROM orders WHERE user_id = %s AND order_number = %s""",
            (CURRENT_USER_ID, order_number),
        )
        order = cursor.fetchone()
        if not order:
            return None
        cursor.execute(
            """SELECT oi.item, oi.quantity, p.name
               FROM order_items oi JOIN products p ON p.item = oi.item
               WHERE oi.order_id = %s ORDER BY oi.id""",
            (order["id"],),
        )
        order["items"] = cursor.fetchall()
        return order


def track_delivery(order_number):
    if CURRENT_USER_ID is None:
        return None
    with DB.cursor() as cursor:
        cursor.execute(
            """SELECT id FROM orders
               WHERE user_id = %s AND order_number = %s""",
            (CURRENT_USER_ID, order_number),
        )
        order = cursor.fetchone()
        if not order:
            return None
        cursor.execute(
            """SELECT carrier, tracking_number, current_status, estimated_delivery_date
               FROM deliveries WHERE order_id = %s""",
            (order["id"],),
        )
        return cursor.fetchone()


def get_order_products(order_number):
    if CURRENT_USER_ID is None:
        return []
    with DB.cursor() as cursor:
        cursor.execute(
            """SELECT id FROM orders
               WHERE user_id = %s AND order_number = %s""",
            (CURRENT_USER_ID, order_number),
        )
        order = cursor.fetchone()
        if not order:
            return []
        cursor.execute(
            """SELECT oi.item, oi.quantity, p.name
               FROM order_items oi JOIN products p ON p.item = oi.item
               WHERE oi.order_id = %s ORDER BY oi.id""",
            (order["id"],),
        )
        return cursor.fetchall()


def get_warranty(order_number, item):
    if CURRENT_USER_ID is None:
        return None
    with DB.cursor() as cursor:
        cursor.execute(
            """SELECT id FROM orders
               WHERE user_id = %s AND order_number = %s""",
            (CURRENT_USER_ID, order_number),
        )
        order = cursor.fetchone()
        if not order:
            return None
        cursor.execute(
            """SELECT oi.id, oi.item, oi.quantity
               FROM order_items oi
               WHERE oi.order_id = %s AND oi.item = %s""",
            (order["id"], item),
        )
        item = cursor.fetchone()
        if not item:
            return None
        cursor.execute(
            """SELECT coverage_months, start_date
               FROM warranties WHERE order_item_id = %s""",
            (item["id"],),
        )
        warranty = cursor.fetchone()
        if not warranty:
            return None
        return {
            "item": item["item"],
            "quantity": item["quantity"],
            "coverage_months": warranty["coverage_months"],
            "start_date": warranty["start_date"],
        }


def extract_order_number(text):
    match = re.search(r"ORD-\d+", text, re.IGNORECASE)
    return match.group().upper() if match else None


def extract_item(text):
    codes = re.findall(r"\b[A-Z]{2,5}-[A-Z0-9]+\b", text.upper())
    for code in codes:
        if not code.startswith("ORD-"):
            return code
    return None


def extract_product_search_term(text):
    term = text.strip().lower()
    if term.startswith("you:"):
        term = term[4:].strip()
    prefixes = [
        "price of", "price for", "cost of", "cost for", "search for",
        "search", "find", "show me", "show", "product", "availability of",
        "availability for", "availability", "stock of", "stock for", "stock",
        "details of", "details for", "details",
    ]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if term.startswith(prefix):
                term = term[len(prefix):].strip()
                changed = True
                break
    term = term.strip(" ?.!:,;")

    # "show products" / "products" -> list the whole catalog
    if term in ("product", "products"):
        return "all products"
    plural_map = {
        "laptops": "laptop", "phones": "phone", "tablets": "tablet",
        "headphones": "headphone", "watches": "watch", "cameras": "camera",
        "chargers": "charger", "speakers": "speaker", "monitors": "monitor",
        "keyboards": "keyboard", "mice": "mouse",
    }
    return plural_map.get(term, term)


def format_product_results(products):
    if not products:
        return "I couldn't find that product."
    lines = ["Products found:"]
    for p in products:
        stock = f"In stock ({p['stock_quantity']} available)" if p["stock_quantity"] > 0 else "Out of stock"
        lines.append(f"- {p['name']} ({p['item']}) | ${p['price']:.2f} | {stock}")
    return "\n".join(lines)


def warranty_response(message):
    global PENDING_WARRANTY_ORDER, PENDING_WARRANTY_PRODUCTS
    text = message.strip()
    order_number = extract_order_number(text)

    if PENDING_WARRANTY_ORDER and PENDING_WARRANTY_PRODUCTS and not order_number and not text.lower().startswith("warranty"):
        selection = text.strip()
        selected = None
        if selection.isdigit():
            index = int(selection) - 1
            if 0 <= index < len(PENDING_WARRANTY_PRODUCTS):
                selected = PENDING_WARRANTY_PRODUCTS[index]
        else:
            item = extract_item(text)
            if item:
                selected = next((p for p in PENDING_WARRANTY_PRODUCTS if p["item"].upper() == item.upper()), None)
        if not selected:
            return "Please select a valid product.\nEnter the product number or item."
        order = PENDING_WARRANTY_ORDER
        warranty = get_warranty(order, selected["item"])
        PENDING_WARRANTY_ORDER = None
        PENDING_WARRANTY_PRODUCTS = []
        if not warranty:
            return f"I couldn't find warranty information for {selected['name']} in order {order}."
        return f"Warranty for {selected['name']} ({selected['item']}):\nCoverage: {warranty['coverage_months']} months\nStart date: {warranty['start_date']}"

    if not order_number:
        return "Please provide your order number.\nFor example: warranty ORD-10001"

    products = get_order_products(order_number)
    if not products:
        return f"I couldn't find order {order_number} on your account."

    item = extract_item(message)
    if item:
        selected = next((p for p in products if p["item"].upper() == item.upper()), None)
        if not selected:
            return f"{item} is not part of order {order_number}."
        warranty = get_warranty(order_number, selected["item"])
        if not warranty:
            return f"I couldn't find warranty information for {selected['name']} in order {order_number}."
        return f"Warranty for {selected['name']} ({selected['item']}):\nCoverage: {warranty['coverage_months']} months\nStart date: {warranty['start_date']}"

    PENDING_WARRANTY_ORDER = order_number
    PENDING_WARRANTY_PRODUCTS = products
    lines = [f"Which product would you like warranty information for in order {order_number}?", ""]
    for i, product in enumerate(products, 1):
        lines.append(f"{i}. {product['name']} ({product['item']})")
    lines.extend(["", "Please enter the product number or item."])
    return "\n".join(lines)
