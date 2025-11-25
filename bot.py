import logging
import platform
import socket
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
from datetime import datetime, time as dt_time, timedelta
import time
from database_manager import db_manager
from flood_protection import flood_protection
import subprocess
import platform
import psutil
import sys
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

def check_reload_flag():
    """Проверяет перезагрузку кэша"""
    reload_flag = 'cache/reload_cache.flag'
    if os.path.exists(reload_flag):
        try:
            parser.clear_cache()
            os.remove(reload_flag)
            logger.info("🔄 Кэш перезагружен по флагу от крона")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка перезагрузки кэша: {e}")
    return False

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

async def check_flood_protection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка защиты от флуда"""
    chat_id = str(update.effective_chat.id)
    
    # Логируем запрос
    db_manager.log_request(
        chat_id, 
        update.message.text if update.message else 'Unknown',
        f"Telegram Bot"
    )
    
    # Проверяем флуд
    flood_check = flood_protection.check_flood(chat_id)
    
    if not flood_check['allowed']:
        if flood_check['reason'] == 'banned':
            ban_info = flood_check.get('ban_info', {})
            reason = ban_info.get('reason', 'Причина не указана')
            banned_until = ban_info.get('banned_until')
            
            if banned_until:
                until_text = banned_until.strftime("%d.%m.%Y в %H:%M")
                ban_message = (
                    f"🚫 Вы заблокированы до {until_text}.\n"
                    f"Причина: {reason}\n\n"
                    f"Обратитесь к администратору для разблокировки."
                )
            else:
                ban_message = (
                    f"🚫 Вы заблокированы навсегда.\n"
                    f"Причина: {reason}\n\n"
                    f"Обратитесь к администратору для разблокировки."
                )
            
            await update.message.reply_text(ban_message)
        elif flood_check['reason'] == 'flood_detected':
            ban_duration = flood_check.get('ban_duration', 60)
            await update.message.reply_text(
                f"🚫 Обнаружен флуд! Вы заблокированы на {ban_duration} минут.\n"
                f"Количество запросов: {flood_check['requests_count']}/{flood_check['max_requests']}"
            )
        
        return False
    
    return True

async def save_chat_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение информации о чате/пользователе"""
    try:
        chat = update.effective_chat
        user = update.effective_user
        
        chat_info = {
            'chat_id': str(chat.id),
            'chat_type': chat.type,
            'title': chat.title if hasattr(chat, 'title') else None
        }
        
        # Для личных чатов сохраняем информацию о пользователе
        if chat.type == 'private' and user:
            chat_info.update({
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            })
        
        # Сохраняем в базу
        db_manager.save_bot_chat(**chat_info)
        
    except Exception as e:
        logger.error(f"Ошибка сохранения информации о чате: {e}")

# Обновите команду start для сохранения информации
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    # Проверка анти-флуда
    if not await check_flood_protection(update, context):
        return
    
    try:
        # Сохраняем информацию о чате
        await save_chat_info(update, context)
        
        chat_id = update.message.chat_id
        user_id = str(update.effective_user.id)
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
            "/changes - управление уведомлениями об изменениях\n"
            "/contact - контактная информация"
        )
        
        # Если пользователь администратор, показываем дополнительную информацию
        if db_manager.is_admin(user_id):
            text += "\n\n🛠️ Вы администратор!\n"
            text += "Используйте /service_help для просмотра сервисных команд"
        
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        await update.message.reply_text("❌ Ошибка при запуске бота. Попробуйте позже.")

# Добавьте обработчик для новых участников (когда бота добавляют в группу/канал)
async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик добавления бота в группу/канал"""
    try:
        # Сохраняем информацию о чате
        await save_chat_info(update, context)
        
        chat = update.effective_chat
        logger.info(f"Бот добавлен в {chat.type}: {chat.title or chat.id}")
        
        # Отправляем приветственное сообщение для групп
        if chat.type in ['group', 'supergroup']:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "👋 Привет! Я бот с расписанием занятий.\n\n"
                    "Чтобы начать работу, выполните следующие шаги:\n"
                    "1. Выберите группу с помощью команды /setgroup\n"
                    "2. Настройте рассылку с помощью /mailing\n"
                    "3. Включите уведомления об изменениях с помощью /changes\n\n"
                    "Для просмотра всех команд используйте /start"
                )
            )
            
    except Exception as e:
        logger.error(f"Ошибка в обработчике chat_member: {e}")

# Добавьте команду startinfo
async def startinfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Информация о всех чатах, которые использовали бота"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        # Получаем параметры фильтрации
        chat_type = None
        if context.args:
            filter_arg = context.args[0].lower()
            if filter_arg in ['private', 'group', 'supergroup', 'channel']:
                chat_type = filter_arg
        
        # Получаем статистику
        stats = db_manager.get_bot_chats_count()
        all_chats = db_manager.get_all_bot_chats(chat_type)
        
        # Формируем заголовок
        if chat_type:
            title = f"📊 ЧАТЫ (тип: {chat_type})"
        else:
            title = "📊 ВСЕ ЧАТЫ"
        
        text_parts = [f"{title}\n"]
        
        # Добавляем статистику
        if stats:
            text_parts.append("\n📈 *СТАТИСТИКА:*")
            text_parts.append(f"• Всего: {stats.get('total', 0)}")
            for ctype, count in stats.items():
                if ctype != 'total':
                    text_parts.append(f"• {ctype}: {count}")
        
        text_parts.append("\n👥 *СПИСОК ЧАТОВ:*")
        
        if not all_chats:
            text_parts.append("\nℹ️ Чатов не найдено")
        else:
            for i, chat in enumerate(all_chats, 1):
                chat_info = []
                
                # ID и тип
                chat_info.append(f"{i}. 🆔 `{chat['chat_id']}`")
                chat_info.append(f"   📝 Тип: {chat['chat_type']}")
                
                # Информация в зависимости от типа
                if chat['chat_type'] == 'private':
                    if chat['first_name']:
                        chat_info.append(f"   👤 Имя: {chat['first_name']}")
                    if chat['last_name']:
                        chat_info.append(f"   📛 Фамилия: {chat['last_name']}")
                    if chat['username']:
                        chat_info.append(f"   🔖 @{chat['username']}")
                else:
                    if chat['title']:
                        chat_info.append(f"   🏷️ Название: {chat['title']}")
                    if chat['username']:
                        chat_info.append(f"   🔖 @{chat['username']}")
                
                # Дата первого контакта
                created = chat['created_at']
                if isinstance(created, str):
                    created = datetime.fromisoformat(created.replace('Z', '+00:00'))
                created_str = created.strftime("%d.%m.%Y %H:%M")
                chat_info.append(f"   📅 Добавлен: {created_str}")
                
                text_parts.append("\n".join(chat_info))
                
                # Ограничиваем вывод для предотвращения слишком длинных сообщений
                if i >= 50:  # Максимум 50 чатов в одном сообщении
                    text_parts.append(f"\n... и ещё {len(all_chats) - i} чатов")
                    break
        
        full_text = "\n".join(text_parts)
        
        # Разбиваем на части если слишком длинное
        if len(full_text) > 4096:
            parts = []
            current_part = ""
            
            for line in full_text.split('\n'):
                if len(current_part) + len(line) + 1 < 4096:
                    current_part += line + '\n'
                else:
                    parts.append(current_part)
                    current_part = line + '\n'
            
            if current_part:
                parts.append(current_part)
            
            for i, part in enumerate(parts, 1):
                if i == 1:
                    await update.message.reply_text(part, parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"*Продолжение ({i}/{len(parts)})*:\n\n{part}", parse_mode='Markdown')
                await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(full_text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Ошибка в команде startinfo: {e}")
        await update.message.reply_text("❌ Ошибка при получении информации о чатах.")

# Добавьте команду для очистки неактивных чатов
async def cleanup_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистка неактивных чатов (только для админов)"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        # Получаем все забаненные пользователи
        banned_users = db_manager.get_banned_users()
        cleaned_count = 0
        
        for banned_user in banned_users:
            chat_id = banned_user['chat_id']
            
            # Удаляем из tracking
            if db_manager.delete_bot_chat(chat_id):
                cleaned_count += 1
        
        await update.message.reply_text(
            f"✅ Очистка завершена\n"
            f"Удалено записей: {cleaned_count}\n"
            f"Заблокированных пользователей: {len(banned_users)}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде cleanup_chats: {e}")
        await update.message.reply_text("❌ Ошибка при очистке чатов.")

# СЕРВИСНЫЕ КОМАНДЫ ДЛЯ АДМИНИСТРАТОРОВ

async def service_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Справка по сервисным командам для администраторов"""
    try:
        await save_chat_info(update, context)
        # Проверяем права администратора
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        text = (
            "🛠️ *СЕРВИСНЫЕ КОМАНДЫ ДЛЯ АДМИНИСТРАТОРОВ*\n\n"
            
            "👑 *Управление правами:*\n"
            "`/setadmin <user_id> [username]` - выдать права администратора\n"
            "`/takeadmin [id/username]` - удалить администратора [спец.доступ]\n"
            "`/service_help` - показать эту справку\n\n"
            
            "🛡️ *Анти-флуд система:*\n"
            "`/floodon` - включить анти-флуд\n"
            "`/floodoff` - выключить анти-флуд\n"
            "`/floodsettings [max_requests] [ban_duration]` - настройки анти-флуда\n\n"
            
            "👮 *Модерация:*\n"
            "`/ban <user_id> [дни] [причина]` - заблокировать пользователя\n"
            "`/unban <user_id>` - разблокировать пользователя\n"
            "`/kick <chat_id>` - выйти из группы/канала\n"
            "`/delmsg` - удалить сообщение бота (ответьте на сообщение)\n"
            "`/settingschats <id> <тип> [значение]` - управление настройками чатов\n"
            "`/delid <user_id>` - удалить все данные пользователя\n\n"
            
            "📊 *Мониторинг и статистика:*\n"
            "`/sysinfo` - подробная системная информация\n"
            "`/stats [время_в_минутах]` - статистика запросов\n"
            "`/settings_info` - информация о настройках\n"
            "`/find <user_id>` - Профиль по id\n"
            "`/startinfo [тип]` - список всех чатов бота\n"
            "`/cleanup_chats` - очистка неактивных чатов\n\n"
            
            "🔄 *Управление ботом:*\n"
            "`/reboot` - перезагрузить бота\n"
            "`/crondownload` - выполнить обновление расписания\n\n"
            
            "💡 *Примеры использования:*\n"
            "• `/setadmin 123456789 @username`\n"
            "• `/floodsettings 30 60`\n"
            "• `/ban 123456789 1 Спам`\n"
            "• `/stats 120` (статистика за 2 часа)\n\n"
            
            "⚙️ *Текущие настройки анти-флуда:*\n"
        )
        
        # Добавляем текущие настройки анти-флуда
        flood_settings = db_manager.get_flood_settings()
        text += (
            f"• Статус: {'✅ ВКЛЮЧЕН' if flood_settings['enabled'] else '❌ ВЫКЛЮЧЕН'}\n"
            f"• Макс. запросов: {flood_settings['max_requests_per_minute']}/мин\n"
            f"• Бан: {flood_settings['ban_duration_minutes']} мин\n\n"
        )
        
        # Добавляем информацию о забаненных пользователях
        banned_users = db_manager.get_banned_users()
        if banned_users:
            text += f"🚫 *Заблокировано пользователей:* {len(banned_users)}\n\n"
        
        # Добавляем информацию об администраторах
        admins = db_manager.get_all_admins()
        if admins:
            text += f"👑 *Администраторов в системе:* {len(admins)}\n\n"
        
        text += "_Используйте команды только при необходимости_"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде service_help: {e}")
        await update.message.reply_text("❌ Ошибка при получении справки.")

