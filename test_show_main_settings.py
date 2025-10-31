import unittest
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot import show_main_settings
from telegram.constants import ParseMode


class TestShowMainSettings(unittest.IsolatedAsyncioTestCase):
    """Тесты для функции show_main_settings"""
    
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
    async def test_show_main_settings_with_message_id(self, mock_db: Mock) -> None:
        """Тест показа основных настроек с message_id"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test welcome',
            'min_account_age_days': 7,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 5,
            'anti_flood_enabled': False
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        await show_main_settings(self.update, self.context, 67890, 111)
        
        # Проверяем что edit_message_text был вызван с правильными параметрами
        self.context.bot.edit_message_text.assert_called_once()
        
        # Получаем аргументы вызова
        call_args = self.context.bot.edit_message_text.call_args
        self.assertIsNotNone(call_args)
        
        # Проверяем аргументы
        kwargs = call_args[1]  # keyword arguments
        self.assertEqual(kwargs['chat_id'], 67890)
        self.assertEqual(kwargs['message_id'], 111)
        self.assertIn("⚙️ <b>Основные настройки</b>", kwargs['text'])
        self.assertIn("Статус бота: <b>ВКЛЮЧЕН</b>", kwargs['text'])
        self.assertIn("Мин. возраст аккаунта: <b>7 дн.</b>", kwargs['text'])
        self.assertIn("Удаление сообщений: <b>ВКЛ</b>", kwargs['text'])
        self.assertIn("Анти-флуд: <b>ВЫКЛ</b>", kwargs['text'])
        self.assertIn("Макс. предупреждений: <b>5</b>", kwargs['text'])
        self.assertIn("Ограничения новых: <b>ВКЛ</b>", kwargs['text'])

    @patch('bot.db')
    async def test_show_main_settings_without_message_id(self, mock_db: Mock) -> None:
        """Тест показа основных настроек без message_id"""
        mock_settings: Dict[str, Any] = {
            'enabled': False,
            'welcome_message': 'Test welcome',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': False,
            'delete_service_messages': False,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings
        
        await show_main_settings(self.update, self.context, 67890)
        
        # Проверяем что send_message был вызван с правильными параметрами
        self.context.bot.send_message.assert_called_once()
        
        # Получаем аргументы вызова
        call_args = self.context.bot.send_message.call_args
        self.assertIsNotNone(call_args)
        
        # Проверяем аргументы
        kwargs = call_args[1]  # keyword arguments
        self.assertEqual(kwargs['chat_id'], 67890)
        self.assertIn("⚙️ <b>Основные настройки</b>", kwargs['text'])
        self.assertIn("Статус бота: <b>ВЫКЛЮЧЕН</b>", kwargs['text'])
        self.assertIn("Мин. возраст аккаунта: <b>1 дн.</b>", kwargs['text'])
        self.assertIn("Удаление сообщений: <b>ВЫКЛ</b>", kwargs['text'])
        self.assertIn("Анти-флуд: <b>ВКЛ</b>", kwargs['text'])
        self.assertIn("Макс. предупреждений: <b>3</b>", kwargs['text'])
        self.assertIn("Ограничения новых: <b>ВЫКЛ</b>", kwargs['text'])

    @patch('bot.db')
    async def test_show_main_settings_no_settings(self, mock_db: Mock) -> None:
        """Тест показа основных настроек когда настройки не найдены"""
        mock_db.get_chat_settings.return_value = None
        
        await show_main_settings(self.update, self.context, 67890, 111)
        
        # Проверяем что функции отправки сообщений не вызывались
        self.context.bot.edit_message_text.assert_not_called()
        self.context.bot.send_message.assert_not_called()

    @patch('bot.db')
    async def test_show_main_settings_keyboard_structure(self, mock_db: Mock) -> None:
        """Тест структуры клавиатуры основных настроек"""
        mock_settings: Dict[str, Any] = {
            'enabled': True,
            'welcome_message': 'Test',
            'min_account_age_days': 3,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        mock_db.get_chat_settings.return_value = mock_settings

        await show_main_settings(self.update, self.context, 67890)

        # Проверяем структуру клавиатуры
        self.context.bot.send_message.assert_called_once()

        call_args = self.context.bot.send_message.call_args
        self.assertIsNotNone(call_args)

        kwargs = call_args[1]
        reply_markup = kwargs['reply_markup']

        # Проверяем что клавиатура создана
        self.assertIsNotNone(reply_markup)

        # Проверяем что текст сообщения содержит ожидаемую информацию
        text = kwargs['text']
        self.assertIn("Основные настройки", text)
        self.assertIn("Статус бота", text)
        self.assertIn("Мин. возраст аккаунта", text)

        # Вместо проверки callback_data в тексте, проверяем что сообщение было отправлено
        # с клавиатурой (косвенная проверка)
        self.assertIsNotNone(reply_markup.inline_keyboard)
        self.assertGreater(len(reply_markup.inline_keyboard), 0)
    
    @patch('bot.db')
    async def test_show_main_settings_different_states(self, mock_db: Mock) -> None:
        """Тест показа основных настроек с разными состояниями параметров"""
        # Используем кортежи вместо сложных типов
        test_cases = [
            (
                'Все включено',
                {
                    'enabled': True,
                    'min_account_age_days': 0,
                    'delete_service_messages': False,
                    'anti_flood_enabled': True,
                    'max_warnings': 10,
                    'restrict_new_users': False
                },
                [
                    "Статус бота: <b>ВКЛЮЧЕН</b>",
                    "Мин. возраст аккаунта: <b>0 дн.</b>",
                    "Удаление сообщений: <b>ВЫКЛ</b>",
                    "Анти-флуд: <b>ВКЛ</b>",
                    "Макс. предупреждений: <b>10</b>",
                    "Ограничения новых: <b>ВЫКЛ</b>"
                ]
            ),
            (
                'Все выключено',
                {
                    'enabled': False,
                    'min_account_age_days': 30,
                    'delete_service_messages': True,
                    'anti_flood_enabled': False,
                    'max_warnings': 1,
                    'restrict_new_users': True
                },
                [
                    "Статус бота: <b>ВЫКЛЮЧЕН</b>",
                    "Мин. возраст аккаунта: <b>30 дн.</b>",
                    "Удаление сообщений: <b>ВКЛ</b>",
                    "Анти-флуд: <b>ВЫКЛ</b>",
                    "Макс. предупреждений: <b>1</b>",
                    "Ограничения новых: <b>ВКЛ</b>"
                ]
            )
        ]

        for test_name, settings, expected_texts in test_cases:
            with self.subTest(test_name):
                mock_db.get_chat_settings.return_value = {
                    'enabled': settings['enabled'],
                    'welcome_message': 'Test',
                    'min_account_age_days': settings['min_account_age_days'],
                    'min_join_date_days': 0,
                    'restrict_new_users': settings['restrict_new_users'],
                    'delete_service_messages': settings['delete_service_messages'],
                    'max_warnings': settings['max_warnings'],
                    'anti_flood_enabled': settings['anti_flood_enabled']
                }

                # Сбрасываем моки перед каждым тестом
                self.context.bot.send_message.reset_mock()

                await show_main_settings(self.update, self.context, 67890)

                # Проверяем вызов
                self.context.bot.send_message.assert_called_once()

                # Проверяем текст
                call_args = self.context.bot.send_message.call_args
                self.assertIsNotNone(call_args)

                kwargs = call_args[1]
                text = kwargs['text']

                for expected_text in expected_texts:
                    self.assertIn(expected_text, text)

    @patch('bot.db')
    async def test_show_main_settings_parse_mode(self, mock_db: Mock) -> None:
        """Тест что сообщение отправляется с правильным parse_mode"""
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
        
        await show_main_settings(self.update, self.context, 67890, 111)
        
        # Проверяем что parse_mode установлен в HTML
        self.context.bot.edit_message_text.assert_called_once()
        
        call_args = self.context.bot.edit_message_text.call_args
        self.assertIsNotNone(call_args)
        
        kwargs = call_args[1]
        self.assertEqual(kwargs['parse_mode'], ParseMode.HTML)


if __name__ == '__main__':
    unittest.main()