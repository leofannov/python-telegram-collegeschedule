import mysql.connector
from mysql.connector import Error
from database_config import db_config
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.config = db_config
        self.init_database()
        self.create_tables()

    def get_connection(self):
        return self.config.get_connection()

    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            conn = self.get_connection()
            if conn:
                logger.info("✅ База данных подключена успешно")
                conn.close()
                return True
            else:
                logger.error("❌ Не удалось подключиться к базе данных")
                return False
        except Error as e:
            logger.error(f"❌ Ошибка инициализации базы данных: {e}")
            return False

    def create_tables(self):
        """Создание всех необходимых таблиц"""
        tables = [
            """
            CREATE TABLE IF NOT EXISTS user_groups (
                id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id VARCHAR(255) UNIQUE NOT NULL,
                group_name VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mailing_settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id VARCHAR(255) UNIQUE NOT NULL,
                enabled BOOLEAN DEFAULT FALSE,
                hour INT DEFAULT 18,
                minute INT DEFAULT 0,
                timezone VARCHAR(50) DEFAULT 'Asia/Tomsk',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS change_notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id VARCHAR(255) UNIQUE NOT NULL,
                enabled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS flood_settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                max_requests_per_minute INT DEFAULT 30,
                ban_duration_minutes INT DEFAULT 60,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS banned_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id VARCHAR(255) UNIQUE NOT NULL,
                reason TEXT,
                banned_until TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS request_stats (
                id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id VARCHAR(255) NOT NULL,
                command VARCHAR(255),
                user_agent TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_chat_id (chat_id),
                INDEX idx_timestamp (timestamp)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                setting_key VARCHAR(255) UNIQUE NOT NULL,
                setting_value TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bot_chats (
                id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id VARCHAR(255) UNIQUE NOT NULL,
                chat_type ENUM('private', 'group', 'supergroup', 'channel') NOT NULL,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                title VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_chat_type (chat_type),
                INDEX idx_created_at (created_at)
            )
            """
        ]

        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            for table in tables:
                cursor.execute(table)
            
            # Добавляем начальные настройки анти-флуда
            cursor.execute("""
                INSERT IGNORE INTO flood_settings (id, enabled, max_requests_per_minute, ban_duration_minutes) 
                VALUES (1, TRUE, 30, 60)
            """)
            
            conn.commit()
            logger.info("✅ Все таблицы созданы успешно")
            return True
            
        except Error as e:
            logger.error(f"❌ Ошибка создания таблиц: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def save_bot_chat(self, chat_id: str, chat_type: str, username: str = None, 
                 first_name: str = None, last_name: str = None, title: str = None) -> bool:
        """Сохранение информации о чате/пользователе"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_chats (chat_id, chat_type, username, first_name, last_name, title) 
                VALUES (%s, %s, %s, %s, %s, %s) 
                ON DUPLICATE KEY UPDATE 
                chat_type = VALUES(chat_type),
                username = VALUES(username),
                first_name = VALUES(first_name),
                last_name = VALUES(last_name),
                title = VALUES(title),
                updated_at = CURRENT_TIMESTAMP
            """, (chat_id, chat_type, username, first_name, last_name, title))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Ошибка сохранения информации о чате: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_all_bot_chats(self, chat_type: str = None) -> List[Dict[str, Any]]:
        """Получение всех чатов (с фильтром по типу)"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor(dictionary=True)
            if chat_type:
                cursor.execute("SELECT * FROM bot_chats WHERE chat_type = %s ORDER BY created_at DESC", (chat_type,))
            else:
                cursor.execute("SELECT * FROM bot_chats ORDER BY created_at DESC")
            return cursor.fetchall()
        except Error as e:
            logger.error(f"❌ Ошибка получения списка чатов: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def remove_admin(self, user_id: str) -> bool:
        """Удаление администратора"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admins WHERE user_id = %s", (user_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            
            if deleted:
                logger.info(f"✅ Администратор {user_id} удален")
            else:
                logger.warning(f"⚠️ Администратор {user_id} не найден")
                
            return deleted
        except Error as e:
            logger.error(f"❌ Ошибка удаления администратора: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_bot_chats_count(self) -> Dict[str, int]:
        """Получение статистики по чатам"""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            cursor = conn.cursor()
            counts = {}
            
            # Общее количество
            cursor.execute("SELECT COUNT(*) FROM bot_chats")
            counts['total'] = cursor.fetchone()[0]
            
            # По типам
            cursor.execute("SELECT chat_type, COUNT(*) FROM bot_chats GROUP BY chat_type")
            for chat_type, count in cursor.fetchall():
                counts[chat_type] = count
                
            return counts
        except Error as e:
            logger.error(f"❌ Ошибка получения статистики чатов: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

    def delete_bot_chat(self, chat_id: str) -> bool:
        """Удаление чата из отслеживания"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bot_chats WHERE chat_id = %s", (chat_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Error as e:
            logger.error(f"❌ Ошибка удаления чата: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    # Методы для работы с группами пользователей
    def set_user_group(self, chat_id: str, group_name: str) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_groups (chat_id, group_name) 
                VALUES (%s, %s) 
                ON DUPLICATE KEY UPDATE group_name = %s, updated_at = CURRENT_TIMESTAMP
            """, (chat_id, group_name, group_name))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Ошибка установки группы: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_user_group(self, chat_id: str) -> Optional[str]:
        conn = self.get_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT group_name FROM user_groups WHERE chat_id = %s", (chat_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            logger.error(f"❌ Ошибка получения группы: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_chats_by_group(self, group_name: str) -> List[str]:
        conn = self.get_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM user_groups WHERE group_name = %s", (group_name,))
            results = cursor.fetchall()
            return [row[0] for row in results]
        except Error as e:
            logger.error(f"❌ Ошибка получения чатов по группе: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    # Методы для настроек рассылки
    def set_mailing_settings(self, chat_id: str, enabled: bool, hour: int = 18, minute: int = 0) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mailing_settings (chat_id, enabled, hour, minute) 
                VALUES (%s, %s, %s, %s) 
                ON DUPLICATE KEY UPDATE enabled = %s, hour = %s, minute = %s, updated_at = CURRENT_TIMESTAMP
            """, (chat_id, enabled, hour, minute, enabled, hour, minute))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Ошибка установки настроек рассылки: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_mailing_settings(self, chat_id: str) -> Dict[str, Any]:
        conn = self.get_connection()
        if not conn:
            return {'enabled': False, 'time': {'hour': 18, 'minute': 0}, 'timezone': 'Asia/Tomsk'}

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM mailing_settings WHERE chat_id = %s", (chat_id,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'enabled': result['enabled'],
                    'time': {'hour': result['hour'], 'minute': result['minute']},
                    'timezone': result['timezone']
                }
            else:
                return {'enabled': False, 'time': {'hour': 18, 'minute': 0}, 'timezone': 'Asia/Tomsk'}
        except Error as e:
            logger.error(f"❌ Ошибка получения настроек рассылки: {e}")
            return {'enabled': False, 'time': {'hour': 18, 'minute': 0}, 'timezone': 'Asia/Tomsk'}
        finally:
            cursor.close()
            conn.close()

    def get_enabled_mailing_chats(self) -> List[str]:
        conn = self.get_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM mailing_settings WHERE enabled = TRUE")
            results = cursor.fetchall()
            return [row[0] for row in results]
        except Error as e:
            logger.error(f"❌ Ошибка получения чатов с рассылкой: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    # Методы для уведомлений об изменениях
    def set_change_notifications(self, chat_id: str, enabled: bool) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO change_notifications (chat_id, enabled) 
                VALUES (%s, %s) 
                ON DUPLICATE KEY UPDATE enabled = %s, updated_at = CURRENT_TIMESTAMP
            """, (chat_id, enabled, enabled))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Ошибка установки уведомлений: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_change_notifications(self, chat_id: str) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT enabled FROM change_notifications WHERE chat_id = %s", (chat_id,))
            result = cursor.fetchone()
            return result[0] if result else False
        except Error as e:
            logger.error(f"❌ Ошибка получения уведомлений: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_enabled_notification_chats(self) -> List[str]:
        conn = self.get_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM change_notifications WHERE enabled = TRUE")
            results = cursor.fetchall()
            return [row[0] for row in results]
        except Error as e:
            logger.error(f"❌ Ошибка получения чатов с уведомлениями: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    # Методы для администраторов
    def add_admin(self, user_id: str, username: str = None) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admins (user_id, username) 
                VALUES (%s, %s)
            """, (user_id, username))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Ошибка добавления администратора: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def is_admin(self, user_id: str) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM admins WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            return result is not None
        except Error as e:
            logger.error(f"❌ Ошибка проверки администратора: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_all_admins(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM admins")
            return cursor.fetchall()
        except Error as e:
            logger.error(f"❌ Ошибка получения администраторов: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    # Методы для анти-флуда
    def get_flood_settings(self) -> Dict[str, Any]:
        conn = self.get_connection()
        if not conn:
            return {'enabled': True, 'max_requests_per_minute': 30, 'ban_duration_minutes': 60}

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM flood_settings WHERE id = 1")
            result = cursor.fetchone()
            return result if result else {'enabled': True, 'max_requests_per_minute': 30, 'ban_duration_minutes': 60}
        except Error as e:
            logger.error(f"❌ Ошибка получения настроек анти-флуда: {e}")
            return {'enabled': True, 'max_requests_per_minute': 30, 'ban_duration_minutes': 60}
        finally:
            cursor.close()
            conn.close()

    def update_flood_settings(self, enabled: bool = None, max_requests: int = None, ban_duration: int = None) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if enabled is not None:
                updates.append("enabled = %s")
                params.append(enabled)
            if max_requests is not None:
                updates.append("max_requests_per_minute = %s")
                params.append(max_requests)
            if ban_duration is not None:
                updates.append("ban_duration_minutes = %s")
                params.append(ban_duration)
            
            if updates:
                query = f"UPDATE flood_settings SET {', '.join(updates)} WHERE id = 1"
                cursor.execute(query, params)
                conn.commit()
            
            return True
        except Error as e:
            logger.error(f"❌ Ошибка обновления настроек анти-флуда: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    # Методы для банов
    def ban_user(self, chat_id: str, reason: str = None, ban_duration_minutes: int = 0) -> bool:
        """Бан пользователя с указанием времени"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
        
            if ban_duration_minutes > 0:
                banned_until = datetime.now() + timedelta(minutes=ban_duration_minutes)
            else:
                banned_until = None  # Навсегда
            
            cursor.execute("""
                INSERT INTO banned_users (chat_id, reason, banned_until) 
                VALUES (%s, %s, %s) 
                ON DUPLICATE KEY UPDATE reason = %s, banned_until = %s
            """, (chat_id, reason, banned_until, reason, banned_until))
        
            conn.commit()
        
            # Логируем бан
            logger.info(f"🚫 Пользователь {chat_id} забанен. Причина: {reason}, Длительность: {ban_duration_minutes} мин")
            return True
        
        except Error as e:
            logger.error(f"❌ Ошибка бана пользователя: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def unban_user(self, chat_id: str) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM banned_users WHERE chat_id = %s", (chat_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Error as e:
            logger.error(f"❌ Ошибка разбана пользователя: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def is_banned(self, chat_id: str) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM banned_users 
                WHERE chat_id = %s AND (banned_until IS NULL OR banned_until > %s)
            """, (chat_id, datetime.now()))
            result = cursor.fetchone()
            return result is not None
        except Error as e:
            logger.error(f"❌ Ошибка проверки бана: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_banned_users(self) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM banned_users")
            return cursor.fetchall()
        except Error as e:
            logger.error(f"❌ Ошибка получения списка банов: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    # Методы для статистики
    def log_request(self, chat_id: str, command: str = None, user_agent: str = None) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO request_stats (chat_id, command, user_agent) 
                VALUES (%s, %s, %s)
            """, (chat_id, command, user_agent))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Ошибка логирования запроса: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_request_stats(self, time_period_minutes: int = 60) -> Dict[str, Any]:
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            cursor = conn.cursor()
            
            # Общее количество запросов
            cursor.execute("SELECT COUNT(*) FROM request_stats")
            total_requests = cursor.fetchone()[0]
            
            # Запросы за указанный период
            cursor.execute("""
                SELECT COUNT(*) FROM request_stats 
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
            """, (time_period_minutes,))
            recent_requests = cursor.fetchone()[0]
            
            # Популярные команды
            cursor.execute("""
                SELECT command, COUNT(*) as count 
                FROM request_stats 
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
                GROUP BY command 
                ORDER BY count DESC 
                LIMIT 10
            """, (time_period_minutes,))
            popular_commands = cursor.fetchall()
            
            # Активные пользователи
            cursor.execute("""
                SELECT chat_id, COUNT(*) as request_count 
                FROM request_stats 
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
                GROUP BY chat_id 
                ORDER BY request_count DESC 
                LIMIT 10
            """, (time_period_minutes,))
            active_users = cursor.fetchall()
            
            return {
                'total_requests': total_requests,
                'recent_requests': recent_requests,
                'popular_commands': popular_commands,
                'active_users': active_users,
                'time_period_minutes': time_period_minutes
            }
        except Error as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

    def get_user_request_count(self, chat_id: str, time_period_minutes: int = 1) -> int:
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM request_stats 
                WHERE chat_id = %s AND timestamp >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
            """, (chat_id, time_period_minutes))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Error as e:
            logger.error(f"❌ Ошибка получения количества запросов пользователя: {e}")
            return 0
        finally:
            cursor.close()
            conn.close()

    # Методы для общих настроек бота
    def set_bot_setting(self, key: str, value: str, description: str = None) -> bool:
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_settings (setting_key, setting_value, description) 
                VALUES (%s, %s, %s) 
                ON DUPLICATE KEY UPDATE setting_value = %s, description = %s, updated_at = CURRENT_TIMESTAMP
            """, (key, value, description, value, description))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Ошибка установки настройки: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_bot_setting(self, key: str, default: str = None) -> str:
        conn = self.get_connection()
        if not conn:
            return default

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_key = %s", (key,))
            result = cursor.fetchone()
            return result[0] if result else default
        except Error as e:
            logger.error(f"❌ Ошибка получения настройки: {e}")
            return default
        finally:
            cursor.close()
            conn.close()

    # Миграция данных из JSON файлов
    def migrate_from_json(self) -> Dict[str, int]:
        """Миграция данных из JSON файлов в базу данных"""
        migration_stats = {
            'user_groups': 0,
            'mailing_settings': 0,
            'change_notifications': 0
        }

        try:
            # Миграция group_settings.json
            if os.path.exists('group_settings.json'):
                with open('group_settings.json', 'r', encoding='utf-8') as f:
                    group_data = json.load(f)
                
                for chat_id, group_name in group_data.items():
                    if self.set_user_group(chat_id, group_name):
                        migration_stats['user_groups'] += 1

            # Миграция mailing_settings.json
            if os.path.exists('mailing_settings.json'):
                with open('mailing_settings.json', 'r', encoding='utf-8') as f:
                    mailing_data = json.load(f)
                
                for chat_id, settings in mailing_data.items():
                    if self.set_mailing_settings(
                        chat_id, 
                        settings.get('enabled', False),
                        settings.get('time', {}).get('hour', 18),
                        settings.get('time', {}).get('minute', 0)
                    ):
                        migration_stats['mailing_settings'] += 1

            # Миграция change_notification_settings.json
            if os.path.exists('change_notification_settings.json'):
                with open('change_notification_settings.json', 'r', encoding='utf-8') as f:
                    notification_data = json.load(f)
                
                for chat_id, enabled in notification_data.items():
                    if self.set_change_notifications(chat_id, enabled):
                        migration_stats['change_notifications'] += 1

            logger.info(f"✅ Миграция завершена: {migration_stats}")
            return migration_stats

        except Exception as e:
            logger.error(f"❌ Ошибка миграции: {e}")
            return migration_stats

    # Получение информации о настройках
    def get_settings_info(self) -> Dict[str, Any]:
        """Получить информацию о всех настройках"""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            cursor = conn.cursor(dictionary=True)
            
            info = {}
            
            # Группы пользователей
            cursor.execute("SELECT COUNT(*) as count FROM user_groups")
            info['user_groups_count'] = cursor.fetchone()['count']
            
            # Настройки рассылки
            cursor.execute("SELECT COUNT(*) as count FROM mailing_settings WHERE enabled = TRUE")
            info['enabled_mailing_count'] = cursor.fetchone()['count']
            
            # Уведомления об изменениях
            cursor.execute("SELECT COUNT(*) as count FROM change_notifications WHERE enabled = TRUE")
            info['enabled_notifications_count'] = cursor.fetchone()['count']
            
            # Администраторы
            cursor.execute("SELECT COUNT(*) as count FROM admins")
            info['admins_count'] = cursor.fetchone()['count']
            
            # Баны
            cursor.execute("SELECT COUNT(*) as count FROM banned_users")
            info['banned_users_count'] = cursor.fetchone()['count']
            
            return info
            
        except Error as e:
            logger.error(f"❌ Ошибка получения информации о настройках: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()