async def setadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выдача админки"""
    try:
        # Проверяем права администратора
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Использование: /setadmin <user_id> [username]")
            return
        
        user_id = context.args[0]
        username = context.args[1] if len(context.args) > 1 else None
        
        if db_manager.add_admin(user_id, username):
            await update.message.reply_text(f"✅ Пользователь {user_id} добавлен в администраторы.")
        else:
            await update.message.reply_text("❌ Ошибка при добавлении администратора.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде setadmin: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")

async def takeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Забрать права администратора"""
    try:
        # Проверяем права администратора (только для суперадминов)
        user_id = str(update.effective_user.id)
        
        # Список суперадминов (нельзя забрать права у себя)
        super_admins = ['']  # Замените на реальные ID суперадминов
        
        if user_id not in super_admins:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Использование: /takeadmin <user_id/username>\n\n"
                "📋 Примеры:\n"
                "• /takeadmin 123456789\n"
                "• /takeadmin @username\n\n"
                "⚠️ Внимание: Эту команду могут использовать только суперадминистраторы."
            )
            return
        
        target_user = context.args[0]
        
        # Проверяем, существует ли такой администратор
        admins = db_manager.get_all_admins()
        target_admin = None
        
        for admin in admins:
            if admin['user_id'] == target_user or admin['username'] == target_user:
                target_admin = admin
                break
        
        if not target_admin:
            await update.message.reply_text(
                f"❌ Пользователь {target_user} не найден в списке администраторов."
            )
            return
        
        # Не позволяем суперадмину забрать права у себя
        if target_admin['user_id'] == user_id:
            await update.message.reply_text("❌ Вы не можете забрать права у себя.")
            return
        
        # Удаляем администратора
        if db_manager.remove_admin(target_admin['user_id']):
            await update.message.reply_text(
                f"✅ Администратор успешно удален:\n"
                f"• ID: {target_admin['user_id']}\n"
                f"• Username: {target_admin['username'] or 'Не указан'}"
            )
        else:
            await update.message.reply_text("❌ Ошибка при удалении администратора.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде takeadmin: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")

async def floodon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Включение анти-флуда"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if db_manager.update_flood_settings(enabled=True):
            await update.message.reply_text("✅ Анти-флуд система включена.")
        else:
            await update.message.reply_text("❌ Ошибка при включении анти-флуда.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде floodon: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")

async def floodoff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выключение анти-флуда"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if db_manager.update_flood_settings(enabled=False):
            await update.message.reply_text("✅ Анти-флуд система выключена.")
        else:
            await update.message.reply_text("❌ Ошибка при выключении анти-флуда.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде floodoff: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")

async def floodsettings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Управление настройками анти-флуда"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if len(context.args) < 2:
            # Показать текущие настройки
            settings = db_manager.get_flood_settings()
            text = (
                "⚙️ Текущие настройки анти-флуда:\n\n"
                f"• Включен: {'✅' if settings['enabled'] else '❌'}\n"
                f"• Макс. запросов в минуту: {settings['max_requests_per_minute']}\n"
                f"• Длительность бана (мин): {settings['ban_duration_minutes']}\n\n"
                "Для изменения: /floodsettings <max_requests> <ban_duration>"
            )
            await update.message.reply_text(text)
            return
        
        try:
            max_requests = int(context.args[0])
            ban_duration = int(context.args[1])
            
            if db_manager.update_flood_settings(max_requests=max_requests, ban_duration=ban_duration):
                await update.message.reply_text(
                    f"✅ Настройки анти-флуда обновлены:\n"
                    f"• Макс. запросов: {max_requests}/мин\n"
                    f"• Бан на: {ban_duration} мин"
                )
            else:
                await update.message.reply_text("❌ Ошибка при обновлении настроек.")
                
        except ValueError:
            await update.message.reply_text("❌ Неверные параметры. Используйте числа.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде floodsettings: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")

