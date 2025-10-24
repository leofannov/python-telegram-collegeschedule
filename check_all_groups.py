import sys
import os
sys.path.append(os.path.dirname(__file__))

from change_detector import ChangeDetector
from change_notifier import ChangeNotifier
from group_manager import GroupManager
from config import TOKEN

def check_all_groups():
    """Проверить все группы из конфига"""
    print("🎯 ПРОВЕРКА ВСЕХ ГРУПП ИЗ КОНФИГА")
    
    gm = GroupManager()
    all_groups = gm.get_available_groups()
    
    print(f"📊 Всего групп: {len(all_groups)}")
    print(f"📋 Список групп: {all_groups}")
    
    detector = ChangeDetector()
    notifier = ChangeNotifier()
    
    for group in all_groups:
        print(f"\n{'='*40}")
        print(f"🔍 ПРОВЕРКА ГРУППЫ: {group}")
        print(f"{'='*40}")
        
        try:
            # Проверяем изменения
            has_changed = detector.has_changed(group)
            
            if has_changed:
                print(f"🎉 ГРУППА {group}: ИЗМЕНЕНИЯ ОБНАРУЖЕНЫ!")
            else:
                print(f"✅ ГРУППА {group}: изменений нет")
                
        except Exception as e:
            print(f"❌ ОШИБКА В ГРУППЕ {group}: {e}")
            continue
    
    print(f"\n{'='*50}")
    print("🏁 ПРОВЕРКА ВСЕХ ГРУПП ЗАВЕРШЕНА")
    print(f"{'='*50}")

if __name__ == "__main__":
    check_all_groups()