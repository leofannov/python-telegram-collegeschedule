import mysql.connector
from mysql.connector import Error
import json
import os
from typing import Dict, Any, List, Optional

class DatabaseConfig:
    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.user = os.getenv('DB_USER', 'user')
        self.password = os.getenv('DB_PASSWORD', 'password')
        self.database = os.getenv('DB_NAME', 'database')
        self.port = os.getenv('DB_PORT', 3306)
        
    def get_connection(self):
        """Получить соединение с базой данных"""
        try:
            connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port
            )
            return connection
        except Error as e:
            print(f"Ошибка подключения к MySQL: {e}")
            return None

# Глобальный экземпляр конфигурации
db_config = DatabaseConfig()