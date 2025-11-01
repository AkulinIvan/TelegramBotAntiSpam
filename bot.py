import asyncio
import logging
import os
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, cast, Tuple, List
from telegram import ChatPermissions, Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, Chat, User
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from dotenv import load_dotenv
import telegram
print(f"=== TELEGRAM LIBRARY VERSION: {telegram.__version__} ===")
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

class CaptchaPolicy:
    PERSISTENT = "persistent"      # ✅ Рекомендуется
    TIME_BASED = "time_based"      # 🔄 Для строгих чатов
    ALWAYS = "always"              # 🚫 Макс. безопасность

class DatabaseManager:
    def __init__(self, connection_string: str):
        self.conn_string = connection_string
        self.init_db()
        self.recreate_table_properly()
        self.update_database_schema()
        self.check_table_structure()

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
                            welcome_message TEXT DEFAULT '👋 Добро пожаловать, {mention}! Рады видеть вас в {chat}!',
                            min_account_age_days INTEGER DEFAULT 1,
                            min_join_date_days INTEGER DEFAULT 0,
                            restrict_new_users BOOLEAN DEFAULT TRUE,
                            delete_service_messages BOOLEAN DEFAULT TRUE,
                            enabled BOOLEAN DEFAULT TRUE,
                            max_warnings INTEGER DEFAULT 3,
                            anti_flood_enabled BOOLEAN DEFAULT TRUE,
                            protect_comments BOOLEAN DEFAULT TRUE,
                            message_cooldown_enabled BOOLEAN DEFAULT FALSE,
                            captcha_enabled BOOLEAN DEFAULT TRUE,
                            captcha_type VARCHAR(20) DEFAULT 'button',
                            captcha_timeout_minutes INTEGER DEFAULT 10,
                            captcha_max_attempts INTEGER DEFAULT 3,
                            captcha_policy VARCHAR(20) DEFAULT 'persistent',
                            captcha_valid_days INTEGER DEFAULT 30,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    # Таблица статистики
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS statistics (
                            id SERIAL PRIMARY KEY,
                            chat_id BIGINT NOT NULL,
                            user_id BIGINT,
                            action_type VARCHAR(50) NOT NULL,
                            details TEXT,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    # Таблица предупреждений
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS user_warnings (
                            id SERIAL PRIMARY KEY,
                            chat_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            warnings_count INTEGER DEFAULT 0,
                            last_warning TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(chat_id, user_id)
                        )
                    ''')
                    
                    # Таблица флуд-контроля для комментариев
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS flood_control (
                            id SERIAL PRIMARY KEY,
                            chat_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            message_count INTEGER DEFAULT 1,
                            last_message TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    # Таблица для ограничения частоты сообщений
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS message_cooldown (
                            id SERIAL PRIMARY KEY,
                            chat_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            last_message TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(chat_id, user_id)
                        )
                    ''')
                    
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS user_captcha (
                            id SERIAL PRIMARY KEY,
                            chat_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            captcha_passed BOOLEAN DEFAULT FALSE,
                            captcha_message_id BIGINT,
                            attempts INTEGER DEFAULT 0,
                            max_attempts INTEGER DEFAULT 3,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP + INTERVAL '10 minutes',
                            UNIQUE(chat_id, user_id)
                        )
                    ''')
                    
                    # Индексы для оптимизации
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cooldown_chat_user ON message_cooldown(chat_id, user_id)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cooldown_timestamp ON message_cooldown(last_message)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_chat_id ON statistics(chat_id)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_timestamp ON statistics(timestamp)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_action ON statistics(action_type)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_warnings_chat_user ON user_warnings(chat_id, user_id)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_flood_control_chat_user ON flood_control(chat_id, user_id)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_flood_control_timestamp ON flood_control(last_message)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_captcha_chat_user ON user_captcha(chat_id, user_id)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_captcha_expires ON user_captcha(expires_at)')
                
                    conn.commit()
                    logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def get_chat_settings(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Получение настроек чата"""
        try:
            logger.info(f"Загрузка настроек для чата {chat_id}")

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        'SELECT * FROM chat_settings WHERE chat_id = %s',
                        (chat_id,)
                    )
                    result = cursor.fetchone()

                    if result:
                        # Универсальная обработка с проверкой наличия столбцов
                        columns = [desc[0] for desc in cursor.description]
                        settings = {
                            'chat_id': result[columns.index('chat_id')],
                            'welcome_message': str(result[columns.index('welcome_message')]),
                            'min_account_age_days': int(result[columns.index('min_account_age_days')]),
                            'min_join_date_days': int(result[columns.index('min_join_date_days')]),
                            'restrict_new_users': bool(result[columns.index('restrict_new_users')]),
                            'delete_service_messages': bool(result[columns.index('delete_service_messages')]),
                            'enabled': bool(result[columns.index('enabled')]),
                            'max_warnings': int(result[columns.index('max_warnings')]),
                            'anti_flood_enabled': bool(result[columns.index('anti_flood_enabled')]),
                            'protect_comments': bool(result[columns.index('protect_comments')]) if 'protect_comments' in columns else True,
                            'message_cooldown_enabled': bool(result[columns.index('message_cooldown_enabled')]) if 'message_cooldown_enabled' in columns else False,
                            'captcha_enabled': bool(result[columns.index('captcha_enabled')]) if 'captcha_enabled' in columns else False,
                            'captcha_type': str(result[columns.index('captcha_type')]) if 'captcha_type' in columns else 'button',
                            'captcha_timeout_minutes': int(result[columns.index('captcha_timeout_minutes')]) if 'captcha_timeout_minutes' in columns else 10,
                            'captcha_max_attempts': int(result[columns.index('captcha_max_attempts')]) if 'captcha_max_attempts' in columns else 3,
                            'captcha_policy': str(result[columns.index('captcha_policy')]) if 'captcha_policy' in columns else 'persistent',
                            'captcha_valid_days': int(result[columns.index('captcha_valid_days')]) if 'captcha_valid_days' in columns else 30
                        }

                        logger.info(f"Загруженные настройки captcha_enabled: {settings.get('captcha_enabled')}")
                        return settings
                    else:
                        # Создаем настройки по умолчанию
                        default_settings = {
                            'chat_id': chat_id,
                            'welcome_message': '👋 Добро пожаловать, {mention}! Рады видеть вас в {chat}!',
                            'min_account_age_days': 1,
                            'min_join_date_days': 0,
                            'restrict_new_users': True,
                            'delete_service_messages': True,
                            'enabled': True,
                            'max_warnings': 3,
                            'anti_flood_enabled': True,
                            'protect_comments': True,
                            'message_cooldown_enabled': False,
                            'captcha_enabled': True,
                            'captcha_type': 'button',
                            'captcha_timeout_minutes': 10,
                            'captcha_max_attempts': 3,
                            'captcha_policy': 'persistent',
                            'captcha_valid_days': 30
                        }
                        self.save_chat_settings(default_settings)
                        return default_settings
        except Exception as e:
            logger.error(f"Error getting chat settings: {e}")
            return None

    def save_chat_settings(self, settings: Dict[str, Any]) -> None:
        """Сохранение настроек чата"""
        try:
            logger.info(f"Сохранение настроек для чата {settings['chat_id']}, captcha_enabled: {settings.get('captcha_enabled')}, policy: {settings.get('captcha_policy')}")

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        INSERT INTO chat_settings 
                        (chat_id, welcome_message, min_account_age_days, min_join_date_days, 
                         restrict_new_users, delete_service_messages, enabled, max_warnings, 
                         anti_flood_enabled, protect_comments, message_cooldown_enabled,
                         captcha_enabled, captcha_type, captcha_timeout_minutes, captcha_max_attempts,
                         captcha_policy, captcha_valid_days)  -- НОВЫЕ ПОЛЯ
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (chat_id) DO UPDATE SET
                        welcome_message = EXCLUDED.welcome_message,
                        min_account_age_days = EXCLUDED.min_account_age_days,
                        min_join_date_days = EXCLUDED.min_join_date_days,
                        restrict_new_users = EXCLUDED.restrict_new_users,
                        delete_service_messages = EXCLUDED.delete_service_messages,
                        enabled = EXCLUDED.enabled,
                        max_warnings = EXCLUDED.max_warnings,
                        anti_flood_enabled = EXCLUDED.anti_flood_enabled,
                        protect_comments = EXCLUDED.protect_comments,
                        message_cooldown_enabled = EXCLUDED.message_cooldown_enabled,
                        captcha_enabled = EXCLUDED.captcha_enabled,
                        captcha_type = EXCLUDED.captcha_type,
                        captcha_timeout_minutes = EXCLUDED.captcha_timeout_minutes,
                        captcha_max_attempts = EXCLUDED.captcha_max_attempts,
                        captcha_policy = EXCLUDED.captcha_policy,  -- НОВОЕ ПОЛЕ
                        captcha_valid_days = EXCLUDED.captcha_valid_days  -- НОВОЕ ПОЛЕ
                    ''', (
                        settings['chat_id'],
                        settings['welcome_message'],
                        settings['min_account_age_days'],
                        settings['min_join_date_days'],
                        settings['restrict_new_users'],
                        settings['delete_service_messages'],
                        settings['enabled'],
                        settings['max_warnings'],
                        settings['anti_flood_enabled'],
                        settings.get('protect_comments', True),
                        settings.get('message_cooldown_enabled', False),
                        settings.get('captcha_enabled'),
                        settings.get('captcha_type', 'button'),
                        settings.get('captcha_timeout_minutes', 10),
                        settings.get('captcha_max_attempts', 3),
                        settings.get('captcha_policy', 'persistent'),  # НОВОЕ ПОЛЕ
                        settings.get('captcha_valid_days', 30)  # НОВОЕ ПОЛЕ
                    ))
                    conn.commit()
                    logger.info("Настройки успешно сохранены в БД")
        except Exception as e:
            logger.error(f"Error saving chat settings: {e}")
            raise


    def log_action(self, chat_id: int, user_id: Optional[int], action_type: str, details: str = "") -> None:
            """Логирование действия в статистику"""
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            'INSERT INTO statistics (chat_id, user_id, action_type, details) VALUES (%s, %s, %s, %s)',
                            (chat_id, user_id, action_type, details)
                        )
                        conn.commit()
            except Exception as e:
                logger.error(f"Error logging action: {e}")

    def get_statistics(self, chat_id: int, days: int = 7) -> Dict[str, Any]:
        """Получение статистики за указанный период"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Общая статистика по действиям
                    cursor.execute('''
                        SELECT action_type, COUNT(*) as count 
                        FROM statistics 
                        WHERE chat_id = %s AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                        GROUP BY action_type
                    ''', (chat_id, days))
                    actions_stats = {row[0]: row[1] for row in cursor.fetchall()}

                    # Статистика по дням
                    cursor.execute('''
                        SELECT DATE(timestamp), COUNT(*) 
                        FROM statistics 
                        WHERE chat_id = %s AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                        GROUP BY DATE(timestamp) 
                        ORDER BY DATE(timestamp) DESC
                        LIMIT 7
                    ''', (chat_id, days))
                    daily_stats = list(cursor.fetchall())

                    # Активность за сегодня
                    cursor.execute('''
                        SELECT COUNT(*) 
                        FROM statistics 
                        WHERE chat_id = %s AND DATE(timestamp) = CURRENT_DATE
                    ''', (chat_id,))
                    today_actions_result = cursor.fetchone()
                    today_actions = today_actions_result[0] if today_actions_result else 0

                    # Новые пользователи за сегодня
                    cursor.execute('''
                        SELECT COUNT(DISTINCT user_id) 
                        FROM statistics 
                        WHERE chat_id = %s AND DATE(timestamp) = CURRENT_DATE 
                        AND action_type = 'new_member'
                    ''', (chat_id,))
                    today_new_users_result = cursor.fetchone()
                    today_new_users = today_new_users_result[0] if today_new_users_result else 0

                    # Топ активных пользователей
                    cursor.execute('''
                        SELECT user_id, COUNT(*) as activity_count 
                        FROM statistics 
                        WHERE chat_id = %s AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '%s days'
                        AND user_id IS NOT NULL
                        GROUP BY user_id 
                        ORDER BY activity_count DESC 
                        LIMIT 5
                    ''', (chat_id, days))
                    top_users = cursor.fetchall()

                    # Статистика предупреждений
                    cursor.execute('''
                        SELECT SUM(warnings_count), COUNT(*) 
                        FROM user_warnings 
                        WHERE chat_id = %s
                    ''', (chat_id,))
                    warnings_result = cursor.fetchone()
                    total_warnings = warnings_result[0] if warnings_result and warnings_result[0] else 0
                    warned_users = warnings_result[1] if warnings_result and warnings_result[1] else 0

                    return {
                        'actions': actions_stats,
                        'daily_stats': daily_stats,
                        'today_actions': today_actions,
                        'today_new_users': today_new_users,
                        'top_users': top_users,
                        'total_warnings': total_warnings,
                        'warned_users': warned_users,
                        'total_actions': sum(actions_stats.values())
                    }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {
                'actions': {},
                'daily_stats': [],
                'today_actions': 0,
                'today_new_users': 0,
                'top_users': [],
                'total_warnings': 0,
                'warned_users': 0,
                'total_actions': 0
            }
        
    def get_detailed_statistics(self, chat_id: int) -> Dict[str, Any]:
            """Получение детальной статистики"""
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Общая статистика за все время
                        cursor.execute('''
                            SELECT action_type, COUNT(*) as count 
                            FROM statistics 
                            WHERE chat_id = %s
                            GROUP BY action_type
                            ORDER BY count DESC
                        ''', (chat_id,))
                        all_time_stats = cursor.fetchall()

                        # Статистика по месяцам
                        cursor.execute('''
                            SELECT 
                                TO_CHAR(timestamp, 'YYYY-MM') as month,
                                COUNT(*) as count
                            FROM statistics 
                            WHERE chat_id = %s
                            GROUP BY TO_CHAR(timestamp, 'YYYY-MM')
                            ORDER BY month DESC
                            LIMIT 6
                        ''', (chat_id,))
                        monthly_stats = cursor.fetchall()

                        # Самые активные дни
                        cursor.execute('''
                            SELECT 
                                DATE(timestamp) as day,
                                COUNT(*) as count
                            FROM statistics 
                            WHERE chat_id = %s
                            GROUP BY DATE(timestamp)
                            ORDER BY count DESC
                            LIMIT 5
                        ''', (chat_id,))
                        top_days = cursor.fetchall()

                        # Эффективность защиты
                        cursor.execute('''
                            SELECT 
                                COUNT(CASE WHEN action_type = 'user_blocked' THEN 1 END) as blocked,
                                COUNT(CASE WHEN action_type = 'new_member' THEN 1 END) as new_members,
                                COUNT(CASE WHEN action_type = 'welcome_sent' THEN 1 END) as welcomes
                            FROM statistics 
                            WHERE chat_id = %s AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '30 days'
                        ''', (chat_id,))
                        protection_stats = cursor.fetchone()

                        return {
                            'all_time': all_time_stats,
                            'monthly': monthly_stats,
                            'top_days': top_days,
                            'protection': protection_stats
                        }
            except Exception as e:
                logger.error(f"Error getting detailed statistics: {e}")
                return {
                    'all_time': [],
                    'monthly': [],
                    'top_days': [],
                    'protection': (0, 0, 0)
                }

    def add_user_warning(self, chat_id: int, user_id: int) -> int:
        """Добавление предупреждения пользователю"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        INSERT INTO user_warnings (chat_id, user_id, warnings_count, last_warning)
                        VALUES (%s, %s, 1, CURRENT_TIMESTAMP)
                        ON CONFLICT (chat_id, user_id) DO UPDATE SET
                        warnings_count = user_warnings.warnings_count + 1,
                        last_warning = CURRENT_TIMESTAMP
                        RETURNING warnings_count
                    ''', (chat_id, user_id))
                    result = cursor.fetchone()
                    conn.commit()
                    return result[0] if result else 1
        except Exception as e:
            logger.error(f"Error adding user warning: {e}")
            return 1

    def get_user_warnings(self, chat_id: int, user_id: int) -> int:
        """Получение количества предупреждений пользователя"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        'SELECT warnings_count FROM user_warnings WHERE chat_id = %s AND user_id = %s',
                        (chat_id, user_id)
                    )
                    result = cursor.fetchone()
                    return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting user warnings: {e}")
            return 0

    def reset_user_warnings(self, chat_id: int, user_id: int) -> None:
        """Сброс предупреждений пользователя"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        'DELETE FROM user_warnings WHERE chat_id = %s AND user_id = %s',
                        (chat_id, user_id)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Error resetting user warnings: {e}")

    def reset_all_statistics(self, chat_id: int) -> None:
        """Сброс всей статистики чата"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('DELETE FROM statistics WHERE chat_id = %s', (chat_id,))
                    cursor.execute('DELETE FROM user_warnings WHERE chat_id = %s', (chat_id,))
                    conn.commit()
        except Exception as e:
            logger.error(f"Error resetting statistics: {e}")

    def check_flood_control(self, chat_id: int, user_id: int, time_window: int = 10, max_messages: int = 5) -> bool:
        """Проверка флуд-контроля для комментариев"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Удаляем старые записи
                    cursor.execute(
                        'DELETE FROM flood_control WHERE last_message < NOW() - INTERVAL %s SECOND',
                        (time_window,)
                    )
                    
                    # Проверяем текущее количество сообщений
                    cursor.execute('''
                        SELECT message_count FROM flood_control 
                        WHERE chat_id = %s AND user_id = %s
                    ''', (chat_id, user_id))
                    
                    result = cursor.fetchone()
                    
                    if result:
                        message_count = result[0] + 1
                        cursor.execute('''
                            UPDATE flood_control 
                            SET message_count = %s, last_message = CURRENT_TIMESTAMP
                            WHERE chat_id = %s AND user_id = %s
                        ''', (message_count, chat_id, user_id))
                    else:
                        message_count = 1
                        cursor.execute('''
                            INSERT INTO flood_control (chat_id, user_id, message_count)
                            VALUES (%s, %s, %s)
                        ''', (chat_id, user_id, message_count))
                    
                    conn.commit()
                    return message_count > max_messages
                    
        except Exception as e:
            logger.error(f"Error checking flood control: {e}")
            return False

    def reset_flood_control(self, chat_id: int, user_id: int) -> None:
        """Сброс флуд-контроля для пользователя"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        'DELETE FROM flood_control WHERE chat_id = %s AND user_id = %s',
                        (chat_id, user_id)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Error resetting flood control: {e}")
    
    def update_database_schema(self) -> None:
        """Обновление структуры базы данных"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Список столбцов для проверки и добавления
                    columns_to_check = [
                        ('protect_comments', 'BOOLEAN DEFAULT TRUE'),
                        ('message_cooldown_enabled', 'BOOLEAN DEFAULT FALSE'),
                        ('captcha_enabled', 'BOOLEAN DEFAULT TRUE'),  # Новая настройка
                        ('captcha_type', 'VARCHAR(20) DEFAULT \'button\''),  # Тип капчи
                        ('captcha_timeout_minutes', 'INTEGER DEFAULT 10'),  # Таймаут капчи
                        ('captcha_max_attempts', 'INTEGER DEFAULT 3'),  # Макс попыток
                        ('captcha_policy', 'VARCHAR(20) DEFAULT \'persistent\''),  # НОВОЕ ПОЛЕ
                        ('captcha_valid_days', 'INTEGER DEFAULT 30')
                    ]

                    for column_name, column_type in columns_to_check:
                        cursor.execute('''
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'chat_settings' AND column_name = %s
                        ''', (column_name,))
                        if not cursor.fetchone():
                            # Добавляем отсутствующий столбец
                            cursor.execute(f'ALTER TABLE chat_settings ADD COLUMN {column_name} {column_type}')
                            logger.info(f"Added {column_name} column to chat_settings table")

                    conn.commit()
        except Exception as e:
            logger.error(f"Error updating database schema: {e}")
    
    
    
    def check_captcha_passed_recently(self, chat_id: int, user_id: int, days: int = 30) -> bool:
        """Проверка, прошел ли пользователь капчу в течение указанного количества дней"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Удаляем просроченные капчи
                    cursor.execute('DELETE FROM user_captcha WHERE expires_at < CURRENT_TIMESTAMP')

                    cursor.execute('''
                        SELECT captcha_passed, created_at FROM user_captcha 
                        WHERE chat_id = %s AND user_id = %s
                        AND created_at >= CURRENT_TIMESTAMP - INTERVAL %s DAY
                    ''', (chat_id, user_id, days))

                    result = cursor.fetchone()
                    if result:
                        passed, created_at = result
                        logger.info(f"Проверка капчи за {days} дней для {user_id}: passed={passed}, created={created_at}")
                        return passed
                    else:
                        logger.info(f"Проверка капчи за {days} дней для {user_id}: запись не найдена или устарела")
                        return False
        except Exception as e:
            logger.error(f"Error checking recent captcha: {e}")
            return False

    def check_table_structure(self):
        """Проверка структуры таблицы chat_settings"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        SELECT column_name, data_type, column_default 
                        FROM information_schema.columns 
                        WHERE table_name = 'chat_settings' 
                        ORDER BY ordinal_position
                    ''')
                    columns = cursor.fetchall()
                    logger.info("Структура таблицы chat_settings:")
                    for column in columns:
                        logger.info(f"  {column[0]} ({column[1]}) - default: {column[2]}")
        except Exception as e:
            logger.error(f"Error checking table structure: {e}")
    
    def recreate_table_properly(self):
        """Полное пересоздание таблицы с правильной структурой"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Создаем временную таблицу с правильной структурой ВКЛЮЧАЯ новый столбец
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS chat_settings_temp (
                            chat_id BIGINT PRIMARY KEY,
                            welcome_message TEXT DEFAULT '👋 Добро пожаловать, {mention}! Рады видеть вас в {chat}!',
                            min_account_age_days INTEGER DEFAULT 1,
                            min_join_date_days INTEGER DEFAULT 0,
                            restrict_new_users BOOLEAN DEFAULT TRUE,
                            delete_service_messages BOOLEAN DEFAULT TRUE,
                            enabled BOOLEAN DEFAULT TRUE,
                            max_warnings INTEGER DEFAULT 3,
                            anti_flood_enabled BOOLEAN DEFAULT TRUE,
                            protect_comments BOOLEAN DEFAULT TRUE,
                            message_cooldown_enabled BOOLEAN DEFAULT FALSE,  -- ДОБАВЛЯЕМ НОВЫЙ СТОЛБЕЦ
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')

                    # Копируем данные из старой таблицы (если она существует)
                    try:
                        cursor.execute('''
                            INSERT INTO chat_settings_temp 
                            (chat_id, welcome_message, min_account_age_days, min_join_date_days, 
                             restrict_new_users, delete_service_messages, enabled, max_warnings, 
                             anti_flood_enabled, protect_comments, message_cooldown_enabled, created_at)
                            SELECT 
                                chat_id, 
                                welcome_message, 
                                min_account_age_days, 
                                min_join_date_days,
                                restrict_new_users, 
                                delete_service_messages, 
                                enabled, 
                                max_warnings,
                                anti_flood_enabled,
                                COALESCE(protect_comments, TRUE) as protect_comments,
                                COALESCE(message_cooldown_enabled, FALSE) as message_cooldown_enabled,  -- Новый столбец
                                COALESCE(created_at, CURRENT_TIMESTAMP) as created_at
                            FROM chat_settings
                        ''')
                        logger.info("Данные скопированы в временную таблицу")
                    except Exception as copy_error:
                        logger.info(f"Не удалось скопировать данные: {copy_error}")
                        # Продолжаем с пустой таблицей

                    # Удаляем старую таблицу
                    cursor.execute('DROP TABLE IF EXISTS chat_settings')

                    # Переименовываем временную таблицу
                    cursor.execute('ALTER TABLE chat_settings_temp RENAME TO chat_settings')

                    conn.commit()
                    logger.info("Таблица chat_settings пересоздана с правильной структурой")

        except Exception as e:
            logger.error(f"Error recreating table: {e}")
    
    def check_message_cooldown(self, chat_id: int, user_id: int, cooldown_seconds: int = 30) -> Tuple[bool, int]:
        """
        Проверка кд на отправку сообщений
        Возвращает (can_send, seconds_remaining)
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Удаляем старые записи (старше 1 дня)
                    cursor.execute(
                        'DELETE FROM message_cooldown WHERE last_message < CURRENT_TIMESTAMP - INTERVAL \'1 day\''
                    )
                    
                    # Проверяем последнее сообщение пользователя
                    cursor.execute('''
                        SELECT last_message FROM message_cooldown 
                        WHERE chat_id = %s AND user_id = %s
                    ''', (chat_id, user_id))
                    
                    result = cursor.fetchone()
                    
                    if result:
                        last_message_time = result[0]
                        time_diff = datetime.now().replace(tzinfo=None) - last_message_time.replace(tzinfo=None)
                        seconds_passed = time_diff.total_seconds()
                        
                        if seconds_passed < cooldown_seconds:
                            seconds_remaining = int(cooldown_seconds - seconds_passed)
                            return False, seconds_remaining
                    
                    # Обновляем время последнего сообщения
                    cursor.execute('''
                        INSERT INTO message_cooldown (chat_id, user_id, last_message)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (chat_id, user_id) DO UPDATE SET
                        last_message = CURRENT_TIMESTAMP
                    ''', (chat_id, user_id))
                    
                    conn.commit()
                    return True, 0
                    
        except Exception as e:
            logger.error(f"Error checking message cooldown: {e}")
            return True, 0

    def reset_user_cooldown(self, chat_id: int, user_id: int) -> None:
        """Сброс кд для пользователя"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        'DELETE FROM message_cooldown WHERE chat_id = %s AND user_id = %s',
                        (chat_id, user_id)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Error resetting user cooldown: {e}")
    
    def create_captcha(self, chat_id: int, user_id: int, message_id: int) -> bool:
        """Создание капчи для пользователя"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        INSERT INTO user_captcha (chat_id, user_id, captcha_message_id, expires_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '10 minutes')
                        ON CONFLICT (chat_id, user_id) DO UPDATE SET
                        captcha_passed = FALSE,
                        captcha_message_id = EXCLUDED.captcha_message_id,
                        attempts = 0,
                        expires_at = EXCLUDED.expires_at
                    ''', (chat_id, user_id, message_id))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Error creating captcha: {e}")
            return False

    def check_captcha_passed(self, chat_id: int, user_id: int) -> bool:
        """Проверка, прошел ли пользователь капчу"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Удаляем просроченные капчи
                    cursor.execute('DELETE FROM user_captcha WHERE expires_at < CURRENT_TIMESTAMP')

                    cursor.execute('''
                        SELECT captcha_passed FROM user_captcha 
                        WHERE chat_id = %s AND user_id = %s
                    ''', (chat_id, user_id))

                    result = cursor.fetchone()
                    return result[0] if result else False
        except Exception as e:
            logger.error(f"Error checking captcha: {e}")
            return False

    def mark_captcha_passed(self, chat_id: int, user_id: int) -> bool:
        """Отметка капчи как пройденной"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        UPDATE user_captcha 
                        SET captcha_passed = TRUE 
                        WHERE chat_id = %s AND user_id = %s
                    ''', (chat_id, user_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error marking captcha passed: {e}")
            return False

    def increment_captcha_attempts(self, chat_id: int, user_id: int) -> Tuple[bool, int]:
        """Увеличение счетчика попыток и проверка лимита"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        UPDATE user_captcha 
                        SET attempts = attempts + 1 
                        WHERE chat_id = %s AND user_id = %s
                        RETURNING attempts, max_attempts
                    ''', (chat_id, user_id))

                    result = cursor.fetchone()
                    conn.commit()

                    if result:
                        attempts, max_attempts = result
                        return attempts >= max_attempts, attempts
                    return False, 0
        except Exception as e:
            logger.error(f"Error incrementing captcha attempts: {e}")
            return False, 0

    def delete_captcha(self, chat_id: int, user_id: int) -> bool:
        """Удаление капчи пользователя"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        DELETE FROM user_captcha 
                        WHERE chat_id = %s AND user_id = %s
                    ''', (chat_id, user_id))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Error deleting captcha: {e}")
            return False

    def get_captcha_message_id(self, chat_id: int, user_id: int) -> Optional[int]:
        """Получение ID сообщения с капчей"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        SELECT captcha_message_id FROM user_captcha 
                        WHERE chat_id = %s AND user_id = %s
                    ''', (chat_id, user_id))

                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting captcha message ID: {e}")
            return None

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
            "🛡️ <b>Я - умный бот защиты от спама</b>\n\n"
            "✨ <b>Мои возможности:</b>\n"
            "• 🤖 Автоматическая модерация\n"
            "• ⏱️ Фильтр по возрасту аккаунтов\n" 
            "• 🌊 Защита от флуда\n"
            "• 👋 Умные приветствия\n"
            "• ⚠️ Система предупреждений\n"
            "• 🗑️ Очистка сервисных сообщений\n\n"
            "🚀 <b>Для начала работы:</b>\n"
            "1. Добавьте меня в группу\n"
            "2. Назначьте администратором\n"
            "3. Настройте через /menu\n\n"
            "💡 <b>Используйте /menu для удобного управления!</b>",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text(
            "🛡️ <b>Бот защиты активирован!</b>\n\n"
            "💫 Используйте /menu для удобной настройки параметров защиты",
            parse_mode=ParseMode.HTML
        )

