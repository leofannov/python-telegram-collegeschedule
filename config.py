# Конфигурация диапазонов ячеек для разных групп
RANGES = {
    'Д013П': {
        'even': {
            'Понедельник': {'schedule': 'BX97:CA110', 'pair_numbers': 'B97:B110', 'time': 'D97:D110'},
            'Вторник': {'schedule': 'BX111:CA124', 'pair_numbers': 'B111:B124', 'time': 'D111:D124'},
            'Среда': {'schedule': 'BX125:CA138', 'pair_numbers': 'B125:B138', 'time': 'D125:D138'},
            'Четверг': {'schedule': 'BX139:CA152', 'pair_numbers': 'B139:B152', 'time': 'D139:D152'},
            'Пятница': {'schedule': 'BX153:CA166', 'pair_numbers': 'B153:B166', 'time': 'D153:D166'},
            'Суббота': {'schedule': 'BX167:CA180', 'pair_numbers': 'B167:B180', 'time': 'D167:D180'}
        },
        'odd': {
            'Понедельник': {'schedule': 'BX10:CA23', 'pair_numbers': 'B10:B23', 'time': 'D10:D23'},
            'Вторник': {'schedule': 'BX24:CA37', 'pair_numbers': 'B24:B37', 'time': 'D24:D37'},
            'Среда': {'schedule': 'BX38:CA51', 'pair_numbers': 'B38:B51', 'time': 'D38:D51'},
            'Четверг': {'schedule': 'BX52:CA65', 'pair_numbers': 'B52:B65', 'time': 'D52:D65'},
            'Пятница': {'schedule': 'BX66:CA79', 'pair_numbers': 'B66:B79', 'time': 'D66:D79'},
            'Суббота': {'schedule': 'BX80:CA93', 'pair_numbers': 'B80:B93', 'time': 'D80:D93'}
        }
    },
    'Д014П': {
        'even': {
            'Понедельник': {'schedule': 'CC97:CF110', 'pair_numbers': 'B97:B110', 'time': 'D97:D110'},
            'Вторник': {'schedule': 'CC111:CF124', 'pair_numbers': 'B111:B124', 'time': 'D111:D124'},
            'Среда': {'schedule': 'CC125:CF138', 'pair_numbers': 'B125:B138', 'time': 'D125:D138'},
            'Четверг': {'schedule': 'CC139:CF152', 'pair_numbers': 'B139:B152', 'time': 'D139:D152'},
            'Пятница': {'schedule': 'CC153:CF166', 'pair_numbers': 'B153:B166', 'time': 'D153:D166'},
            'Суббота': {'schedule': 'CC167:CF180', 'pair_numbers': 'B167:B180', 'time': 'D167:D180'}
        },
        'odd': {
            'Понедельник': {'schedule': 'CC10:CF23', 'pair_numbers': 'B10:B23', 'time': 'D10:D23'},
            'Вторник': {'schedule': 'CC24:CF37', 'pair_numbers': 'B24:B37', 'time': 'D24:D37'},
            'Среда': {'schedule': 'CC38:CF51', 'pair_numbers': 'B38:B51', 'time': 'D38:D51'},
            'Четверг': {'schedule': 'CC52:CF65', 'pair_numbers': 'B52:B65', 'time': 'D52:D65'},
            'Пятница': {'schedule': 'CC66:CF79', 'pair_numbers': 'B66:B79', 'time': 'D66:D79'},
            'Суббота': {'schedule': 'CC80:CF93', 'pair_numbers': 'B80:B93', 'time': 'D80:D93'}
        }
    },
    'Д015П': {
        'even': {
            'Понедельник': {'schedule': 'CH97:CK110', 'pair_numbers': 'B97:B110', 'time': 'D97:D110'},
            'Вторник': {'schedule': 'CH111:CK124', 'pair_numbers': 'B111:B124', 'time': 'D111:D124'},
            'Среда': {'schedule': 'CH125:CK138', 'pair_numbers': 'B125:B138', 'time': 'D125:D138'},
            'Четверг': {'schedule': 'CH139:CK152', 'pair_numbers': 'B139:B152', 'time': 'D139:D152'},
            'Пятница': {'schedule': 'CH153:CK166', 'pair_numbers': 'B153:B166', 'time': 'D153:D166'},
            'Суббота': {'schedule': 'CH167:CK180', 'pair_numbers': 'B167:B180', 'time': 'D167:D180'}
        },
        'odd': {
            'Понедельник': {'schedule': 'CH10:CK23', 'pair_numbers': 'B10:B23', 'time': 'D10:D23'},
            'Вторник': {'schedule': 'CH24:CK37', 'pair_numbers': 'B24:B37', 'time': 'D24:D37'},
            'Среда': {'schedule': 'CH38:CK51', 'pair_numbers': 'B38:B51', 'time': 'D38:D51'},
            'Четверг': {'schedule': 'CH52:CK65', 'pair_numbers': 'B52:B65', 'time': 'D52:D65'},
            'Пятница': {'schedule': 'CH66:CK79', 'pair_numbers': 'B66:B79', 'time': 'D66:D79'},
            'Суббота': {'schedule': 'CH80:CK93', 'pair_numbers': 'B80:B93', 'time': 'D80:D93'}
        }
    }
}

# Список доступных групп (берётся из ключей RANGES)
AVAILABLE_GROUPS = list(RANGES.keys())

