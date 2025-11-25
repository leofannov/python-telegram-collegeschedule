from database_manager import db_manager
from datetime import datetime, time, timedelta
import pytz

# Часовой пояс Томска
TOMSK_TZ = pytz.timezone('Asia/Tomsk')

class MailingManager:
    def __init__(self):
        pass  # Больше не нужно загружать из файла

    def enable_mailing(self, chat_id: str, hour: int = 18, minute: int = 0):
        """Включение рассылки для чата"""
        return db_manager.set_mailing_settings(str(chat_id), True, hour, minute)

    def disable_mailing(self, chat_id: str):
        """Выключение рассылки для чата"""
        return db_manager.set_mailing_settings(str(chat_id), False)

    def set_mailing_time(self, chat_id: str, hour: int, minute: int):
        """Установка времени рассылки для чата"""
        return db_manager.set_mailing_settings(str(chat_id), True, hour, minute)

    def get_mailing_info(self, chat_id: str):
        """Получение информации о рассылке для чата"""
        return db_manager.get_mailing_settings(str(chat_id))

    def is_mailing_enabled(self, chat_id: str) -> bool:
        """Проверка, включена ли рассылка для чата"""
        settings = db_manager.get_mailing_settings(str(chat_id))
        return settings.get('enabled', False)

    def get_mailing_time(self, chat_id: str) -> time:
        """Получение времени рассылки для чата"""
        settings = db_manager.get_mailing_settings(str(chat_id))
        time_settings = settings.get('time', {'hour': 18, 'minute': 0})
        return time(time_settings['hour'], time_settings['minute'])

    def get_all_enabled_chats(self):
        """Получение всех чатов с включенной рассылкой"""
        return db_manager.get_enabled_mailing_chats()

    def get_next_mailing_datetime(self, chat_id: str) -> datetime:
        """Получение следующего времени рассылки"""
        mailing_time = self.get_mailing_time(chat_id)
        now = datetime.now(TOMSK_TZ)
        
        # Создаем datetime на сегодня с указанным временем
        next_mailing = TOMSK_TZ.localize(
            datetime.combine(now.date(), mailing_time)
        )
        
        # Если время уже прошло сегодня, планируем на завтра
        if next_mailing <= now:
            next_mailing += timedelta(days=1)
            
        return next_mailing