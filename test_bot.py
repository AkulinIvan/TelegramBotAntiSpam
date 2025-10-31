import unittest
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

import logging
from datetime import datetime

import sys
import os

# Добавляем путь к модулю для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем тестируемые функции и классы
from bot import DatabaseManager, start, menu, show_status
from bot import show_stats
from bot import button_handler
from bot import handle_message, new_chat_members, enable_bot, disable_bot
from bot import help_command, error_handler

# Настройка тестового логгера
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestDatabaseManager(unittest.TestCase):
    """Тесты для класса DatabaseManager"""
    
    def setUp(self) -> None:
        """Настройка перед каждым тестом"""
        self.connection_string = "postgresql://test:test@localhost/test_db"
        
        # Патчим psycopg2.connect перед созданием DatabaseManager
        self.patcher = patch('bot.psycopg2.connect')
        self.mock_connect = self.patcher.start()
        self.mock_conn = Mock()
        self.mock_connect.return_value = self.mock_conn
        self.mock_cursor = Mock()
        self.mock_conn.cursor.return_value = self.mock_cursor
        self.mock_conn.__enter__ = Mock(return_value=self.mock_conn)
        self.mock_conn.__exit__ = Mock(return_value=None)
        self.mock_cursor.__enter__ = Mock(return_value=self.mock_cursor)
        self.mock_cursor.__exit__ = Mock(return_value=None)
        
        self.db_manager = DatabaseManager(self.connection_string)
    
    def tearDown(self) -> None:
        """Очистка после каждого теста"""
        self.patcher.stop()
        
    def test_get_connection_success(self) -> None:
        """Тест успешного подключения к базе данных"""
        # Сбрасываем счетчик вызовов для этого теста
        self.mock_connect.reset_mock()
        
        connection = self.db_manager.get_connection()
        
        self.mock_connect.assert_called_once_with(self.connection_string)
        self.assertEqual(connection, self.mock_conn)
    
    def test_get_connection_error(self) -> None:
        """Тест ошибки подключения к базе данных"""
        self.mock_connect.side_effect = Exception("Connection failed")
        
        with self.assertRaises(Exception):
            self.db_manager.get_connection()
    
    def test_init_db_success(self) -> None:
        """Тест успешной инициализации базы данных"""
        # Уже выполнено в setUp, проверяем что были вызваны SQL команды
        self.assertTrue(self.mock_cursor.execute.call_count >= 4)
    
    def test_get_chat_settings_existing(self) -> None:
        """Тест получения существующих настроек чата"""
        # Мокаем результат запроса
        test_data = (
            12345,  # chat_id
            'Test welcome message',  # welcome_message
            1,  # min_account_age_days
            0,  # min_join_date_days
            True,  # restrict_new_users
            True,  # delete_service_messages
            True,  # enabled
            3,  # max_warnings
            True,  # anti_flood_enabled
            datetime.now()  # created_at
        )
        self.mock_cursor.fetchone.return_value = test_data
        
        settings = self.db_manager.get_chat_settings(12345)
        
        self.assertIsNotNone(settings)
        if settings:  # Добавляем проверку на None
            self.assertEqual(settings['chat_id'], 12345)
            self.assertEqual(settings['welcome_message'], 'Test welcome message')
    
    def test_get_chat_settings_new(self) -> None:
        """Тест получения настроек для нового чата"""
        # Мокаем что настройки не найдены
        self.mock_cursor.fetchone.return_value = None
        
        settings = self.db_manager.get_chat_settings(12345)
        
        self.assertIsNotNone(settings)
        if settings:  # Добавляем проверку на None
            self.assertEqual(settings['chat_id'], 12345)
        # Проверяем что были вызваны запросы SELECT и INSERT
        self.assertTrue(self.mock_cursor.execute.call_count >= 5)
    
    def test_save_chat_settings(self) -> None:
        """Тест сохранения настроек чата"""
        test_settings: Dict[str, Any] = {
            'chat_id': 12345,
            'welcome_message': 'Test message',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'enabled': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        
        self.db_manager.save_chat_settings(test_settings)
        
        self.mock_conn.commit.assert_called()
    
    def test_log_action(self) -> None:
        """Тест логирования действия"""
        self.db_manager.log_action(12345, 67890, 'test_action', 'test_details')
        
        self.mock_conn.commit.assert_called()
    
    def test_get_statistics(self) -> None:
        """Тест получения статистики"""
        # Мокаем различные результаты запросов
        self.mock_cursor.fetchall.side_effect = [
            [('new_member', 5), ('user_blocked', 2)],  # actions_stats
            [('2023-01-01', 10), ('2023-01-02', 15)],  # daily_stats
            [(123, 10), (456, 8)],  # top_users
        ]
        self.mock_cursor.fetchone.side_effect = [(25,), (3,), (15, 5)]
        
        stats = self.db_manager.get_statistics(12345, 7)
        
        self.assertIsInstance(stats, dict)
        self.assertEqual(stats['today_actions'], 25)
        self.assertEqual(stats['today_new_users'], 3)
        self.assertEqual(len(stats['top_users']), 2)
    
    def test_add_user_warning(self) -> None:
        """Тест добавления предупреждения пользователю"""
        self.mock_cursor.fetchone.return_value = (2,)  # Новое количество предупреждений
        
        warnings_count = self.db_manager.add_user_warning(12345, 67890)
        
        self.assertEqual(warnings_count, 2)
        self.mock_conn.commit.assert_called()
    
    def test_get_user_warnings(self) -> None:
        """Тест получения количества предупреждений пользователя"""
        self.mock_cursor.fetchone.return_value = (3,)  # Количество предупреждений
        
        warnings_count = self.db_manager.get_user_warnings(12345, 67890)
        
        self.assertEqual(warnings_count, 3)
    
    def test_reset_user_warnings(self) -> None:
        """Тест сброса предупреждений пользователя"""
        self.db_manager.reset_user_warnings(12345, 67890)
        
        self.mock_conn.commit.assert_called()
    
    def test_reset_all_statistics(self) -> None:
        """Тест сброса всей статистики"""
        self.db_manager.reset_all_statistics(12345)
        
        self.mock_conn.commit.assert_called()


class TestBotHandlers(unittest.IsolatedAsyncioTestCase):
    """Тесты для обработчиков бота"""
    
    async def asyncSetUp(self) -> None:
        """Настройка перед каждым тестом"""
        self.update = Mock()
        self.context = Mock()
        self.context.bot = Mock()
        self.context.user_data = {}
        
        # Мокаем базовые объекты Telegram с AsyncMock для асинхронных методов
        self.user = Mock()
        self.user.id = 12345
        self.user.first_name = "TestUser"
        
        self.chat = Mock()
        self.chat.id = 67890
        self.chat.type = "private"
        self.chat.title = "Test Chat"
        
        self.message = AsyncMock()  # Используем AsyncMock для сообщений
        self.message.chat = self.chat
        self.message.from_user = self.user
        
        self.update.effective_user = self.user
        self.update.effective_chat = self.chat
        self.update.message = self.message
        
        # Мокаем асинхронные методы
        self.context.bot.send_message = AsyncMock()
        self.context.bot.get_chat_member = AsyncMock()
        self.context.bot.ban_chat_member = AsyncMock()
        self.context.bot.unban_chat_member = AsyncMock()
        self.context.bot.edit_message_text = AsyncMock()
    
    @patch('bot.db')
    async def test_start_private_chat(self, mock_db: Mock) -> None:
        """Тест команды /start в приватном чате"""
        # Настраиваем моки
        self.chat.type = "private"
        mock_db.get_chat_settings.return_value = None
        
        # Вызываем тестируемую функцию
        await start(self.update, self.context)
        
        # Проверяем что был отправлен ответ
        self.message.reply_text.assert_called_once()
    
    @patch('bot.db')
    async def test_start_group_chat(self, mock_db: Mock) -> None:
        """Тест команды /start в групповом чате"""
        # Настраиваем моки
        self.chat.type = "group"
        mock_db.get_chat_settings.return_value = None
        
        # Вызываем тестируемую функцию
        await start(self.update, self.context)
        
        # Проверяем что был отправлен ответ
        self.message.reply_text.assert_called_once()
    
    @patch('bot.db')
    async def test_menu_private_chat(self, mock_db: Mock) -> None:
        """Тест команды /menu в приватном чате"""
        # Настраиваем моки
        self.chat.type = "private"
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        # Вызываем тестируемую функцию
        await menu(self.update, self.context)
        
        # Проверяем что был отправлен ответ с клавиатурой
        self.message.reply_text.assert_called_once()
    
    @patch('bot.db')
    async def test_menu_group_chat_non_admin(self, mock_db: Mock) -> None:
        """Тест команды /menu в группе без прав администратора"""
        # Настраиваем моки
        self.chat.type = "group"
        mock_member = Mock()
        mock_member.status = "member"  # Не администратор
        self.context.bot.get_chat_member.return_value = mock_member
        
        # Вызываем тестируемую функцию
        await menu(self.update, self.context)
        
        # Проверяем что было отправлено сообщение об ошибке
        self.message.reply_text.assert_called_once()
    
    @patch('bot.db')
    async def test_show_status(self, mock_db: Mock) -> None:
        """Тест показа статуса защиты"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        # Вызываем тестируемую функцию
        await show_status(self.update, self.context, 12345)
        
        # Проверяем что было отправлено сообщение
        self.context.bot.send_message.assert_called_once()
    
    @patch('bot.db')
    async def test_button_handler_main_menu(self, mock_db: Mock) -> None:
        """Тест обработки кнопки главного меню"""
        # Создаем мок callback query
        query = AsyncMock()
        query.data = "main_menu"
        query.message = self.message
        self.update.callback_query = query
        
        # Мокаем функцию menu
        with patch('bot.menu', AsyncMock()) as mock_menu:
            await button_handler(self.update, self.context)
            
            # Проверяем что была вызвана функция menu
            mock_menu.assert_called_once_with(self.update, self.context)
            query.answer.assert_called_once()
    
    @patch('bot.db')
    async def test_button_handler_toggle_enable(self, mock_db: Mock) -> None:
        """Тест обработки кнопки включения/выключения"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        mock_db.save_chat_settings = Mock()
        
        # Создаем мок callback query
        query = AsyncMock()
        query.data = "toggle_enable"
        query.message = self.message
        self.update.callback_query = query
        
        with patch('bot.show_main_settings', AsyncMock()) as mock_show:
            await button_handler(self.update, self.context)
            
            # Проверяем что настройки были сохранены
            mock_db.save_chat_settings.assert_called_once()
            # Исправлено: проверяем что answer был вызван хотя бы один раз
            query.answer.assert_called()
            mock_show.assert_called_once()
    
    @patch('bot.db')
    async def test_handle_message_welcome_text(self, mock_db: Mock) -> None:
        """Тест обработки текста приветственного сообщения"""
        # Настраиваем контекст для ожидания приветственного сообщения
        self.context.user_data['awaiting_welcome'] = True
        self.context.user_data['settings_message_id'] = 111
        
        self.message.text = "Новое приветственное сообщение"
        
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Old message',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        mock_db.save_chat_settings = Mock()
        
        # Исправлено: мокаем все необходимые функции
        with patch('bot.show_welcome_settings', AsyncMock()) as mock_show:
            # Также мокаем edit_message_text чтобы избежать ошибок при вызове
            self.context.bot.edit_message_text = AsyncMock()
            
            await handle_message(self.update, self.context)
            
            # Проверяем что настройки были обновлены
            mock_db.save_chat_settings.assert_called_once()
            self.message.reply_text.assert_called_once_with("✅ Приветственное сообщение обновлено!")
            
            # Проверяем что show_welcome_settings была вызвана с правильными аргументами
            mock_show.assert_called_once_with(self.update, self.context, self.chat.id, 111)
    
    @patch('bot.db')
    async def test_new_chat_members_young_account(self, mock_db: Mock) -> None:
        """Тест обработки новых участников с молодым аккаунтом"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 7,  # Требуем аккаунт старше 7 дней
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        mock_db.log_action = Mock()
        
        # Создаем нового пользователя с молодым аккаунтом
        new_user = Mock()
        new_user.id = 99999
        new_user.first_name = "NewUser"
        new_user.username = "newuser"
        # Аккаунт создан сегодня
        new_user.date = datetime.now().replace(tzinfo=None)
        
        self.message.new_chat_members = [new_user]
        self.message.delete = AsyncMock()
        
        await new_chat_members(self.update, self.context)
        
        # Проверяем что пользователь был забанен (кикнут)
        self.context.bot.ban_chat_member.assert_called_once()
        mock_db.log_action.assert_called()
    
    @patch('bot.db')
    async def test_enable_bot(self, mock_db: Mock) -> None:
        """Тест команды включения бота"""
        mock_settings: Dict[str, Any] = {
            'enabled': False,
            'welcome_message': 'Test',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        mock_db.save_chat_settings = Mock()
        
        await enable_bot(self.update, self.context)
        
        # Проверяем что настройки были обновлены
        mock_db.save_chat_settings.assert_called_once()
        saved_settings_call = mock_db.save_chat_settings.call_args
        assert saved_settings_call is not None
        saved_settings = saved_settings_call[0][0]
        self.assertTrue(saved_settings['enabled'])
        self.message.reply_text.assert_called_once_with("✅ Бот защиты включен!")
    
    @patch('bot.db')
    async def test_disable_bot(self, mock_db: Mock) -> None:
        """Тест команды выключения бота"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        mock_db.save_chat_settings = Mock()
        
        await disable_bot(self.update, self.context)
        
        # Проверяем что настройки были обновлены
        mock_db.save_chat_settings.assert_called_once()
        saved_settings_call = mock_db.save_chat_settings.call_args
        assert saved_settings_call is not None
        saved_settings = saved_settings_call[0][0]
        self.assertFalse(saved_settings['enabled'])
        self.message.reply_text.assert_called_once_with("❌ Бот защиты выключен!")
    
    async def test_help_command(self) -> None:
        """Тест команды помощи"""
        await help_command(self.update, self.context)
        
        self.message.reply_text.assert_called_once()
    
    async def test_error_handler(self) -> None:
        """Тест обработчика ошибок"""
        # Мокаем логгер для проверки вызова
        with patch('bot.logger') as mock_logger:
            test_error = Exception("Test error")
            self.context.error = test_error
            
            await error_handler(self.update, self.context)
            
            # Проверяем что ошибка была залогирована
            mock_logger.error.assert_called_once()


class TestIntegrationScenarios(unittest.IsolatedAsyncioTestCase):
    """Тесты интеграционных сценариев"""
    
    async def asyncSetUp(self) -> None:
        """Настройка перед каждым тестом"""
        self.update = Mock()
        self.context = Mock()
        self.context.bot = Mock()
        self.context.user_data = {}
        
        self.user = Mock()
        self.user.id = 12345
        self.user.first_name = "TestUser"
        
        self.chat = Mock()
        self.chat.id = 67890
        self.chat.type = "group"
        self.chat.title = "Test Group"
        
        self.message = AsyncMock()
        self.message.chat = self.chat
        self.message.from_user = self.user
        
        self.update.effective_user = self.user
        self.update.effective_chat = self.chat
        self.update.message = self.message
        
        # Мокаем асинхронные методы
        self.context.bot.send_message = AsyncMock()
        self.context.bot.get_chat_member = AsyncMock()
    
    @patch('bot.db')
    async def test_complete_settings_flow(self, mock_db: Mock) -> None:
        """Тест полного цикла настройки"""
        # Начальные настройки
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': '👋 Добро пожаловать, {mention}! Рады видеть вас в {chat}!',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        mock_db.save_chat_settings = Mock()
        
        # 1. Показываем главное меню
        await menu(self.update, self.context)
        self.message.reply_text.assert_called_once()
        
        # 2. Обрабатываем нажатие кнопки основных настроек
        query = AsyncMock()
        query.data = "main_settings"
        query.message = self.message
        self.update.callback_query = query
        
        with patch('bot.show_main_settings', AsyncMock()) as mock_show:
            await button_handler(self.update, self.context)
            mock_show.assert_called_once()
        
        # 3. Изменяем настройки возраста аккаунта
        query.data = "age_7"
        
        with patch('bot.show_age_settings', AsyncMock()):
            await button_handler(self.update, self.context)
            
            # Проверяем что настройки были сохранены
            mock_db.save_chat_settings.assert_called_once()
            saved_settings_call = mock_db.save_chat_settings.call_args
            assert saved_settings_call is not None
            saved_settings = saved_settings_call[0][0]
            self.assertEqual(saved_settings['min_account_age_days'], 7)
    
    @patch('bot.db')
    async def test_statistics_flow(self, mock_db: Mock) -> None:
        """Тест цикла работы со статистикой"""
        # Мокаем данные статистики
        mock_stats: Dict[str, Any] = {
            'actions': {'new_member': 5, 'user_blocked': 2, 'welcome_sent': 3},
            'daily_stats': [('2023-01-01', 10), ('2023-01-02', 15)],
            'today_actions': 25,
            'today_new_users': 3,
            'top_users': [(123, 10), (456, 8)],
            'total_warnings': 15,
            'warned_users': 5,
            'total_actions': 50
        }
        mock_db.get_statistics.return_value = mock_stats
        
        # Мокаем получение информации о пользователях
        mock_user1 = Mock()
        mock_user1.user.first_name = "User1"
        mock_user2 = Mock()
        mock_user2.user.first_name = "User2"
        self.context.bot.get_chat_member.side_effect = [mock_user1, mock_user2]
        
        # Показываем статистику
        await show_stats(self.update, self.context, 67890)
        
        # Проверяем что сообщение было отправлено
        self.context.bot.send_message.assert_called_once()


class TestEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Тесты граничных случаев и обработки ошибок"""
    
    async def asyncSetUp(self) -> None:
        """Настройка перед каждым тестом"""
        self.update = Mock()
        self.context = Mock()
        self.context.bot = Mock()
        self.context.user_data = {}
        
        # Мокаем асинхронные методы
        self.context.bot.send_message = AsyncMock()
    
    async def test_start_with_missing_parameters(self) -> None:
        """Тест команды /start с отсутствующими параметрами"""
        # Убираем необходимые атрибуты
        self.update.effective_user = None
        self.update.effective_chat = None
        self.update.message = None
        
        # Функция должна завершиться без ошибок
        await start(self.update, self.context)
        
        # Не должно быть вызовов reply_text
        if hasattr(self.update, 'message') and self.update.message:
            self.update.message.reply_text.assert_not_called()
    
    async def test_menu_with_missing_parameters(self) -> None:
        """Тест команды /menu с отсутствующими параметрами"""
        self.update.effective_user = None
        self.update.effective_chat = None
        self.update.message = None
        
        await menu(self.update, self.context)
        
        # Функция должна завершиться без ошибок
        if hasattr(self.update, 'message') and self.update.message:
            self.update.message.reply_text.assert_not_called()
    
    @patch('bot.db')
    async def test_button_handler_unknown_callback(self, mock_db: Mock) -> None:
        """Тест обработки неизвестного callback"""
        query = AsyncMock()
        query.data = "unknown_callback"
        query.message = Mock()
        query.message.chat_id = 12345
        query.message.message_id = 111
        self.update.callback_query = query
        
        # Функция должна завершиться без ошибок
        await button_handler(self.update, self.context)
        
        query.answer.assert_called_once()
    
    @patch('bot.db')
    async def test_database_errors_handling(self, mock_db: Mock) -> None:
        """Тест обработки ошибок базы данных"""
        # Создаем правильные моки
        self.update.effective_chat = Mock()
        self.update.effective_chat.id = 12345
        self.update.message = AsyncMock()
        self.update.message.reply_text = AsyncMock()
        
        # Мокаем ошибку при получении настроек
        mock_db.get_chat_settings.side_effect = Exception("DB error")
        
        # Функция должна обработать ошибку
        await menu(self.update, self.context)
        
        # Должно быть сообщение об ошибке
        self.update.message.reply_text.assert_called_once_with("❌ Ошибка загрузки настроек")
    
    @patch('bot.db')
    async def test_database_connection_error(self, mock_db: Mock) -> None:
        """Тест обработки ошибки подключения к базе данных"""
        # Создаем правильные моки
        self.update.effective_chat = Mock()
        self.update.effective_chat.id = 12345
        self.update.message = AsyncMock()
        self.update.message.reply_text = AsyncMock()
        
        # Мокаем ошибку подключения
        mock_db.get_chat_settings.side_effect = Exception("Connection failed")
        
        # Функция должна обработать ошибку
        await menu(self.update, self.context)
        
        # Должно быть сообщение об ошибке
        self.update.message.reply_text.assert_called_once_with("❌ Ошибка загрузки настроек")


if __name__ == '__main__':
    # Запуск тестов
    unittest.main()