# database.py
import sqlite3
import pandas as pd
import re

DB_NAME = "queryspeak.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        city TEXT,
        join_date TEXT
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT,
        category TEXT,
        price REAL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        product_id INTEGER,
        quantity INTEGER,
        order_date TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    )""")

    # Seed default sample records if tables are empty
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT INTO customers (name, city, join_date) VALUES (?, ?, ?)", [
            ('Aarav Sharma', 'Mumbai', '2025-01-10'),
            ('Priya Patel', 'Pune', '2025-02-15'),
            ('Rohan Verma', 'Delhi', '2025-03-01'),
            ('Neha Singh', 'Bangalore', '2025-03-20'),
            ('Aditya Joshi', 'Mumbai', '2025-04-12')
        ])
        cursor.executemany("INSERT INTO products (product_name, category, price) VALUES (?, ?, ?)", [
            ('Mechanical Keyboard', 'Electronics', 3500.0),
            ('Wireless Mouse', 'Electronics', 1200.0),
            ('Gaming Headset', 'Audio', 2400.0),
            ('USB-C Dock', 'Accessories', 4500.0),
            ('Noise-Cancelling Buds', 'Audio', 3999.0)
        ])
        cursor.executemany("INSERT INTO orders (customer_id, product_id, quantity, order_date) VALUES (?, ?, ?, ?)", [
            (1, 1, 1, '2026-01-05'),
            (1, 3, 2, '2026-02-12'),
            (2, 2, 1, '2026-02-18'),
            (3, 4, 1, '2026-03-01'),
            (4, 1, 2, '2026-03-15'),
            (5, 5, 1, '2026-04-10')
        ])
        conn.commit()
    conn.close()

def load_csv_to_db(uploaded_file, table_name="custom_dataset"):
    # Clean table name
    clean_table_name = re.sub(r'\W+', '_', table_name).strip('_').lower()
    df = pd.read_csv(uploaded_file)
    # Sanitize column names
    df.columns = [re.sub(r'\W+', '_', col).strip('_').lower() for col in df.columns]
    
    conn = sqlite3.connect(DB_NAME)
    df.to_sql(clean_table_name, conn, if_exists="replace", index=False)
    conn.close()
    return clean_table_name, len(df), list(df.columns)

def get_dynamic_schema_summary() -> str:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]
    
    schema_lines = []
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        cols_desc = ", ".join([f"{col[1]} {col[2]}" for col in columns])
        schema_lines.append(f"Table: {table} ({cols_desc})")
    
    conn.close()
    return "\n".join(schema_lines)

def run_query(sql_query: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    clean_query = sql_query.strip().rstrip(';')
    is_select = clean_query.lower().startswith("select")
    
    cursor.execute(sql_query)
    
    if not is_select:
        conn.commit()
        # Find which table was touched to return its updated preview
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]
        
        target_table = "products"
        for t in tables:
            if t in clean_query.lower():
                target_table = t
                break
        
        cursor.execute(f"SELECT * FROM {target_table} ORDER BY 1 DESC LIMIT 10")
        columns = [col[0] for col in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        conn.close()
        return columns, rows, f"Action committed successfully on table '{target_table}'."
    else:
        columns = [col[0] for col in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        conn.close()
        return columns, rows, None