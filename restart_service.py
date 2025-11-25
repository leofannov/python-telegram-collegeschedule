import subprocess
import time
import sys
import ctypes

def is_admin():
    """Проверяем права администратора"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def restart_service(service_name="TelegramBotService"):
    """Перезагружает службу Windows используя SC команды"""
    try:
        print(f"🔄 Перезагрузка службы {service_name}...")
        
        # Проверяем существование службы
        try:
            result = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode != 0:
                print(f"❌ Служба {service_name} не найдена")
                return False
            print("✅ Служба найдена")
        except Exception as e:
            print(f"❌ Ошибка проверки службы: {e}")
            return False
        
        # Останавливаем службу
        print("⏹️ Останавливаем службу...")
        try:
            stop_result = subprocess.run(
                ["sc", "stop", service_name],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='ignore'
            )
            
            if stop_result.returncode == 0:
                print("✅ Служба остановлена")
            else:
                # Если служба уже остановлена - это не ошибка
                if "1062" in stop_result.stdout or "1062" in stop_result.stderr:
                    print("ℹ️ Служба уже была остановлена")
                else:
                    print(f"⚠️ Не удалось остановить службу (код: {stop_result.returncode})")
        except subprocess.TimeoutExpired:
            print("❌ Таймаут при остановке службы")
            return False
        
        # Ждем
        print("⏳ Ждем 5 секунд...")
        time.sleep(5)
        
        # Проверяем статус после остановки
        status_after_stop = get_service_status(service_name)
        print(f"Статус после остановки: {status_after_stop}")
        
        # Если служба уже запущена (автоперезапуск), считаем успехом
        if status_after_stop == "RUNNING":
            print("✅ Служба уже автоматически перезапущена")
            return True
        
        # Запускаем службу только если она остановлена
        if status_after_stop == "STOPPED":
            print("▶️ Запускаем службу...")
            try:
                start_result = subprocess.run(
                    ["sc", "start", service_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding='utf-8',
                    errors='ignore'
                )
                
                if start_result.returncode == 0:
                    print("✅ Служба запущена")
                elif start_result.returncode == 1056:
                    print("✅ Служба уже запущена (код 1056)")
                    return True
                else:
                    print(f"❌ Ошибка запуска службы (код: {start_result.returncode})")
                    return False
            except subprocess.TimeoutExpired:
                print("❌ Таймаут при запуске службы")
                return False
        else:
            print(f"⚠️ Неизвестный статус службы: {status_after_stop}")
            return False
        
        # Проверяем финальный статус
        print("🔍 Проверяем финальный статус...")
        time.sleep(3)
        
        final_status = get_service_status(service_name)
        print(f"Финальный статус: {final_status}")
        
        if final_status == "RUNNING":
            print("🎉 Служба успешно перезапущена и работает!")
            return True
        else:
            print(f"⚠️ Служба не запущена. Статус: {final_status}")
            return False
            
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        return False

def get_service_status(service_name="TelegramBotService"):
    """Получает статус службы"""
    try:
        result = subprocess.run(
            ["sc", "query", service_name],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            if "RUNNING" in result.stdout:
                return "RUNNING"
            elif "STOPPED" in result.stdout:
                return "STOPPED"
            elif "START_PENDING" in result.stdout:
                return "START_PENDING"
            elif "STOP_PENDING" in result.stdout:
                return "STOP_PENDING"
            else:
                return "UNKNOWN"
        else:
            return "NOT_FOUND"
            
    except Exception:
        return "ERROR"

if __name__ == "__main__":
    service_name = "rasp13"  # Используем правильное имя службы
    
    # Проверяем права администратора
    if not is_admin():
        print("❌ Требуются права администратора!")
        print("Запустите скрипт от имени администратора")
        sys.exit(1)
    
    print("=" * 50)
    print("🔧 PYTHON SERVICE RESTART TOOL")
    print("=" * 50)
    
    # Показываем текущий статус
    initial_status = get_service_status(service_name)
    print(f"Начальный статус: {initial_status}")
    print()
    
    # Перезагружаем службу
    success = restart_service(service_name)
    
    print("\n" + "=" * 50)
    if success:
        print("✅ ПЕРЕЗАГРУЗКА УСПЕШНА")
    else:
        print("❌ ПЕРЕЗАГРУЗКА НЕ УДАЛАСЯ")
    print("=" * 50)
    
    sys.exit(0 if success else 1)