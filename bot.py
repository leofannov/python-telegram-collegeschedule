import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler,
    ContextTypes, MessageHandler, filters
)
from schedule_parser import ScheduleParser
from mailing_manager import MailingManager, TOMSK_TZ
from change_notifier import ChangeNotifier
from group_manager import GroupManager
from config import BELLS_SCHEDULE
from datetime import datetime, time, timedelta
import os
import json

# Настройки
TOKEN = ""

# Состояния разговора
SELECT_GROUP, SELECT_WEEK, SELECT_DAY, SET_MAILING_TIME = range(4)

# Инициализация парсеров и менеджеров
parser = ScheduleParser()
mailing_manager = MailingManager()
change_notifier = ChangeNotifier()
group_manager = GroupManager()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    try:
        chat_id = update.message.chat_id
        group = group_manager.get_group(chat_id)
        
        text = (
            "👋 Привет! Я бот с расписанием занятий.\n\n"
            f"📋 Текущая группа: {group if group else 'не выбрана'}\n\n"
            "📋 Доступные команды:\n"
            "/setgroup - выбрать группу\n"
            "/schedule - посмотреть расписание\n"
            "/today - расписание на сегодня\n"
            "/tomorrow - расписание на завтра\n"
            "/week - расписание на всю неделю\n"
            "/bells - расписание звонков\n"
            "/bells_today - звонки на сегодня\n"
            "/update_info - информация об обновлении\n"
            "/mailing - управление ежедневной рассылкой\n"
            "/mailing_status - статус ежедневной рассылки\n"
            "/changes - управление уведомлениями об изменениях"
        )
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        await update.message.reply_text("❌ Ошибка при запуске бота. Попробуйте позже.")

async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор группы"""
    try:
        available_groups = group_manager.get_available_groups()
        
        # Логируем для отладки
        logger.info(f"Доступные группы из конфига: {available_groups}")
        
        if not available_groups:
            await update.message.reply_text("❌ В системе нет доступных групп. Обратитесь к администратору.")
            return ConversationHandler.END
        
        keyboard = []
        for group in available_groups:
            keyboard.append([InlineKeyboardButton(group, callback_data=f'group_{group}')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👥 Выберите вашу группу:",
            reply_markup=reply_markup
        )
        return SELECT_GROUP
    except Exception as e:
        logger.error(f"Ошибка в команде set_group: {e}")
        await update.message.reply_text("❌ Ошибка при выборе группы. Попробуйте позже.")
        return ConversationHandler.END

async def group_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора группы"""
    try:
        query = update.callback_query
        await query.answer()
        
        group = query.data.replace('group_', '')
        chat_id = query.message.chat_id
        
        # Логируем выбранную группу
        logger.info(f"Пользователь {chat_id} выбрал группу: {group}")
        
        try:
            group_manager.set_group(chat_id, group)
            await query.edit_message_text(f"✅ Группа {group} установлена!")
        except ValueError as e:
            logger.error(f"Ошибка установки группы: {e}")
            await query.edit_message_text(f"❌ Ошибка: {e}")
            return ConversationHandler.END
        
        # Показываем главное меню
        await query.message.reply_text(
            "Теперь вы можете использовать команды:\n"
            "/today - расписание на сегодня\n"
            "/week - расписание на неделю\n"
            "/mailing - настройка рассылки\n"
            "и другие команды из /start"
        )
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в group_select: {e}")
        await update.message.reply_text("❌ Ошибка при выборе группы. Попробуйте позже.")
        return ConversationHandler.END