async def settings_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Управление настройками чатов"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Использование: /settingschats <id_чата> <тип> [значение] [время]\n\n"
                "📋 Типы настроек:\n"
                "• `mailing` [вкл/выкл] [ЧЧ:ММ] - рассылка по времени (время обязательно при включении)\n"
                "• `notifications` [вкл/выкл] - уведомления об изменениях\n"
                "• `group` <название_группы> - смена группы\n\n"
                "📝 Примеры:\n"
                "• `/settingschats 123456789 mailing вкл 18:00` - включить рассылку на 18:00\n"
                "• `/settingschats 123456789 mailing выкл` - выключить рассылку\n"
                "• `/settingschats 123456789 notifications вкл` - включить уведомления\n"
                "• `/settingschats 123456789 group Д013П` - смена группы\n"
                "• `/settingschats 123456789 info` - информация о настройках"
            )
            return
        
        chat_id = context.args[0]
        setting_type = context.args[1].lower()
        value = context.args[2].lower() if len(context.args) > 2 else None
        time_value = context.args[3] if len(context.args) > 3 else None
        
        # Получаем информацию о чате
        try:
            chat = await context.bot.get_chat(chat_id)
            chat_info = f"💬 Чат: {chat.title if hasattr(chat, 'title') and chat.title else 'Личный чат'}\n"
            chat_info += f"🆔 ID: `{chat_id}`\n"
            if hasattr(chat, 'username') and chat.username:
                chat_info += f"🔖 @{chat.username}\n"
        except Exception as e:
            chat_info = f"⚠️ Не удалось получить информацию о чате {chat_id}: {e}\n"
        
        result_text = chat_info + "\n"
        
        if setting_type == 'info':
            # Показать информацию о текущих настройках
            group = group_manager.get_group(chat_id)
            mailing_info = mailing_manager.get_mailing_info(chat_id)
            notifications_status = change_notifier.is_notification_enabled(chat_id)
            
            result_text += (
                f"📊 Текущие настройки:\n\n"
                f"📚 Группа: {group if group else '❌ Не выбрана'}\n"
                f"📧 Рассылка: {'✅ ВКЛ' if mailing_info['enabled'] else '❌ ВЫКЛ'}\n"
                f"   ⏰ Время: {mailing_info['time']['hour']:02d}:{mailing_info['time']['minute']:02d}\n"
                f"🔔 Уведомления: {'✅ ВКЛ' if notifications_status else '❌ ВЫКЛ'}\n"
            )
            
        elif setting_type == 'mailing':
            # Управление рассылкой
            if not value or value.lower() not in ['вкл', 'выкл']:
                result_text += "❌ Укажите значение: 'вкл' или 'выкл'"
            else:
                enabled = value.lower() == 'вкл'
                
                if enabled:
                    # При включении рассылки время обязательно
                    if not time_value:
                        result_text += "❌ При включении рассылки обязательно укажите время в формате ЧЧ:ММ\n"
                        result_text += "Пример: `/settingschats 123456789 mailing вкл 18:00`"
                    else:
                        try:
                            # Парсим время
                            hour, minute = map(int, time_value.split(':'))
                            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                                result_text += "❌ Неверное время! Используйте формат ЧЧ:ММ (например, 18:00)"
                            else:
                                mailing_manager.enable_mailing(chat_id, hour, minute)
                                result_text += f"✅ Рассылка ВКЛЮЧЕНА для чата {chat_id} на {hour:02d}:{minute:02d}"
                                # Перезапускаем задачу рассылки
                                await restart_mailing_job(context, chat_id)
                        except ValueError:
                            result_text += "❌ Неверный формат времени! Используйте ЧЧ:ММ (например, 18:00)"
                        except Exception as e:
                            result_text += f"❌ Ошибка при установке времени: {e}"
                else:
                    # При выключении время не нужно
                    mailing_manager.disable_mailing(chat_id)
                    result_text += f"✅ Рассылка ВЫКЛЮЧЕНА для чата {chat_id}"
                    # Удаляем задачу рассылки
                    await remove_mailing_job(context, chat_id)
        
        elif setting_type == 'notifications':
            # Управление уведомлениями об изменениях
            if not value or value.lower() not in ['вкл', 'выкл']:
                result_text += "❌ Укажите значение: 'вкл' или 'выкл'"
            else:
                enabled = value.lower() == 'вкл'
                if enabled:
                    change_notifier.enable_notifications(chat_id)
                    result_text += f"✅ Уведомления об изменениях ВКЛЮЧЕНЫ для чата {chat_id}"
                else:
                    change_notifier.disable_notifications(chat_id)
                    result_text += f"✅ Уведомления об изменениях ВЫКЛЮЧЕНЫ для чата {chat_id}"
        
        elif setting_type == 'group':
            # Смена группы
            if not value:
                result_text += "❌ Укажите название группы"
            else:
                available_groups = group_manager.get_available_groups()
                if value not in available_groups:
                    result_text += f"❌ Группа '{value}' не найдена.\n\n"
                    result_text += f"📋 Доступные группы: {', '.join(available_groups)}"
                else:
                    try:
                        group_manager.set_group(chat_id, value)
                        result_text += f"✅ Группа установлена: {value}"
                    except Exception as e:
                        result_text += f"❌ Ошибка установки группы: {e}"
        
        else:
            result_text += f"❌ Неизвестный тип настройки: {setting_type}\n\n"
            result_text += (
                "📋 Доступные типы:\n"
                "• `mailing` - рассылка по времени\n"
                "• `notifications` - уведомления об изменениях\n"
                "• `group` - смена группы\n"
                "• `info` - информация о настройках"
            )
        
        await update.message.reply_text(result_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде settingschats: {e}")
        await update.message.reply_text(f"❌ Ошибка при изменении настроек: {e}")

async def sysinfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подробная техническая информация о боте"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        # Собираем информацию частями
        info_parts = []
        
        # 1. ИНФОРМАЦИЯ О СИСТЕМЕ
        info_parts.append("💻 *СИСТЕМНАЯ ИНФОРМАЦИЯ*")
        info_parts.append("")
        
        python_version = platform.python_version()
        system = platform.system()
        node = platform.node()
        processor = platform.processor()
        architecture = platform.architecture()[0]
        machine = platform.machine()
        platform_info = platform.platform()
        
        info_parts.append("🖥️ *Операционная система:*")
        info_parts.append(f"• Система: {system}")
        info_parts.append(f"• Платформа: {platform_info}")
        info_parts.append(f"• Архитектура: {architecture}")
        info_parts.append(f"• Машина: {machine}")
        info_parts.append(f"• Имя узла: {node}")
        info_parts.append(f"• Процессор: {processor}")
        info_parts.append(f"• Python: {python_version}")
        info_parts.append("")
        
        # 2. UPTIME И ВРЕМЯ РАБОТЫ
        info_parts.append("⏰ *ВРЕМЯ РАБОТЫ*")
        info_parts.append("")
        
        try:
            # Uptime системы
            boot_time = psutil.boot_time()
            current_time = time.time()
            uptime_seconds = current_time - boot_time
            uptime_days = uptime_seconds // (24 * 3600)
            uptime_hours = (uptime_seconds % (24 * 3600)) // 3600
            uptime_minutes = (uptime_seconds % 3600) // 60
            
            # Время запуска бота (приблизительно)
            process = psutil.Process()
            bot_start_time = process.create_time()
            bot_uptime_seconds = current_time - bot_start_time
            bot_uptime_days = bot_uptime_seconds // (24 * 3600)
            bot_uptime_hours = (bot_uptime_seconds % (24 * 3600)) // 3600
            bot_uptime_minutes = (bot_uptime_seconds % 3600) // 60
            
            info_parts.append("🖥️ *Система:*")
            info_parts.append(f"• Запущена: {datetime.fromtimestamp(boot_time).strftime('%d.%m.%Y %H:%M:%S')}")
            info_parts.append(f"• Работает: {int(uptime_days)}д {int(uptime_hours)}ч {int(uptime_minutes)}м")
            info_parts.append("")
            
            info_parts.append("🤖 *Бот:*")
            info_parts.append(f"• Запущен: {datetime.fromtimestamp(bot_start_time).strftime('%d.%m.%Y %H:%M:%S')}")
            info_parts.append(f"• Работает: {int(bot_uptime_days)}д {int(bot_uptime_hours)}ч {int(bot_uptime_minutes)}м")
            info_parts.append("")
            
        except Exception as e:
            info_parts.append(f"⚠️ Ошибка получения uptime: {e}")
            info_parts.append("")
        
        # 3. ПАМЯТЬ И ДИСКИ
        info_parts.append("💾 *РЕСУРСЫ СИСТЕМЫ*")
        info_parts.append("")
        
        try:
            # Оперативная память
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            info_parts.append("🧠 *Оперативная память:*")
            info_parts.append(f"• Всего: {memory.total // (1024**3)} GB")
            info_parts.append(f"• Использовано: {memory.used // (1024**3)} GB ({memory.percent}%)")
            info_parts.append(f"• Доступно: {memory.available // (1024**3)} GB")
            info_parts.append(f"• Swap: {swap.used // (1024**3)}/{swap.total // (1024**3)} GB ({swap.percent}%)")
            info_parts.append("")
            
            # Диски
            info_parts.append("💿 *Дисковое пространство:*")
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    info_parts.append(f"• {partition.device} ({partition.fstype}):")
                    info_parts.append(f"  {usage.used // (1024**3)}/{usage.total // (1024**3)} GB ({usage.percent}%)")
                    info_parts.append(f"  Монтирован в: {partition.mountpoint}")
                except Exception:
                    continue
            info_parts.append("")
            
        except Exception as e:
            info_parts.append(f"⚠️ Ошибка получения ресурсов: {e}")
            info_parts.append("")
        
        # 4. ПРОЦЕСС БОТА
        info_parts.append("⚡ *ПРОЦЕСС БОТА*")
        info_parts.append("")
        
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent(interval=0.1)
            threads = process.num_threads()
            
            # Сетевые соединения
            try:
                connections = len(process.net_connections())
            except (AttributeError, psutil.AccessDenied):
                try:
                    connections = len(process.connections())
                except:
                    connections = "недоступно"
            
            # Открытые файлы
            try:
                open_files = len(process.open_files())
            except (psutil.AccessDenied, Exception):
                open_files = "недоступно"
            
            info_parts.append(f"• Память: {memory_info.rss // 1024 // 1024} MB")
            info_parts.append(f"• CPU: {cpu_percent}%")
            info_parts.append(f"• Потоки: {threads}")
            info_parts.append(f"• Открытые файлы: {open_files}")
            info_parts.append(f"• Сетевые соединения: {connections}")
            info_parts.append(f"• PID: {process.pid}")
            info_parts.append(f"• Статус: {process.status()}")
            info_parts.append("")
            
        except Exception as e:
            info_parts.append(f"⚠️ Ошибка получения информации о процессе: {e}")
            info_parts.append("")
        
        # 5. БАЗА ДАННЫХ MYSQL
        info_parts.append("🗄️ *БАЗА ДАННЫХ MYSQL*")
        info_parts.append("")
        
        try:
            conn = db_manager.get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                
                # Версия MySQL
                cursor.execute("SELECT VERSION() as version")
                mysql_version = cursor.fetchone()
                if mysql_version and 'version' in mysql_version:
                    info_parts.append(f"• Версия: {mysql_version['version']}")
                else:
                    info_parts.append("• Версия: неизвестна")
                
                # Статус базы данных
                cursor.execute("SHOW STATUS LIKE 'Uptime'")
                mysql_uptime_result = cursor.fetchone()
                if mysql_uptime_result and 'Value' in mysql_uptime_result:
                    mysql_uptime = int(mysql_uptime_result['Value'])
                    uptime_days = mysql_uptime // 86400
                    uptime_hours = (mysql_uptime % 86400) // 3600
                    uptime_minutes = (mysql_uptime % 3600) // 60
                    info_parts.append(f"• Uptime: {uptime_days}д {uptime_hours}ч {uptime_minutes}м")
                else:
                    info_parts.append("• Uptime: неизвестен")
                
                # Подключения
                cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                threads_result = cursor.fetchone()
                threads_connected = threads_result['Value'] if threads_result and 'Value' in threads_result else "неизвестно"
                
                cursor.execute("SHOW STATUS LIKE 'Max_used_connections'")
                max_connections_result = cursor.fetchone()
                max_used_connections = max_connections_result['Value'] if max_connections_result and 'Value' in max_connections_result else "неизвестно"
                
                info_parts.append(f"• Подключения: {threads_connected} (макс: {max_used_connections})")
                
                # Запросы
                cursor.execute("SHOW STATUS LIKE 'Questions'")
                questions_result = cursor.fetchone()
                questions = questions_result['Value'] if questions_result and 'Value' in questions_result else "неизвестно"
                
                cursor.execute("SHOW STATUS LIKE 'Slow_queries'")
                slow_queries_result = cursor.fetchone()
                slow_queries = slow_queries_result['Value'] if slow_queries_result and 'Value' in slow_queries_result else "неизвестно"
                
                info_parts.append(f"• Запросов: {questions}")
                info_parts.append(f"• Медленных запросов: {slow_queries}")
                
                # Размер базы данных
                cursor.execute("""
                    SELECT table_schema as database_name, 
                    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as size_mb
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE()
                    GROUP BY table_schema
                """)
                db_size = cursor.fetchone()
                if db_size and 'size_mb' in db_size:
                    info_parts.append(f"• Размер БД: {db_size['size_mb']} MB")
                else:
                    info_parts.append("• Размер БД: неизвестен")
                
                cursor.close()
                conn.close()
            else:
                info_parts.append("❌ Не удалось подключиться к БД")
            info_parts.append("")
            
        except Exception as e:
            info_parts.append(f"⚠️ Ошибка получения информации о БД: {e}")
            info_parts.append("")
        
        # 6. СТАТИСТИКА БОТА
        info_parts.append("📊 *СТАТИСТИКА БОТА*")
        info_parts.append("")
        
        try:
            db_stats = db_manager.get_settings_info()
            flood_settings = db_manager.get_flood_settings()
            request_stats_1h = db_manager.get_request_stats(60)
            request_stats_24h = db_manager.get_request_stats(1440)
            
            info_parts.append("👥 *Пользователи:*")
            info_parts.append(f"• Всего: {db_stats.get('user_groups_count', 0)}")
            info_parts.append(f"• С рассылкой: {db_stats.get('enabled_mailing_count', 0)}")
            info_parts.append(f"• С уведомлениями: {db_stats.get('enabled_notifications_count', 0)}")
            info_parts.append(f"• Администраторов: {db_stats.get('admins_count', 0)}")
            info_parts.append(f"• Заблокировано: {db_stats.get('banned_users_count', 0)}")
            info_parts.append("")
            
            info_parts.append("📈 *Запросы:*")
            info_parts.append(f"• За 1 час: {request_stats_1h.get('recent_requests', 0)}")
            info_parts.append(f"• За 24 часа: {request_stats_24h.get('recent_requests', 0)}")
            info_parts.append(f"• Всего: {request_stats_24h.get('total_requests', 0)}")
            info_parts.append("")
            
            info_parts.append("🛡️ *Анти-флуд:*")
            info_parts.append(f"• Статус: {'✅ ВКЛЮЧЕН' if flood_settings['enabled'] else '❌ ВЫКЛЮЧЕН'}")
            info_parts.append(f"• Лимит: {flood_settings['max_requests_per_minute']}/мин")
            info_parts.append(f"• Бан: {flood_settings['ban_duration_minutes']} мин")
            info_parts.append("")
            
        except Exception as e:
            info_parts.append(f"⚠️ Ошибка получения статистики: {e}")
            info_parts.append("")
        
        # 7. СЕТЕВАЯ ИНФОРМАЦИЯ
        info_parts.append("🌐 *СЕТЕВАЯ ИНФОРМАЦИЯ*")
        info_parts.append("")
        
        try:
            # IP адреса
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            info_parts.append(f"• Hostname: {hostname}")
            info_parts.append(f"• Локальный IP: {local_ip}")
            
            # Сетевые интерфейсы
            interfaces = psutil.net_io_counters(pernic=True)
            interface_count = 0
            for interface, stats in interfaces.items():
                if interface_count < 3:  # Показываем первые 3 интерфейса
                    info_parts.append(f"• {interface}:")
                    info_parts.append(f"  Отправлено: {stats.bytes_sent // 1024 // 1024} MB")
                    info_parts.append(f"  Получено: {stats.bytes_recv // 1024 // 1024} MB")
                    interface_count += 1
                else:
                    break
            
            info_parts.append("")
            
        except Exception as e:
            info_parts.append(f"⚠️ Ошибка получения сетевой информации: {e}")
            info_parts.append("")
        
        # 8. ДАТА И ВРЕМЯ
        info_parts.append("📅 *ВРЕМЯ И ДАТА*")
        info_parts.append("")
        
        now = datetime.now()
        info_parts.append(f"• Текущее время: {now.strftime('%d.%m.%Y %H:%M:%S')}")
        
        try:
            tz_name = time.tzname[0] if time.tzname else "неизвестно"
            info_parts.append(f"• Часовой пояс: {tz_name}")
        except Exception:
            info_parts.append("• Часовой пояс: неизвестно")
        
        try:
            utc_offset = time.timezone // 3600
            info_parts.append(f"• UTC смещение: {utc_offset} часов")
        except Exception:
            info_parts.append("• UTC смещение: неизвестно")
        
        info_parts.append("")
        
        # Объединяем всю информацию
        full_info = "\n".join(info_parts)
        
        # Разбиваем на части если слишком длинное
        if len(full_info) > 4096:
            parts = []
            current_part = ""
            
            for line in full_info.split('\n'):
                if len(current_part) + len(line) + 1 < 4096:
                    current_part += line + '\n'
                else:
                    parts.append(current_part)
                    current_part = line + '\n'
            
            if current_part:
                parts.append(current_part)
            
            for i, part in enumerate(parts, 1):
                if i == 1:
                    await update.message.reply_text(f"*СИСТЕМНАЯ ИНФОРМАЦИЯ (часть {i}/{len(parts)})*:\n\n{part}", parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"*Продолжение (часть {i}/{len(parts)})*:\n\n{part}", parse_mode='Markdown')
                await asyncio.sleep(0.5)  # Небольшая задержка между сообщениями
        else:
            await update.message.reply_text(full_info, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде sysinfo: {e}")
        await update.message.reply_text("❌ Ошибка при получении системной информации.")
        
async def delid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаление всех данных пользователя по ID"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Использование: /delid <user_id>")
            return
        
        user_id = context.args[0]
        
        # Удаляем пользователя из всех таблиц
        deleted_tables = []
        
        # Удаляем из user_groups
        conn = db_manager.get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                
                # Удаляем из user_groups
                cursor.execute("DELETE FROM user_groups WHERE chat_id = %s", (user_id,))
                if cursor.rowcount > 0:
                    deleted_tables.append("user_groups")
                
                # Удаляем из mailing_settings
                cursor.execute("DELETE FROM mailing_settings WHERE chat_id = %s", (user_id,))
                if cursor.rowcount > 0:
                    deleted_tables.append("mailing_settings")
                
                # Удаляем из change_notifications
                cursor.execute("DELETE FROM change_notifications WHERE chat_id = %s", (user_id,))
                if cursor.rowcount > 0:
                    deleted_tables.append("change_notifications")
                
                # Удаляем из banned_users (если забанен)
                cursor.execute("DELETE FROM banned_users WHERE chat_id = %s", (user_id,))
                if cursor.rowcount > 0:
                    deleted_tables.append("banned_users")
                
                conn.commit()
                
                if deleted_tables:
                    await update.message.reply_text(
                        f"✅ Пользователь {user_id} удален из таблиц:\n" +
                        "\n".join([f"• {table}" for table in deleted_tables])
                    )
                else:
                    await update.message.reply_text(f"ℹ️ Пользователь {user_id} не найден в базе данных.")
                    
            except Exception as e:
                conn.rollback()
                logger.error(f"Ошибка при удалении пользователя {user_id}: {e}")
                await update.message.reply_text(f"❌ Ошибка при удалении пользователя: {e}")
            finally:
                cursor.close()
                conn.close()
        else:
            await update.message.reply_text("❌ Ошибка подключения к базе данных.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде delid: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")

# Обновите команду ban_user для поддержки времени бана
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Бан пользователя с указанием времени в днях"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Использование: /ban <user_id> [дни] [причина]\n\n"
                "📋 Параметры:\n"
                "• user_id - ID пользователя или username\n"
                "• дни - количество дней бана (0 = навсегда, по умолчанию 0)\n"
                "• причина - текст причины бана\n\n"
                "📝 Примеры:\n"
                "• /ban 123456789 7 Спам - бан на 7 дней\n"
                "• /ban 123456789 0 Нарушение правил - бан навсегда\n"
                "• /ban 123456789 Спам - бан навсегда\n"
                "• /ban @username 30 Флуд - бан на 30 дней по username"
            )
            return
        
        user_id = context.args[0]
        
        # Парсим аргументы
        days = 0  # 0 = навсегда по умолчанию
        reason_parts = []
        
        # Пытаемся получить количество дней (второй аргумент)
        if len(context.args) > 1:
            try:
                # Проверяем, является ли второй аргумент числом (дни бана)
                days = int(context.args[1])
                # Если это число, то причина - все остальные аргументы
                reason_parts = context.args[2:] if len(context.args) > 2 else []
            except ValueError:
                # Если не число, то все аргументы кроме первого - причина
                reason_parts = context.args[1:]
        
        reason = ' '.join(reason_parts) if reason_parts else "Причина не указана"
        
        # Валидация дней
        if days < 0:
            await update.message.reply_text("❌ Количество дней не может быть отрицательным.")
            return
        
        # Преобразуем дни в минуты для базы данных
        ban_duration_minutes = days * 24 * 60  # дни × 24 часа × 60 минут
        
        # Получаем информацию о пользователе
        user_info = ""
        try:
            user = await context.bot.get_chat(user_id)
            user_info = f"\n👤 Пользователь: {getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}"
            if hasattr(user, 'username'):
                user_info += f" (@{user.username})"
        except Exception as e:
            user_info = f"\n⚠️ Не удалось получить информацию о пользователе: {e}"
        
        # Выполняем бан
        if db_manager.ban_user(user_id, reason, ban_duration_minutes):
            if days == 0:
                ban_text = "навсегда"
            else:
                ban_text = f"на {days} дней"
            
            await update.message.reply_text(
                f"✅ Пользователь {user_id} забанен {ban_text}.\n"
                f"Причина: {reason}"
                f"{user_info}"
            )
        else:
            await update.message.reply_text("❌ Ошибка при бане пользователя.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде ban: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Разбан пользователя"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Использование: /unban <user_id>")
            return
        
        user_id = context.args[0]
        
        if db_manager.unban_user(user_id):
            await update.message.reply_text(f"✅ Пользователь {user_id} разбанен.")
        else:
            await update.message.reply_text(f"❌ Пользователь {user_id} не найден в списке забаненных.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде unban: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")

async def reboot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перезагрузка бота через restart_service.py"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        await update.message.reply_text("🔄 Запуск перезагрузки...")
        
        # Проверяем существование файла
        if not os.path.exists("restart_service.py"):
            await update.message.reply_text("❌ Файл restart_service.py не найден!")
            return
        
        # Запускаем с минимальным выводом
        try:
            result = subprocess.run(
                [sys.executable, "restart_service.py"], 
                timeout=30,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'  # Игнорируем все ошибки кодировки
            )
            
            if result.returncode == 0:
                await update.message.reply_text("✅ Служба перезапущена успешно!")
            else:
                # Просто показываем код ошибки без вывода
                await update.message.reply_text(f"❌ Ошибка перезагрузки (код: {result.returncode})")
                    
        except subprocess.TimeoutExpired:
            await update.message.reply_text("✅ Перезагрузка выполняется...")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            
    except Exception as e:
        logger.error(f"Ошибка в команде reboot: {e}")
        await update.message.reply_text("❌ Ошибка при перезагрузке.")

async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаление сообщения бота по ответу на него"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return

        # Проверяем, что команда отправлена в ответ на сообщение
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "❌ Используйте эту команду в ответ на сообщение бота, которое нужно удалить.\n\n"
                "Просто ответьте на сообщение бота командой /delmsg"
            )
            return

        # Проверяем, что сообщение отправлено ботом
        if update.message.reply_to_message.from_user.id != context.bot.id:
            await update.message.reply_text("❌ Можно удалять только сообщения, отправленные ботом.")
            return

        # Удаляем целевое сообщение
        try:
            await update.message.reply_to_message.delete()
            await update.message.reply_text("✅ Сообщение удалено.")
        except Exception as e:
            logger.error(f"Ошибка удаления сообщения: {e}")
            await update.message.reply_text(
                "❌ Не удалось удалить сообщение. Возможно, у бота нет прав на удаление сообщений в этом чате."
            )

    except Exception as e:
        logger.error(f"Ошибка в команде delmsg: {e}")
        await update.message.reply_text("❌ Ошибка при удалении сообщения.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Информация о запросах к боту"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        time_period = 60  # Статистика за последний час
        if context.args:
            try:
                time_period = int(context.args[0])
            except ValueError:
                pass
        
        stats_data = db_manager.get_request_stats(time_period)
        
        # ИСПРАВЛЕНИЕ: Убираем Markdown разметку и используем обычный текст
        text = (
            f"📊 СТАТИСТИКА ЗАПРОСОВ (последние {time_period} мин)\n\n"
            f"• Всего запросов: {stats_data.get('recent_requests', 0)}\n"
            f"• Всего за всё время: {stats_data.get('total_requests', 0)}\n\n"
        )
        
        # Популярные команды
        popular_commands = stats_data.get('popular_commands', [])
        if popular_commands:
            text += "📈 Популярные команды:\n"
            for cmd, count in popular_commands[:5]:
                text += f"• {cmd}: {count}\n"
            text += "\n"
        
        # Активные пользователи
        active_users = stats_data.get('active_users', [])
        if active_users:
            text += "👥 Активные пользователи:\n"
            for user_id, count in active_users[:5]:
                text += f"• {user_id}: {count} запросов\n"
        
        # ИСПРАВЛЕНИЕ: Отправляем без parse_mode='Markdown'
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"Ошибка в команде stats: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики.")

