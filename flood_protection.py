import time
from datetime import datetime, timedelta
from database_manager import db_manager
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FloodProtection:
    def __init__(self):
        self.user_requests = {}  # Кэш запросов пользователей

    def check_flood(self, chat_id: str) -> Dict[str, Any]:
        """
        Проверка на флуд
        Возвращает словарь с результатом проверки
        """
        settings = db_manager.get_flood_settings()
        
        if not settings.get('enabled', True):
            return {'allowed': True, 'reason': 'flood_disabled'}
        
        # Проверяем бан и получаем информацию о нем
        if db_manager.is_banned(chat_id):
            ban_info = self.get_ban_info(chat_id)
            return {
                'allowed': False, 
                'reason': 'banned',
                'ban_info': ban_info
            }
        
        current_time = time.time()
        user_key = str(chat_id)
        
        # Инициализация данных пользователя
        if user_key not in self.user_requests:
            self.user_requests[user_key] = {
                'timestamps': [],
                'last_cleanup': current_time
            }
        
        user_data = self.user_requests[user_key]
        
        # Очистка старых записей (раз в минуту для пользователя)
        if current_time - user_data['last_cleanup'] > 60:
            user_data['timestamps'] = [
                ts for ts in user_data['timestamps'] 
                if current_time - ts < 60
            ]
            user_data['last_cleanup'] = current_time
        
        # Добавляем текущий запрос
        user_data['timestamps'].append(current_time)
        
        max_requests = settings.get('max_requests_per_minute', 30)
        
        if len(user_data['timestamps']) > max_requests:
            # Превышен лимит - бан
            ban_duration = settings.get('ban_duration_minutes', 60)
            db_manager.ban_user(
                chat_id, 
                f"Flood protection: {len(user_data['timestamps'])} requests in 1 minute",
                ban_duration
            )
            
            # Очищаем историю
            user_data['timestamps'] = []
            
            logger.warning(f"🚫 User {chat_id} banned for flood")
            return {
                'allowed': False, 
                'reason': 'flood_detected',
                'requests_count': len(user_data['timestamps']),
                'max_requests': max_requests,
                'ban_duration': ban_duration
            }
        
        return {
            'allowed': True,
            'reason': 'within_limits',
            'requests_count': len(user_data['timestamps']),
            'max_requests': max_requests
        }

    def get_flood_info(self, chat_id: str) -> Dict[str, Any]:
        """Получить информацию о флуд-статусе пользователя"""
        settings = db_manager.get_flood_settings()
        user_requests = db_manager.get_user_request_count(chat_id, 1)
        
        return {
            'flood_protection_enabled': settings.get('enabled', True),
            'max_requests_per_minute': settings.get('max_requests_per_minute', 30),
            'user_requests_last_minute': user_requests,
            'is_banned': db_manager.is_banned(chat_id),
            'ban_duration_minutes': settings.get('ban_duration_minutes', 60)
        }
    def get_ban_info(self, chat_id: str) -> Dict[str, Any]:
        """Получить подробную информацию о бане"""
        conn = db_manager.get_connection()
        if not conn:
            return {'reason': 'Неизвестно', 'banned_until': None}
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT reason, banned_until, created_at 
                FROM banned_users 
                WHERE chat_id = %s AND (banned_until IS NULL OR banned_until > %s)
                ORDER BY created_at DESC 
                LIMIT 1
            """, (chat_id, datetime.now()))
            
            result = cursor.fetchone()
            if result:
                return {
                    'reason': result['reason'] or 'Причина не указана',
                    'banned_until': result['banned_until'],
                    'banned_since': result['created_at']
                }
            return {'reason': 'Неизвестно', 'banned_until': None}
            
        except Error as e:
            logger.error(f"❌ Ошибка получения информации о бане: {e}")
            return {'reason': 'Неизвестно', 'banned_until': None}
        finally:
            cursor.close()
            conn.close()

# Глобальный экземпляр защиты от флуда
flood_protection = FloodProtection()