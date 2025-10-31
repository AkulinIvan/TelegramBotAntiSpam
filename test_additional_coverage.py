import unittest
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot import (
    DatabaseManager, show_welcome_settings, show_quick_actions, 
    show_age_settings, show_warnings_settings, show_help_menu,
    show_detailed_stats, show_reset_stats_confirm
)


class TestAdditionalCoverage(unittest.IsolatedAsyncioTestCase):
    """Дополнительные тесты для расширения покрытия"""
    
    async def asyncSetUp(self) -> None:
        """Настройка перед каждым тестом"""
        self.update = Mock()
        self.context = Mock()
        self.context.bot = Mock()
        self.context.user_data = {}
        
        # Мокаем базовые объекты Telegram
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
        self.context.bot.edit_message_text = AsyncMock()
        self.context.bot.get_chat_member = AsyncMock()

    @patch('bot.db')
    async def test_show_welcome_settings_with_message_id(self, mock_db: Mock) -> None:
        """Тест показа настроек приветствий с message_id"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test welcome message',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        await show_welcome_settings(self.update, self.context, 67890, 111)
        
        self.context.bot.edit_message_text.assert_called_once()

    @patch('bot.db')
    async def test_show_welcome_settings_without_message_id(self, mock_db: Mock) -> None:
        """Тест показа настроек приветствий без message_id"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test welcome message',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        await show_welcome_settings(self.update, self.context, 67890)
        
        self.context.bot.send_message.assert_called_once()

    @patch('bot.db')
    async def test_show_welcome_settings_no_settings(self, mock_db: Mock) -> None:
        """Тест показа настроек приветствий когда настройки не найдены"""
        mock_db.get_chat_settings.return_value = None
        
        await show_welcome_settings(self.update, self.context, 67890)
        
        self.context.bot.send_message.assert_not_called()
        self.context.bot.edit_message_text.assert_not_called()

    @patch('bot.db')
    async def test_show_quick_actions_with_message_id(self, mock_db: Mock) -> None:
        """Тест показа быстрых действий с message_id"""
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
        
        await show_quick_actions(self.update, self.context, 67890, 111)
        
        self.context.bot.edit_message_text.assert_called_once()

    @patch('bot.db')
    async def test_show_quick_actions_without_message_id(self, mock_db: Mock) -> None:
        """Тест показа быстрых действий без message_id"""
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
        
        await show_quick_actions(self.update, self.context, 67890)
        
        self.context.bot.send_message.assert_called_once()

    @patch('bot.db')
    async def test_show_age_settings_with_message_id(self, mock_db: Mock) -> None:
        """Тест показа настроек возраста с message_id"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 7,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        await show_age_settings(self.update, self.context, 67890, 111)
        
        self.context.bot.edit_message_text.assert_called_once()

    @patch('bot.db')
    async def test_show_age_settings_custom_age(self, mock_db: Mock) -> None:
        """Тест показа настроек возраста с пользовательским возрастом"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 15,  # Пользовательское значение
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        await show_age_settings(self.update, self.context, 67890)
        
        self.context.bot.send_message.assert_called_once()

    @patch('bot.db')
    async def test_show_warnings_settings_with_message_id(self, mock_db: Mock) -> None:
        """Тест показа настроек предупреждений с message_id"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 5,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        await show_warnings_settings(self.update, self.context, 67890, 111)
        
        self.context.bot.edit_message_text.assert_called_once()

    @patch('bot.db')
    async def test_show_help_menu_with_message_id(self, mock_db: Mock) -> None:
        """Тест показа меню помощи с message_id"""
        await show_help_menu(self.update, self.context, 67890, 111)
        
        self.context.bot.edit_message_text.assert_called_once()

    @patch('bot.db')
    async def test_show_detailed_stats_with_message_id(self, mock_db: Mock) -> None:
        """Тест показа детальной статистики с message_id"""
        mock_detailed_stats: Dict[str, Any] = {
            'all_time': [('new_member', 10), ('user_blocked', 5)],
            'monthly': [('2023-01', 15), ('2023-02', 20)],
            'top_days': [('2023-01-01', 5), ('2023-01-02', 3)],
            'protection': (10, 20, 15)
        }
        mock_db.get_detailed_statistics.return_value = mock_detailed_stats
        
        await show_detailed_stats(self.update, self.context, 67890, 111)
        
        self.context.bot.edit_message_text.assert_called_once()

    @patch('bot.db')
    async def test_show_detailed_stats_empty_data(self, mock_db: Mock) -> None:
        """Тест показа детальной статистики с пустыми данными"""
        mock_detailed_stats: Dict[str, Any] = {
            'all_time': [],
            'monthly': [],
            'top_days': [],
            'protection': (0, 0, 0)
        }
        mock_db.get_detailed_statistics.return_value = mock_detailed_stats
        
        await show_detailed_stats(self.update, self.context, 67890)
        
        self.context.bot.send_message.assert_called_once()

    @patch('bot.db')
    async def test_show_detailed_stats_with_protection_zero(self, mock_db: Mock) -> None:
        """Тест показа детальной статистики с нулевой защитой"""
        mock_detailed_stats: Dict[str, Any] = {
            'all_time': [('new_member', 10)],
            'monthly': [('2023-01', 15)],
            'top_days': [('2023-01-01', 5)],
            'protection': (0, 0, 0)  # Нет новых участников
        }
        mock_db.get_detailed_statistics.return_value = mock_detailed_stats
        
        await show_detailed_stats(self.update, self.context, 67890)
        
        self.context.bot.send_message.assert_called_once()

    @patch('bot.db')
    async def test_show_reset_stats_confirm_with_message_id(self, mock_db: Mock) -> None:
        """Тест подтверждения сброса статистики с message_id"""
        await show_reset_stats_confirm(self.update, self.context, 67890, 111)
        
        self.context.bot.edit_message_text.assert_called_once()

    @patch('bot.db')
    async def test_show_reset_stats_confirm_without_message_id(self, mock_db: Mock) -> None:
        """Тест подтверждения сброса статистики без message_id"""
        await show_reset_stats_confirm(self.update, self.context, 67890)
        
        self.context.bot.send_message.assert_called_once()

    @patch('bot.db')
    async def test_button_handler_view_welcome(self, mock_db: Mock) -> None:
        """Тест обработки кнопки просмотра приветствия"""
        query = AsyncMock()
        query.data = "view_welcome"
        query.message = Mock()
        query.message.chat_id = 67890
        self.update.callback_query = query
        
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test welcome message',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        from bot import button_handler
        await button_handler(self.update, self.context)
        
        query.answer.assert_called_with('📝 Текущее приветствие: Test welcome message', show_alert=True)

    @patch('bot.db')
    async def test_button_handler_noop(self, mock_db: Mock) -> None:
        """Тест обработки пустой кнопки"""
        query = AsyncMock()
        query.data = "noop"
        query.message = Mock()
        query.message.chat_id = 67890
        self.update.callback_query = query
        
        from bot import button_handler
        await button_handler(self.update, self.context)
        
        query.answer.assert_called()

    @patch('bot.db')
    async def test_button_handler_toggle_restrict(self, mock_db: Mock) -> None:
        """Тест обработки кнопки переключения ограничений"""
        query = AsyncMock()
        query.data = "toggle_restrict"
        query.message = Mock()
        query.message.chat_id = 67890
        self.update.callback_query = query
        
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
        
        with patch('bot.show_main_settings', AsyncMock()) as mock_show:
            from bot import button_handler
            await button_handler(self.update, self.context)
            
            mock_db.save_chat_settings.assert_called_once()
            query.answer.assert_called()
            mock_show.assert_called_once()

    @patch('bot.db')
    async def test_button_handler_increase_warnings(self, mock_db: Mock) -> None:
        """Тест обработки кнопки увеличения предупреждений"""
        query = AsyncMock()
        query.data = "increase_warnings"
        query.message = Mock()
        query.message.chat_id = 67890
        self.update.callback_query = query
        
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
        
        with patch('bot.show_warnings_settings', AsyncMock()) as mock_show:
            from bot import button_handler
            await button_handler(self.update, self.context)
            
            mock_db.save_chat_settings.assert_called_once()
            query.answer.assert_called()
            mock_show.assert_called_once()

    @patch('bot.db')
    async def test_button_handler_decrease_warnings(self, mock_db: Mock) -> None:
        """Тест обработки кнопки уменьшения предупреждений"""
        query = AsyncMock()
        query.data = "decrease_warnings"
        query.message = Mock()
        query.message.chat_id = 67890
        self.update.callback_query = query
        
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
        
        with patch('bot.show_warnings_settings', AsyncMock()) as mock_show:
            from bot import button_handler
            await button_handler(self.update, self.context)
            
            mock_db.save_chat_settings.assert_called_once()
            query.answer.assert_called()
            mock_show.assert_called_once()

    @patch('bot.db')
    async def test_button_handler_reset_all_warnings(self, mock_db: Mock) -> None:
        """Тест обработки кнопки сброса всех предупреждений"""
        query = AsyncMock()
        query.data = "reset_all_warnings"
        query.message = Mock()
        query.message.chat_id = 67890
        self.update.callback_query = query
        
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
        mock_db.reset_user_warnings = Mock()
        with patch('bot.show_warnings_settings', AsyncMock()) as mock_show:
            from bot import button_handler
            await button_handler(self.update, self.context)
            
            query.answer.assert_called()
            mock_show.assert_called_once()

    @patch('bot.db')
    async def test_button_handler_set_welcome(self, mock_db: Mock) -> None:
        """Тест обработки кнопки установки приветствия"""
        query = AsyncMock()
        query.data = "set_welcome"
        query.message = Mock()
        query.message.chat_id = 67890
        query.message.message_id = 111
        self.update.callback_query = query
        
        from bot import button_handler
        await button_handler(self.update, self.context)
        
        query.edit_message_text.assert_called_once()
        self.assertEqual(self.context.user_data['awaiting_welcome'], True)
        self.assertEqual(self.context.user_data['settings_message_id'], 111)

    @patch('bot.db')
    async def test_button_handler_reset_welcome(self, mock_db: Mock) -> None:
        """Тест обработки кнопки сброса приветствия"""
        query = AsyncMock()
        query.data = "reset_welcome"
        query.message = Mock()
        query.message.chat_id = 67890
        self.update.callback_query = query
        
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
        
        with patch('bot.show_welcome_settings', AsyncMock()) as mock_show:
            from bot import button_handler
            await button_handler(self.update, self.context)
            
            mock_db.save_chat_settings.assert_called_once()
            query.answer.assert_called()
            mock_show.assert_called_once()

    @patch('bot.db')
    async def test_new_chat_members_bot_itself(self, mock_db: Mock) -> None:
        """Тест обработки добавления самого бота в чат"""
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
        
        # Создаем бота как нового участника
        bot_user = Mock()
        bot_user.id = self.context.bot.id  # ID бота
        bot_user.first_name = "TestBot"
        
        self.message.new_chat_members = [bot_user]
        
        from bot import new_chat_members
        await new_chat_members(self.update, self.context)
        
        # Бот не должен быть забанен
        self.context.bot.ban_chat_member.assert_not_called()

    @patch('bot.db')
    async def test_new_chat_members_old_account(self, mock_db: Mock) -> None:
        """Тест обработки участника со старым аккаунтом"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 7,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings  # Исправлено: используем mock_settings
        mock_db.log_action = Mock()

        # Создаем пользователя со старым аккаунтом
        old_user = Mock()
        old_user.id = 88888
        old_user.first_name = "OldUser"
        old_user.username = "olduser"
        # Аккаунт создан 30 дней назад
        old_user.date = (datetime.now() - timedelta(days=30)).replace(tzinfo=None)

        self.message.new_chat_members = [old_user]
        self.message.delete = AsyncMock()

        from bot import new_chat_members
        await new_chat_members(self.update, self.context)

        # Пользователь не должен быть забанен
        self.context.bot.ban_chat_member.assert_not_called()

    @patch('bot.db')
    async def test_new_chat_members_no_date_attribute(self, mock_db: Mock) -> None:
        """Тест обработки участника без атрибута date"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 7,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        mock_db.log_action = Mock()
        
        # Создаем пользователя без атрибута date
        user_no_date = Mock()
        user_no_date.id = 77777
        user_no_date.first_name = "NoDateUser"
        user_no_date.username = "nodateuser"
        # Убираем атрибут date
        if hasattr(user_no_date, 'date'):
            delattr(user_no_date, 'date')
        
        self.message.new_chat_members = [user_no_date]
        self.message.delete = AsyncMock()
        
        from bot import new_chat_members
        await new_chat_members(self.update, self.context)
        
        # Пользователь не должен быть забанен (нет даты для проверки)
        self.context.bot.ban_chat_member.assert_not_called()


class TestDatabaseManagerAdditional(unittest.TestCase):
    """Дополнительные тесты для DatabaseManager"""
    
    def setUp(self) -> None:
        """Настройка перед каждым тестом"""
        self.connection_string = "postgresql://test:test@localhost/test_db"
        
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

    def test_log_action_exception(self) -> None:
        """Тест логирования действия с исключением"""
        self.mock_conn.commit.side_effect = Exception("Commit failed")
        
        # Должно обработать исключение без падения
        self.db_manager.log_action(12345, 67890, 'test_action', 'test_details')

    def test_get_statistics_exception(self) -> None:
        """Тест получения статистики с исключением"""
        self.mock_cursor.fetchall.side_effect = Exception("Query failed")
        
        stats = self.db_manager.get_statistics(12345, 7)
        
        # Должен вернуть структуру по умолчанию
        self.assertEqual(stats['today_actions'], 0)
        self.assertEqual(stats['today_new_users'], 0)
        self.assertEqual(stats['total_actions'], 0)

    def test_get_detailed_statistics_exception(self) -> None:
        """Тест получения детальной статистики с исключением"""
        self.mock_cursor.fetchall.side_effect = Exception("Query failed")
        
        stats = self.db_manager.get_detailed_statistics(12345)
        
        # Должен вернуть структуру по умолчанию
        self.assertEqual(stats['all_time'], [])
        self.assertEqual(stats['monthly'], [])
        self.assertEqual(stats['top_days'], [])
        self.assertEqual(stats['protection'], (0, 0, 0))

    def test_add_user_warning_exception(self) -> None:
        """Тест добавления предупреждения с исключением"""
        self.mock_cursor.fetchone.side_effect = Exception("Query failed")
        
        warnings_count = self.db_manager.add_user_warning(12345, 67890)
        
        # Должен вернуть 1 при ошибке
        self.assertEqual(warnings_count, 1)

    def test_get_user_warnings_exception(self) -> None:
        """Тест получения предупреждений с исключением"""
        self.mock_cursor.fetchone.side_effect = Exception("Query failed")
        
        warnings_count = self.db_manager.get_user_warnings(12345, 67890)
        
        # Должен вернуть 0 при ошибке
        self.assertEqual(warnings_count, 0)

    def test_reset_user_warnings_exception(self) -> None:
        """Тест сброса предупреждений с исключением"""
        self.mock_conn.commit.side_effect = Exception("Commit failed")
        
        # Должно обработать исключение без падения
        self.db_manager.reset_user_warnings(12345, 67890)

    def test_reset_all_statistics_exception(self) -> None:
        """Тест сброса всей статистики с исключением"""
        self.mock_conn.commit.side_effect = Exception("Commit failed")
        
        # Должно обработать исключение без падения
        self.db_manager.reset_all_statistics(12345)



if __name__ == '__main__':
    unittest.main()
    
    