async def crondownload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Исполнение файла cron_download"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        await update.message.reply_text("🔄 Запуск cron_download...")
        
        # Запускаем cron_download в отдельном процессе с указанием кодировки
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        result = subprocess.run(
            [sys.executable, "cron_download.py"], 
            capture_output=True, 
            text=True, 
            timeout=300,
            encoding='utf-8',
            errors='replace',  # Заменяем проблемные символы
            env=env
        )
        
        if result.returncode == 0:
            response = "✅ cron_download выполнен успешно!\n\n"
            # Берем последние строки вывода и очищаем от битых символов
            lines = result.stdout.strip().split('\n')[-10:]
            clean_lines = []
            for line in lines:
                # Заменяем эмодзи на текстовые аналоги для надежности
                clean_line = (line
                    .replace('🎯', '[ЦЕЛЬ]')
                    .replace('📥', '[СКАЧИВАНИЕ]')
                    .replace('📦', '[БЭКАП]')
                    .replace('✅', '[УСПЕХ]')
                    .replace('❌', '[ОШИБКА]')
                    .replace('⚠️', '[ВНИМАНИЕ]')
                    .replace('🔄', '[ОБНОВЛЕНИЕ]')
                    .replace('🗑️', '[ОЧИСТКА]')
                    .replace('🔍', '[ПРОВЕРКА]')
                    .replace('📊', '[ДАННЫЕ]')
                    .replace('💾', '[СОХРАНЕНИЕ]')
                    .replace('🎉', '[УСПЕХ]')
                    .replace('ℹ️', '[ИНФО]')
                    .replace('🏁', '[ЗАВЕРШЕНИЕ]')
                )
                clean_lines.append(clean_line)
            
            response += "Последние строки вывода:\n" + '\n'.join(clean_lines)
        else:
            response = f"❌ Ошибка выполнения cron_download (код: {result.returncode})\n\n"
            # Очищаем stderr от проблемных символов
            clean_stderr = result.stderr
            if clean_stderr:
                clean_stderr = (clean_stderr
                    .replace('🎯', '[ЦЕЛЬ]')
                    .replace('📥', '[СКАЧИВАНИЕ]')
                    .replace('❌', '[ОШИБКА]')
                )
            response += "Ошибка:\n" + clean_stderr
        
        # Разбиваем длинное сообщение на части
        if len(response) > 4096:
            parts = [response[i:i+4096] for i in range(0, len(response), 4096)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(response)
            
    except subprocess.TimeoutExpired:
        await update.message.reply_text("⏰ cron_download превысил время выполнения (5 минут)")
    except Exception as e:
        logger.error(f"Ошибка в команде crondownload: {e}")
        await update.message.reply_text(f"❌ Ошибка при выполнении cron_download: {str(e)}")

async def settings_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выдача информации о настройках"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        settings_info = db_manager.get_settings_info()
        
        text = (
            "⚙️ *ИНФОРМАЦИЯ О НАСТРОЙКАХ*\n\n"
            f"• Пользователей с группами: {settings_info.get('user_groups_count', 0)}\n"
            f"• Активных рассылок: {settings_info.get('enabled_mailing_count', 0)}\n"
            f"• Уведомлений включено: {settings_info.get('enabled_notifications_count', 0)}\n"
            f"• Администраторов: {settings_info.get('admins_count', 0)}\n"
            f"• Заблокированных: {settings_info.get('banned_users_count', 0)}\n\n"
        )
        
        # Получаем списки
        conn = db_manager.get_connection()
        if conn:
            try:
                cursor = conn.cursor(dictionary=True)
                
                # Администраторы
                cursor.execute("SELECT user_id, username FROM admins")
                admins = cursor.fetchall()
                if admins:
                    text += "👑 *Администраторы:*\n"
                    for admin in admins:
                        text += f"• {admin['user_id']} ({admin['username'] or 'без username'})\n"
                    text += "\n"
                
                # Заблокированные
                cursor.execute("SELECT chat_id, reason, banned_until FROM banned_users")
                banned = cursor.fetchall()
                if banned:
                    text += "🚫 *Заблокированные:*\n"
                    for ban in banned[:10]:  # Ограничиваем вывод
                        until = ban['banned_until'].strftime("%d.%m.%Y %H:%M") if ban['banned_until'] else "навсегда"
                        text += f"• {ban['chat_id']} ({until}) - {ban['reason'] or 'без причины'}\n"
                    if len(banned) > 10:
                        text += f"• ... и ещё {len(banned) - 10}\n"
                
            finally:
                cursor.close()
                conn.close()
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде settings_info: {e}")
        await update.message.reply_text("❌ Ошибка при получении информации о настройках.")

async def kick_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выход бота из группы/канала"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Использование: /kick <chat_id>")
            return
        
        chat_id = context.args[0]
        
        try:
            # Пытаемся выйти из чата
            await context.bot.leave_chat(chat_id)
            await update.message.reply_text(f"✅ Бот вышел из чата {chat_id}.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при выходе из чата: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка в команде kick: {e}")
        await update.message.reply_text("❌ Ошибка при выполнении команды.")
        
