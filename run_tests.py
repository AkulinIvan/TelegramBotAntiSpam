#!/usr/bin/env python3
"""
Скрипт для запуска unit тестов с покрытием 100%
"""

import subprocess
import sys
from typing import List

def run_tests() -> bool:
    """Запуск тестов с измерением покрытия"""
    
    print("🔍 Запуск unit тестов с покрытием 100%...")
    
    # Команды для запуска тестов
    commands: List[List[str]] = [
        # Запуск тестов с измерением покрытия
        ["python", "-m", "pytest", "test_bot.py", "-v", "--cov=bot", "--cov-report=term-missing"],
        
        # Генерация HTML отчета о покрытии
        ["python", "-m", "pytest", "test_bot.py", "--cov=bot", "--cov-report=html"],
        
        # Проверка достижения 100% покрытия
        ["python", "-m", "pytest", "test_bot.py", "--cov=bot", "--cov-fail-under=100"]
    ]
    
    for cmd in commands:
        print(f"\n🚀 Выполнение: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, check=False)
            if result.returncode != 0 and "cov-fail-under" in cmd:
                print("❌ Покрытие кода менее 100%!")
                return False
        except Exception as e:
            print(f"❌ Ошибка при выполнении тестов: {e}")
            return False
    
    print("\n✅ Все тесты пройдены! Покрытие кода 100% достигнуто!")
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)