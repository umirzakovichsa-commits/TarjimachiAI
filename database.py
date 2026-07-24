import sqlite3
import os
from datetime import datetime

class Database:
    def __init__(self, db_path="receipts.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Ma'lumotlar bazasini yaratish va jadvallarni sozlash."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_chat_id INTEGER,
                    group_message_id INTEGER,
                    sender_id INTEGER,
                    sender_username TEXT,
                    sender_display_name TEXT,
                    client_name TEXT,
                    invoice_number TEXT,
                    amount TEXT,
                    status TEXT DEFAULT 'pending', -- pending, approved, rejected
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def check_invoice_exists(self, invoice_number: str) -> bool:
        """Tasdiqlangan nakladnoy raqami bazada borligini tekshirish."""
        if not invoice_number:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM receipts WHERE invoice_number = ? AND status = 'approved'",
                (invoice_number.strip(),)
            )
            return cursor.fetchone() is not None

    def add_receipt(self, group_chat_id: int, sender_id: int, 
                    sender_username: str, sender_display_name: str, 
                    client_name: str, invoice_number: str, amount: str) -> int:
        """Yangi to'lov arizasini barcha ma'lumotlari bilan kiritish."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO receipts (
                    group_chat_id, sender_id, sender_username, sender_display_name, 
                    client_name, invoice_number, amount, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (group_chat_id, sender_id, sender_username, sender_display_name, 
                 client_name.strip(), invoice_number.strip(), amount.strip())
            )
            conn.commit()
            return cursor.lastrowid

    def update_group_message_id(self, receipt_id: int, group_message_id: int):
        """Guruhga yuborilgan (tugmalari bor) xabar ID sini saqlash."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE receipts SET group_message_id = ?, updated_at = ? WHERE id = ?",
                (group_message_id, datetime.now(), receipt_id)
            )
            conn.commit()

    def get_receipt(self, receipt_id: int):
        """To'lov ma'lumotlarini ID bo'yicha olish."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_receipt_by_group_message(self, group_message_id: int):
        """Guruhdagi xabar ID si bo'yicha to'lov ma'lumotlarini olish."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM receipts WHERE group_message_id = ?",
                (group_message_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_receipt_status(self, receipt_id: int, status: str):
        """To'lov holatini o'zgartirish (approved yoki rejected)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE receipts SET status = ?, updated_at = ? WHERE id = ?",
                (status, datetime.now(), receipt_id)
            )
            conn.commit()
