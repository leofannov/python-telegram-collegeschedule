import json
import os
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, Any

# Часовой пояс Томска
TOMSK_TZ = pytz.timezone('Asia/Tomsk')

class MailingManager:
    def __init__(self, settings_file='mailing_settings.json'):
        self.settings_file = settings_file
        self.settings = self.load_settings()

    def load_settings(self) -> Dict[str, Any]:
        """Загрузка настроек рассылки из файла"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка загрузки настроек рассылки: {e}")
        return {}

    def save_settings(self):
        """Сохранение настроек рассылки в файл"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения настроек рассылки: {e}")

    def enable_mailing(self, chat_id: str, hour: int = 18, minute: int = 0):
        """Включение рассылки для чата"""
        self.settings[str(chat_id)] = {
            'enabled': True,
            'time': {'hour': hour, 'minute': minute},
            'timezone': 'Asia/Tomsk'
        }
        self.save_settings()

    def disable_mailing(self, chat_id: str):
        """Выключение рассылки для чата"""
        if str(chat_id) in self.settings:
            self.settings[str(chat_id)]['enabled'] = False
            self.save_settings()

    def set_mailing_time(self, chat_id: str, hour: int, minute: int):
        """Установка времени рассылки для чата"""
        if str(chat_id) not in self.settings:
            self.settings[str(chat_id)] = {'enabled': True, 'timezone': 'Asia/Tomsk'}
        
        self.settings[str(chat_id)]['time'] = {'hour': hour, 'minute': minute}
        self.settings[str(chat_id)]['enabled'] = True
        self.save_settings()

    def get_mailing_info(self, chat_id: str) -> Dict[str, Any]:
        """Получение информации о рассылке для чата"""
        return self.settings.get(str(chat_id), {
            'enabled': False,
            'time': {'hour': 18, 'minute': 0},
            'timezone': 'Asia/Tomsk'
        })

    def is_mailing_enabled(self, chat_id: str) -> bool:
        """Проверка, включена ли рассылка для чата"""
        settings = self.settings.get(str(chat_id), {})
        return settings.get('enabled', False)

    def get_mailing_time(self, chat_id: str) -> time:
        """Получение времени рассылки для чата"""
        settings = self.settings.get(str(chat_id), {})
        time_settings = settings.get('time', {'hour': 18, 'minute': 0})
        return time(time_settings['hour'], time_settings['minute'])

    def get_all_enabled_chats(self):
        """Получение всех чатов с включенной рассылкой"""
        return [chat_id for chat_id, settings in self.settings.items() 
                if settings.get('enabled', False)]

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