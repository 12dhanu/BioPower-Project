
import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", "3306"))
}


def get_connection():
    try:
        missing = [
            key for key in ["host", "user", "password", "database"]
            if not DB_CONFIG.get(key)
        ]

        if missing:
            print("Missing database settings:", ", ".join(missing))
            return None

        connection = mysql.connector.connect(**DB_CONFIG)

        if connection.is_connected():
            return connection

        connection.close()
        return None

    except (Error, ValueError) as e:
        print("Database connection error:", e)
        return None


def initialize_database():
    connection = get_connection()

    if connection is None:
        return False

    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generation_records (
                record_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                waste_type VARCHAR(100) NOT NULL,
                waste_quantity FLOAT NOT NULL,
                biogas_volume FLOAT NOT NULL,
                methane_percentage FLOAT NOT NULL,
                methane_volume FLOAT NOT NULL,
                generator_efficiency FLOAT NOT NULL,
                electricity_generated FLOAT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id)
                    REFERENCES users(user_id)
                    ON DELETE CASCADE
            )
        """)

        connection.commit()
        print("Database tables initialized successfully.")
        return True

    except Error as e:
        print("Database initialization error:", e)
        return False

    finally:
        if cursor is not None:
            cursor.close()

        connection.close()
