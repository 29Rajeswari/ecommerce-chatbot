from database import DB, seed_database, verify_password
from services import (
    set_current_user,
    list_orders,
    get_order_status,
    track_delivery,
    warranty_response,
    search_products,
    get_all_products,
    extract_order_number,
    extract_item,
    extract_product_search_term,
    format_product_results,
    has_pending_warranty,
    clear_pending_warranty,
)
from guardrails import check_input, check_output

CURRENT_USER_NAME = None
CURRENT_USER_EMAIL = None

ALL_PRODUCTS_TERMS = {"", "products", "product", "catalog", "product catalog", "all products"}

HELP_TEXT = (
    "I can help with:\n"
    "- My orders\n- Order status\n- Delivery tracking\n"
    "- Warranty information\n- Product price and availability\n"
    "- Product search\n\n"
    "Examples:\n"
    "- my orders\n- status of ORD-10001\n- track ORD-10001\n"
    "- warranty ORD-10001\n- warranty ORD-10001 PHN-X100\n"
    "- price of phone\n- search smartwatch\n- show products"
)


def login():
    print("\n" + "=" * 60)
    print("LOGIN")
    print("=" * 60)
    email = input("Email: ").strip().lower()
    password = input("Password: ").strip()

    with DB.cursor() as cursor:
        cursor.execute(
            """SELECT id, name, email, password_hash
               FROM users WHERE email = %s""",
            (email,),
        )
        user = cursor.fetchone()

    if not user or not verify_password(password, user["password_hash"]):
        print("\nLogin failed.\nInvalid email or password.")
        return None

    print("\nAuthentication successful.")
    return user


def find_products(term):
    """Search for a term; if nothing matches and it looks plural, retry singular."""
    products = search_products(term)
    if not products and term.endswith("s") and len(term) > 3:
        products = search_products(term[:-1])
    return products


def chatbot(message):
    allowed, _ = check_input(message)
    if not allowed:
        return "I can't process that request. Please provide a normal customer-service request."

    text = message.strip().lower()
    order_number = extract_order_number(message)

    # 1. Answer to a pending "which product?" warranty question
    #    (a product number, or an item code such as PHN-X100).
    if has_pending_warranty() and (message.strip().isdigit() or extract_item(message)):
        return safe_output(warranty_response(message))

    # 2. New warranty request, or a bare number with no pending question
    if "warranty" in text or (not order_number and message.strip().isdigit()):
        return safe_output(warranty_response(message))

    # Any other message abandons a half-finished warranty conversation,
    # so a later bare number isn't mistaken for a product choice.
    clear_pending_warranty()

    if "my orders" in text or "list my orders" in text or "show my orders" in text or text == "orders":
        orders = list_orders()
        if not orders:
            return "You don't have any orders."
        response = "Your orders:\n" + "\n".join(
            f"- {o['order_number']} | {o['status']} | {o['placed_at']}" for o in orders
        )
        return safe_output(response)

    if "status" in text or "order status" in text or "current status" in text:
        if not order_number:
            return "Please provide your order number.\nFor example: status of ORD-10002"
        order = get_order_status(order_number)
        if not order:
            return f"I couldn't find order {order_number} on your account."
        items = ", ".join(f"{i['quantity']}x {i['item']}" for i in order["items"]) or "No items found"
        return safe_output(
            f"Order {order['order_number']}:\nStatus: {order['status']}\n"
            f"Placed: {order['placed_at']}\nItems: {items}"
        )

    if "track" in text or "tracking" in text or "delivery" in text or "where is my order" in text:
        if not order_number:
            return "Please provide your order number.\nFor example: track ORD-10002"
        delivery = track_delivery(order_number)
        if not delivery:
            return f"I couldn't find order {order_number} on your account."
        return safe_output(
            f"Order {order_number} delivery:\n"
            f"Carrier: {delivery['carrier']}\n"
            f"Tracking: {delivery['tracking_number']}\n"
            f"Status: {delivery['current_status']}\n"
            f"Estimated delivery: {delivery['estimated_delivery_date']}"
        )

    # 3. Explicit product requests ("price of phone", "search smartwatch", "show products")
    product_words = ["product", "price", "cost", "available", "availability", "stock", "search", "find", "show", "details"]
    if any(word in text for word in product_words):
        term = extract_product_search_term(text)
        if term in ALL_PRODUCTS_TERMS:
            return safe_output(format_product_results(get_all_products()))
        return safe_output(format_product_results(find_products(term)))

    # 4. A bare item code, e.g. "PHN-X100"
    item = extract_item(message)
    if item:
        products = search_products(item)
        if products:
            return safe_output(format_product_results(products))

    # 5. Last resort: treat the message as a product name ("phones", "laptop").
    #    Only answer if something matches; otherwise fall through to the help text.
    term = extract_product_search_term(text)
    if term and term not in ALL_PRODUCTS_TERMS:
        products = find_products(term)
        if products:
            return safe_output(format_product_results(products))

    return safe_output(HELP_TEXT)


def safe_output(response):
    allowed, safe_response = check_output(response)
    return safe_response if allowed else "I can't provide that response."


def main():
    global CURRENT_USER_NAME, CURRENT_USER_EMAIL
    print("=" * 60)
    print("ECOMMERCE CUSTOMER SERVICE CHATBOT")
    print("PostgreSQL + NVIDIA NeMo Guardrails")
    print("=" * 60)

    try:
        seed_database()
        print("\nDatabase initialized successfully.")

        user = login()
        if not user:
            print("\nExiting...")
            return

        CURRENT_USER_NAME = user["name"]
        CURRENT_USER_EMAIL = user["email"]
        set_current_user(user["id"])

        print(f"\nWelcome, {CURRENT_USER_NAME}!")
        print("\nAvailable commands:")
        print("  my orders")
        print("  status of ORD-10001")
        print("  track ORD-10001")
        print("  warranty ORD-10001")
        print("  warranty ORD-10001 PHN-X100")
        print("  price of phone")
        print("  search smartwatch")
        print("  show products")
        print("  exit")

        while True:
            try:
                message = input("\nYou: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\nExiting chatbot...")
                break

            if not message:
                continue
            if message.lower() in {"exit", "quit", "bye"}:
                print("\nThank you for using the chatbot.")
                break

            print(f"\nBot: {chatbot(message)}")

    finally:
        if DB:
            DB.close()
            print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()