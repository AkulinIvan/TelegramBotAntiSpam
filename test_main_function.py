import unittest
from unittest.mock import Mock, patch, call
import sys
import os


sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class TestMainFunction(unittest.TestCase):
    """Тесты для основной функции запуска бота main()"""
    
    def setUp(self) -> None:
        """Настройка перед каждым тестом"""
        self.original_exit = sys.exit
        sys.exit = Mock()
    
    def tearDown(self) -> None:
        """Очистка после каждого теста"""
        sys.exit = self.original_exit
    
    @patch('bot.logger')
    @patch('bot.Application')
    @patch('bot.BOT_TOKEN', 'test_token')
    def test_main_successful_startup(self, mock_application: Mock, mock_logger: Mock) -> None:
        """Тест успешного запуска бота"""
        # Мокаем Application builder
        mock_builder = Mock()
        mock_application.builder.return_value = mock_builder
        mock_app_instance = Mock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app_instance
        
        # Мокаем run_polling чтобы он сразу завершался
        mock_app_instance.run_polling.return_value = None
        
        # Импортируем main после настройки моков
        from bot import main
        
        # Вызываем функцию
        main()
        
        # Проверяем что Application был создан с правильным токеном
        mock_application.builder.assert_called_once()
        mock_builder.token.assert_called_once_with('test_token')
        mock_builder.build.assert_called_once()
        
        # Проверяем что обработчики были добавлены
        self.assertGreaterEqual(mock_app_instance.add_handler.call_count, 9)
        
        # Проверяем что был вызван run_polling
        mock_app_instance.run_polling.assert_called_once()
        
        # Проверяем логирование
        mock_logger.info.assert_called_with("Бот запускается...")
    
    @patch('bot.logger')
    @patch('bot.Application')
    @patch('bot.BOT_TOKEN', 'test_token')
    def test_main_handler_registration(self, mock_application: Mock, mock_logger: Mock) -> None:
        """Тест регистрации всех обработчиков"""
        # Мокаем Application
        mock_builder = Mock()
        mock_application.builder.return_value = mock_builder
        mock_app_instance = Mock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app_instance
        
        # Мокаем run_polling чтобы он сразу завершался
        mock_app_instance.run_polling.return_value = None
        
        from bot import main
        
        # Вызываем функцию
        main()
        
        # Получаем все вызовы add_handler
        handler_calls = mock_app_instance.add_handler.call_args_list
        
        # Проверяем количество обработчиков (примерное)
        self.assertGreaterEqual(len(handler_calls), 9)
    
    @patch('bot.logger')
    @patch('bot.Application')
    @patch('bot.BOT_TOKEN', 'test_token')
    def test_main_specific_command_handlers(self, mock_application: Mock, mock_logger: Mock) -> None:
        """Тест конкретных командных обработчиков"""
        # Мокаем Application
        mock_builder = Mock()
        mock_application.builder.return_value = mock_builder
        mock_app_instance = Mock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app_instance
        
        # Мокаем run_polling чтобы он сразу завершался
        mock_app_instance.run_polling.return_value = None
        
        from bot import main
        
        # Мокаем конкретные функции
        with patch('bot.start') as mock_start, \
            patch('bot.menu') as mock_menu, \
            patch('bot.enable_bot') as mock_enable, \
            patch('bot.disable_bot') as mock_disable, \
            patch('bot.help_command') as mock_help, \
            patch('bot.button_handler') as mock_button:
            
            
            # Мокаем CommandHandler и другие классы
            with patch('bot.CommandHandler') as mock_cmd_handler, \
                 patch('bot.CallbackQueryHandler') as mock_callback_handler:
                
                # Вызываем функцию
                main()
                
                # Проверяем вызовы CommandHandler
                expected_command_calls = [
                    call("start", mock_start),
                    call("menu", mock_menu),
                    call("settings", mock_menu),  # Перенаправление на menu
                    call("status", mock_menu),    # Перенаправление на menu
                    call("enable", mock_enable),
                    call("disable", mock_disable),
                    call("help", mock_help)
                ]
                
                # Проверяем что CommandHandler вызывался с правильными параметрами
                for expected_call in expected_command_calls:
                    self.assertIn(expected_call, mock_cmd_handler.call_args_list)
                
                # Проверяем CallbackQueryHandler
                mock_callback_handler.assert_called_once_with(mock_button)
    
    @patch('bot.logger')
    @patch('bot.Application')
    @patch('bot.BOT_TOKEN', 'test_token')
    def test_main_token_casting(self, mock_application: Mock, mock_logger: Mock) -> None:
        """Тест приведения типа токена"""
        mock_builder = Mock()
        mock_application.builder.return_value = mock_builder
        mock_app_instance = Mock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app_instance
        
        # Мокаем run_polling чтобы он сразу завершался
        mock_app_instance.run_polling.return_value = None
        
        from bot import main
        
        # Вызываем функцию
        main()
        
        # Проверяем что токен был передан как строка
        mock_builder.token.assert_called_once_with('test_token')
    
    
    
    @patch('bot.logger')
    @patch('bot.Application')
    @patch('bot.BOT_TOKEN', 'test_token')
    def test_main_application_exception(self, mock_application: Mock, mock_logger: Mock) -> None:
        """Тест обработки исключения при создании Application"""
        # Мокаем исключение при создании Application
        mock_application.builder.side_effect = Exception("Application creation failed")
        
        from bot import main
        
        # Вызываем функцию
        main()
        
        # Проверяем что ошибка была залогирована
        mock_logger.error.assert_called_with("Bot error: Application creation failed")
    
    @patch('bot.logger')
    @patch('bot.Application')
    @patch('bot.BOT_TOKEN', 'test_token')
    def test_main_run_polling_exception(self, mock_application: Mock, mock_logger: Mock) -> None:
        """Тест обработки исключения при запуске polling"""
        # Мокаем Application
        mock_builder = Mock()
        mock_application.builder.return_value = mock_builder
        mock_app_instance = Mock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app_instance
        
        # Мокаем исключение при run_polling
        mock_app_instance.run_polling.side_effect = Exception("Polling failed")
        
        from bot import main
        
        # Вызываем функцию
        main()
        
        # Проверяем что ошибка была залогирована
        mock_logger.error.assert_called_with("Bot error: Polling failed")
    
    @patch('bot.logger')
    @patch('bot.Application')
    @patch('bot.BOT_TOKEN', 'test_token')
    def test_main_error_handler_registration(self, mock_application: Mock, mock_logger: Mock) -> None:
        """Тест регистрации обработчика ошибок"""
        mock_builder = Mock()
        mock_application.builder.return_value = mock_builder
        mock_app_instance = Mock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app_instance
        
        # Мокаем run_polling чтобы он сразу завершался
        mock_app_instance.run_polling.return_value = None
        
        from bot import main
        
        with patch('bot.error_handler') as mock_error_handler:
            # Вызываем функцию
            main()
            
            # Проверяем что обработчик ошибок был зарегистрирован
            mock_app_instance.add_error_handler.assert_called_once_with(mock_error_handler)
    
    @patch('bot.logger')
    @patch('bot.Application')
    @patch('bot.BOT_TOKEN', 'test_token')
    def test_main_logging_info(self, mock_application: Mock, mock_logger: Mock) -> None:
        """Тест информационного логирования при запуске"""
        mock_builder = Mock()
        mock_application.builder.return_value = mock_builder
        mock_app_instance = Mock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app_instance
        
        # Мокаем run_polling чтобы он сразу завершался
        mock_app_instance.run_polling.return_value = None
        
        from bot import main
        
        # Вызываем функцию
        main()
        
        # Проверяем что было информационное сообщение о запуске
        mock_logger.info.assert_called_with("Бот запускается...")


if __name__ == '__main__':
    unittest.main()