async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_flood_protection(update, context):
        return
        
    """Контактная информация"""
    try:
        await save_chat_info(update, context)
        # Получаем информацию о системе
        python_version = platform.python_version()
        system = platform.system()
        node = platform.node()
        
        # Получаем hostname (работает и на Windows и на Linux)
        try:
            hostname = socket.gethostname()
        except:
            hostname = "Не удалось определить"
        
        # Сегодняшняя дата
        today_date = datetime.now().strftime("%d.%m.%Y")
        
        text = (
            "📞 *Контактная информация*\n\n"
            "🔧 *Эксплуатацией бота занимается:*\n"
            "Управление серверной инфраструктурой ГЕНКА, 2025 г.\n\n"
            "📞 *Телефон:*\n"
            "+7(3822) 70-03-08\n\n"
            "📧 *Адрес эл.почты:*\n"
            "usig@srv-usig.ru\n"
            "gkuznetsov@srv-usig.ru\n\n"
            "👨‍💻 *Разработчик:*\n"
            "ВК: https://vk.com/leofannov\n"
            "ТГ: @leofannov\n\n"
            "📅 *Сегодняшняя дата:*\n"
            f"{today_date}\n\n"
            "🐍 *Информация о системе:*\n"
            f"Python: {python_version}\n"
            f"ОС: {system}\n"
            f"Имя ПК: {hostname}\n"
            f"Сетевое имя: {node}"
        )
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в команде contact: {e}")
        await update.message.reply_text("❌ Ошибка при получении контактной информации.")