# Расписание звонков (первая и вторая половины пар)
BELLS_SCHEDULE = {
    'Понедельник': [
        {'pair': '1 пара', 'first_half': '9:30-10:15', 'second_half': '10:20-11:05'},
        {'pair': '2 пара', 'first_half': '11:25-12:10', 'second_half': '12:15-13:00'},
        {'pair': '3 пара', 'first_half': '13:30-14:15', 'second_half': '14:20-15:05'},
        {'pair': '4 пара', 'first_half': '15:15-16:00', 'second_half': '16:05-16:50'},
        {'pair': '5 пара', 'first_half': '17:00-17:45', 'second_half': '17:50-18:35'},
        {'pair': '6 пара', 'first_half': '18:45-19:30', 'second_half': '19:35-20:20'},
        {'pair': '7 пара', 'first_half': '20:30-21:15', 'second_half': '21:20-22:00'}
    ],
    'Вторник': [
        {'pair': '1 пара', 'first_half': '8:30-9:15', 'second_half': '9:20-10:05'},
        {'pair': '2 пара', 'first_half': '10:25-11:10', 'second_half': '11:15-12:00'},
        {'pair': '3 пара', 'first_half': '12:45-13:30', 'second_half': '13:35-14:20'},
        {'pair': '4 пара', 'first_half': '14:35-15:20', 'second_half': '15:25-16:10'},
        {'pair': '5 пара', 'first_half': '16:20-17:05', 'second_half': '17:10-17:55'},
        {'pair': '6 пара', 'first_half': '18:05-18:50', 'second_half': '18:55-19:40'},
        {'pair': '7 пара', 'first_half': '19:50-20:35', 'second_half': '20:40-21:25'}
    ],
    'Среда': [
        {'pair': '1 пара', 'first_half': '8:30-9:15', 'second_half': '9:20-10:05'},
        {'pair': '2 пара', 'first_half': '10:25-11:10', 'second_half': '11:15-12:00'},
        {'pair': '3 пара', 'first_half': '12:45-13:30', 'second_half': '13:35-14:20'},
        {'pair': '4 пара', 'first_half': '14:35-15:20', 'second_half': '15:25-16:10'},
        {'pair': '5 пара', 'first_half': '16:20-17:05', 'second_half': '17:10-17:55'},
        {'pair': '6 пара', 'first_half': '18:05-18:50', 'second_half': '18:55-19:40'},
        {'pair': '7 пара', 'first_half': '19:50-20:35', 'second_half': '20:40-21:25'}
    ],
    'Четверг': [
        {'pair': '1 пара', 'first_half': '8:30-9:15', 'second_half': '9:20-10:05'},
        {'pair': '2 пара', 'first_half': '10:25-11:10', 'second_half': '11:15-12:00'},
        {'pair': '3 пара', 'first_half': '12:45-13:30', 'second_half': '13:35-14:20'},
        {'pair': '4 пара', 'first_half': '14:35-15:20', 'second_half': '15:25-16:10'},
        {'pair': '5 пара', 'first_half': '16:20-17:05', 'second_half': '17:10-17:55'},
        {'pair': '6 пара', 'first_half': '18:05-18:50', 'second_half': '18:55-19:40'},
        {'pair': '7 пара', 'first_half': '19:50-20:35', 'second_half': '20:40-21:25'}
    ],
    'Пятница': [
        {'pair': '1 пара', 'first_half': '8:30-9:15', 'second_half': '9:20-10:05'},
        {'pair': '2 пара', 'first_half': '10:25-11:10', 'second_half': '11:15-12:00'},
        {'pair': '3 пара', 'first_half': '12:45-13:30', 'second_half': '13:35-14:20'},
        {'pair': '4 пара', 'first_half': '14:35-15:20', 'second_half': '15:25-16:10'},
        {'pair': '5 пара', 'first_half': '16:20-17:05', 'second_half': '17:10-17:55'},
        {'pair': '6 пара', 'first_half': '18:05-18:50', 'second_half': '18:55-19:40'},
        {'pair': '7 пара', 'first_half': '19:50-20:35', 'second_half': '20:40-21:25'}
    ],
    'Суббота': [
        {'pair': '1 пара', 'first_half': '8:30-9:15', 'second_half': '9:20-10:05'},
        {'pair': '2 пара', 'first_half': '10:25-11:10', 'second_half': '11:15-12:00'},
        {'pair': '3 пара', 'first_half': '12:45-13:30', 'second_half': '13:35-14:20'},
        {'pair': '4 пара', 'first_half': '14:35-15:20', 'second_half': '15:25-16:10'},
        {'pair': '5 пара', 'first_half': '16:20-17:05', 'second_half': '17:10-17:55'},
        {'pair': '6 пара', 'first_half': '18:05-18:50', 'second_half': '18:55-19:40'},
        {'pair': '7 пара', 'first_half': '19:50-20:35', 'second_half': '20:40-21:25'}
    ]
}

# Настройки недели
WEEK_CONFIG = {
    'base_week_type': 'odd',  # Тип базовой недели
    'base_week_number': 36      # Номер недели в году для базовой недели
}

# Пути к файлам
EXCEL_FILE = 'cache/schedule.xlsx'
CACHE_FILE = 'cache/schedule_hash.cache'
LAST_UPDATE_FILE = 'cache/last_update.txt'

# Токен бота Telegram
TOKEN = ""

# Настройки для cron
CRON_CHECK_INTERVAL = 10  # Интервал проверки в минутах (каждый час)