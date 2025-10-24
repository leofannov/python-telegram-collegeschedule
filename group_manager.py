import json
import os
from typing import Dict, List, Any
from config import AVAILABLE_GROUPS

class GroupManager:
    def __init__(self, settings_file='group_settings.json'):
        self.settings_file = settings_file
        self.settings = self.load_settings()

    def load_settings(self) -> Dict[str, Any]:
        """Загрузка настроек групп из файла"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка загрузки настроек групп: {e}")
        return {}

    def save_settings(self):
        """Сохранение настроек групп в файл"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения настроек групп: {e}")

    def set_group(self, chat_id: str, group: str):
        """Установка группы для чата"""
        if group in AVAILABLE_GROUPS:
            self.settings[str(chat_id)] = group
            self.save_settings()
        else:
            raise ValueError(f"Группа {group} не найдена в списке доступных")

    def get_group(self, chat_id: str) -> str:
        """Получение группы для чата"""
        return self.settings.get(str(chat_id), '')

    def get_all_chats_with_group(self, group: str) -> List[str]:
        """Получение всех чатов с определенной группой"""
        return [chat_id for chat_id, chat_group in self.settings.items() 
                if chat_group == group]

    def get_available_groups(self) -> List[str]:
        """Получение списка доступных групп из конфига"""
        return AVAILABLE_GROUPS