async def safe_edit_message(
    context: ContextTypes.DEFAULT_TYPE, 
    chat_id: int, 
    message_id: int, 
    text: str, 
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """
    Безопасное редактирование сообщения с обработкой ошибок
    Возвращает True если успешно, False если ошибка
    """
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return True
    except Exception as e:
        if "Message is not modified" in str(e):
            # Это не ошибка, просто сообщение не изменилось
            logger.debug(f"Message {message_id} in chat {chat_id} was not modified (same content)")
            return True
        elif "Message to edit not found" in str(e):
            logger.warning(f"Message {message_id} not found in chat {chat_id}")
            return False
        else:
            logger.error(f"Error editing message {message_id} in chat {chat_id}: {e}")
            return False
    
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: Optional[int] = None, message_id: Optional[int] = None) -> None:
    """Главное меню бота - работает с командами и кнопками"""
    
    # Определяем источник вызова с безопасной проверкой
    query: Optional[CallbackQuery] = update.callback_query
    source_message: Optional[Message] = None
    chat: Optional[Chat] = None
    user: Optional[User] = None
    
    if query and query.message:
        # Вызов из кнопки
        source_message = query.message
        chat = source_message.chat
        user = query.from_user
    elif update.message:
        # Вызов из команды
        source_message = update.message
        chat = update.effective_chat
        user = update.effective_user
    
    # Безопасная проверка на None
    if not chat or not user:
        logger.error("Cannot determine chat or user from update")
        return
    
    # Устанавливаем параметры с проверкой на None
    final_chat_id = chat_id or chat.id
    final_message_id = message_id or (source_message.message_id if source_message else None)
    
    # Проверка прав администратора в группах
    if chat.type != 'private':  # chat гарантированно не None здесь
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ['administrator', 'creator']:
                error_msg = "❌ Доступ запрещен. Только для администраторов."
                if query:
                    await query.answer(error_msg, show_alert=True)
                elif source_message:
                    await source_message.reply_text(error_msg)
                return
        except Exception as e:
            logger.error(f"Error checking admin rights: {e}")
            # В случае ошибки проверки прав, все равно показываем меню
            # или обрабатываем ошибку в зависимости от требований
    
    try:
        settings_data = db.get_chat_settings(final_chat_id)
        if not settings_data:
            error_msg = "❌ Ошибка загрузки настроек"
            if query:
                await query.answer(error_msg, show_alert=True)
            elif source_message:
                await source_message.reply_text(error_msg)
            return
    except Exception as e:
        logger.error(f"Error getting chat settings: {e}")
        error_msg = "❌ Ошибка загрузки настроек"
        if query:
            await query.answer(error_msg, show_alert=True)
        elif source_message:
            await source_message.reply_text(error_msg)
        return
    
    # Главное меню
    keyboard = [
        [InlineKeyboardButton("🛡️ Статус защиты", callback_data="status")],
        [
            InlineKeyboardButton("⚙️ Основные настройки", callback_data="main_settings"),
            InlineKeyboardButton("👋 Приветствия", callback_data="welcome_settings")
        ],
        [
            InlineKeyboardButton("💬 Комментарии", callback_data="comments_settings"),
            InlineKeyboardButton("⏰ Ограничения", callback_data="cooldown_settings")  # Новая кнопка
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
            InlineKeyboardButton("❓ Помощь", callback_data="help_menu")
        ],
        [InlineKeyboardButton("🔧 Быстрые действия", callback_data="quick_actions")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_icon = "🟢" if settings_data['enabled'] else "🔴"
    
    # Безопасное получение названия чата
    chat_title = "Личные сообщения"
    if chat and hasattr(chat, 'title') and chat.title:
        chat_title = chat.title
    
    menu_text = (
        f"🎛️ <b>Главное меню защиты</b>\n\n"
        f"{status_icon} <b>Статус:</b> {'ВКЛЮЧЕН' if settings_data['enabled'] else 'ВЫКЛЮЧЕН'}\n"
        f"👥 <b>Чат:</b> {chat_title}\n\n"
        f"💫 <b>Выберите раздел для управления:</b>"
    )
    
    # Отправка/редактирование сообщения с безопасной проверкой
    try:
        if final_message_id and query:
            # Редактируем существующее сообщение
            await context.bot.edit_message_text(
                chat_id=final_chat_id,
                message_id=final_message_id,
                text=menu_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        elif source_message:
            # Отправляем новое сообщение
            await source_message.reply_text(
                menu_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        else:
            # Запасной вариант - отправляем в чат
            await context.bot.send_message(
                chat_id=final_chat_id,
                text=menu_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Error sending menu: {e}")
        # Последняя попытка отправить сообщение
        try:
            await context.bot.send_message(
                chat_id=final_chat_id,
                text=menu_text + "\n\n⚠️ <i>Не удалось обновить предыдущее сообщение</i>",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        except Exception as send_error:
            logger.error(f"Critical error sending menu: {send_error}")

async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Показать статус защиты"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Настроить", callback_data="main_settings")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("◀️ В главное меню", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Иконки статусов
    status_icon = "🟢" if settings_data['enabled'] else "🔴"
    age_icon = "✅" if settings_data['min_account_age_days'] > 0 else "❌"
    welcome_icon = "✅" if settings_data['welcome_message'] != '' else "❌"
    delete_icon = "✅" if settings_data['delete_service_messages'] else "❌"
    flood_icon = "✅" if settings_data['anti_flood_enabled'] else "❌"
    
    
    text = (
        f"🛡️ <b>Статус защиты</b>\n\n"
        f"{status_icon} <b>Общий статус:</b> {'ВКЛЮЧЕН' if settings_data['enabled'] else 'ВЫКЛЮЧЕН'}\n\n"
        
        f"<b>📊 Активные модули:</b>\n"
        f"{age_icon} Проверка возраста аккаунта: <b>{settings_data['min_account_age_days']} дн.</b>\n"
        f"{welcome_icon} Приветственные сообщения\n"
        f"{delete_icon} Удаление сервисных сообщений\n"
        f"{flood_icon} Защита от флуда\n"
        
        
        f"<b>⚙️ Дополнительные настройки:</b>\n"
        f"• Макс. предупреждений: <b>{settings_data['max_warnings']}</b>\n"
        f"• Ограничения новых пользователей: {'ВКЛ' if settings_data['restrict_new_users'] else 'ВЫКЛ'}\n\n"
        
        f"💡 <i>Используйте кнопки ниже для управления</i>"
    )
    
    if message_id:
        success = await safe_edit_message(context, chat_id, message_id, text, reply_markup)
        if not success:
            # Если не удалось отредактировать, отправляем новое сообщение
            await context.bot.send_message(
                chat_id=chat_id,
                text=text + "\n\n⚠️ <i>Не удалось обновить сообщение</i>",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_main_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Основные настройки"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [
            InlineKeyboardButton(f"{'🔴 Выкл' if settings_data['enabled'] else '🟢 Вкл'} бота", 
                               callback_data="toggle_enable"),
            InlineKeyboardButton("📅 Возраст аккаунта", callback_data="age_settings")
        ],
        [
            InlineKeyboardButton(f"{'✅' if settings_data['delete_service_messages'] else '❌'} Удаление сообщений", 
                               callback_data="toggle_service"),
            InlineKeyboardButton(f"{'✅' if settings_data['anti_flood_enabled'] else '❌'} Анти-флуд", 
                               callback_data="toggle_flood")
        ],
        [
            InlineKeyboardButton(f"{'✅' if settings_data.get('captcha_enabled', False) else '❌'} Капча", 
                               callback_data="captcha_settings"),
            InlineKeyboardButton("⚠️ Предупреждения", callback_data="warnings_settings")
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="main_menu"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Добавляем временную метку чтобы сообщение всегда было уникальным
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    text = (
        f"⚙️ <b>Основные настройки</b>\n\n"
        f"<b>Текущие параметры:</b>\n"
        f"• Статус бота: <b>{'ВКЛЮЧЕН' if settings_data['enabled'] else 'ВЫКЛЮЧЕН'}</b>\n"
        f"• Мин. возраст аккаунта: <b>{settings_data['min_account_age_days']} дн.</b>\n"
        f"• Удаление сообщений: <b>{'ВКЛ' if settings_data['delete_service_messages'] else 'ВЫКЛ'}</b>\n"
        f"• Анти-флуд: <b>{'ВКЛ' if settings_data['anti_flood_enabled'] else 'ВЫКЛ'}</b>\n"
        f"• Капча для новых: <b>{'ВКЛ' if settings_data.get('captcha_enabled', False) else 'ВЫКЛ'}</b>\n"
        f"• Макс. предупреждений: <b>{settings_data['max_warnings']}</b>\n\n"
        
        f"💡 <i>Выберите параметр для изменения</i>\n"
        f"<i>Обновлено: {timestamp}</i>"
    )
    
    if message_id:
        success = await safe_edit_message(context, chat_id, message_id, text, reply_markup)
        if not success:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_welcome_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Настройки приветствий"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить приветствие", callback_data="set_welcome")],
        [InlineKeyboardButton("👀 Посмотреть текущее", callback_data="view_welcome")],
        [InlineKeyboardButton("🔄 Сбросить к стандартному", callback_data="reset_welcome")],
        [InlineKeyboardButton("🏠 В главное", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_preview = settings_data['welcome_message'][:100] + "..." if len(settings_data['welcome_message']) > 100 else settings_data['welcome_message']
    
    text = (
        f"👋 <b>Настройки приветствий</b>\n\n"
        f"<b>Текущее приветствие:</b>\n"
        f"<code>{welcome_preview}</code>\n\n"
        
        f"<b>📝 Доступные переменные:</b>\n"
        f"• <code>{{name}}</code> - имя пользователя\n"
        f"• <code>{{mention}}</code> - упоминание\n"
        f"• <code>{{chat}}</code> - название чата\n"
        f"• <code>{{rules}}</code> - ссылка на правила\n\n"
        
        f"💡 <i>Пример: Добро пожаловать, {{mention}}! 🎉</i>"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_quick_actions(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Быстрые действия"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [
            InlineKeyboardButton("🟢 Включить всё", callback_data="enable_all"),
            InlineKeyboardButton("🔴 Выключить всё", callback_data="disable_all")
        ],
        [
            InlineKeyboardButton("🛡️ Стандартная защита", callback_data="standard_preset"),
            InlineKeyboardButton("🚫 Макс. защита", callback_data="max_preset")
        ],
        [
            InlineKeyboardButton("📊 Сброс статистики", callback_data="reset_stats"),
            InlineKeyboardButton("🔄 Перезагрузить бота", callback_data="reload_bot")
        ],
        [InlineKeyboardButton("◀️ В главное меню", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"🔧 <b>Быстрые действия</b>\n\n"
        f"💫 <b>Предустановки:</b>\n"
        f"• <b>Стандартная защита</b> - базовые настройки\n"
        f"• <b>Макс. защита</b> - строгий режим\n\n"
        
        f"⚡ <b>Быстрые команды:</b>\n"
        f"• Включить/выключить все модули\n"
        f"• Сброс статистики\n"
        f"• Перезагрузка бота\n\n"
        
        f"💡 <i>Выберите действие для быстрой настройки</i>"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_age_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Настройки возраста аккаунта"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [InlineKeyboardButton("0 дней - разрешить все", callback_data="age_0")],
        [InlineKeyboardButton("1 день - минимальная", callback_data="age_1")],
        [InlineKeyboardButton("3 дня - стандартная", callback_data="age_3")],
        [InlineKeyboardButton("7 дней - строгая", callback_data="age_7")],
        [InlineKeyboardButton("30 дней - максимальная", callback_data="age_30")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="main_settings"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_age = settings_data['min_account_age_days']
    age_description = {
        0: "🟢 Разрешить все аккаунты",
        1: "🟡 Минимальная защита", 
        3: "🟠 Стандартная защита",
        7: "🔴 Строгая защита",
        30: "🚫 Максимальная защита"
    }.get(current_age, "⚙️ Пользовательская настройка")
    
    text = (
        f"📅 <b>Настройки возраста аккаунта</b>\n\n"
        f"<b>Текущая настройка:</b>\n"
        f"• <b>{current_age} дней</b> - {age_description}\n\n"
        
        f"<b>💡 Рекомендации:</b>\n"
        f"• <b>0 дней</b> - для тестовых чатов\n"
        f"• <b>1-3 дня</b> - для обычных групп\n"
        f"• <b>7+ дней</b> - для важных чатов\n\n"
        
        f"<i>Выберите минимальный возраст аккаунта:</i>"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_warnings_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Настройки предупреждений"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [
            InlineKeyboardButton("➖", callback_data="decrease_warnings"),
            InlineKeyboardButton(f"Текущее: {settings_data['max_warnings']}", callback_data="noop"),
            InlineKeyboardButton("➕", callback_data="increase_warnings")
        ],
        [InlineKeyboardButton("⚡ Сбросить все варны", callback_data="reset_all_warnings")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="main_settings"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"⚠️ <b>Настройки предупреждений</b>\n\n"
        f"<b>Текущие настройки:</b>\n"
        f"• Макс. предупреждений: <b>{settings_data['max_warnings']}</b>\n\n"
        
        f"<b>💡 Как это работает:</b>\n"
        f"• Пользователь получает предупреждения за нарушения\n"
        f"• При достижении лимита - автоматический бан\n"
        f"• Рекомендуется: <b>3-5 предупреждений</b>\n\n"
        
        f"<i>Используйте кнопки для настройки:</i>"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Меню помощи"""
    keyboard = [
        [InlineKeyboardButton("📚 Команды бота", callback_data="bot_commands")],
        [InlineKeyboardButton("🛡️ Как настроить защиту", callback_data="setup_guide")],
        [InlineKeyboardButton("❓ Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton("📞 Поддержка", callback_data="support")],
        [
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"❓ <b>Помощь и поддержка</b>\n\n"
        f"💫 <b>Разделы помощи:</b>\n"
        f"• 📚 <b>Команды бота</b> - список всех команд\n"
        f"• 🛡️ <b>Настройка защиты</b> - руководство по настройке\n"
        f"• ❓ <b>Частые вопросы</b> - ответы на популярные вопросы\n"
        f"• 📞 <b>Поддержка</b> - связь с разработчиком\n\n"
        
        f"💡 <i>Выберите интересующий раздел:</i>"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Показать статистику"""
    stats_data: Dict[str, Any] = db.get_statistics(chat_id, days=7)
    
    # Получаем информацию о топ пользователях
    top_users_info: List[str] = []
    for user_id, count in stats_data.get('top_users', [])[:3]:
        try:
            user = await context.bot.get_chat_member(chat_id, user_id)
            name = user.user.first_name or f"User {user_id}"
            top_users_info.append(f"• {name}: {count} действий")
        except Exception:
            top_users_info.append(f"• User {user_id}: {count} действий")
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="stats")],
        [InlineKeyboardButton("📈 Детальная статистика", callback_data="detailed_stats")],
        [InlineKeyboardButton("🗑️ Сбросить статистику", callback_data="reset_stats_confirm")],
        [
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Форматируем статистику
    actions: Dict[str, int] = stats_data.get('actions', {})
    
    text = (
        f"📊 <b>Статистика защиты</b>\n\n"
        
        f"<b>📈 Активность за 7 дней:</b>\n"
        f"• 🔍 Проверено пользователей: <b>{actions.get('new_member', 0)}</b>\n"
        f"• 🚫 Заблокировано: <b>{actions.get('user_blocked', 0)}</b>\n"
        f"• 👋 Приветствий отправлено: <b>{actions.get('welcome_sent', 0)}</b>\n"
        f"• ⚠️ Предупреждений: <b>{stats_data.get('total_warnings', 0)}</b>\n"
        f"• 🗑️ Удалено сообщений: <b>{actions.get('service_message_deleted', 0)}</b>\n"
        f"• 📝 Всего действий: <b>{stats_data.get('total_actions', 0)}</b>\n\n"
        
        f"<b>📅 Сегодня:</b>\n"
        f"• Действий: <b>{stats_data.get('today_actions', 0)}</b>\n"
        f"• Новых пользователей: <b>{stats_data.get('today_new_users', 0)}</b>\n\n"
        
        f"<b>👥 Топ активные пользователи:</b>\n"
    )
    
    if top_users_info:
        text += "\n".join(top_users_info) + "\n\n"
    else:
        text += "• Нет данных\n\n"
        
    text += f"💡 <i>Статистика обновляется в реальном времени</i>"
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_detailed_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Показать детальную статистику"""
    detailed_stats: Dict[str, Any] = db.get_detailed_statistics(chat_id)
    
    keyboard = [
        [InlineKeyboardButton("📊 Основная статистика", callback_data="stats")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="detailed_stats")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="stats"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Форматируем детальную статистику
    all_time_text = ""
    for action, count in detailed_stats.get('all_time', [])[:10]:
        action_name = {
            'new_member': '👤 Новые участники',
            'user_blocked': '🚫 Блокировки',
            'welcome_sent': '👋 Приветствия',
            'service_message_deleted': '🗑️ Удаленные сообщения',
            'warning_issued': '⚠️ Предупреждения'
        }.get(action, action)
        all_time_text += f"• {action_name}: <b>{count}</b>\n"
    
    monthly_text = ""
    for month, count in detailed_stats.get('monthly', [])[:6]:
        month_name = datetime.strptime(month, '%Y-%m').strftime('%B %Y')
        monthly_text += f"• {month_name}: <b>{count}</b> действий\n"
    
    protection: Tuple[int, int, int] = detailed_stats.get('protection', (0, 0, 0))
    if protection[1] > 0:
        efficiency = (protection[0] / protection[1]) * 100
    else:
        efficiency = 0.0
    
    text = (
        f"📈 <b>Детальная статистика</b>\n\n"
        
        f"<b>🛡️ Эффективность защиты (30 дней):</b>\n"
        f"• Заблокировано спамеров: <b>{protection[0]}</b>\n"
        f"• Новых участников: <b>{protection[1]}</b>\n"
        f"• Эффективность: <b>{efficiency:.1f}%</b>\n\n"
        
        f"<b>📅 Активность по месяцам:</b>\n"
        f"{monthly_text or '• Нет данных'}\n"
        
        f"<b>🏆 Всего действий:</b>\n"
        f"{all_time_text or '• Нет данных'}\n"
        
        f"💡 <i>Подробная аналитика работы защиты</i>"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
        
async def show_reset_stats_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Подтверждение сброса статистики"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, сбросить", callback_data="reset_stats"),
            InlineKeyboardButton("❌ Отмена", callback_data="stats")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"🗑️ <b>Сброс статистики</b>\n\n"
        f"⚠️ <b>Внимание!</b>\n\n"
        f"Вы собираетесь сбросить всю статистику чата:\n"
        f"• История действий\n"
        f"• Предупреждения пользователей\n"
        f"• Вся аналитика\n\n"
        f"<b>Это действие нельзя отменить!</b>\n\n"
        f"Вы уверены, что хотите продолжить?"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
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
    
    # Навигация по меню
    if data == "main_menu":
        await menu(update, context, chat_id, message_id)
        return
    elif data == "status":
        await show_status(update, context, chat_id, message_id)
        return
    elif data == "main_settings":
        await show_main_settings(update, context, chat_id, message_id)
        return
    elif data == "welcome_settings":
        await show_welcome_settings(update, context, chat_id, message_id)
        return
    elif data == "quick_actions":
        await show_quick_actions(update, context, chat_id, message_id)
        return
    elif data == "age_settings":
        await show_age_settings(update, context, chat_id, message_id)
        return
    elif data == "warnings_settings":
        await show_warnings_settings(update, context, chat_id, message_id)
        return
    elif data == "help_menu":
        await show_help_menu(update, context, chat_id, message_id)
        return
    elif data == "stats":
        await show_stats(update, context, chat_id, message_id)
        return
    elif data == "detailed_stats":
        await show_detailed_stats(update, context, chat_id, message_id)
        return
    elif data == "reset_stats_confirm":
        await show_reset_stats_confirm(update, context, chat_id, message_id)
        return
    elif data == "reset_stats":
        db.reset_all_statistics(chat_id)
        await query.answer("✅ Статистика сброшена")
        await show_stats(update, context, chat_id, message_id)
        return
    elif data == "bot_commands":
        await show_bot_commands(update, context, chat_id, message_id)
        return
    elif data == "setup_guide":
        await show_setup_guide(update, context, chat_id, message_id)
        return
    elif data == "faq":
        await show_faq(update, context, chat_id, message_id)
        return
    elif data == "support":
        await show_support(update, context, chat_id, message_id)
        return
    elif data == "comments_settings":
        await show_comments_settings(update, context, chat_id, message_id)
        return
    elif data == "toggle_comments":
        logger.info(f"Обработка нажатия кнопки toggle_comments для чата {chat_id}")
        await toggle_comments_protection(update, context, chat_id, message_id)
        return
    elif data == "comments_stats":
        await show_comments_stats(update, context, chat_id, message_id)
        return
    elif data == "flood_settings":
        await show_flood_settings(update, context, chat_id, message_id)
        return
    elif data == "reset_flood_stats":
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('DELETE FROM flood_control WHERE chat_id = %s', (chat_id,))
                    conn.commit()
            await query.answer("✅ Статистика флуда сброшена")
            await show_flood_settings(update, context, chat_id, message_id)
        except Exception as e:
            logger.error(f"Error resetting flood stats: {e}")
            await query.answer("❌ Ошибка при сбросе статистики")
    elif data == "cooldown_settings":
        await show_cooldown_settings(update, context, chat_id, message_id)
        return
    elif data == "toggle_cooldown":
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            current_value = settings_data.get('message_cooldown_enabled', False)
            settings_data['message_cooldown_enabled'] = not current_value
            db.save_chat_settings(settings_data)
            status = "включено" if settings_data['message_cooldown_enabled'] else "выключено"
            await query.answer(f"✅ Ограничение сообщений {status}")
            await show_cooldown_settings(update, context, chat_id, message_id)
        return
    elif data == "reset_all_cooldowns":
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('DELETE FROM message_cooldown WHERE chat_id = %s', (chat_id,))
                    conn.commit()
            await query.answer("✅ Все ограничения сброшены")
            await show_cooldown_settings(update, context, chat_id, message_id)
        except Exception as e:
            logger.error(f"Error resetting cooldowns: {e}")
            await query.answer("❌ Ошибка при сбросе ограничений")
        return
    elif data == "captcha_settings":
        await show_captcha_settings(update, context, chat_id, message_id)
        return
    elif data == "toggle_captcha":
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            current_value = settings_data.get('captcha_enabled', False)
            logger.info(f"Текущее значение captcha_enabled: {current_value}")

            settings_data['captcha_enabled'] = not current_value
            logger.info(f"Новое значение captcha_enabled: {settings_data['captcha_enabled']}")

            # Принудительно сохраняем все настройки
            try:
                db.save_chat_settings(settings_data)
                logger.info("Настройки успешно сохранены")

                # Проверяем сохранение
                settings_after_save = db.get_chat_settings(chat_id)
                if settings_after_save:
                    logger.info(f"Проверка после сохранения - captcha_enabled: {settings_after_save.get('captcha_enabled')}")

                status = "включена" if settings_data['captcha_enabled'] else "выключена"
                await query.answer(f"✅ Капча {status}")

                # Добавляем небольшую задержку перед обновлением
                await asyncio.sleep(0.5)
                await show_captcha_settings(update, context, chat_id, message_id)

            except Exception as save_error:
                logger.error(f"Error saving captcha settings: {save_error}")
                await query.answer("❌ Ошибка при сохранении настроек", show_alert=True)
        return
    elif data == "captcha_policy_settings":
        await show_captcha_policy_settings(update, context, chat_id, message_id)
        return
    elif data.startswith("captcha_policy_"):
        policy = data.split("_")[2]  # persistent, time_based, always
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data['captcha_policy'] = policy
            db.save_chat_settings(settings_data)
            policy_names = {
                'persistent': 'Постоянная',
                'time_based': 'Временная', 
                'always': 'Всегда'
            }
            await query.answer(f"✅ Установлена политика: {policy_names.get(policy, policy)}")
            await show_captcha_policy_settings(update, context, chat_id, message_id)
        return
    elif data in ["increase_valid_days", "decrease_valid_days"]:
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            current_days = settings_data.get('captcha_valid_days', 30)
            if data == "increase_valid_days":
                new_days = min(365, current_days + 1)
            else:
                new_days = max(1, current_days - 1)

            settings_data['captcha_valid_days'] = new_days
            db.save_chat_settings(settings_data)
            await query.answer(f"✅ Срок действия: {new_days} дней")
            await show_captcha_policy_settings(update, context, chat_id, message_id)
        return
    elif data == "reset_all_warnings":
        # Сброс всех предупреждений в чате
        # Здесь должна быть логика сброса всех предупреждений
        # Например: db.reset_all_warnings(chat_id)
        await query.answer("✅ Все предупреждения сброшены")
        await show_warnings_settings(update, context, chat_id, message_id)
    
    # Основные действия
    elif data.startswith("age_"):
        days = int(data.split("_")[1])
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data['min_account_age_days'] = days
            db.save_chat_settings(settings_data)
            await query.answer(f"✅ Установлен возраст: {days} дней")
            await show_age_settings(update, context, chat_id, message_id)
    
    elif data.startswith("toggle_"):
        settings_data = db.get_chat_settings(chat_id)
        if not settings_data:
            return
            
        # Инициализируем переменную status_text
        status_text = ""
        if data == "toggle_enable":
            settings_data['enabled'] = not settings_data['enabled']
            status_text = "включен" if settings_data['enabled'] else "выключен"
        elif data == "toggle_service":
            settings_data['delete_service_messages'] = not settings_data['delete_service_messages']
            status_text = "включено" if settings_data['delete_service_messages'] else "выключено"
        elif data == "toggle_flood":
            settings_data['anti_flood_enabled'] = not settings_data['anti_flood_enabled']
            status_text = "включена" if settings_data['anti_flood_enabled'] else "выключена"
        elif data == "toggle_restrict":
            settings_data['restrict_new_users'] = not settings_data['restrict_new_users']
            status_text = "включены" if settings_data['restrict_new_users'] else "выключены"
        
                
        db.save_chat_settings(settings_data)
        await query.answer(f"✅ Тихий режим {status_text}")
        await show_main_settings(update, context, chat_id, message_id)
    
    elif data in ["increase_warnings", "decrease_warnings"]:
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            if data == "increase_warnings":
                settings_data['max_warnings'] = min(10, settings_data['max_warnings'] + 1)
            else:
                settings_data['max_warnings'] = max(1, settings_data['max_warnings'] - 1)
                
            db.save_chat_settings(settings_data)
            await query.answer(f"✅ Установлено: {settings_data['max_warnings']} предупреждений")
            await show_warnings_settings(update, context, chat_id, message_id)
    
    elif data == "set_welcome":
        await query.edit_message_text(
            "✏️ <b>Введите новое приветственное сообщение:</b>\n\n"
            "<i>Доступные переменные:</i>\n"
            "<code>{name}</code> - имя пользователя\n"
            "<code>{mention}</code> - упоминание\n"
            "<code>{chat}</code> - название чата\n"
            "<code>{rules}</code> - ссылка на правила\n\n"
            "<i>Пример:</i> <code>Добро пожаловать, {mention}! 🎉 Ознакомься с {rules}.</code>\n\n"
            "💡 <i>Отправьте новое сообщение в чат:</i>",
            parse_mode=ParseMode.HTML
        )
        if context.user_data is not None:
            context.user_data['awaiting_welcome'] = True
            context.user_data['settings_message_id'] = message_id
    
    elif data == "view_welcome":
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            await query.answer(f"📝 Текущее приветствие: {settings_data['welcome_message']}", show_alert=True)
    
    elif data == "reset_welcome":
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data['welcome_message'] = '👋 Добро пожаловать, {mention}! Рады видеть вас в {chat}!'
            db.save_chat_settings(settings_data)
            await query.answer("✅ Приветствие сброшено к стандартному")
            await show_welcome_settings(update, context, chat_id, message_id)
    
    elif data == "noop":
        await query.answer()
    
    # Быстрые действия
    elif data == "enable_all":
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data.update({
                'enabled': True,
                'restrict_new_users': True,
                'delete_service_messages': True,
                'anti_flood_enabled': True
            })
            db.save_chat_settings(settings_data)
            await query.answer("✅ Все модули включены")
            await show_quick_actions(update, context, chat_id, message_id)
    
    elif data == "disable_all":
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data.update({
                'enabled': False,
                'restrict_new_users': False,
                'delete_service_messages': False,
                'anti_flood_enabled': False
            })
            db.save_chat_settings(settings_data)
            await query.answer("✅ Все модули выключены")
            await show_quick_actions(update, context, chat_id, message_id)
    
    elif data == "standard_preset":
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data.update({
                'enabled': True,
                'min_account_age_days': 1,
                'restrict_new_users': True,
                'delete_service_messages': True,
                'anti_flood_enabled': True,
                'max_warnings': 3
            })
            db.save_chat_settings(settings_data)
            await query.answer("✅ Установлена стандартная защита")
            await show_quick_actions(update, context, chat_id, message_id)
    
    elif data == "max_preset":
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data.update({
                'enabled': True,
                'min_account_age_days': 7,
                'restrict_new_users': True,
                'delete_service_messages': True,
                'anti_flood_enabled': True,
                'max_warnings': 2
            })
            db.save_chat_settings(settings_data)
            await query.answer("✅ Установлена максимальная защита")
            await show_quick_actions(update, context, chat_id, message_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    message = update.message
    chat = update.effective_chat
    
    if not message or not chat or not context.user_data:
        return
        
    if 'awaiting_welcome' in context.user_data and context.user_data['awaiting_welcome']:
        chat_id = chat.id
        welcome_message = message.text
        
        if not welcome_message:
            return
            
        settings_data = db.get_chat_settings(chat_id)
        if settings_data:
            settings_data['welcome_message'] = welcome_message
            db.save_chat_settings(settings_data)
            
            del context.user_data['awaiting_welcome']
            message_id = context.user_data.get('settings_message_id')
            if 'settings_message_id' in context.user_data:
                del context.user_data['settings_message_id']
                
            await message.reply_text("✅ Приветственное сообщение обновлено!")
            
            # Возвращаемся к меню настроек приветствий
            if message_id:
                await show_welcome_settings(update, context, chat_id, message_id)

def should_show_captcha(chat_id: int, user_id: int) -> bool:
        """Определяет, нужно ли показывать капчу пользователю"""
        try:
            settings = db.get_chat_settings(chat_id)

            if not settings or not settings.get('captcha_enabled', False):
                return False

            policy = settings.get('captcha_policy', CaptchaPolicy.PERSISTENT)

            if policy == CaptchaPolicy.ALWAYS:
                logger.info(f"Политика ALWAYS: показываем капчу пользователю {user_id}")
                return True
            elif policy == CaptchaPolicy.TIME_BASED:
                days_valid = settings.get('captcha_valid_days', 30)
                captcha_passed = db.check_captcha_passed_recently(chat_id, user_id, days_valid)
                logger.info(f"Политика TIME_BASED ({days_valid} дней): пользователь {user_id} прошел капчу: {not captcha_passed}")
                return not captcha_passed
            else:  # PERSISTENT
                captcha_passed = db.check_captcha_passed(chat_id, user_id)
                logger.info(f"Политика PERSISTENT: пользователь {user_id} прошел капчу: {not captcha_passed}")
                return not captcha_passed

        except Exception as e:
            logger.error(f"Error in should_show_captcha: {e}")
            return True  # В случае ошибки показываем капчу для безопасности
                
async def new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик новых участников с улучшенной логикой капчи"""
    chat = update.effective_chat
    message = update.message
    
    if not chat or not message:
        return
        
    settings_data = db.get_chat_settings(chat.id)
    if not settings_data or not settings_data['enabled']:
        return
    
    for member in message.new_chat_members:
        if not member:
            continue
            
        # Пропускаем самого бота
        if member.id == context.bot.id:
            continue
            
        # Логируем нового участника
        db.log_action(chat.id, member.id, 'new_member', f'username: {member.username}')
            
        # Проверка возраста аккаунта
        if settings_data['min_account_age_days'] > 0:
            member_date = getattr(member, 'date', None)
            if member_date:
                account_age_delta = datetime.now().replace(tzinfo=None) - member_date.replace(tzinfo=None)
                account_age_days = account_age_delta.days
                
                if account_age_days < settings_data['min_account_age_days']:
                    try:
                        await context.bot.ban_chat_member(chat.id, member.id)
                        await context.bot.unban_chat_member(chat.id, member.id)
                        db.log_action(chat.id, member.id, 'user_blocked', f'young_account_{account_age_days}days')
                        logger.info(f"Kicked user {member.id} for young account")
                        continue
                    except Exception as e:
                        logger.error(f"Error kicking user: {e}")
        
        # Улучшенная проверка капчи с использованием политик
        captcha_enabled = settings_data.get('captcha_enabled', False)
        logger.info(f"КАПЧА ДЛЯ ПОЛЬЗОВАТЕЛЯ {member.id}: {captcha_enabled}")
        
        if captcha_enabled:
            user_name = member.first_name or 'Пользователь'
            
            # Используем новую функцию для определения необходимости капчи
            should_show = should_show_captcha(chat.id, member.id)
            
            if should_show:
                logger.info(f"Пользователь {member.id} должен пройти капчу (политика: {settings_data.get('captcha_policy', 'persistent')})")
                await send_captcha(update, context, chat.id, member.id, user_name)
            else:
                logger.info(f"Пользователь {member.id} уже прошел капчу или не требует проверки")
                # Отправляем стандартное приветствие
                if settings_data['welcome_message']:
                    await send_welcome_message(chat, member, settings_data, context)
        else:
            # Если капча отключена, отправляем стандартное приветствие
            if settings_data['welcome_message']:
                await send_welcome_message(chat, member, settings_data, context)
    
    # Удаление сервисного сообщения (если включено в настройках)
    if settings_data['delete_service_messages']:
        try:
            await message.delete()
            db.log_action(chat.id, None, 'service_message_deleted')
        except Exception as e:
            logger.error(f"Error deleting service message: {e}")
            
async def send_welcome_message(chat: Chat, member: User, settings_data: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка стандартного приветственного сообщения"""
    if settings_data['welcome_message']:
        welcome_text = settings_data['welcome_message']
        
        user_name = member.first_name or 'Пользователь'
        user_mention = f'<a href="tg://user?id={member.id}">{user_name}</a>'
        chat_title = chat.title or 'чат'
        
        welcome_text = welcome_text.replace('{name}', user_name)
        welcome_text = welcome_text.replace('{mention}', user_mention)
        welcome_text = welcome_text.replace('{chat}', chat_title)
        welcome_text = welcome_text.replace('{rules}', 'правилами')
        
        try:
            await context.bot.send_message(
                chat.id,
                welcome_text,
                parse_mode=ParseMode.HTML
            )
            db.log_action(chat.id, member.id, 'welcome_sent')
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

async def check_db(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для проверки структуры базы данных"""
    chat = update.effective_chat
    message = update.message
    
    if not chat or not message:
        return
        
    try:
        # Принудительное обновление схемы
        db.update_database_schema()
        
        # Проверка структуры таблицы
        db.check_table_structure()
        
        # Проверка настроек текущего чата
        settings = db.get_chat_settings(chat.id)
        
        response = (
            "✅ <b>Проверка базы данных завершена</b>\n\n"
            f"🆔 ID чата: <code>{chat.id}</code>\n"
            f"🛡️ Защита включена: <b>{settings['enabled']}</b>\n"
            f"🤖 Капча включена: <b>{settings.get('captcha_enabled', False)}</b>\n"
            f"💬 Защита комментариев: <b>{settings.get('protect_comments', True)}</b>\n\n"
            "📊 <i>Подробности в логах бота</i>"
        )
        
        await message.reply_text(response, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error checking database: {e}")
        await message.reply_text("❌ Ошибка при проверке базы данных")

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
🛡️ <b>Команды бота защиты</b>

🎛️ <b>Основные команды:</b>
/menu - Главное меню управления
/settings - Быстрые настройки
/status - Статус защиты
/enable - Включить бота
/disable - Выключить бота

💫 <b>Удобное управление:</b>
• Используйте /menu для полного контроля
• Настройте защиту в несколько кликов
• Просматривайте статистику в реальном времени

🚀 <b>Добавьте бота в группу и назначьте администратором!</b>
    """
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    # Безопасное логирование дополнительной информации с правильной типизацией
    try:
        # Приводим update к правильному типу для проверки атрибутов
        from telegram import Update
        if isinstance(update, Update):
            if update.callback_query and update.callback_query.data:
                logger.error(f"Callback data: {update.callback_query.data}")
            if update.message and update.message.text:
                logger.error(f"Message text: {update.message.text}")
        else:
            # Для объекта типа object используем безопасные проверки
            update_dict = update.__dict__ if hasattr(update, '__dict__') else {}
            if 'callback_query' in update_dict:
                callback_data = getattr(update_dict['callback_query'], 'data', 'N/A')
                logger.error(f"Callback data: {callback_data}")
            if 'message' in update_dict:
                message_text = getattr(update_dict['message'], 'text', 'N/A')
                logger.error(f"Message text: {message_text}")
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

async def show_captcha_policy_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Настройки политик капчи"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    current_policy = settings_data.get('captcha_policy', 'persistent')
    valid_days = settings_data.get('captcha_valid_days', 30)
    
    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 Постоянная" + (" ✅" if current_policy == CaptchaPolicy.PERSISTENT else ""), 
                callback_data="captcha_policy_persistent"
            )
        ],
        [
            InlineKeyboardButton(
                "⏰ Временная" + (" ✅" if current_policy == CaptchaPolicy.TIME_BASED else ""), 
                callback_data="captcha_policy_time_based"
            )
        ],
        [
            InlineKeyboardButton(
                "🚫 Всегда" + (" ✅" if current_policy == CaptchaPolicy.ALWAYS else ""), 
                callback_data="captcha_policy_always"
            )
        ],
        [
            InlineKeyboardButton("➖ Дни", callback_data="decrease_valid_days"),
            InlineKeyboardButton(f"Действует: {valid_days} дн.", callback_data="noop"),
            InlineKeyboardButton("➕ Дни", callback_data="increase_valid_days")
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="captcha_settings"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    policy_descriptions = {
        CaptchaPolicy.PERSISTENT: "✅ <b>Постоянная верификация</b>\n• Пользователь проходит капчу один раз\n• При повторном входе капча не требуется\n• <i>Рекомендуется для большинства чатов</i>",
        CaptchaPolicy.TIME_BASED: "⏰ <b>Временная верификация</b>\n• Капча действует ограниченное время\n• После истечения срока - повторная проверка\n• <i>Для чатов с повышенной безопасностью</i>",
        CaptchaPolicy.ALWAYS: "🚫 <b>Всегда показывать капчу</b>\n• Капча при каждом входе в чат\n• Максимальная безопасность\n• <i>Может раздражать пользователей</i>"
    }
    
    text = (
        f"🎛️ <b>Настройки политики капчи</b>\n\n"
        f"{policy_descriptions.get(current_policy, '')}\n\n"
        
        f"<b>Текущая политика:</b> <code>{current_policy}</code>\n"
        f"<b>Срок действия:</b> <code>{valid_days} дней</code>\n\n"
        
        f"💡 <i>Выберите политику проверки пользователей:</i>"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_bot_commands(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Показать список команд бота"""
    keyboard = [
        [InlineKeyboardButton("◀️ Назад в помощь", callback_data="help_menu")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📚 <b>Команды бота защиты</b>\n\n"
        
        "🎛️ <b>Основные команды:</b>\n"
        "• <code>/start</code> - Запуск бота и информация\n"
        "• <code>/menu</code> - Главное меню управления\n"
        "• <code>/settings</code> - Быстрые настройки\n"
        "• <code>/status</code> - Статус защиты\n"
        "• <code>/help</code> - Справка по командам\n\n"
        
        "⚙️ <b>Управление защитой:</b>\n"
        "• <code>/enable</code> - Включить бота\n"
        "• <code>/disable</code> - Выключить бота\n"
        "• <code>/stats</code> - Показать статистику\n\n"
        
        "🛡️ <b>Модерация:</b>\n"
        "• <code>/warn</code> [ответ на сообщение] - Выдать предупреждение\n"
        "• <code>/unwarn</code> [ответ на сообщение] - Снять предупреждение\n"
        "• <code>/warnings</code> [@username] - Проверить предупреждения\n\n"
        
        "💡 <b>Совет:</b> Используйте <code>/menu</code> для удобного графического управления!\n\n"
        
        "🚀 <b>Бот должен быть администратором с правами:</b>\n"
        "• Блокировка пользователей\n"
        "• Удаление сообщений\n"
        "• Приглашение пользователей\n"
        "• Закрепление сообщений"
    )
    
    if message_id:
        await safe_edit_message(context, chat_id, message_id, text, reply_markup)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_setup_guide(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Руководство по настройке защиты"""
    keyboard = [
        [
            InlineKeyboardButton("🛡️ Стандартная настройка", callback_data="standard_preset"),
            InlineKeyboardButton("🚫 Макс. защита", callback_data="max_preset")
        ],
        [InlineKeyboardButton("◀️ Назад в помощь", callback_data="help_menu")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    bot_username = getattr(context.bot, 'username', 'your_bot_username')
    
    text = (
        "🛡️ <b>Руководство по настройке защиты</b>\n\n"
        
        "📋 <b>Шаг 1: Добавление бота</b>\n"
        "1. Добавьте @{} в группу\n"
        "2. Назначьте администратором\n"
        "3. Выдайте все необходимые права\n\n"
        
        "⚙️ <b>Шаг 2: Базовая настройка</b>\n"
        "• Используйте <code>/menu</code> для входа в панель управления\n"
        "• Включите нужные модули защиты\n"
        "• Настройте приветственные сообщения\n\n"
        
        "🛡️ <b>Шаг 3: Настройка фильтров</b>\n\n"
        
        "🔒 <b>Возраст аккаунтов:</b>\n"
        "• <b>0 дней</b> - отключена проверка (не рекомендуется)\n"
        "• <b>1 день</b> - минимальная защита от ботов\n"
        "• <b>3 дня</b> - стандартная защита\n"
        "• <b>7+ дней</b> - строгая защита\n\n"
        
        "⚠️ <b>Система предупреждений:</b>\n"
        "• Установите лимит предупреждений (3-5)\n"
        "• При достижении лимита - автоматический бан\n"
        "• Используйте команду <code>/warn</code> для модерации\n\n"
        
        "🌊 <b>Защита от флуда:</b>\n"
        "• Автоматическое обнаружение спама\n"
        "• Блокировка массовых сообщений\n"
        "• Защита от повторяющегося контента\n\n"
        
        "👋 <b>Приветственные сообщения:</b>\n"
        "• Настройте текст приветствия\n"
        "• Используйте переменные: {{name}}, {{mention}}, {{chat}}\n"
        "• Добавьте ссылку на правила {{rules}}\n\n"
        
        "💡 <b>Рекомендуемые настройки:</b>\n"
        "• Возраст аккаунта: 1-3 дня\n"
        "• Лимит предупреждений: 3\n"
        "• Все модули защиты: ВКЛ\n"
        "• Удаление сервисных сообщений: ВКЛ"
    ).format(bot_username)
    
    if message_id:
        await safe_edit_message(context, chat_id, message_id, text, reply_markup)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Часто задаваемые вопросы"""
    keyboard = [
        [InlineKeyboardButton("◀️ Назад в помощь", callback_data="help_menu")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "❓ <b>Часто задаваемые вопросы</b>\n\n"
        
        "🔧 <b>Вопрос: Бот не работает в группе</b>\n"
        "✅ <b>Решение:</b>\n"
        "• Проверьте, что бот добавлен как администратор\n"
        "• Убедитесь, что выданы все необходимые права\n"
        "• Проверьте, что защита включена в /menu\n\n"
        
        "👤 <b>Вопрос: Новые пользователи блокируются</b>\n"
        "✅ <b>Решение:</b>\n"
        "• Проверьте настройки возраста аккаунта\n"
        "• Уменьшите минимальный возраст если нужно\n"
        "• Исключите чат из проверки если необходимо\n\n"
        
        "💬 <b>Вопрос: Приветственные сообщения не отправляются</b>\n"
        "✅ <b>Решение:</b>\n"
        "• Проверьте настройки приветствий в /menu\n"
        "• Убедитесь, что бот может отправлять сообщения\n"
        "• Проверьте, не превышен ли лимит символов\n\n"
        
        "⚠️ <b>Вопрос: Система предупреждений не работает</b>\n"
        "✅ <b>Решение:</b>\n"
        "• Проверьте настройки предупреждений\n"
        "• Убедитесь, что бот может банить пользователей\n"
        "• Используйте команду /warn [ответ на сообщение]\n\n"
        
        "📊 <b>Вопрос: Статистика не отображается</b>\n"
        "✅ <b>Решение:</b>\n"
        "• Подождите накопления данных (1-2 дня)\n"
        "• Проверьте, что бот активен в чате\n"
        "• Убедитесь, что логирование включено\n\n"
        
        "🔄 <b>Вопрос: Как сбросить настройки?</b>\n"
        "✅ <b>Решение:</b>\n"
        "• Используйте кнопку 'Сбросить к стандартному' в настройках\n"
        "• Или настройте параметры вручную через /menu\n\n"
        
        "🚫 <b>Вопрос: Бот блокирует легитимных пользователей</b>\n"
        "✅ <b>Решение:</b>\n"
        "• Уменьшите строгость фильтров\n"
        "• Отключите проверку возраста если нужно\n"
        "• Добавьте исключения для доверенных пользователей\n\n"
        
        "💡 <b>Нужна дополнительная помощь?</b>\n"
        "Нажмите кнопку 'Поддержка' для связи с разработчиком"
    )
    
    if message_id:
        await safe_edit_message(context, chat_id, message_id, text, reply_markup)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Информация о поддержке"""
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад в помощь", callback_data="help_menu"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    support_info = (
        "🤝 <b>Поддержка и обратная связь</b>\n\n"
        
        "📞 <b>Связь с разработчиком:</b>\n"
        "• По вопросам работы бота\n"
        "• Предложения по улучшению\n"
        "• Сообщения об ошибках\n"
        "• Техническая поддержка\n\n"
        
        "💬 <b>Каналы связи:</b>\n"
        "• <b>Telegram:</b> @username_разработчика\n"
        "• <b>Email:</b> developer@example.com\n"
        "• <b>GitHub:</b> github.com/username/project\n\n"
        
        "🛠️ <b>Перед обращением проверьте:</b>\n"
        "✅ Бот добавлен как администратор\n"
        "✅ Выданы все необходимые права\n"
        "✅ Защита включена в настройках\n"
        "✅ Прочитаны ответы в разделе FAQ\n\n"
        
        "📋 <b>При обращении укажите:</b>\n"
        "• ID чата (можно получить через /info)\n"
        "• Описание проблемы\n"
        "• Скриншоты если возможно\n"
        "• Шаги для воспроизведения\n\n"
        
        "⏱️ <b>Время ответа:</b>\n"
        "• Обычно в течение 24 часов\n"
        "• Срочные вопросы - быстрее\n"
        "• Выходные - могут быть задержки\n\n"
        
        "❤️ <b>Бот распространяется бесплатно</b>\n"
        "Поддержка развития приветствуется!"
    )
    
    # Замените контактные данные на реальные
    support_text = support_info.replace("@username_разработчика", "@Akula_Iv").replace("developer@example.com", "ivanakulin175@gmail.com").replace("github.com/username/project", "github.com/AkulinIvan/TelegramBotAntiSpam")
    
    if message_id:
        await safe_edit_message(context, chat_id, message_id, support_text, reply_markup)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=support_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /info - информация о чате"""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    
    if not chat or not user or not message:
        return
        
    chat_info = (
        f"📋 <b>Информация о чате</b>\n\n"
        f"🆔 <b>ID чата:</b> <code>{chat.id}</code>\n"
        f"👥 <b>Тип:</b> {chat.type}\n"
        f"📛 <b>Название:</b> {chat.title if hasattr(chat, 'title') else 'Личные сообщения'}\n\n"
        f"👤 <b>Ваш ID:</b> <code>{user.id}</code>\n"
        f"📛 <b>Ваше имя:</b> {user.first_name or 'Не указано'}\n"
        f"🔗 <b>Username:</b> @{user.username if user.username else 'Не указан'}\n\n"
        f"💡 <b>Эта информация может понадобиться для поддержки</b>"
    )
    
    await message.reply_text(chat_info, parse_mode=ParseMode.HTML)

async def handle_comments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ВСЕХ текстовых сообщений (комментариев и обычных сообщений)"""
    try:
        message = update.message
        if not message:
            return

        chat = update.effective_chat
        if not chat:
            return

        chat_id = message.chat_id
        user_id = message.from_user.id

        if context.user_data and context.user_data.get('awaiting_welcome'):
            welcome_message = message.text
            if welcome_message:
                settings_data = db.get_chat_settings(chat_id)
                if settings_data:
                    settings_data['welcome_message'] = welcome_message
                    db.save_chat_settings(settings_data)
                    
                    del context.user_data['awaiting_welcome']
                    message_id = context.user_data.get('settings_message_id')
                    if 'settings_message_id' in context.user_data:
                        del context.user_data['settings_message_id']
                        
                    await message.reply_text("✅ Приветственное сообщение обновлено!")
                    
                    # Возвращаемся к меню настроек приветствий
                    if message_id:
                        await show_welcome_settings(update, context, chat_id, message_id)
            return

        settings = db.get_chat_settings(chat_id)
        if not settings or not settings['enabled']:
            return

        # Проверка капчи (если включена)
        if settings.get('captcha_enabled', False):
            captcha_passed = db.check_captcha_passed(chat_id, user_id)
            if not captcha_passed:
                try:
                    await message.delete()
                    # Отправляем напоминание о капче
                    reminder_msg = await message.reply_text(
                        f"⏳ <b>Пройдите проверку безопасности!</b>\n\n"
                        f"Чтобы писать сообщения, сначала подтвердите, что вы не бот.",
                        reply_to_message_id=message.message_id
                    )
                    # Удаляем напоминание через 5 секунд
                    await asyncio.sleep(5)
                    await reminder_msg.delete()
                    return
                except Exception as e:
                    logger.error(f"Error handling captcha check: {e}")
                    return
        
        # Проверка ограничения частоты сообщений (для всех сообщений)
        if settings.get('message_cooldown_enabled', False):
            can_send, seconds_remaining = db.check_message_cooldown(chat_id, user_id, 30)
            if not can_send:
                try:
                    await message.delete()
                    warning_msg = await message.reply_text(
                        f"⏰ Слишком часто! Отправляйте сообщения не чаще 1 раза в 30 секунд.\n"
                        f"Попробуйте через {seconds_remaining} сек.",
                        reply_to_message_id=message.message_id
                    )
                    # Удаляем предупреждение через 5 секунд
                    await asyncio.sleep(5)
                    await warning_msg.delete()
                    return
                except Exception as e:
                    logger.error(f"Error handling message cooldown: {e}")
                    return
        
        # Проверяем, является ли сообщение комментарием
        is_comment = False
        
        # Способ 1: Проверка через message_thread_id (для топиков/форумов)
        if hasattr(message, 'message_thread_id') and message.message_thread_id is not None:
            is_comment = True
            logger.info(f"Обнаружен комментарий через message_thread_id: {message.message_thread_id}")
            
        # Способ 2: Проверка, является ли это ответом в обсуждении
        elif (message.reply_to_message and 
              hasattr(message.reply_to_message, 'message_thread_id') and 
              message.reply_to_message.message_thread_id is not None):
            is_comment = True
            logger.info(f"Обнаружен комментарий через reply в топике")
            
        # Способ 3: Проверка специальных атрибутов для комментариев
        elif hasattr(message, 'is_topic_message') and message.is_topic_message:
            is_comment = True
            logger.info(f"Обнаружен комментарий через is_topic_message")
            
        # Способ 4: Проверка для форумов (специальный тип чата)
        elif hasattr(chat, 'type') and chat.type == 'supergroup' and hasattr(chat, 'is_forum') and chat.is_forum:
            is_comment = True
            logger.info(f"Обнаружен комментарий в форуме")
        
        settings = db.get_chat_settings(chat_id)
        if not settings or not settings['enabled']:
            return
            
        # Если это комментарий, проверяем включена ли защита комментариев
        if is_comment and not settings.get('protect_comments', True):
            return
        
        # Логируем действие
        action_type = 'comment_posted' if is_comment else 'message_posted'
        db.log_action(chat_id, user_id, action_type, f'text: {message.text[:100] if message.text else "no text"}')
        
        # Проверка возраста аккаунта (только для комментариев)
        if is_comment and settings['min_account_age_days'] > 0:
            user_created = message.from_user.date
            if user_created:
                account_age = (datetime.now().replace(tzinfo=None) - user_created.replace(tzinfo=None)).days
                if account_age < settings['min_account_age_days']:
                    try:
                        await message.delete()
                        db.log_action(chat_id, user_id, 'comment_deleted', f'young_account_{account_age}days')
                        
                        # Отправляем предупреждение
                        warning_msg = await message.reply_text(
                            f"❌ Комментарий удален. Аккаунт должен быть старше {settings['min_account_age_days']} дней.",
                            reply_to_message_id=message.message_id
                        )
                        
                        # Удаляем предупреждение через 5 секунд
                        await asyncio.sleep(5)
                        await warning_msg.delete()
                        
                        return
                    except Exception as e:
                        logger.error(f"Error deleting comment from young account: {e}")
        
        # Проверка флуд-контроля (для всех сообщений)
        if settings['anti_flood_enabled']:
            is_flood = db.check_flood_control(chat_id, user_id)
            if is_flood:
                try:
                    await message.delete()
                    action_deleted = 'comment_deleted' if is_comment else 'message_deleted'
                    db.log_action(chat_id, user_id, action_deleted, 'flood_detected')
                    
                    # Добавляем предупреждение
                    warnings_count = db.add_user_warning(chat_id, user_id)
                    
                    flood_msg = await message.reply_text(
                        f"⚠️ Флуд-контроль! Предупреждение {warnings_count}/{settings['max_warnings']}",
                        reply_to_message_id=message.message_id
                    )
                    
                    # Проверяем лимит предупреждений
                    if warnings_count >= settings['max_warnings']:
                        try:
                            await context.bot.ban_chat_member(chat_id, user_id)
                            await context.bot.unban_chat_member(chat_id, user_id)
                            ban_type = 'max_warnings_comments' if is_comment else 'max_warnings_messages'
                            db.log_action(chat_id, user_id, 'user_banned', ban_type)
                            
                            ban_msg = await message.reply_text(
                                "🚫 Пользователь забанен за превышение лимита предупреждений",
                                reply_to_message_id=message.message_id
                            )
                            await asyncio.sleep(10)
                            await ban_msg.delete()
                        except Exception as e:
                            logger.error(f"Error banning user for flood: {e}")
                    
                    await asyncio.sleep(5)
                    await flood_msg.delete()
                    return
                    
                except Exception as e:
                    logger.error(f"Error handling flood: {e}")
        
        # Проверка на спам-слова (только для комментариев)
        if is_comment and message.text:
            spam_keywords = ["http://", "https://", "купить", "заказать", "скидка", "распродажа"]
            if any(keyword in message.text.lower() for keyword in spam_keywords):
                # Проверяем возраст аккаунта для ссылок
                user_created = message.from_user.date
                if user_created:
                    account_age = (datetime.now().replace(tzinfo=None) - user_created.replace(tzinfo=None)).days
                    if account_age < 7:  # Строгая проверка для ссылок
                        try:
                            await message.delete()
                            db.log_action(chat_id, user_id, 'comment_deleted', 'spam_link_detected')
                            
                            spam_msg = await message.reply_text(
                                "❌ Ссылки запрещены для новых аккаунтов",
                                reply_to_message_id=message.message_id
                            )
                            await asyncio.sleep(5)
                            await spam_msg.delete()
                            return
                        except Exception as e:
                            logger.error(f"Error deleting spam comment: {e}")
                        
    except Exception as e:
        logger.error(f"Error in handle_comments: {e}")

async def show_flood_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Настройки флуд-контроля для комментариев"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'🔴 Выкл' if settings_data['anti_flood_enabled'] else '🟢 Вкл'} флуд-контроль", 
                callback_data="toggle_flood"
            )
        ],
        [
            InlineKeyboardButton(
                f"{'🔴 Выкл' if settings_data.get('protect_comments', True) else '🟢 Вкл'} для комментариев", 
                callback_data="toggle_comments"
            )
        ],
        [InlineKeyboardButton("🔄 Сбросить флуд-статистику", callback_data="reset_flood_stats")],
        [
            InlineKeyboardButton("◀️ Назад к комментариям", callback_data="comments_settings"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем статистику флуда
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT COUNT(*) FROM flood_control 
                    WHERE chat_id = %s AND last_message >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
                ''', (chat_id,))
                recent_flood_events = cursor.fetchone()[0] or 0
                
                cursor.execute('''
                    SELECT COUNT(DISTINCT user_id) FROM flood_control 
                    WHERE chat_id = %s AND last_message >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                ''', (chat_id,))
                flood_users_24h = cursor.fetchone()[0] or 0
    except Exception as e:
        logger.error(f"Error getting flood stats: {e}")
        recent_flood_events = 0
        flood_users_24h = 0
    
    text = (
        f"🌊 <b>Настройки флуд-контроля</b>\n\n"
        
        f"<b>Текущие параметры:</b>\n"
        f"• Флуд-контроль: <b>{'ВКЛ' if settings_data['anti_flood_enabled'] else 'ВЫКЛ'}</b>\n"
        f"• Для комментариев: <b>{'ВКЛ' if settings_data.get('protect_comments', True) else 'ВЫКЛ'}</b>\n"
        f"• Лимит сообщений: <b>5 сообщений</b>\n"
        f"• Временное окно: <b>10 секунд</b>\n\n"
        
        f"<b>📊 Статистика флуда:</b>\n"
        f"• Событий за час: <b>{recent_flood_events}</b>\n"
        f"• Пользователей за 24ч: <b>{flood_users_24h}</b>\n\n"
        
        f"<b>💡 Как работает:</b>\n"
        f"• Система отслеживает количество сообщений\n"
        f"• Если больше 5 сообщений за 10 секунд - флуд\n"
        f"• При флуде - удаление + предупреждение\n"
        f"• При 3+ предупреждениях - автоматический бан\n\n"
        
        f"💡 <i>Флуд-контроль применяется к комментариям и основному чату</i>"
    )
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
async def toggle_comments_protection(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Переключение защиты комментариев"""
    try:
        logger.info(f"Начало toggle_comments_protection для чата {chat_id}")
        
        settings_data = db.get_chat_settings(chat_id)
        if not settings_data:
            logger.error(f"Не удалось загрузить настройки для чата {chat_id}")
            await update.callback_query.answer("❌ Ошибка загрузки настроек")
            return
            
        # Получаем текущее значение защиты комментариев
        current_value = settings_data.get('protect_comments', True)
        logger.info(f"Текущее значение protect_comments: {current_value}")
        
        # Инвертируем значение
        new_value = not current_value
        settings_data['protect_comments'] = new_value
        
        logger.info(f"Новое значение protect_comments: {new_value}")
        
        # Сохраняем настройки
        db.save_chat_settings(settings_data)
        logger.info("Настройки сохранены в БД")
        
        settings_data_after_save = db.get_chat_settings(chat_id)
        if settings_data_after_save:
            logger.info(f"Проверка после сохранения - protect_comments: {settings_data_after_save.get('protect_comments')}")
            
        # Формируем текст ответа
        status = "включена" if new_value else "выключена"
        await update.callback_query.answer(f"✅ Защита комментариев {status}")
        logger.info(f"Отправлен ответ: Защита комментариев {status}")
        
        # Обновляем сообщение с настройками
        await show_comments_settings(update, context, chat_id, message_id)
        logger.info("Сообщение с настройками обновлено")
        
    except Exception as e:
        logger.error(f"Error in toggle_comments_protection: {e}")
        await update.callback_query.answer("❌ Ошибка при изменении настроек")
        
async def show_comments_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Настройки защиты комментариев"""
    try:
        logger.info(f"Начало show_comments_settings для чата {chat_id}")
        
        settings_data = db.get_chat_settings(chat_id)
        if not settings_data:
            logger.error(f"Не удалось загрузить настройки для чата {chat_id}")
            return
        
        # Получаем текущее состояние защиты комментариев
        protect_comments = settings_data.get('protect_comments', True)
        logger.info(f"Текущее состояние защиты комментариев: {protect_comments}")
        
        # Формируем текст кнопки в зависимости от состояния
        button_text = f"{'🔴 Выключить' if protect_comments else '🟢 Включить'} защиту комментариев"
        logger.info(f"Текст кнопки: {button_text}")
        
        keyboard = [
            [InlineKeyboardButton(button_text, callback_data="toggle_comments")],
            [
                InlineKeyboardButton("📊 Статистика комментариев", callback_data="comments_stats"),
                InlineKeyboardButton("⚙️ Настройки флуд-контроля", callback_data="flood_settings")
            ],
            [
                InlineKeyboardButton("◀️ Назад", callback_data="main_settings"),
                InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        stats = db.get_statistics(chat_id, 7)
        comments_stats = stats.get('actions', {}).get('comment_posted', 0)
        comments_deleted = stats.get('actions', {}).get('comment_deleted', 0)
        
        # Добавляем временную метку для уникальности сообщения
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Безопасный расчет эффективности
        if comments_stats > 0:
            efficiency = (comments_deleted / comments_stats) * 100
        else:
            efficiency = 0
        
        text = (
            f"💬 <b>Защита комментариев</b>\n\n"
            f"<b>Текущий статус:</b> {'🟢 ВКЛЮЧЕНА' if protect_comments else '🔴 ВЫКЛЮЧЕНА'}\n\n"
            
            f"<b>📊 Статистика за 7 дней:</b>\n"
            f"• Обработано комментариев: <b>{comments_stats}</b>\n"
            f"• Удалено комментариев: <b>{comments_deleted}</b>\n"
            f"• Эффективность: <b>{efficiency:.1f}%</b>\n\n"
            
            f"<b>🛡️ Активные защиты:</b>\n"
            f"• Проверка возраста аккаунта\n"
            f"• Флуд-контроль\n"
            f"• Фильтр спам-ссылок\n"
            f"• Система предупреждений\n\n"
            
            f"💡 <i>Защита применяет те же правила, что и для основного чата</i>\n"
            f"<i>Обновлено: {timestamp}</i>"  # Добавляем временную метку
        )
        
        if message_id:
            logger.info(f"Редактируем сообщение {message_id} в чате {chat_id}")
            success = await safe_edit_message(context, chat_id, message_id, text, reply_markup)
            if not success:
                logger.warning(f"Не удалось отредактировать сообщение {message_id}")
                # Если не удалось отредактировать, отправляем новое сообщение
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text + "\n\n⚠️ <i>Не удалось обновить сообщение</i>",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
        else:
            logger.info(f"Отправляем новое сообщение в чат {chat_id}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            
        logger.info("show_comments_settings завершена успешно")
        
    except Exception as e:
        logger.error(f"Error in show_comments_settings: {e}")

async def show_comments_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Статистика комментариев"""
    stats_data = db.get_statistics(chat_id, 30)  # Статистика за 30 дней
    detailed_stats = db.get_detailed_statistics(chat_id)
    
    # Фильтруем статистику по комментариям
    comments_actions = {}
    for action_type, count in stats_data.get('actions', {}).items():
        if 'comment' in action_type:
            comments_actions[action_type] = count
    
    # Получаем топ комментаторов
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT user_id, COUNT(*) as comment_count 
                    FROM statistics 
                    WHERE chat_id = %s AND action_type = 'comment_posted'
                    AND timestamp >= CURRENT_TIMESTAMP - INTERVAL '30 days'
                    GROUP BY user_id 
                    ORDER BY comment_count DESC 
                    LIMIT 5
                ''', (chat_id,))
                top_commenters = cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting top commenters: {e}")
        top_commenters = []
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="comments_stats")],
        [InlineKeyboardButton("⚙️ Настройки комментариев", callback_data="comments_settings")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="comments_settings"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Форматируем статистику комментариев
    total_comments = comments_actions.get('comment_posted', 0)
    deleted_comments = comments_actions.get('comment_deleted', 0)
    spam_blocked = comments_actions.get('comment_deleted', 0)  # Упрощенно
    
    if total_comments > 0:
        efficiency_rate = (deleted_comments / total_comments) * 100
    else:
        efficiency_rate = 0
    
    # Форматируем топ комментаторов
    top_commenters_text = ""
    for i, (user_id, count) in enumerate(top_commenters[:3], 1):
        try:
            user = await context.bot.get_chat_member(chat_id, user_id)
            name = user.user.first_name or f"User {user_id}"
            top_commenters_text += f"{i}. {name}: {count} коммент.\n"
        except Exception:
            top_commenters_text += f"{i}. User {user_id}: {count} коммент.\n"
    
    if not top_commenters_text:
        top_commenters_text = "• Нет данных\n"
    
    text = (
        f"📊 <b>Статистика комментариев</b>\n\n"
        
        f"<b>📈 Общая статистика (30 дней):</b>\n"
        f"• Всего комментариев: <b>{total_comments}</b>\n"
        f"• Удалено комментариев: <b>{deleted_comments}</b>\n"
        f"• Заблокировано спама: <b>{spam_blocked}</b>\n"
        f"• Эффективность: <b>{efficiency_rate:.1f}%</b>\n\n"
        
        f"<b>🛡️ Детали защиты:</b>\n"
        f"• Молодые аккаунты: <b>{comments_actions.get('comment_deleted_young_account', 0)}</b>\n"
        f"• Флуд: <b>{comments_actions.get('comment_deleted_flood', 0)}</b>\n"
        f"• Спам-ссылки: <b>{comments_actions.get('comment_deleted_spam', 0)}</b>\n\n"
        
        f"<b>🏆 Топ комментаторов:</b>\n"
        f"{top_commenters_text}\n"
        
        f"<b>💡 Аналитика:</b>\n"
    )
    
    # Добавляем аналитику
    if total_comments == 0:
        text += "• Комментарии еще не поступали\n"
    elif efficiency_rate > 20:
        text += f"• Высокий уровень спама ({efficiency_rate:.1f}%)\n"
    elif efficiency_rate > 5:
        text += f"• Умеренный уровень спама ({efficiency_rate:.1f}%)\n"
    else:
        text += f"• Низкий уровень спама ({efficiency_rate:.1f}%)\n"
    
    if deleted_comments > 0:
        text += f"• Защита активно работает\n"
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def show_cooldown_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Настройки ограничения частоты сообщений"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'🔴 Выкл' if settings_data.get('message_cooldown_enabled', False) else '🟢 Вкл'} ограничение сообщений", 
                callback_data="toggle_cooldown"
            )
        ],
        [InlineKeyboardButton("🔄 Сбросить все ограничения", callback_data="reset_all_cooldowns")],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="main_settings"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем статистику ограничений
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT COUNT(*) FROM message_cooldown 
                    WHERE chat_id = %s AND last_message >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
                ''', (chat_id,))
                recent_blocks = cursor.fetchone()[0] or 0
                
                cursor.execute('''
                    SELECT COUNT(DISTINCT user_id) FROM message_cooldown 
                    WHERE chat_id = %s AND last_message >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                ''', (chat_id,))
                affected_users = cursor.fetchone()[0] or 0
    except Exception as e:
        logger.error(f"Error getting cooldown stats: {e}")
        recent_blocks = 0
        affected_users = 0
    
    # Добавляем временную метку для уникальности сообщения
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    text = (
        f"⏰ <b>Ограничение частоты сообщений</b>\n\n"
        
        f"<b>Текущий статус:</b> {'🟢 ВКЛЮЧЕНО' if settings_data.get('message_cooldown_enabled', False) else '🔴 ВЫКЛЮЧЕНО'}\n\n"
        
        f"<b>⚙️ Параметры:</b>\n"
        f"• Ограничение: <b>1 сообщение в 30 секунд</b>\n"
        f"• При нарушении: <b>Удаление сообщения + предупреждение</b>\n\n"
        
        f"<b>📊 Статистика за 24 часа:</b>\n"
        f"• Заблокировано сообщений: <b>{recent_blocks}</b>\n"
        f"• Затронуто пользователей: <b>{affected_users}</b>\n\n"
        
        f"<b>💡 Для кого полезно:</b>\n"
        f"• Против спамеров и ботов\n"
        f"• Для уменьшения флуда\n"
        f"• В важных деловых чатах\n\n"
        
        f"💡 <i>Ограничение применяется ко всем сообщениям и комментариям</i>\n"
        f"<i>Обновлено: {timestamp}</i>"  # Добавляем временную метку
    )
    
    if message_id:
        success = await safe_edit_message(context, chat_id, message_id, text, reply_markup)
        if not success:
            # Если не удалось отредактировать, отправляем новое сообщение
            await context.bot.send_message(
                chat_id=chat_id,
                text=text + "\n\n⚠️ <i>Не удалось обновить сообщение</i>",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

async def send_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, user_name: str) -> None:
    """Улучшенная отправка капчи новому пользователю"""
    try:
        settings = db.get_chat_settings(chat_id)
        if not settings:
            return

        # Создаем клавиатуру с кнопкой капчи
        keyboard = [
            [InlineKeyboardButton("✅ Я не бот", callback_data=f"captcha_verify_{user_id}")],
            [InlineKeyboardButton("🚫 Я бот", callback_data=f"captcha_bot_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем сообщение с капчей
        captcha_message = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"👋 <b>Добро пожаловать, {user_name}!</b>\n\n"
                "🛡️ <b>Проверка безопасности</b>\n\n"
                "Чтобы доказать, что вы не бот, нажмите кнопку '✅ Я не бот':\n\n"
                "⏰ <i>У вас есть 10 минут для прохождения проверки</i>\n"
                "❌ <i>При неудаче вы будете удалены из чата</i>"
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

        # Сохраняем капчу в базу
        success = db.create_captcha(chat_id, user_id, captcha_message.message_id)
        
        if success:
            logger.info(f"Капча успешно отправлена пользователю {user_id} в чате {chat_id}")
            
            # Ограничиваем права пользователя - используем ТОЛЬКО старый формат
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(
                        can_send_messages=False
                    )
                )
                logger.info(f"Права пользователя {user_id} ограничены")
            except Exception as e:
                logger.error(f"Error restricting user: {e}")

        else:
            logger.error(f"Не удалось сохранить капчу для пользователя {user_id}")

    except Exception as e:
        logger.error(f"Error sending captcha: {e}")

async def handle_captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик только для кнопок верификации капчи"""
    query = update.callback_query
    if not query or not query.data:
        return

    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data

    logger.info(f"CAPTCHA VERIFICATION: user_id={user_id}, chat_id={chat_id}, data={data}")

    try:
        await query.answer()
    except Exception as e:
        if "Query is too old" in str(e) or "response timeout expired" in str(e):
            logger.warning(f"Captcha callback query expired for user {user_id}")
        else:
            logger.error(f"Error answering captcha callback: {e}")
            return

    try:
        parts = data.split('_')
        if len(parts) < 3:
            return
            
        target_user_id = int(parts[-1])
        
        if user_id != target_user_id:
            try:
                await query.answer("❌ Эта проверка не для вас!", show_alert=True)
            except Exception:
                pass
            return

        if data.startswith('captcha_verify_'):
            logger.info(f"User {user_id} passed captcha in chat {chat_id}")
            
            success = db.mark_captcha_passed(chat_id, user_id)
            
            if success:
                try:
                    await context.bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=ChatPermissions(
                            can_send_messages=True
                        )
                    )
                    logger.info(f"✅ Rights restored for user {user_id}")
                    
                except Exception as e:
                    logger.error(f"❌ Error unrestricting user {user_id}: {e}")

                # Редактируем сообщение с капчей
                try:
                    await query.edit_message_text(
                        "✅ <b>Проверка пройдена успешно!</b>\n\n"
                        "Теперь вы можете общаться в чате.\n\n"
                        f"👤 <i>Пользователь: {query.from_user.first_name}</i>",
                        parse_mode=ParseMode.HTML
                    )
                    logger.info(f"✅ Captcha message updated for user {user_id}")
                except Exception as e:
                    logger.error(f"❌ Error editing captcha message: {e}")
                
                db.log_action(chat_id, user_id, 'captcha_passed')
                logger.info(f"🎉 CAPTCHA COMPLETED SUCCESSFULLY for user {user_id}")

            else:
                logger.error(f"❌ Failed to mark captcha as passed for user {user_id}")
                try:
                    await query.answer("❌ Ошибка проверки. Попробуйте еще раз.", show_alert=True)
                except Exception:
                    pass

        elif data.startswith('captcha_bot_'):
            logger.info(f"User {user_id} failed captcha in chat {chat_id}")
            
            max_attempts_reached, attempts = db.increment_captcha_attempts(chat_id, user_id)
            
            if max_attempts_reached:
                logger.info(f"🚫 Max attempts reached for user {user_id}, banning")
                try:
                    await context.bot.ban_chat_member(chat_id, user_id)
                    await context.bot.unban_chat_member(chat_id, user_id)
                    
                    try:
                        await query.edit_message_text(
                            f"🚫 <b>Пользователь удален</b>\n\n"
                            f"Причина: превышение попыток проверки\n"
                            f"👤 <i>Пользователь: {query.from_user.first_name}</i>",
                            parse_mode=ParseMode.HTML
                        )
                        logger.info(f"🚫 User {user_id} banned for failed captcha")
                    except Exception as e:
                        logger.error(f"❌ Error editing ban message: {e}")
                    
                    db.log_action(chat_id, user_id, 'user_banned', 'failed_captcha')
                    
                except Exception as e:
                    logger.error(f"❌ Error banning user: {e}")
            else:
                remaining_attempts = 3 - attempts
                logger.info(f"⚠️ User {user_id} failed captcha, attempts: {attempts}, remaining: {remaining_attempts}")
                try:
                    await query.answer(
                        f"⚠️ Неверный ответ! Попыток осталось: {remaining_attempts}",
                        show_alert=True
                    )
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"❌ Error handling captcha callback: {e}")

async def check_captcha_expired(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка просроченных капч (запускается по расписанию)"""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Находим просроченные капчи
                cursor.execute('''
                    SELECT chat_id, user_id, captcha_message_id 
                    FROM user_captcha 
                    WHERE expires_at < CURRENT_TIMESTAMP AND captcha_passed = FALSE
                ''')
                expired_captchas = cursor.fetchall()

                for chat_id, user_id, message_id in expired_captchas:
                    try:
                        # Кикаем пользователя
                        await context.bot.ban_chat_member(chat_id, user_id)
                        await context.bot.unban_chat_member(chat_id, user_id)
                        
                        # Редактируем сообщение с капчей
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text="⏰ <b>Время проверки истекло</b>\n\nПользователь был удален из чата.",
                            parse_mode=ParseMode.HTML
                        )
                        
                        # Удаляем капчу из базы
                        db.delete_captcha(chat_id, user_id)
                        
                        db.log_action(chat_id, user_id, 'user_banned', 'captcha_timeout')
                        logger.info(f"User {user_id} kicked for captcha timeout in chat {chat_id}")
                        
                    except Exception as e:
                        logger.error(f"Error handling expired captcha for user {user_id}: {e}")
                        # Все равно удаляем капчу из базы
                        db.delete_captcha(chat_id, user_id)

    except Exception as e:
        logger.error(f"Error checking expired captchas: {e}")
        
async def show_captcha_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int] = None) -> None:
    """Настройки капчи"""
    settings_data = db.get_chat_settings(chat_id)
    if not settings_data:
        return
    
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'🔴 Выкл' if settings_data.get('captcha_enabled', False) else '🟢 Вкл'} капчу", 
                callback_data="toggle_captcha"
            )
        ],
        [
            InlineKeyboardButton("⏰ Таймаут: 10 мин", callback_data="noop"),
            InlineKeyboardButton("🔄 Попытки: 3", callback_data="noop")
        ],
        [InlineKeyboardButton("🎛️ Настройки политики", callback_data="captcha_policy_settings")],  # НОВАЯ КНОПКА
        [
            InlineKeyboardButton("◀️ Назад", callback_data="main_settings"),
            InlineKeyboardButton("🏠 В главное", callback_data="main_menu")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Статистика капчи
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN captcha_passed = TRUE THEN 1 END) as passed,
                        COUNT(CASE WHEN captcha_passed = FALSE AND expires_at < CURRENT_TIMESTAMP THEN 1 END) as failed
                    FROM user_captcha 
                    WHERE chat_id = %s
                ''', (chat_id,))
                stats = cursor.fetchone()
                total, passed, failed = stats if stats else (0, 0, 0)
    except Exception as e:
        logger.error(f"Error getting captcha stats: {e}")
        total, passed, failed = 0, 0, 0
    
    current_policy = settings_data.get('captcha_policy', 'persistent')
    policy_names = {
        'persistent': '🔄 Постоянная',
        'time_based': '⏰ Временная',
        'always': '🚫 Всегда'
    }
    
    # Добавляем временную метку для уникальности сообщения
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    text = (
        f"🤖 <b>Настройки капчи</b>\n\n"
        
        f"<b>Текущий статус:</b> {'🟢 ВКЛЮЧЕНА' if settings_data.get('captcha_enabled', False) else '🔴 ВЫКЛЮЧЕНА'}\n"
        f"<b>Политика:</b> {policy_names.get(current_policy, '🔄 Постоянная')}\n\n"
        
        f"<b>📊 Статистика капчи:</b>\n"
        f"• Всего проверок: <b>{total}</b>\n"
        f"• Успешно пройдено: <b>{passed}</b>\n"
        f"• Провалено/истекло: <b>{failed}</b>\n\n"
        
        f"<b>⚙️ Параметры капчи:</b>\n"
        f"• Тип: <b>Кнопочная капча</b>\n"
        f"• Таймаут: <b>10 минут</b>\n"
        f"• Макс. попыток: <b>3</b>\n\n"
        
        f"<b>💡 Как работает:</b>\n"
        f"• Новые пользователи получают проверку\n"
        f"• Нужно нажать кнопку 'Я не бот'\n"
        f"• При неудаче - удаление из чата\n"
        f"• При успехе - полный доступ к чату\n\n"
        
        f"💡 <i>Эффективно против ботов и спамеров</i>\n"
        f"<i>Обновлено: {timestamp}</i>"
    )
    
    if message_id:
        success = await safe_edit_message(context, chat_id, message_id, text, reply_markup)
        if not success:
            # Если не удалось отредактировать, отправляем новое сообщение
            await context.bot.send_message(
                chat_id=chat_id,
                text=text + "\n\n⚠️ <i>Не удалось обновить сообщение</i>",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
def main() -> None:
    """Основная функция запуска бота"""
    try:
        token = cast(str, BOT_TOKEN)
        application = Application.builder().token(token).build()
        
        # ВАЖНО: сначала обработчик капчи с паттерном, потом общий обработчик
        application.add_handler(CallbackQueryHandler(
            handle_captcha_callback, 
            pattern="^captcha_(verify|bot)_"
        ))
        
        # Затем общий обработчик кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Остальные обработчики...
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", menu))
        application.add_handler(CommandHandler("settings", menu))  
        application.add_handler(CommandHandler("status", menu))   
        application.add_handler(CommandHandler("enable", enable_bot))
        application.add_handler(CommandHandler("disable", disable_bot))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(CommandHandler("checkdb", check_db))
        # application.add_handler(CommandHandler("debug_captcha", debug_captcha))
        
        # Обработчики сообщений
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            handle_comments
        ))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Планировщик
        job_queue = application.job_queue
        if job_queue:
            job_queue.run_repeating(check_captcha_expired, interval=60, first=10)
        
        application.add_error_handler(error_handler)
        
        logger.info("Бот запускается...")
        logger.info("Обработчики зарегистрированы: сначала капча, потом общие кнопки")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == '__main__':
    main()