async def update_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Информация о последнем обновлении"""
    try:
        chat_id = update.message.chat_id
        group = group_manager.get_group(chat_id)
        
        last_update = parser.get_last_update()
        
        if group:
            # Используем умный детектор для получения информации
            cache_info = change_notifier.detector.get_cache_info_for_group(group)
            text = (
                f"🔄 Информация об обновлениях для группы {group}\n\n"
                f"📅 Последнее обновление файла: {last_update}\n"
                f"🔍 Последняя проверка изменений: {cache_info['last_checked']}\n"
                f"🔐 Хэш расписания группы: {cache_info['hash']}\n\n"
                f"Система использует умный детектор изменений,\n"
                f"который отслеживает только значимые изменения в расписании."
            )
        else:
            text = (
                f"🔄 Информация об обновлениях\n\n"
                f"📅 Последнее обновление файла: {last_update}\n\n"
                f"❌ Группа не выбрана\n"
                f"Используйте /setgroup для выбора группы"
            )
        
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Ошибка в команде update_info: {e}")
        await update.message.reply_text("❌ Ошибка при получении информации об обновлениях.")

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало выбора расписания"""
    try:
        chat_id = update.message.chat_id
        group = group_manager.get_group(chat_id)
        
        if not group:
            await update.message.reply_text(
                "❌ Сначала выберите группу с помощью команды /setgroup"
            )
            return ConversationHandler.END
        
        keyboard = [
            [
                InlineKeyboardButton("Чётная неделя", callback_data='even'),
                InlineKeyboardButton("Нечётная неделя", callback_data='odd'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Показываем текущую неделю
        current_week = parser.get_week_type()
        current_week_text = "чётная" if current_week == 'even' else "нечётная"
        
        await update.message.reply_text(
            f"📅 Выберите тип недели для группы {group}:\n(Текущая неделя: {current_week_text})",
            reply_markup=reply_markup
        )
        return SELECT_WEEK
    except Exception as e:
        logger.error(f"Ошибка в команде schedule: {e}")
        await update.message.reply_text("❌ Ошибка при выборе расписания. Попробуйте позже.")
        return ConversationHandler.END

async def week_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора недели"""
    try:
        query = update.callback_query
        await query.answer()
        
        week_type = query.data
        context.user_data['week_type'] = week_type
        
        # Создаем клавиатуру с днями недели
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        keyboard = []
        
        # По 2 кнопки в ряду
        for i in range(0, len(days), 2):
            row = []
            row.append(InlineKeyboardButton(days[i], callback_data=days[i]))
            if i + 1 < len(days):
                row.append(InlineKeyboardButton(days[i + 1], callback_data=days[i + 1]))
            keyboard.append(row)
        
        # Добавляем кнопку "Вся неделя"
        keyboard.append([InlineKeyboardButton("📋 Вся неделя", callback_data='all_week')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        week_type_text = "чётную" if week_type == 'even' else "нечётную"
        await query.edit_message_text(
            f"Выбрана {week_type_text} неделя. Теперь выберите день:",
            reply_markup=reply_markup
        )
        return SELECT_DAY
    except Exception as e:
        logger.error(f"Ошибка в week_select: {e}")
        await update.message.reply_text("❌ Ошибка при выборе недели. Попробуйте позже.")
        return ConversationHandler.END

async def day_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора дня"""
    try:
        query = update.callback_query
        await query.answer()
        
        day = query.data
        week_type = context.user_data.get('week_type', 'even')
        chat_id = query.message.chat_id
        group = group_manager.get_group(chat_id)
        
        if day == 'all_week':
            # Показать всю неделю
            text = get_full_week_schedule(group, week_type)
        else:
            # Показать конкретный день
            lessons = parser.get_day_schedule(group, week_type, day)
            text = parser.format_schedule_text(group, week_type, day, lessons)
        
        # Добавляем информацию о последнем обновлении
        last_update = parser.get_last_update()
        text += f"\n\n🔄 Последнее обновление: {last_update}"
        
        # Если сообщение слишком длинное, разбиваем на части
        if len(text) > 4096:
            # Разбиваем текст на части по 4096 символов
            parts = [text[i:i+4096] for i in range(0, len(text), 4096)]
            for part in parts:
                await query.edit_message_text(part)
        else:
            await query.edit_message_text(text)
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в day_select: {e}")
        await update.message.reply_text("❌ Ошибка при получении расписания. Попробуйте позже.")
        return ConversationHandler.END

def get_full_week_schedule(group, week_type):
    """Получить расписание на всю неделю"""
    try:
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        week_type_text = "чётная" if week_type == 'even' else "нечётная"
        
        # Используем оптимизированную функцию
        week_schedule = parser.get_week_schedule(group, week_type)
        
        text = f"📅 Расписание на {week_type_text} неделю - {group}:\n\n"
        
        for day in days:
            lessons = week_schedule.get(day, [])
            day_text = parser.format_schedule_text(group, week_type, day, lessons)
            text += day_text + "\n" + "─" * 30 + "\n\n"
        
        return text
    except Exception as e:
        logger.error(f"Ошибка в get_full_week_schedule: {e}")
        return f"❌ Ошибка при получении расписания на неделю: {e}"

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Расписание на сегодня"""
    try:
        from datetime import datetime
        
        chat_id = update.message.chat_id
        group = group_manager.get_group(chat_id)
        
        if not group:
            await update.message.reply_text(
                "❌ Сначала выберите группу с помощью команды /setgroup"
            )
            return
        
        # Соответствие номеров дням недели (понедельник=0, воскресенье=6)
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        today_index = datetime.now().weekday()
        
        if today_index >= len(days):  # Воскресенье
            await update.message.reply_text("Сегодня воскресенье - занятий нет! 🎉")
            return
        
        day = days[today_index]
        week_type = parser.get_week_type()
        
        lessons = parser.get_day_schedule(group, week_type, day)
        text = parser.format_schedule_text(group, week_type, day, lessons)
        
        last_update = parser.get_last_update()
        text += f"\n\n🔄 Последнее обновление: {last_update}"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"Ошибка в команде today: {e}")
        await update.message.reply_text(
            "❌ Ошибка при получении расписания. Возможно, проблема с файлом расписания.\n"
            "Попробуйте позже или используйте /update_info для проверки статуса."
        )

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Расписание на завтра"""
    try:
        from datetime import datetime, timedelta
        
        chat_id = update.message.chat_id
        group = group_manager.get_group(chat_id)
        
        if not group:
            await update.message.reply_text(
                "❌ Сначала выберите группу с помощью команды /setgroup"
            )
            return
        
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        tomorrow_index = (datetime.now() + timedelta(days=1)).weekday()
        
        if tomorrow_index >= len(days):  # Воскресенье
            await update.message.reply_text("Завтра воскресенье - занятий нет! 🎉")
            return
        
        day = days[tomorrow_index]
        
        # Определяем тип недели для завтра
        tomorrow_date = datetime.now() + timedelta(days=1)
        week_type = parser.get_week_type_for_date(tomorrow_date)
        
        lessons = parser.get_day_schedule(group, week_type, day)
        text = parser.format_schedule_text(group, week_type, day, lessons)
        
        last_update = parser.get_last_update()
        text += f"\n\n🔄 Последнее обновление: {last_update}"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"Ошибка в команде tomorrow: {e}")
        await update.message.reply_text(
            "❌ Ошибка при получении расписания на завтра. Попробуйте позже."
        )

async def week_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Расписание на всю текущую неделю"""
    try:
        chat_id = update.message.chat_id
        group = group_manager.get_group(chat_id)
        
        if not group:
            await update.message.reply_text(
                "❌ Сначала выберите группу с помощью команды /setgroup"
            )
            return
        
        week_type = parser.get_week_type()
        
        # Используем оптимизированную функцию
        week_schedule_data = parser.get_week_schedule(group, week_type)
        text = parser.format_week_schedule_text(group, week_type, week_schedule_data)
        
        last_update = parser.get_last_update()
        text += f"\n🔄 Последнее обновление: {last_update}"
        
        # Если сообщение слишком длинное, разбиваем на части
        if len(text) > 4096:
            parts = [text[i:i+4096] for i in range(0, len(text), 4096)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(text)
            
    except Exception as e:
        logger.error(f"Ошибка в команде week: {e}")
        await update.message.reply_text(
            "❌ Ошибка при получении расписания на неделю.\n"
            "Попробуйте позже или используйте /update_info для проверки статуса."
        )

async def bells(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Расписание звонков"""
    try:
        text = "🔔 Расписание звонков:\n\n"
        
        for day, pairs in BELLS_SCHEDULE.items():
            text += f"**{day}:**\n"
            for pair_info in pairs:
                text += f"• {pair_info['pair']}:\n"
                text += f"  Первая половина: {pair_info['first_half']}\n"
                text += f"  Вторая половина: {pair_info['second_half']}\n"
            text += "\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка в команде bells: {e}")
        await update.message.reply_text("❌ Ошибка при получении расписания звонков.")

async def bells_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Расписание звонков на сегодня"""
    try:
        from datetime import datetime
        
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        today_index = datetime.now().weekday()
        
        if today_index >= len(days):  # Воскресенье
            await update.message.reply_text("Сегодня воскресенье - звонков нет! 🎉")
            return
        
        day = days[today_index]
        pairs = BELLS_SCHEDULE.get(day, [])
        
        text = f"🔔 Расписание звонков на {day}:\n\n"
        
        for pair_info in pairs:
            text += f"• {pair_info['pair']}:\n"
            text += f"  Первая половина: {pair_info['first_half']}\n"
            text += f"  Вторая половина: {pair_info['second_half']}\n\n"
        
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Ошибка в команде bells_today: {e}")
        await update.message.reply_text("❌ Ошибка при получении расписания звонков на сегодня.")

async def mailing_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Управление рассылкой - главное меню"""
    try:
        chat_id = update.message.chat_id
        mailing_info = mailing_manager.get_mailing_info(chat_id)
        
        # Проверяем, выбрана ли группа
        group = group_manager.get_group(chat_id)
        if not group:
            await update.message.reply_text(
                "❌ Сначала выберите группу с помощью команды /setgroup"
            )
            return ConversationHandler.END
        
        keyboard = [
            [InlineKeyboardButton("✅ Включить рассылку", callback_data='mailing_enable')],
            [InlineKeyboardButton("❌ Выключить рассылку", callback_data='mailing_disable')],
            [InlineKeyboardButton("⏰ Установить время", callback_data='mailing_set_time')],
            [InlineKeyboardButton("📊 Статус рассылки", callback_data='mailing_status')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status = "включена" if mailing_info['enabled'] else "выключена"
        time_str = f"{mailing_info['time']['hour']:02d}:{mailing_info['time']['minute']:02d}"
        
        text = (
            f"📧 Управление рассылкой\n\n"
            f"Текущий статус: {status}\n"
            f"Время рассылки: {time_str}\n"
            f"Группа: {group}\n"
            f"Часовой пояс: Томск (UTC+7)\n\n"
            f"Выберите действия:"
        )
        
        await update.message.reply_text(text, reply_markup=reply_markup)
        return SET_MAILING_TIME
    except Exception as e:
        logger.error(f"Ошибка в команде mailing: {e}")
        await update.message.reply_text("❌ Ошибка при управлении рассылкой. Попробуйте позже.")
        return ConversationHandler.END

async def mailing_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик кнопок управления рассылкой"""
    try:
        query = update.callback_query
        await query.answer()
        
        chat_id = query.message.chat_id
        action = query.data
        
        if action == 'mailing_enable':
            mailing_manager.enable_mailing(chat_id)
            await query.edit_message_text("✅ Рассылка включена! Будем отправлять расписание на следующий день.")
            
            # Перезапускаем задачу для этого чата
            await restart_mailing_job(context, chat_id)
            
        elif action == 'mailing_disable':
            mailing_manager.disable_mailing(chat_id)
            await query.edit_message_text("❌ Рассылка выключена.")
            
            # Удаляем задачу для этого чата
            await remove_mailing_job(context, chat_id)
            
        elif action == 'mailing_set_time':
            await query.edit_message_text(
                "⏰ Введите время для рассылки в формате ЧЧ:ММ (например, 18:00):\n"
                "Часовой пояс: Томск (UTC+7)"
            )
            return SET_MAILING_TIME
            
        elif action == 'mailing_status':
            mailing_info = mailing_manager.get_mailing_info(chat_id)
            status = "включена" if mailing_info['enabled'] else "выключена"
            time_str = f"{mailing_info['time']['hour']:02d}:{mailing_info['time']['minute']:02d}"
            next_mailing = mailing_manager.get_next_mailing_datetime(chat_id)
            
            text = (
                f"📊 Статус рассылки:\n\n"
                f"• Статус: {status}\n"
                f"• Время: {time_str}\n"
                f"• Часовой пояс: Томск\n"
                f"• Следующая рассылка: {next_mailing.strftime('%d.%m.%Y в %H:%M')}"
            )
            await query.edit_message_text(text)
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в mailing_button_handler: {e}")
        await update.message.reply_text("❌ Ошибка при обработке команды рассылки.")
        return ConversationHandler.END

async def set_mailing_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Установка времени рассылки"""
    try:
        time_str = update.message.text.strip()
        hour, minute = map(int, time_str.split(':'))
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await update.message.reply_text("❌ Неверное время! Используйте формат ЧЧ:ММ (например, 18:00)")
            return SET_MAILING_TIME
        
        chat_id = update.message.chat_id
        mailing_manager.set_mailing_time(chat_id, hour, minute)
        
        # Перезапускаем задачу
        await restart_mailing_job(context, chat_id)
        
        next_mailing = mailing_manager.get_next_mailing_datetime(chat_id)
        
        await update.message.reply_text(
            f"✅ Время рассылки установлено на {hour:02d}:{minute:02d}\n"
            f"Следующая рассылка: {next_mailing.strftime('%d.%m.%Y в %H:%M')}\n"
            f"Часовой пояс: Томск (UTC+7)"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат! Используйте ЧЧ:ММ (например, 18:00)")
        return SET_MAILING_TIME
    except Exception as e:
        logger.error(f"Ошибка установки времени рассылки: {e}")
        await update.message.reply_text("❌ Ошибка при установке времени")
    
    return ConversationHandler.END

async def mailing_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать статус рассылки"""
    try:
        chat_id = update.message.chat_id
        mailing_info = mailing_manager.get_mailing_info(chat_id)
        status = "включена" if mailing_info['enabled'] else "выключена"
        time_str = f"{mailing_info['time']['hour']:02d}:{mailing_info['time']['minute']:02d}"
        
        text = f"📊 Статус рассылки:\n\n• Статус: {status}\n• Время: {time_str}\n• Часовой пояс: Томск"
        
        if mailing_info['enabled']:
            next_mailing = mailing_manager.get_next_mailing_datetime(chat_id)
            text += f"\n• Следующая рассылка: {next_mailing.strftime('%d.%m.%Y в %H:%M')}"
        
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Ошибка в команде mailing_status: {e}")
        await update.message.reply_text("❌ Ошибка при получении статуса рассылки.")

async def changes_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Управление уведомлениями об изменениях расписания с обработкой ошибок"""
    try:
        chat_id = update.message.chat_id
        status_text = change_notifier.get_notification_status(chat_id)
        
        keyboard = [
            [InlineKeyboardButton("🔔 Включить уведомления", callback_data='changes_enable')],
            [InlineKeyboardButton("🔕 Выключить уведомления", callback_data='changes_disable')],
            [InlineKeyboardButton("📊 Статус уведомлений", callback_data='changes_status')],
            [InlineKeyboardButton("📈 Статистика", callback_data='changes_stats')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"🔄 Управление уведомлениями об изменениях расписания\n\n"
            f"{status_text}\n\n"
            f"При включении бот будет присылать уведомление в этот чат при любом изменении расписания."
        )
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде changes: {e}")
        await update.message.reply_text("❌ Ошибка при управлении уведомлениями. Попробуйте позже.")

async def changes_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопок управления уведомлениями об изменениях"""
    try:
        query = update.callback_query
        await query.answer()
        
        chat_id = query.message.chat_id
        action = query.data
        
        if action == 'changes_enable':
            change_notifier.enable_notifications(chat_id)
            await query.edit_message_text(
                "🔔 *Уведомления об изменениях включены!*\n\n"
                "Теперь бот будет присылать уведомление в этот чат при изменении расписания вашей группы.",
                parse_mode='Markdown'
            )
            
        elif action == 'changes_disable':
            change_notifier.disable_notifications(chat_id)
            await query.edit_message_text(
                "🔕 *Уведомления об изменениях выключены!*",
                parse_mode='Markdown'
            )
            
        elif action == 'changes_status':
            status_text = change_notifier.get_notification_status(chat_id)
            await query.edit_message_text(status_text, parse_mode='Markdown')
            
        elif action == 'changes_stats':
            stats = change_notifier.get_statistics()
            
            text = (
                "📈 *Статистика уведомлений об изменениях*\n\n"
                f"• Всего чатов в системе: {stats['total_chats']}\n"
                f"• Чатов с уведомлениями: {stats['enabled_chats']}\n"
                f"• Чатов без уведомлений: {stats['disabled_chats']}\n\n"
                "• Подписки по группам:\n"
            )
            
            for group, count in stats['groups_stats'].items():
                text += f"  - {group}: {count} чат(ов)\n"
            
            await query.edit_message_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка в changes_button_handler: {e}")
        await update.message.reply_text("❌ Ошибка при обработке уведомлений.")

async def send_tomorrow_schedule(context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    """Отправка расписания на завтра"""
    try:
        from datetime import datetime, timedelta
        
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        tomorrow_index = (datetime.now() + timedelta(days=1)).weekday()
        
        if tomorrow_index >= len(days):  # Воскресенье
            await context.bot.send_message(
                chat_id=chat_id,
                text="📅 Расписание на завтра:\n\nЗавтра воскресенье - занятий нет! 🎉"
            )
            return
        
        day = days[tomorrow_index]
        
        # Получаем группу пользователя
        group = group_manager.get_group(chat_id)
        if not group:
            logger.warning(f"Рассылка для {chat_id} пропущена - группа не выбрана")
            return
        
        # Определяем тип недели для завтра
        tomorrow_date = datetime.now() + timedelta(days=1)
        week_type = parser.get_week_type_for_date(tomorrow_date)
        
        lessons = parser.get_day_schedule(group, week_type, day)
        text = parser.format_schedule_text(group, week_type, day, lessons)
        
        last_update = parser.get_last_update()
        text = f"📅 Расписание на завтра ({day}) - {group}:\n\n{text}"
        text += f"\n\n🔄 Последнее обновление: {last_update}"
        
        await context.bot.send_message(chat_id=chat_id, text=text)
        
    except Exception as e:
        logger.error(f"Ошибка отправки рассылки для {chat_id}: {e}")

async def mailing_job_callback(context: ContextTypes.DEFAULT_TYPE):
    """Callback для job рассылки"""
    job = context.job
    chat_id = job.chat_id
    
    if mailing_manager.is_mailing_enabled(chat_id):
        await send_tomorrow_schedule(context, chat_id)

async def restart_mailing_job(context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    """Перезапуск job рассылки для чата"""
    # Удаляем существующую job
    await remove_mailing_job(context, chat_id)
    
    # Создаем новую job
    if mailing_manager.is_mailing_enabled(chat_id):
        mailing_time = mailing_manager.get_mailing_time(chat_id)
        
        # Создаем время с учетом часового пояса Томска
        job_time = time(mailing_time.hour, mailing_time.minute, tzinfo=TOMSK_TZ)
        
        context.job_queue.run_daily(
            mailing_job_callback,
            time=job_time,
            days=tuple(range(7)),  # Все дни недели
            chat_id=chat_id,
            name=f"mailing_{chat_id}"
        )
        
        logger.info(f"Создана job рассылки для {chat_id} на {mailing_time}")

async def remove_mailing_job(context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    """Удаление job рассылки для чата"""
    current_jobs = context.job_queue.get_jobs_by_name(f"mailing_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
    
    if current_jobs:
        logger.info(f"Удалена job рассылки для {chat_id}")

async def init_mailing_jobs(application: Application):
    """Инициализация jobs рассылки при старте бота"""
    enabled_chats = mailing_manager.get_all_enabled_chats()
    
    for chat_id in enabled_chats:
        await restart_mailing_job(application, chat_id)
    
    logger.info(f"Инициализировано {len(enabled_chats)} jobs рассылки")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога"""
    await update.message.reply_text('Отменено.')
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Подробное логирование ошибки
    error_msg = f"❌ Ошибка: {context.error}"
    logger.error(error_msg)
    
    # Логируем дополнительную информацию
    if update and update.message:
        chat_id = update.message.chat_id
        group = group_manager.get_group(chat_id)
        logger.error(f"Чат: {chat_id}, Группа: {group}, Текст: {update.message.text}")
    
    if update and update.message:
        try:
            await update.message.reply_text(
                '❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору.\n\n'
                'Если ошибка повторяется, попробуйте:\n'
                '1. Выбрать группу заново /setgroup\n'
                '2. Проверить доступность расписания /update_info'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

def main() -> None:
    """Запуск бота"""
    # Создаем папку cache если нет
    if not os.path.exists('cache'):
        os.makedirs('cache')
    
    # Проверяем доступные группы при старте
    available_groups = group_manager.get_available_groups()
    logger.info(f"Загружены группы из конфига: {available_groups}")
    
    if not available_groups:
        logger.error("❌ В конфиге не найдено ни одной группы!")
    
    # Создаем Application
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("update_info", update_info))
    application.add_handler(CommandHandler("today", today))
    application.add_handler(CommandHandler("tomorrow", tomorrow))
    application.add_handler(CommandHandler("week", week_schedule))
    application.add_handler(CommandHandler("bells", bells))
    application.add_handler(CommandHandler("bells_today", bells_today))
    application.add_handler(CommandHandler("mailing_status", mailing_status))
    application.add_handler(CommandHandler("changes", changes_management))

    # Обработчик для выбора группы
    conv_handler_group = ConversationHandler(
        entry_points=[CommandHandler('setgroup', set_group)],
        states={
            SELECT_GROUP: [CallbackQueryHandler(group_select, pattern='^group_')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler_group)

    # Обработчик для кнопок уведомлений об изменениях
    application.add_handler(CallbackQueryHandler(changes_button_handler, pattern='^changes_'))

    # Обработчик диалога выбора расписания
    conv_handler_schedule = ConversationHandler(
        entry_points=[CommandHandler('schedule', schedule)],
        states={
            SELECT_WEEK: [CallbackQueryHandler(week_select)],
            SELECT_DAY: [CallbackQueryHandler(day_select)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler_schedule)

    # Обработчик диалога управления рассылкой
    conv_handler_mailing = ConversationHandler(
        entry_points=[CommandHandler('mailing', mailing_management)],
        states={
            SET_MAILING_TIME: [
                CallbackQueryHandler(mailing_button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_mailing_time)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler_mailing)
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Инициализация jobs рассылки при старте
    application.post_init = init_mailing_jobs

    # Запуск бота
    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()