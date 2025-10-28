import logging
import os
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, cast
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not found in environment variables")
    exit(1)

if not DATABASE_URL:
    logger.error("DATABASE_URL not found in environment variables")
    exit(1)

class DatabaseManager:
    def __init__(self, connection_string: str):
        self.conn_string = connection_string
        self.init_db()

    def get_connection(self) -> psycopg2.extensions.connection:
        """Создание подключения к PostgreSQL"""
        try:
            return psycopg2.connect(self.conn_string)
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise

    def init_db(self) -> None:
        """Инициализация таблиц в PostgreSQL"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Таблица настроек чатов
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS chat_settings (
                            chat_id BIGINT PRIMARY KEY,
                            welcome_message TEXT DEFAULT '👋 Добро пожаловать, {mention}!',
                            min_account_age_days INTEGER DEFAULT 1,
                            min_join_date_days INTEGER DEFAULT 0,
                            restrict_new_users BOOLEAN DEFAULT TRUE,
                            delete_service_messages BOOLEAN DEFAULT TRUE,
                            enabled BOOLEAN DEFAULT TRUE,
                            max_warnings INTEGER DEFAULT 3,
                            anti_flood_enabled BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.commit()
                    logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def get_chat_settings(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Получение настроек чата"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        'SELECT * FROM chat_settings WHERE chat_id = %s',
                        (chat_id,)
                    )
                    result = cursor.fetchone()
                    
                    if result:
                        return {
                            'chat_id': result[0],
                            'welcome_message': str(result[1]),
                            'min_account_age_days': int(result[2]),
                            'min_join_date_days': int(result[3]),
                            'restrict_new_users': bool(result[4]),
                            'delete_service_messages': bool(result[5]),
                            'enabled': bool(result[6]),
                            'max_warnings': int(result[7]),
                            'anti_flood_enabled': bool(result[8])
                        }
                    else:
                        # Создаем настройки по умолчанию
                        default_settings: Dict[str, Any] = {
                            'chat_id': chat_id,
                            'welcome_message': '👋 Добро пожаловать, {mention}!',
                            'min_account_age_days': 1,
                            'min_join_date_days': 0,
                            'restrict_new_users': True,
                            'delete_service_messages': True,
                            'enabled': True,
                            'max_warnings': 3,
                            'anti_flood_enabled': True
                        }
                        self.save_chat_settings(default_settings)
                        return default_settings
        except Exception as e:
            logger.error(f"Error getting chat settings: {e}")
            return None

    def save_chat_settings(self, settings: Dict[str, Any]) -> None:
        """Сохранение настроек чата"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        INSERT INTO chat_settings 
                        (chat_id, welcome_message, min_account_age_days, min_join_date_days, 
                         restrict_new_users, delete_service_messages, enabled, max_warnings, anti_flood_enabled)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (chat_id) DO UPDATE SET
                        welcome_message = EXCLUDED.welcome_message,
                        min_account_age_days = EXCLUDED.min_account_age_days,
                        min_join_date_days = EXCLUDED.min_join_date_days,
                        restrict_new_users = EXCLUDED.restrict_new_users,
                        delete_service_messages = EXCLUDED.delete_service_messages,
                        enabled = EXCLUDED.enabled,
                        max_warnings = EXCLUDED.max_warnings,
                        anti_flood_enabled = EXCLUDED.anti_flood_enabled
                    ''', (
                        settings['chat_id'],
                        settings['welcome_message'],
                        settings['min_account_age_days'],
                        settings['min_join_date_days'],
                        settings['restrict_new_users'],
                        settings['delete_service_messages'],
                        settings['enabled'],
                        settings['max_warnings'],
                        settings['anti_flood_enabled']
                    ))
                    conn.commit()
        except Exception as e:
            logger.error(f"Error saving chat settings: {e}")
            raise

# Инициализация базы данных
try:
    db = DatabaseManager(DATABASE_URL)
    logger.info("Database connected successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    exit(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    if not user or not chat or not message:
        return
        
    if chat.type == 'private':
        await message.reply_text(
            f"👋 <b>Привет, {user.first_name}!</b>\n\n"
            "🛡️ <b>Я - бот защиты от спама</b>\n\n"
            "<b>Основные возможности:</b>\n"
            "• Автопроверка новых участников\n"
            "• Фильтр по возрасту аккаунтов\n"
            "• Защита от флуда\n"
            "• Умные приветствия\n\n"
            "<b>Добавьте меня в группу и назначьте администратором!</b>",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            "🛡️ <b>Бот защиты активирован!</b>\n\n"
            "Используйте /settings для настройки параметров защиты",
            parse_mode=ParseMode.HTML
        )

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /settings"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if not chat or not user or not message:
        return
    
    # Проверка прав администратора в группах
    if chat.type != 'private':
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member and member.status not in ['administrator', 'creator']:
                await message.reply_text("❌ Только администраторы могут настраивать бота")
                return
        except Exception as e:
            logger.error(f"Error checking admin rights: {e}")
    
    settings_data = db.get_chat_settings(chat.id)
    if not settings_data:
        await message.reply_text("❌ Ошибка загрузки настроек")
        return
    
    keyboard = [
        [InlineKeyboardButton("✏️ Приветствие", callback_data="set_welcome")],
        [InlineKeyboardButton("📅 Возраст аккаунта", callback_data="set_age")],
        [InlineKeyboardButton("⚡ Основные настройки", callback_data="main_settings")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="close")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status = "✅ ВКЛ" if settings_data['enabled'] else "❌ ВЫКЛ"
    restrict = "✅ ВКЛ" if settings_data['restrict_new_users'] else "❌ ВЫКЛ"
    service = "✅ ВКЛ" if settings_data['delete_service_messages'] else "❌ ВЫКЛ"
    
    await message.reply_text(
        f"⚙️ <b>Настройки защиты</b>\n\n"
        f"🛡️ Статус: {status}\n"
        f"📅 Мин. возраст: {settings_data['min_account_age_days']} дн.\n"
        f"🔒 Ограничения: {restrict}\n"
        f"🗑️ Удаление сообщений: {service}\n\n"
        f"<i>Выберите параметр для настройки:</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Показать меню настроек (для callback обработчиков)"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [InlineKeyboardButton("✏️ Приветствие", callback_data="set_welcome")],
        [InlineKeyboardButton("📅 Возраст аккаунта", callback_data="set_age")],
        [InlineKeyboardButton("⚡ Основные настройки", callback_data="main_settings")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="close")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status = "✅ ВКЛ" if settings_data['enabled'] else "❌ ВЫКЛ"
    restrict = "✅ ВКЛ" if settings_data['restrict_new_users'] else "❌ ВЫКЛ"
    service = "✅ ВКЛ" if settings_data['delete_service_messages'] else "❌ ВЫКЛ"
    
    text = (
        f"⚙️ <b>Настройки защиты</b>\n\n"
        f"🛡️ Статус: {status}\n"
        f"📅 Мин. возраст: {settings_data['min_account_age_days']} дн.\n"
        f"🔒 Ограничения: {restrict}\n"
        f"🗑️ Удаление сообщений: {service}\n\n"
        f"<i>Выберите параметр для настройки:</i>"
    )
    
    if message_id:
        # Редактируем существующее сообщение
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        # Отправляем новое сообщение
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    
    if not query or not query.message:
        return
        
    await query.answer()
    
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    data = query.data
    
    if not data:
        return
    
    if data == "close":
        await query.message.delete()
        return
        
    elif data == "set_age":
        keyboard = [
            [InlineKeyboardButton("0 дней", callback_data="age_0")],
            [InlineKeyboardButton("1 день", callback_data="age_1")],
            [InlineKeyboardButton("3 дня", callback_data="age_3")],
            [InlineKeyboardButton("7 дней", callback_data="age_7")],
            [InlineKeyboardButton("30 дней", callback_data="age_30")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📅 <b>Выберите минимальный возраст аккаунта:</b>",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
    elif data.startswith("age_"):
        days = int(data.split("_")[1])
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data['min_account_age_days'] = days
            db.save_chat_settings(settings_data)
            await query.answer(f"✅ Установлено: {days} дней")
            await show_settings_menu(update, context, chat_id, message_id)
        
    elif data == "main_settings":
        settings_data = db.get_chat_settings(chat_id)
        if not settings_data:
            return
            
        keyboard = [
            [
                InlineKeyboardButton("🛡️ Вкл/Выкл", callback_data="toggle_enable"),
                InlineKeyboardButton("🔒 Ограничения", callback_data="toggle_restrict")
            ],
            [
                InlineKeyboardButton("🗑️ Удаление", callback_data="toggle_service"),
                InlineKeyboardButton("🌊 Анти-флуд", callback_data="toggle_flood")
            ],
            [InlineKeyboardButton("◀️ Назад", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        enable_status = "✅ ВКЛ" if settings_data['enabled'] else "❌ ВЫКЛ"
        restrict_status = "✅ ВКЛ" if settings_data['restrict_new_users'] else "❌ ВЫКЛ"
        service_status = "✅ ВКЛ" if settings_data['delete_service_messages'] else "❌ ВЫКЛ"
        flood_status = "✅ ВКЛ" if settings_data['anti_flood_enabled'] else "❌ ВЫКЛ"
        
        await query.edit_message_text(
            f"⚡ <b>Основные настройки</b>\n\n"
            f"🛡️ Бот: {enable_status}\n"
            f"🔒 Ограничения: {restrict_status}\n"
            f"🗑️ Удаление: {service_status}\n"
            f"🌊 Анти-флуд: {flood_status}\n\n"
            f"<i>Выберите параметр:</i>",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
    elif data.startswith("toggle_"):
        settings_data = db.get_chat_settings(chat_id)
        if not settings_data:
            return
            
        status_text = ""
        if data == "toggle_enable":
            settings_data['enabled'] = not settings_data['enabled']
            status_text = "включен" if settings_data['enabled'] else "выключен"
        elif data == "toggle_restrict":
            settings_data['restrict_new_users'] = not settings_data['restrict_new_users']
            status_text = "включены" if settings_data['restrict_new_users'] else "выключены"
        elif data == "toggle_service":
            settings_data['delete_service_messages'] = not settings_data['delete_service_messages']
            status_text = "включено" if settings_data['delete_service_messages'] else "выключено"
        elif data == "toggle_flood":
            settings_data['anti_flood_enabled'] = not settings_data['anti_flood_enabled']
            status_text = "включена" if settings_data['anti_flood_enabled'] else "выключена"
            
        db.save_chat_settings(settings_data)
        await query.answer(f"✅ {status_text.capitalize()}")
        await show_settings_menu(update, context, chat_id, message_id)
        
    elif data == "back":
        await show_settings_menu(update, context, chat_id, message_id)
        
    elif data == "set_welcome":
        await query.edit_message_text(
            "✏️ <b>Введите приветственное сообщение:</b>\n\n"
            "<i>Доступные переменные:</i>\n"
            "<code>{name}</code> - имя пользователя\n"
            "<code>{mention}</code> - упоминание\n"
            "<code>{chat}</code> - название чата\n\n"
            "<i>Пример:</i> Добро пожаловать, {mention}!",
            parse_mode=ParseMode.HTML
        )
        if context.user_data is not None:
            context.user_data['awaiting_welcome'] = True
            context.user_data['settings_message_id'] = message_id

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    message = update.message
    chat = update.effective_chat
    
    if not message or not chat or not context.user_data:
        return
        
    if 'awaiting_welcome' in context.user_data:
        chat_id = chat.id
        welcome_message = message.text
        
        if not welcome_message:
            return
            
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data['welcome_message'] = welcome_message
            db.save_chat_settings(settings_data)
            
            del context.user_data['awaiting_welcome']
            if 'settings_message_id' in context.user_data:
                del context.user_data['settings_message_id']
                
            await message.reply_text("✅ Приветственное сообщение обновлено!")
            
            # Возвращаемся к меню настроек
            message_id = context.user_data.get('settings_message_id')
            if message_id:
                await show_settings_menu(update, context, chat_id, message_id)

async def new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик новых участников"""
    chat = update.effective_chat
    message = update.message
    
    if not chat or not message:
        return
        
    settings_data = db.get_chat_settings(chat.id)
    
    if not settings_data or not settings_data['enabled']:
        return
    
    for member in message.new_chat_members:
        # Проверка что member не None
        if not member:
            continue
            
        # Пропускаем самого бота
        if member.id == context.bot.id:
            continue
            
        # Проверка возраста аккаунта с явным приведением типа
        if settings_data['min_account_age_days'] > 0:
            # Используем getattr для безопасного доступа к атрибуту date
            member_date = getattr(member, 'date', None)
            if member_date:
                # Явное указание типа для account_age_delta
                account_age_delta: timedelta = datetime.now().replace(tzinfo=None) - member_date.replace(tzinfo=None)
                account_age_days: int = account_age_delta.days
                
                if account_age_days < settings_data['min_account_age_days']:
                    try:
                        await context.bot.ban_chat_member(chat.id, member.id)
                        await context.bot.unban_chat_member(chat.id, member.id)
                        logger.info(f"Kicked user {member.id} for young account")
                        continue
                    except Exception as e:
                        logger.error(f"Error kicking user: {e}")
        
        # Отправка приветственного сообщения
        welcome_text = settings_data['welcome_message']
        welcome_text = welcome_text.replace('{name}', member.first_name or 'Пользователь')
        welcome_text = welcome_text.replace('{mention}', f'<a href="tg://user?id={member.id}">{member.first_name}</a>')
        welcome_text = welcome_text.replace('{chat}', chat.title or 'чат')
        
        try:
            await message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")
    
    # Удаление сервисного сообщения
    if settings_data['delete_service_messages']:
        try:
            await message.delete()
        except Exception as e:
            logger.error(f"Error deleting service message: {e}")

async def enable_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /enable"""
    chat = update.effective_chat
    message = update.message
    
    if not chat or not message:
        return
        
    settings_data = db.get_chat_settings(chat.id)
    if settings_data:
        settings_data['enabled'] = True
        db.save_chat_settings(settings_data)
        await message.reply_text("✅ Бот защиты включен!")

async def disable_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /disable"""
    chat = update.effective_chat
    message = update.message
    
    if not chat or not message:
        return
        
    settings_data = db.get_chat_settings(chat.id)
    if settings_data:
        settings_data['enabled'] = False
        db.save_chat_settings(settings_data)
        await message.reply_text("❌ Бот защиты выключен!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    message = update.message
    
    if not message:
        return
        
    help_text = """
🛡️ <b>Команды бота защиты:</b>

/settings - Настройки защиты
/enable - Включить бота
/disable - Выключить бота
/help - Справка

<b>Добавьте бота в группу и назначьте администратором для полного функционала!</b>
    """
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")

def main() -> None:
    """Основная функция запуска бота"""
    try:
        # Приведение типа для токена
        token = cast(str, BOT_TOKEN)
        application = Application.builder().token(token).build()
        
        # Добавление обработчиков
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("settings", settings))
        application.add_handler(CommandHandler("enable", enable_bot))
        application.add_handler(CommandHandler("disable", disable_bot))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        logger.info("Бот запускается...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == '__main__':
    main()