from database_manager import db_manager
from config import AVAILABLE_GROUPS

class GroupManager:
    def __init__(self):
        pass  # Больше не нужно загружать из файла

    def set_group(self, chat_id: str, group: str):
        """Установка группы для чата"""
        if group in AVAILABLE_GROUPS:
            return db_manager.set_user_group(str(chat_id), group)
        else:
            raise ValueError(f"Группа {group} не найдена в списке доступных")

    def get_group(self, chat_id: str) -> str:
        """Получение группы для чата"""
        return db_manager.get_user_group(str(chat_id)) or ''

    def get_all_chats_with_group(self, group: str):
        """Получение всех чатов с определенной группой"""
        return db_manager.get_chats_by_group(group)

    def get_available_groups(self):
        """Получение списка доступных групп из конфига"""
        return AVAILABLE_GROUPS