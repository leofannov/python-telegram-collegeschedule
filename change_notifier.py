import json
import os
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from telegram import Bot
from schedule_parser import ScheduleParser
from change_detector import ChangeDetector
from group_manager import GroupManager
from config import RANGES
from database_manager import db_manager

class ChangeNotifier:
    def __init__(self, settings_file='change_notification_settings.json'):
        self.parser = ScheduleParser()
        self.detector = ChangeDetector()
        self.group_manager = GroupManager()
        
    def check_reload_flag(self):
        """Проверяет перезагрузку кэша (аналогично функции в bot.py)"""
        reload_flag = 'cache/reload_cache.flag'
        if os.path.exists(reload_flag):
            try:
                self.parser.clear_cache()
                os.remove(reload_flag)
                print("🔄 Кэш парсера перезагружен по флагу от крона")
                return True
            except Exception as e:
                print(f"❌ Ошибка перезагрузки кэша парсера: {e}")
        return False

    def enable_notifications(self, chat_id: str):
        """Включение уведомлений об изменениях для чата"""
        db_manager.set_change_notifications(str(chat_id), True)
        print(f"Уведомления об изменениях включены для чата {chat_id}")

    def disable_notifications(self, chat_id: str):
        """Выключение уведомлений об изменениях для чата"""
        db_manager.set_change_notifications(str(chat_id), False)
        print(f"Уведомления об изменениях выключены для чата {chat_id}")

    def is_notification_enabled(self, chat_id: str) -> bool:
        """Проверка, включены ли уведомления для чата"""
        return db_manager.get_change_notifications(str(chat_id))

    def get_all_enabled_chats(self) -> List[str]:
        """Получение всех чатов с включенными уведомлениями"""
        return db_manager.get_enabled_notification_chats()

    def get_chats_for_group(self, group: str) -> List[str]:
        """Получение всех чатов, подписанных на определенную группу"""
        return self.group_manager.get_all_chats_with_group(group)

    def find_next_school_day(self, group: str, start_date: datetime = None) -> Tuple[str, str, List[Dict]]:
        """
        Находит следующий учебный день с занятиями для конкретной группы
        
        Args:
            group: Группа для поиска
            start_date: Дата, с которой начинать поиск (по умолчанию завтра)
            
        Returns:
            Tuple: (день_недели, тип_недели, расписание) или (None, None, []) если дни закончились
        """
        if start_date is None:
            start_date = datetime.now() + timedelta(days=1)
            
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        
        # Ищем в течение 14 дней (2 недели)
        for i in range(14):
            current_date = start_date + timedelta(days=i)
            day_index = current_date.weekday()
            
            # Пропускаем воскресенье (индекс 6)
            if day_index >= len(days):
                continue
                
            day_name = days[day_index]
            week_type = self.parser.get_week_type_for_date(current_date)
            lessons = self.parser.get_day_schedule(group, week_type, day_name)
            
            # Если есть занятия, возвращаем этот день
            if lessons:
                return day_name, week_type, lessons
                
        return None, None, []

    async def check_and_notify_async(self, bot_token: str):
        """Асинхронная проверка изменений и отправка уведомлений для ВСЕХ групп"""
        print("Проверка изменений в расписании для всех групп...")
        
        # Получаем все доступные группы
        available_groups = self.group_manager.get_available_groups()
        print(f"Доступные группы для проверки: {available_groups}")
        
        changed_groups = []
        
        # Проверяем изменения для каждой группы
        for group in available_groups:
            print(f"🔍 Проверка изменений для группы {group}...")
            has_changed, changes = self.detector.smart_detector.has_changed(group)
            if has_changed:
                print(f"🔄 Обнаружено изменение в расписании для группы {group}!")
                print(f"   Детали изменений: {changes}")
                changed_groups.append(group)
        
        if not changed_groups:
            print("Изменений нет ни в одной группе")
            return False

        print(f"🔄 Обнаружены изменения в группах: {changed_groups}")
        
        # Отправляем уведомления для каждой измененной группы
        for group in changed_groups:
            await self._notify_group_changes(bot_token, group)
        
        return True

    async def _notify_group_changes(self, bot_token: str, group: str):
        """Отправка уведомлений об изменениях для конкретной группы"""
        # ОЧИСТКА КЭША ПЕРЕД ФОРМИРОВАНИЕМ РАСПИСАНИЯ
        self.check_reload_flag()
        
        # ДОПОЛНИТЕЛЬНАЯ ОЧИСТКА КЭША ПАРСЕРА
        try:
            self.parser.clear_cache()
        except Exception as e:
            print(f"⚠️ Не удалось очистить кэш парсера: {e}")
        
        # Получаем все чаты, подписанные на эту группу
        group_chats = self.get_chats_for_group(group)
        enabled_chats = [chat_id for chat_id in group_chats if self.is_notification_enabled(chat_id)]
        
        if not enabled_chats:
            print(f"Нет включенных чатов для уведомлений группы {group}")
            return
        
        print(f"Найдено {len(enabled_chats)} чатов для уведомления группы {group}")

        # Получаем актуальное расписание (после очистки кэша)
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        tomorrow_index = (datetime.now() + timedelta(days=1)).weekday()
        
        day_name = None
        week_type = None
        lessons = []
        schedule_text = ""
        
        if tomorrow_index >= len(days):  # Воскресенье
            # Ищем следующий учебный день
            day_name, week_type, lessons = self.find_next_school_day(group)
            if day_name:
                schedule_text = self.parser.format_schedule_text(group, week_type, day_name, lessons)
                extra_info = f"\n\n💡 На завтра (воскресенье) занятий нет, поэтому показываем расписание на следующий учебный день: {day_name}"
            else:
                schedule_text = "Завтра воскресенье - занятий нет! 🎉"
                day_name = "Воскресенье"
                extra_info = ""
        else:
            day_name = days[tomorrow_index]
            tomorrow_date = datetime.now() + timedelta(days=1)
            week_type = self.parser.get_week_type_for_date(tomorrow_date)
            lessons = self.parser.get_day_schedule(group, week_type, day_name)
            
            # Проверяем, есть ли занятия
            if not lessons:
                # Ищем следующий учебный день
                next_day_name, next_week_type, next_lessons = self.find_next_school_day(group)
                if next_day_name:
                    schedule_text = self.parser.format_schedule_text(group, next_week_type, next_day_name, next_lessons)
                    extra_info = f"\n\n💡 На завтра ({day_name}) занятий нет, поэтому показываем расписание на следующий учебный день: {next_day_name}"
                    day_name = next_day_name
                    week_type = next_week_type
                else:
                    schedule_text = f"На {day_name} занятий нет"
                    extra_info = ""
            else:
                schedule_text = self.parser.format_schedule_text(group, week_type, day_name, lessons)
                extra_info = ""

        last_update = self.parser.get_last_update()
        
        message_text = (
            "🔄 *ОБНОВЛЕНИЕ РАСПИСАНИЯ!*\n\n"
            f"Расписание для группы {group} было обновлено! Вот актуальное расписание:\n\n"
            f"{schedule_text}"
            f"{extra_info}\n"
            f"🔄 Последнее обновление: {last_update}"
        )

        # Отправляем уведомления во все включенные чаты этой группы
        bot = Bot(token=bot_token)
        success_count = 0
        failed_chats = []
        
        for chat_id in enabled_chats:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode='Markdown'
                )
                success_count += 1
                print(f"✅ Уведомление для группы {group} отправлено в чат {chat_id}")
            except Exception as e:
                error_msg = f"Ошибка отправки уведомления в чат {chat_id}: {e}"
                print(f"❌ {error_msg}")
                failed_chats.append((chat_id, str(e)))

        print(f"✅ Уведомления для группы {group} отправлены в {success_count} чатов")
        
        if failed_chats:
            print(f"❌ Не удалось отправить в {len(failed_chats)} чатов:")
            for chat_id, error in failed_chats:
                print(f"   Чат {chat_id}: {error}")

    def check_and_notify(self, bot_token: str):
        """Синхронная обертка для асинхронной проверки изменений"""
        return asyncio.run(self.check_and_notify_async(bot_token))

    def check_changes_after_download(self, bot_token: str):
        """Проверка изменений после скачивания нового файла"""
        print("🔄 ПРОВЕРКА ИЗМЕНЕНИЙ ПОСЛЕ СКАЧИВАНИЯ")
        
        # Получаем все доступные группы
        available_groups = self.group_manager.get_available_groups()
        print(f"Доступные группы для проверки: {available_groups}")
        
        changed_groups = []
        
        # Проверяем изменения для каждой группы
        for group in available_groups:
            print(f"🔍 Проверка изменений для группы {group}...")
            
            # Используем умный детектор для проверки изменений
            has_changed, changes = self.detector.smart_detector.has_changed(group)
            
            if has_changed:
                print(f"🔄 Обнаружено изменение в расписании для группы {group}!")
                print(f"   Детали изменений: {changes}")
                changed_groups.append((group, changes))
        
        if not changed_groups:
            print("ℹ️ Изменений нет ни в одной группе")
            return False

        print(f"🎉 Обнаружены изменения в группах: {[g[0] for g in changed_groups]}")
        
        # ОЧИЩАЕМ КЭШ ПАРСЕРА ПЕРЕД ОТПРАВКОЙ УВЕДОМЛЕНИЙ
        print("\n🗑️ Очистка кэша парсера перед отправкой уведомлений...")
        try:
            from schedule_parser import ScheduleParser
            parser = ScheduleParser()
            parser.clear_cache()
            print("✅ Очищен кэш парсера")
        except Exception as e:
            print(f"⚠️ Не удалось очистить кэш парсера: {e}")
        
        # Отправляем уведомления для каждой измененной группы
        for group, changes in changed_groups:
            asyncio.run(self._notify_group_changes(bot_token, group))
        
        # ТЕПЕРЬ ОБНОВЛЯЕМ КЭШ ДЕТЕКТОРА ПОСЛЕ ОТПРАВКИ УВЕДОМЛЕНИЙ
        print("\n💾 Обновление кэша детектора после отправки уведомлений...")
        for group, changes in changed_groups:
            self.detector.smart_detector.force_update_cache(group)
            print(f"✅ Обновлен кэш для группы {group}")
        
        # Устанавливаем флаг перезагрузки для бота
        print("\n🔄 Установка флага перезагрузки кэша для бота...")
        try:
            reload_flag = 'cache/reload_cache.flag'
            with open(reload_flag, 'w') as f:
                f.write(datetime.now().isoformat())
            print("✅ Флаг перезагрузки кэша установлен")
        except Exception as e:
            print(f"⚠️ Не удалось установить флаг перезагрузки: {e}")
    
        return True

    def force_check_and_notify(self, bot_token: str):
        """Принудительная проверка и отправка уведомлений"""
        print("🎯 ПРИНУДИТЕЛЬНАЯ ПРОВЕРКА ИЗМЕНЕНИЙ")
        
        # Очищаем кэш перед принудительной проверкой
        print("🗑️ Очистка кэша для принудительной проверки...")
        self.detector.smart_detector.clear_cache()
        
        return self.check_changes_after_download(bot_token)

    def force_detect_changes(self):
        """Принудительная детекция изменений для всех групп"""
        print("🎯 ПРИНУДИТЕЛЬНАЯ ДЕТЕКЦИЯ ИЗМЕНЕНИЙ ДЛЯ ВСЕХ ГРУПП")
        
        available_groups = self.group_manager.get_available_groups()
        print(f"Доступные группы: {available_groups}")
        
        changes_found = False
        
        for group in available_groups:
            print(f"\n🔍 Проверка группы: {group}")
            
            # Используем умный детектор для проверки изменений
            has_changed, changes = self.detector.smart_detector.has_changed(group)
            
            if has_changed:
                print(f"🎉 ОБНАРУЖЕНЫ ИЗМЕНЕНИЯ ДЛЯ ГРУППЫ {group}!")
                print(f"   Детали: {changes}")
                changes_found = True
                
                # Обновляем кэш для этой группы
                self.detector.smart_detector.force_update_cache(group)
            else:
                print(f"✅ Изменений нет для группы {group}")
                # ВСЕГДА обновляем кэш, даже если изменений нет
                self.detector.smart_detector.force_update_cache(group)
        
        return changes_found

    def get_notification_status(self, chat_id: str) -> str:
        """Получение статуса уведомлений для чата"""
        if self.is_notification_enabled(chat_id):
            return "🔔 Уведомления об изменениях расписания *ВКЛЮЧЕНЫ*"
        else:
            return "🔕 Уведомления об изменениях расписания *ВЫКЛЮЧЕНЫ*"

    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики по уведомлениям"""
        try:
            # Получаем все чаты с группами из базы данных
            enabled_chats = self.get_all_enabled_chats()
            
            # Статистика по группам
            groups_stats = {}
            available_groups = self.group_manager.get_available_groups()
            
            for group in available_groups:
                group_chats = self.get_chats_for_group(group)
                enabled_in_group = len([chat_id for chat_id in group_chats if self.is_notification_enabled(chat_id)])
                groups_stats[group] = enabled_in_group
            
            # Получаем общее количество чатов из базы данных
            try:
                from database_manager import db_manager
                settings_info = db_manager.get_settings_info()
                total_chats = settings_info.get('user_groups_count', 0)
            except Exception as e:
                print(f"⚠️ Ошибка получения общего количества чатов: {e}")
                total_chats = len(enabled_chats)  # fallback
            
            return {
                'total_chats': total_chats,
                'enabled_chats': len(enabled_chats),
                'disabled_chats': total_chats - len(enabled_chats),
                'groups_stats': groups_stats
            }
        except Exception as e:
            print(f"❌ Ошибка получения статистики: {e}")
            return {
                'total_chats': 0,
                'enabled_chats': 0,
                'disabled_chats': 0,
                'groups_stats': {}
            }

    async def force_check_async(self, bot_token: str):
        """Асинхронная принудительная проверка изменений"""
        print("Принудительная проверка изменений для всех групп...")
        # Для каждой группы обновляем хэш
        available_groups = self.group_manager.get_available_groups()
        for group in available_groups:
            print(f"Принудительное обновление хэша для группы {group}")
            # Здесь должна быть логика принудительного обновления хэша для умного детектора
        return await self.check_and_notify_async(bot_token)

    def force_check(self, bot_token: str):
        """Синхронная обертка для асинхронной принудительной проверки"""
        return asyncio.run(self.force_check_async(bot_token))
        
    def get_next_school_day_info(self, group: str) -> Dict[str, Any]:
        """Получить информацию о следующем учебном дне для группы"""
        # ДОБАВЛЕНО: Проверка флага перезагрузки кэша
        self.check_reload_flag()
        
        next_day, week_type, lessons = self.find_next_school_day(group)
        
        if next_day:
            schedule_text = self.parser.format_schedule_text(group, week_type, next_day, lessons)
            return {
                'day': next_day,
                'week_type': week_type,
                'lessons': lessons,
                'schedule_text': schedule_text,
                'found': True
            }
        else:
            return {
                'day': None,
                'week_type': None,
                'lessons': [],
                'schedule_text': "Не найдено учебных дней с занятиями",
                'found': False
            }

    async def send_test_notification_async(self, bot_token: str, chat_id: str = None):
        """Асинхронная отправка тестового уведомления"""
        try:
            bot = Bot(token=bot_token)
            
            if chat_id:
                # Отправка конкретному чату
                chats_to_notify = [chat_id]
            else:
                # Отправка всем включенным чатам
                chats_to_notify = self.get_all_enabled_chats()
            
            if not chats_to_notify:
                print("❌ Нет чатов для отправки тестового уведомления")
                return False
                
            # Для каждого чата получаем его группу и отправляем соответствующее сообщение
            for chat_id in chats_to_notify:
                group = self.group_manager.get_group(chat_id)
                if not group:
                    continue
                    
                # Тестируем новую функцию поиска следующего учебного дня
                next_day, next_week_type, next_lessons = self.find_next_school_day(group)
                
                if next_day:
                    schedule_text = self.parser.format_schedule_text(group, next_week_type, next_day, next_lessons)
                    test_message = (
                        "🔔 *ТЕСТОВОЕ УВЕДОМЛЕНИЕ*\n\n"
                        "Это тестовое сообщение для проверки системы уведомлений.\n"
                        f"Группа: {group}\n"
                        f"Следующий учебный день: {next_day}\n\n"
                        f"{schedule_text}\n\n"
                        f"Время отправки: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                    )
                else:
                    test_message = (
                        "🔔 *ТЕСТОВОЕ УВЕДОМЛЕНИЕ*\n\n"
                        "Это тестовое сообщение для проверки системы уведомлений.\n"
                        f"Группа: {group}\n"
                        "Не найдено следующих учебных дней с занятиями.\n\n"
                        f"Время отправки: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                    )
                
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=test_message,
                        parse_mode='Markdown'
                    )
                    print(f"✅ Тестовое сообщение отправлено в чат {chat_id} для группы {group}")
                except Exception as e:
                    print(f"❌ Ошибка отправки в чат {chat_id}: {e}")
            
            print(f"✅ Тестовые сообщения отправлены в {len(chats_to_notify)} чатов")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при тестовой отправке: {e}")
            import traceback
            traceback.print_exc()
            return False

    def send_test_notification(self, bot_token: str, chat_id: str = None):
        """Синхронная обертка для асинхронной тестовой отправки"""
        return asyncio.run(self.send_test_notification_async(bot_token, chat_id))

    def get_next_school_day_info(self, group: str) -> Dict[str, Any]:
        """Получить информацию о следующем учебном дне для группы"""
        next_day, week_type, lessons = self.find_next_school_day(group)
        
        if next_day:
            schedule_text = self.parser.format_schedule_text(group, week_type, next_day, lessons)
            return {
                'day': next_day,
                'week_type': week_type,
                'lessons': lessons,
                'schedule_text': schedule_text,
                'found': True
            }
        else:
            return {
                'day': None,
                'week_type': None,
                'lessons': [],
                'schedule_text': "Не найдено учебных дней с занятиями",
                'found': False
            }

    def debug_group(self, group_name):
        """Отладочная функция для группы"""
        print(f"🔍 ОТЛАДКА ГРУППЫ: {group_name}")
        self.detector.smart_detector.debug_group(group_name)

if __name__ == "__main__":
    # Тестирование нотификатора
    print("=== Тестирование ChangeNotifier ===")
    
    notifier = ChangeNotifier()
    
    # Статистика
    stats = notifier.get_statistics()
    print(f"Статистика уведомлений:")
    print(f"  Всего чатов: {stats['total_chats']}")
    print(f"  Включенных: {stats['enabled_chats']}")
    print(f"  Выключенных: {stats['disabled_chats']}")
    print(f"  Статистика по группам: {stats['groups_stats']}")
    
    # Тестирование поиска следующего учебного дня
    print("\n=== Тестирование поиска следующего учебного дня ===")
    available_groups = notifier.group_manager.get_available_groups()
    for group in available_groups:
        next_day_info = notifier.get_next_school_day_info(group)
        if next_day_info['found']:
            print(f"Группа {group}: следующий учебный день: {next_day_info['day']}")
            print(f"  Тип недели: {next_day_info['week_type']}")
            print(f"  Количество пар: {len(next_day_info['lessons'])}")
        else:
            print(f"Группа {group}: учебные дни не найдены")
    
    # Тестовое включение уведомлений д