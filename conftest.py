# conftest.py
import pytest
import asyncio
from unittest.mock import Mock, patch
from typing import Generator

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Создание event loop для асинхронных тестов"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_db() -> Generator[Mock, None, None]:
    """Фикстура для мока базы данных"""
    with patch('bot.db') as mock:
        instance = mock.return_value
        instance.get_chat_settings.return_value = {
            'enabled': True,
            'welcome_message': 'Test welcome',
            'min_account_age_days': 1,
            'min_join_date_days': 0,
            'restrict_new_users': True,
            'delete_service_messages': True,
            'max_warnings': 3,
            'anti_flood_enabled': True
        }
        yield instance

@pytest.fixture
def telegram_update() -> Mock:
    """Фикстура для создания мока Telegram Update"""
    # Создаем моки без указания spec, чтобы избежать проблем с импортом
    update = Mock()
    user = Mock()
    user.id = 12345
    user.first_name = "TestUser"
    
    chat = Mock()
    chat.id = 67890
    chat.type = "private"
    chat.title = "Test Chat"
    
    message = Mock()
    message.chat = chat
    message.from_user = user
    message.message_id = 111
    
    update.effective_user = user
    update.effective_chat = chat
    update.message = message
    
    return update

@pytest.fixture
def telegram_context() -> Mock:
    """Фикстура для создания мока Telegram Context"""
    context = Mock()
    context.bot = Mock()
    context.user_data = {}
    return context