async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_flood_protection(update, context):
        return
        
    """Выбор группы"""
    try:
        await save_chat_info(update, context)
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
    if not await check_flood_protection(update, context):
        return
        
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
    if not await check_flood_protection(update, context):
        return
        
    """Информация о последнем обновлении"""
    try:
        await save_chat_info(update, context)
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
    if not await check_flood_protection(update, context):
        return
        
    """Начало выбора расписания"""
    try:
        await save_chat_info(update, context)
        # ДОБАВЛЕНО: Проверка флага перезагрузки
        check_reload_flag()
        
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
    if not await check_flood_protection(update, context):
        return
        
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
    if not await check_flood_protection(update, context):
        return
        
    """Обработчик выбора дня"""
    try:
        # ДОБАВЛЕНО: Проверка флага перезагрузки
        check_reload_flag()
        
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
    if not await check_flood_protection(update, context):
        return
        
    """Расписание на сегодня"""
    try:
        await save_chat_info(update, context)
        # ДОБАВЛЕНО: Проверка флага перезагрузки
        check_reload_flag()
        
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
    if not await check_flood_protection(update, context):
        return
        
    """Расписание на завтра"""
    try:
        await save_chat_info(update, context)
        # ДОБАВЛЕНО: Проверка флага перезагрузки
        check_reload_flag()
        
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
    if not await check_flood_protection(update, context):
        return
        
    """Расписание на всю текущую неделю"""
    try:
        await save_chat_info(update, context)
        # ДОБАВЛЕНО: Проверка флага перезагрузки
        check_reload_flag()
        
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
    if not await check_flood_protection(update, context):
        return
        
    """Расписание звонков"""
    try:
        await save_chat_info(update, context)
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
    if not await check_flood_protection(update, context):
        return
        
    """Расписание звонков на сегодня"""
    try:
        await save_chat_info(update, context)
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

