import sqlite3
import json
import hashlib
from datetime import date

# Tietokannan ja tiedostojen nimet
DB_FILE = "seuranta.db"
PORTFOLIO_FILE = "portfolios.json"
HISTORY_FILE = "portfolio_history.json"

def init_db():
    """Alustaa tietokantataulut, jos ne eivät ole olemassa."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                user_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY,
                name TEXT,
                ticker TEXT,
                buy_price REAL,
                shares REAL,
                manual_price REAL,
                is_manual BOOLEAN,
                currency TEXT,
                buy_currency_rate REAL,
                current_currency_rate REAL,
                target_percentage REAL,
                portfolio_id INTEGER,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INTEGER PRIMARY KEY,
                portfolio_id INTEGER,
                record_date TEXT NOT NULL,
                total_value REAL NOT NULL,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios (id),
                UNIQUE(portfolio_id, record_date)
            )
        """)
        conn.commit()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def migrate_data():
    """Siirtää salkkudatan JSON-tiedostoista SQLite-tietokantaan."""
    init_db()
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # 1. Käyttäjätietojen luominen
        # Koska paikallinen versio ei vaadi käyttäjätunnusta, luomme oletuskäyttäjän
        username = "oma_kayttaja"
        password = "oma_salasana"  # VAIHDA TÄMÄ TURVALLISEEN SALASANAAN
        hashed_password = hash_password(password)

        try:
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed_password))
            user_id = cursor.lastrowid
            print(f"Luotu oletuskäyttäjä '{username}' ID:llä {user_id}. Muista vaihtaa salasana!")
        except sqlite3.IntegrityError:
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user_id = cursor.fetchone()[0]
            print(f"Käyttäjä '{username}' on jo olemassa ID:llä {user_id}.")

        # 2. Salkkudatan siirto portfolios.json-tiedostosta
        try:
            with open(PORTFOLIO_FILE, 'r') as f:
                portfolios_data = json.load(f)

            for portfolio_name, assets in portfolios_data.items():
                cursor.execute("INSERT INTO portfolios (name, user_id) VALUES (?, ?)", (portfolio_name, user_id))
                portfolio_id = cursor.lastrowid

                for asset in assets:
                    is_manual_val = 1 if asset.get('is_manual') else 0
                    cursor.execute("""
                        INSERT INTO assets (name, ticker, buy_price, shares, manual_price, is_manual, currency, buy_currency_rate, current_currency_rate, target_percentage, portfolio_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (asset['name'], asset['ticker'], asset['buy_price'], asset['shares'], asset['manual_price'], is_manual_val, asset['currency'], asset['buy_currency_rate'], asset['current_currency_rate'], asset['target_percentage'], portfolio_id))
            print("Salkkudata siirretty onnistuneesti.")
        except FileNotFoundError:
            print(f"Varoitus: Tiedostoa '{PORTFOLIO_FILE}' ei löydy. Salkkuja ei siirretty.")

        # 3. Historiadatan siirto portfolio_history.json-tiedostosta
        try:
            with open(HISTORY_FILE, 'r') as f:
                history_data = json.load(f)

            for portfolio_name, history_records in history_data.items():
                cursor.execute("SELECT id FROM portfolios WHERE name = ? AND user_id = ?", (portfolio_name, user_id))
                portfolio_id_row = cursor.fetchone()
                if portfolio_id_row:
                    portfolio_id = portfolio_id_row[0]
                    for record in history_records:
                        record_date = record[0]
                        total_value = record[1]
                        try:
                            cursor.execute("""
                                INSERT INTO portfolio_history (portfolio_id, record_date, total_value)
                                VALUES (?, ?, ?)
                            """, (portfolio_id, record_date, total_value))
                        except sqlite3.IntegrityError:
                            print(f"Varoitus: Historiatieto päivältä {record_date} on jo olemassa salkulle '{portfolio_name}'.")
                else:
                    print(f"Varoitus: Salkkua '{portfolio_name}' ei löydy tietokannasta historiatietojen siirtoa varten.")
            print("Historiadata siirretty onnistuneesti.")
        except FileNotFoundError:
            print(f"Varoitus: Tiedostoa '{HISTORY_FILE}' ei löydy. Historiatietoja ei siirretty.")

        conn.commit()

if __name__ == "__main__":
    migrate_data()
