import os
import hashlib
import secrets
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

# Always load .env from the project folder
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


def get_db_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


DB = get_db_connection()

HASH_ALGORITHM = "sha256"
ITERATIONS = 100_000
SALT_LENGTH = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_LENGTH)
    password_hash = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        ITERATIONS,
    )
    return (
        f"pbkdf2_{HASH_ALGORITHM}${ITERATIONS}$"
        f"{salt.hex()}${password_hash.hex()}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, hash_hex = stored_hash.split("$")
        calculated_hash = hashlib.pbkdf2_hmac(
            HASH_ALGORITHM,
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return secrets.compare_digest(calculated_hash.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def seed_database():
    users = [
        ("Alice Johnson", "alice@example.com", "Alice@123"),
        ("Bob Martinez", "bob@example.com", "Bob@123"),
    ]

    products = [
        ("PHN-X100", "Nova Phone X100", 449.99, 25),
        ("HDPH-200", "Aura Wireless Headphones", 129.50, 0),
        ("LAP-PRO14", "Zenith Laptop Pro 14", 1199.00, 8),
        ("TAB-S10", "Galaxy Tab S10", 699.99, 15),
        ("WATCH-X1", "Nova Smart Watch X1", 250.00, 20),
    ]

    with DB.cursor() as cursor:
        for name, email, password in users:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if not cursor.fetchone():
                cursor.execute(
                    """INSERT INTO users (name, email, password_hash)
                       VALUES (%s, %s, %s)""",
                    (name, email, hash_password(password)),
                )

        for item, name, price, stock in products:
            cursor.execute("SELECT item FROM products WHERE item = %s", (item,))
            if not cursor.fetchone():
                cursor.execute(
                    """INSERT INTO products (item, name, price, stock_quantity)
                       VALUES (%s, %s, %s, %s)""",
                    (item, name, price, stock),
                )

        cursor.execute("SELECT id FROM users WHERE email = %s", ("alice@example.com",))
        alice_id = cursor.fetchone()["id"]
        cursor.execute("SELECT id FROM users WHERE email = %s", ("bob@example.com",))
        bob_id = cursor.fetchone()["id"]

        cursor.execute("SELECT id FROM orders WHERE order_number = %s", ("ORD-10001",))
        if not cursor.fetchone():
            cursor.execute(
                """INSERT INTO orders (order_number, user_id, status, placed_at)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                ("ORD-10001", alice_id, "delivered", "2026-09-18 10:30:00"),
            )
            order_id = cursor.fetchone()["id"]
            cursor.execute(
                """INSERT INTO order_items (order_id, item, quantity)
                   VALUES (%s, %s, %s) RETURNING id""",
                (order_id, "PHN-X100", 1),
            )
            phone_item_id = cursor.fetchone()["id"]
            cursor.execute(
                """INSERT INTO order_items (order_id, item, quantity)
                   VALUES (%s, %s, %s) RETURNING id""",
                (order_id, "TAB-S10", 1),
            )
            tablet_item_id = cursor.fetchone()["id"]
            cursor.execute(
                """INSERT INTO warranties (order_item_id, coverage_months, start_date)
                   VALUES (%s, %s, %s)""",
                (phone_item_id, 12, "2026-09-18"),
            )
            cursor.execute(
                """INSERT INTO warranties (order_item_id, coverage_months, start_date)
                   VALUES (%s, %s, %s)""",
                (tablet_item_id, 12, "2026-09-18"),
            )
            cursor.execute(
                """INSERT INTO deliveries
                   (order_id, carrier, tracking_number, current_status, estimated_delivery_date)
                   VALUES (%s, %s, %s, %s, %s)""",
                (order_id, "FastShip", "FS123456789", "delivered", "2026-09-20"),
            )

        cursor.execute("SELECT id FROM orders WHERE order_number = %s", ("ORD-10002",))
        if not cursor.fetchone():
            cursor.execute(
                """INSERT INTO orders (order_number, user_id, status, placed_at)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                ("ORD-10002", bob_id, "shipped", "2026-09-19 14:15:00"),
            )
            order_id = cursor.fetchone()["id"]
            cursor.execute(
                """INSERT INTO order_items (order_id, item, quantity)
                   VALUES (%s, %s, %s) RETURNING id""",
                (order_id, "LAP-PRO14", 1),
            )
            laptop_item_id = cursor.fetchone()["id"]
            cursor.execute(
                """INSERT INTO warranties (order_item_id, coverage_months, start_date)
                   VALUES (%s, %s, %s)""",
                (laptop_item_id, 12, "2026-09-19"),
            )
            cursor.execute(
                """INSERT INTO deliveries
                   (order_id, carrier, tracking_number, current_status, estimated_delivery_date)
                   VALUES (%s, %s, %s, %s, %s)""",
                (order_id, "QuickCarrier", "QC987654321", "in_transit", "2026-09-24"),
            )

    DB.commit()
