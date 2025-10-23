"""
Модуль для автоматической перезагрузки сервера с освобождением порта.

Использование:
    from restart_server import ServerReloader
    
    reloader = ServerReloader(port=8000, start_command="python app.py")
    reloader.restart()

Или как скрипт из корня проекта:
    python restart_server.py --port 5000 --command "python3 app.py"
    python restart_server.py  # По умолчанию порт 5000, команда "python3 app.py"
"""
import sys
import os
import time
import subprocess
import logging
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore


class ServerReloader:
    """Утилита для перезапуска сервера с автоматическим освобождением порта."""
    
    def __init__(self, port: int, start_command: str, wait_time: float = 2.5):
        """
        Инициализация перезагрузчика сервера.
        
        Args:
            port: Номер порта для освобождения
            start_command: Команда запуска сервера (например, "python app.py")
            wait_time: Время ожидания между остановкой и запуском (секунды)
        """
        self.port = port
        self.start_command = start_command
        self.wait_time = wait_time
        self.logger = self._setup_logger()
        
        if psutil is None:
            self.logger.warning(
                "⚠️  psutil не установлен. Используется fallback через lsof/netstat. "
                "Для корректной работы установите: pip install psutil"
            )
    
    def _setup_logger(self) -> logging.Logger:
        """Настройка логгера для вывода в консоль."""
        logger = logging.getLogger('ServerReloader')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def free_port(self) -> bool:
        """
        Освобождает порт, завершая процессы, которые его занимают.
        
        Returns:
            True если порт был освобождён или уже свободен, False при ошибке
        """
        self.logger.info(f"🔍 Проверка порта {self.port}...")
        
        if psutil:
            return self._free_port_psutil()
        else:
            return self._free_port_fallback()
    
    def _free_port_psutil(self) -> bool:
        """Освобождение порта через psutil (предпочтительный метод)."""
        killed = []
        
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr.port == self.port and conn.pid:
                    try:
                        proc = psutil.Process(conn.pid)
                        proc_name = proc.name()
                        self.logger.info(
                            f"🔪 Завершаю процесс {proc_name} (PID: {conn.pid}) на порту {self.port}"
                        )
                        proc.terminate()
                        killed.append(conn.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        self.logger.warning(f"⚠️  Не удалось завершить процесс {conn.pid}: {e}")
            
            # Даём время на корректное завершение
            if killed:
                time.sleep(0.5)
                # Принудительное завершение если процесс ещё жив
                for pid in killed:
                    try:
                        proc = psutil.Process(pid)
                        if proc.is_running():
                            self.logger.warning(f"⚠️  Принудительное завершение процесса {pid}")
                            proc.kill()
                    except psutil.NoSuchProcess:
                        pass  # Процесс уже завершён
                
                self.logger.info(f"✅ Порт {self.port} освобождён (завершено процессов: {len(killed)})")
            else:
                self.logger.info(f"✅ Порт {self.port} свободен")
            
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Ошибка при освобождении порта: {e}")
            return False
    
    def _free_port_fallback(self) -> bool:
        """Освобождение порта через системные команды (fallback для macOS/Linux)."""
        try:
            # Определяем команду в зависимости от ОС
            if sys.platform == 'darwin':  # macOS
                cmd = f"lsof -ti:{self.port} | xargs kill -9 2>/dev/null || true"
            elif sys.platform.startswith('linux'):
                cmd = f"fuser -k {self.port}/tcp 2>/dev/null || true"
            else:
                self.logger.error(f"❌ Неподдерживаемая ОС: {sys.platform}")
                return False
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.logger.info(f"✅ Порт {self.port} освобождён")
                return True
            else:
                self.logger.warning(f"⚠️  Команда вернула код {result.returncode}")
                return True  # Считаем успехом, порт может быть уже свободен
        
        except Exception as e:
            self.logger.error(f"❌ Ошибка при освобождении порта: {e}")
            return False
    
    def start_server(self) -> Optional[subprocess.Popen]:
        """
        Запускает сервер с указанной командой.
        
        Returns:
            subprocess.Popen объект запущенного процесса или None при ошибке
        """
        try:
            self.logger.info(f"🚀 Запуск сервера: {self.start_command}")
            
            # Разбиваем команду на части для subprocess
            cmd_parts = self.start_command.split()
            
            # Запускаем в фоновом режиме
            process = subprocess.Popen(
                cmd_parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.getcwd()
            )
            
            # Даём серверу время на старт
            time.sleep(1)
            
            # Проверяем, что процесс запустился
            if process.poll() is None:
                self.logger.info(f"✅ Сервер запущен (PID: {process.pid})")
                return process
            else:
                stdout, stderr = process.communicate()
                self.logger.error(f"❌ Сервер завершился сразу после запуска")
                if stderr:
                    self.logger.error(f"Ошибка: {stderr}")
                return None
        
        except Exception as e:
            self.logger.error(f"❌ Ошибка при запуске сервера: {e}")
            return None
    
    def restart(self) -> bool:
        """
        Полный цикл перезапуска: освобождение порта, ожидание, запуск сервера.
        
        Returns:
            True если перезапуск прошёл успешно, False при ошибке
        """
        self.logger.info("="*60)
        self.logger.info("🔄 Начинаю перезагрузку сервера...")
        self.logger.info("="*60)
        
        # 1. Освобождаем порт
        if not self.free_port():
            self.logger.error("❌ Не удалось освободить порт")
            return False
        
        # 2. Ждём перед запуском
        self.logger.info(f"⏳ Ожидание {self.wait_time} сек перед запуском...")
        time.sleep(self.wait_time)
        
        # 3. Запускаем сервер
        process = self.start_server()
        
        if process:
            self.logger.info("="*60)
            self.logger.info("✅ Перезагрузка завершена успешно!")
            self.logger.info(f"📍 Сервер работает на порту {self.port}")
            self.logger.info("="*60)
            return True
        else:
            self.logger.error("="*60)
            self.logger.error("❌ Перезагрузка завершилась с ошибкой")
            self.logger.error("="*60)
            return False


def main():
    """Точка входа при запуске как скрипт."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Перезапуск сервера с автоматическим освобождением порта'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8081,
        help='Номер порта для освобождения (по умолчанию: 8081)'
    )
    parser.add_argument(
        '--command', '-c',
        type=str,
        default='python3 app.py',
        help='Команда запуска сервера (по умолчанию: "python3 app.py")'
    )
    parser.add_argument(
        '--wait', '-w',
        type=float,
        default=2.5,
        help='Время ожидания между остановкой и запуском в секундах (по умолчанию: 2.5)'
    )
    
    args = parser.parse_args()
    
    reloader = ServerReloader(
        port=args.port,
        start_command=args.command,
        wait_time=args.wait
    )
    
    success = reloader.restart()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
