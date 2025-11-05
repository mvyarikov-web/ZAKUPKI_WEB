"""
Простой тест для модуля server_reloader.py
"""
import sys
import os

# Добавляем путь к utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.server_reloader import ServerReloader


def test_free_port():
    """Тест освобождения порта (без запуска сервера)."""
    print("\n" + "="*60)
    print("ТЕСТ 1: Освобождение порта 5000")
    print("="*60)
    
    reloader = ServerReloader(port=5000, start_command="dummy")
    success = reloader.free_port()
    
    if success:
        print("✅ Тест пройден: порт освобождён")
    else:
        print("❌ Тест провален: ошибка при освобождении порта")
    
    return success


def test_import():
    """Тест импорта модуля."""
    print("\n" + "="*60)
    print("ТЕСТ 2: Проверка импорта")
    print("="*60)
    
    try:
        print("✅ Тест пройден: модуль импортируется")
        return True
    except Exception as e:
        print(f"❌ Тест провален: {e}")
        return False


def test_class_init():
    """Тест инициализации класса."""
    print("\n" + "="*60)
    print("ТЕСТ 3: Инициализация класса")
    print("="*60)
    
    try:
        reloader = ServerReloader(
            port=8000,
            start_command="echo 'test'",
            wait_time=1.0
        )
        print("✅ Тест пройден: класс создан")
        print(f"   - Порт: {reloader.port}")
        print(f"   - Команда: {reloader.start_command}")
        print(f"   - Время ожидания: {reloader.wait_time}")
        return True
    except Exception as e:
        print(f"❌ Тест провален: {e}")
        return False


def main():
    """Запуск всех тестов."""
    print("\n🧪 Запуск тестов для server_reloader.py\n")
    
    results = []
    
    # Тест 1: Импорт
    results.append(("Импорт модуля", test_import()))
    
    # Тест 2: Инициализация
    results.append(("Инициализация класса", test_class_init()))
    
    # Тест 3: Освобождение порта
    results.append(("Освобождение порта", test_free_port()))
    
    # Итоги
    print("\n" + "="*60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*60)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} - {name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print(f"\nВсего: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("\n🎉 Все тесты пройдены успешно!")
        return 0
    else:
        print(f"\n⚠️  Некоторые тесты провалены ({total - passed})")
        return 1


if __name__ == '__main__':
    sys.exit(main())
