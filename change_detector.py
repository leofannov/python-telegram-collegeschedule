import hashlib
import json
import os
from datetime import datetime
from schedule_parser import ScheduleParser
from smart_change_detector import SmartChangeDetector

class ChangeDetector:
    def __init__(self, cache_file='cache/schedule_hash.cache'):
        self.cache_file = cache_file
        self.parser = ScheduleParser()
        self.smart_detector = SmartChangeDetector()
        
        # Создаем папку cache если нет
        if not os.path.exists('cache'):
            os.makedirs('cache')

    def has_schedule_changed(self, group=None):
        """Проверка, изменилось ли расписание для конкретной группы"""
        if group:
            # Используем умный детектор для конкретной группы
            has_changed, changes = self.smart_detector.has_changed(group)
            return has_changed
        else:
            # Старая логика для обратной совместимости
            return self._legacy_has_schedule_changed()

    def _legacy_has_schedule_changed(self):
        """Старая проверка изменений для всего файла"""
        current_hash = self.get_schedule_hash()
        if not current_hash:
            print("Не удалось получить текущий хэш расписания")
            return False

        previous_hash = self.get_previous_hash()
        
        if not previous_hash:
            print("Предыдущий хэш не найден, сохраняем текущий хэш")
            self.save_hash(current_hash)
            return False
        
        print(f"Сравнение хэшей: предыдущий={previous_hash[:8]}..., текущий={current_hash[:8]}...")
        return current_hash != previous_hash

    def get_schedule_hash(self):
        """Получение хэша текущего расписания (старая версия)"""
        try:
            wb = self.parser.load_workbook()
            ws = wb.active
            
            # Получаем все данные из важных диапазонов
            all_data = []
            
            # Диапазоны для четной недели
            for day_ranges in self.parser.ranges['even'].values():
                for range_type, cell_range in day_ranges.items():
                    try:
                        data = self.parser.get_cell_range(ws, cell_range)
                        all_data.append(str(data))
                    except Exception as e:
                        print(f"Ошибка чтения диапазона {cell_range}: {e}")
                        all_data.append(f"error_{cell_range}")
            
            # Диапазоны для нечетной недели  
            for day_ranges in self.parser.ranges['odd'].values():
                for range_type, cell_range in day_ranges.items():
                    try:
                        data = self.parser.get_cell_range(ws, cell_range)
                        all_data.append(str(data))
                    except Exception as e:
                        print(f"Ошибка чтения диапазона {cell_range}: {e}")
                        all_data.append(f"error_{cell_range}")
            
            wb.close()
            
            # Создаем хэш из всех данных
            data_string = ''.join(all_data)
            return hashlib.md5(data_string.encode()).hexdigest()
            
        except Exception as e:
            print(f"Ошибка при получении хэша расписания: {e}")
            return None

    def get_previous_hash(self):
        """Получение предыдущего хэша из кэша"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('hash')
        except Exception as e:
            print(f"Ошибка чтения кэша хэша: {e}")
        return None

    def save_hash(self, hash_value):
        """Сохранение хэша в кэш"""
        try:
            cache_data = {
                'hash': hash_value,
                'last_checked': datetime.now().isoformat(),
                'last_checked_human': datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            print(f"Хэш сохранен в кэш: {hash_value[:8]}...")
        except Exception as e:
            print(f"Ошибка сохранения хэша: {e}")

    def update_hash(self):
        """Обновление хэша в кэше (после рассылки уведомлений)"""
        current_hash = self.get_schedule_hash()
        if current_hash:
            self.save_hash(current_hash)
            print("Хэш обновлен после уведомлений")
            return True
        return False

    def get_cache_info(self):
        """Получение информации о кэше"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        'last_checked': data.get('last_checked_human', 'Неизвестно'),
                        'hash': data.get('hash', 'Неизвестно')[:8] + '...'
                    }
        except Exception as e:
            print(f"Ошибка чтения информации о кэше: {e}")
        return {'last_checked': 'Неизвестно', 'hash': 'Неизвестно'}

    def get_cache_info_for_group(self, group):
        """Получение информации о кэше для конкретной группы"""
        return self.smart_detector.get_cache_info_for_group(group)

    def force_update_hash(self):
        """Принудительное обновление хэша (например, после сбоя)"""
        current_hash = self.get_schedule_hash()
        if current_hash:
            self.save_hash(current_hash)
            print("Хэш принудительно обновлен")
            return True
        return False

if __name__ == "__main__":
    # Тестирование детектора
    detector = ChangeDetector()
    print("=== Тестирование ChangeDetector ===")
    
    cache_info = detector.get_cache_info()
    print(f"Информация о кэше: {cache_info}")
    
    has_changed = detector.has_schedule_changed()
    print(f"Расписание изменилось: {has_changed}")
    
    current_hash = detector.get_schedule_hash()
    print(f"Текущий хэш: {current_hash[:8]}...")