async def find_user_detailed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Расширенная информация о пользователе"""
    try:
        if not db_manager.is_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Использование: /find <ID_пользователя>")
            return
        
        user_id_str = context.args[0]
        
        try:
            user_id = int(user_id_str)
        except ValueError:
            await update.message.reply_text("❌ ID должен быть числом")
            return
        
        try:
            user = await context.bot.get_chat(user_id)
            user_group = group_manager.get_group(str(user.id))
            mailing_info = mailing_manager.get_mailing_info(str(user.id))
            notifications_status = change_notifier.is_notification_enabled(str(user.id))
            is_banned = db_manager.is_banned(str(user.id))
            
            # Получаем подробную информацию о бане
            ban_info = {}
            if is_banned:
                conn = db_manager.get_connection()
                if conn:
                    try:
                        cursor = conn.cursor(dictionary=True)
                        cursor.execute("""
                            SELECT reason, banned_until, created_at 
                            FROM banned_users 
                            WHERE chat_id = %s AND (banned_until IS NULL OR banned_until > %s)
                            ORDER BY created_at DESC 
                            LIMIT 1
                        """, (str(user.id), datetime.now()))
                        ban_info = cursor.fetchone() or {}
                    except Exception as e:
                        logger.error(f"Ошибка получения информации о бане: {e}")
                    finally:
                        cursor.close()
                        conn.close()
            
            # Статистика запросов пользователя
            requests_1h = db_manager.get_user_request_count(str(user.id), 60)
            requests_24h = db_manager.get_user_request_count(str(user.id), 1440)
            total_requests = db_manager.get_request_stats().get('total_requests', 0)
            
            user_info = []
            user_info.append("🔍 *ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ*")
            user_info.append("")
            
            # Основная информация
            user_info.append("👤 *Основная информация:*")
            user_info.append(f"   🆔 ID: `{user.id}`")
            user_info.append(f"   👤 Имя: {getattr(user, 'first_name', '❌ Не указано')}")
            user_info.append(f"   📛 Фамилия: {getattr(user, 'last_name', '❌ Не указана')}")
            user_info.append(f"   🔖 Username: @{getattr(user, 'username', '❌ Не указан')}")
            
            if hasattr(user, 'bio') and user.bio:
                user_info.append(f"   📝 Bio: {user.bio}")
            
            if hasattr(user, 'language_code'):
                user_info.append(f"   🌐 Язык: {user.language_code}")
            
            user_info.append("")
            
            # Информация о чате
            user_info.append("💬 *Информация о чате:*")
            user_info.append(f"   📝 Тип чата: {user.type}")
            
            if hasattr(user, 'title'):
                user_info.append(f"   🏷️ Название: {user.title}")
            
            user_info.append("")
            
            # Настройки в боте
            user_info.append("⚙️ *Настройки в боте:*")
            user_info.append(f"   📚 Группа: {user_group if user_group else '❌ Не выбрана'}")
            user_info.append(f"   📧 Рассылка: {'✅ Включена' if mailing_info['enabled'] else '❌ Выключена'}")
            if mailing_info['enabled']:
                user_info.append(f"   ⏰ Время рассылки: {mailing_info['time']['hour']:02d}:{mailing_info['time']['minute']:02d}")
            user_info.append(f"   🔔 Уведомления: {'✅ Включены' if notifications_status else '❌ Выключены'}")
            
            user_info.append("")
            
            # Статистика
            user_info.append("📊 *Статистика:*")
            user_info.append(f"   📈 Запросов (1ч): {requests_1h}")
            user_info.append(f"   📈 Запросов (24ч): {requests_24h}")
            user_info.append(f"   📊 Всего запросов: {total_requests}")
            
            user_info.append("")
            
            # Статус блокировки
            user_info.append("🛡️ *Статус блокировки:*")
            if is_banned:
                user_info.append("   🚫 *ЗАБАНЕН*")
                
                # Информация о бане
                reason = ban_info.get('reason', 'Причина не указана')
                banned_until = ban_info.get('banned_until')
                banned_since = ban_info.get('created_at')
                
                user_info.append(f"   ⚠️ Причина: {reason}")
                
                if banned_until:
                    until_text = banned_until.strftime("%d.%m.%Y в %H:%M")
                    user_info.append(f"   ⏰ Бан до: {until_text}")
                    
                    # Рассчитываем оставшееся время
                    now = datetime.now()
                    if banned_until > now:
                        time_left = banned_until - now
                        days = time_left.days
                        hours = time_left.seconds // 3600
                        minutes = (time_left.seconds % 3600) // 60
                        user_info.append(f"   ⏳ Осталось: {days}д {hours}ч {minutes}м")
                else:
                    user_info.append("   ⏰ Бан до: *НАВСЕГДА*")
                
                if banned_since:
                    since_text = banned_since.strftime("%d.%m.%Y в %H:%M")
                    user_info.append(f"   📅 Забанен: {since_text}")
            else:
                user_info.append("   ✅ Активен")
            
            user_info.append("")
            
            # Информация о последней активности
            user_info.append("🕒 *Последняя активность:*")
            try:
                # Получаем последние запросы пользователя
                conn = db_manager.get_connection()
                if conn:
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute("""
                        SELECT command, timestamp 
                        FROM request_stats 
                        WHERE chat_id = %s 
                        ORDER BY timestamp DESC 
                        LIMIT 1
                    """, (str(user.id),))
                    last_activity = cursor.fetchone()
                    
                    if last_activity:
                        last_time = last_activity['timestamp']
                        if isinstance(last_time, str):
                            last_time = datetime.fromisoformat(last_time)
                        last_time_str = last_time.strftime("%d.%m.%Y в %H:%M:%S")
                        user_info.append(f"   📅 Последний запрос: {last_time_str}")
                        user_info.append(f"   🎯 Команда: {last_activity['command'] or 'Неизвестно'}")
                    else:
                        user_info.append("   📅 Активность: не зафиксирована")
                    
                    cursor.close()
                    conn.close()
            except Exception as e:
                logger.error(f"Ошибка получения последней активности: {e}")
                user_info.append("   📅 Активность: ошибка получения")
            
            response = "\n".join(user_info)
            
            # Если сообщение слишком длинное, разбиваем на части
            if len(response) > 4096:
                parts = [response[i:i+4096] for i in range(0, len(response), 4096)]
                for i, part in enumerate(parts, 1):
                    if i == 1:
                        await update.message.reply_text(part, parse_mode='Markdown')
                    else:
                        await update.message.reply_text(f"*Продолжение ({i}/{len(parts)})*:\n\n{part}", parse_mode='Markdown')
                    await asyncio.sleep(0.5)
            else:
                await update.message.reply_text(response, parse_mode='Markdown')
            
        except Exception as e:
            error_msg = str(e).lower()
            if "chat not found" in error_msg:
                await update.message.reply_text(
                    f"❌ Пользователь с ID `{user_id}` не найден в Telegram\n\n"
                    f"*Возможные причины:*\n"
                    f"• Пользователь удалил аккаунт\n"
                    f"• Бот заблокирован пользователем\n"
                    f"• Неверный ID пользователя", 
                    parse_mode='Markdown'
                )
            elif "user is deleted" in error_msg:
                await update.message.reply_text(
                    f"❌ Пользователь с ID `{user_id}` удалил аккаунт", 
                    parse_mode='Markdown'
                )
            elif "forbidden" in error_msg:
                await update.message.reply_text(
                    f"❌ Пользователь с ID `{user_id}` скрыл профиль или заблокировал бота", 
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"❌ Ошибка при поиске пользователя: {str(e)}\n\n"
                    f"*Рекомендации:*\n"
                    f"• Проверьте правильность ID\n"
                    f"• Убедитесь, что пользователь не блокировал бота", 
                    parse_mode='Markdown'
                )
                
    except Exception as e:
        logger.error(f"Ошибка в команде find: {e}")
        await update.message.reply_text(
            "❌ Ошибка при поиске пользователя\n\n"
            "Проверьте:\n"
            "• Правильность введенного ID\n"
            "• Доступность пользователя\n"
            "• Наличие прав у бота"
        )

async def mailing_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_flood_protection(update, context):
        return
        
    """Управление рассылкой - главное меню"""
    try:
        await save_chat_info(update, context)
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
        # ИСПРАВЛЕНИЕ: Используем query для отправки сообщения об ошибке
        try:
            await query.edit_message_text("❌ Ошибка при обработке команды рассылки.")
        except:
            # Если query недоступен, пробуем через update
            if update.message:
                await update.message.reply_text("❌ Ошибка при обработке команды рассылки.")
        return ConversationHandler.END

async def set_mailing_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_flood_protection(update, context):
        return
        
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
    if not await check_flood_protection(update, context):
        return
        
    """Показать статус рассылки"""
    try:
        await save_chat_info(update, context)
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
    if not await check_flood_protection(update, context):
        return
        
    """Управление уведомлениями об изменениях расписания с обработкой ошибок"""
    try:
        await save_chat_info(update, context)
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
    if not await check_flood_protection(update, context):
        return
        
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
        # ИСПРАВЛЕНИЕ: Используем query для отправки сообщения об ошибке
        try:
            await query.edit_message_text("❌ Ошибка при обработке уведомлений.")
        except:
            # Если query недоступен, пробуем через update
            if update.message:
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
        
        # ИСПРАВЛЕНИЕ: Используем datetime.time вместо модуля time
        from datetime import time
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

    migration_result = db_manager.migrate_from_json()
    if any(migration_result.values()):
        logger.info(f"✅ Мигрированы данные: {migration_result}")
    
    # Проверяем доступные группы при старте
    available_groups = group_manager.get_available_groups()
    logger.info(f"Загружены группы из конфига: {available_groups}")
    
    if not available_groups:
        logger.error("❌ В конфиге не найдено ни одной группы!")
    
    # Создаем Application
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("contact", contact))
    application.add_handler(CommandHandler("update_info", update_info))
    application.add_handler(CommandHandler("today", today))
    application.add_handler(CommandHandler("tomorrow", tomorrow))
    application.add_handler(CommandHandler("week", week_schedule))
    application.add_handler(CommandHandler("bells", bells))
    application.add_handler(CommandHandler("bells_today", bells_today))
    application.add_handler(CommandHandler("mailing_status", mailing_status))
    application.add_handler(CommandHandler("changes", changes_management))
    application.add_handler(CommandHandler("find", find_user_detailed))
    application.add_handler(CommandHandler("setadmin", setadmin))
    application.add_handler(CommandHandler("floodon", floodon))
    application.add_handler(CommandHandler("floodoff", floodoff))
    application.add_handler(CommandHandler("floodsettings", floodsettings))
    application.add_handler(CommandHandler("sysinfo", sysinfo))
    application.add_handler(CommandHandler("reboot", reboot))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("crondownload", crondownload))
    application.add_handler(CommandHandler("settings_info", settings_info))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("kick", kick_chat))
    application.add_handler(CommandHandler("delid", delid))
    application.add_handler(CommandHandler("startinfo", startinfo))
    application.add_handler(CommandHandler("cleanup_chats", cleanup_chats))
    application.add_handler(CommandHandler("service_help", service_help))
    application.add_handler(CommandHandler("delmsg", delete_message))
    application.add_handler(CommandHandler("settingschats", settings_chats))
    application.add_handler(CommandHandler("takeadmin", takeadmin))
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, chat_member_handler))

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