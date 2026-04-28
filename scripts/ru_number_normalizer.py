"""
РФ-нормализация телефонных номеров.

Приводит номера к формату +7XXXXXXXXXX (E.164 для РФ).
Отбрасывает не-РФ номера при включённом фильтре.
"""

import re
from typing import Optional


# РФ мобильные DEF-коды (3-значные, начинаются с 9)
RU_MOBILE_DEF_CODES = set(range(900, 1000))  # 900-999

# РФ городские ABC-коды
RU_LANDLINE_ABC_CODES = set(range(300, 500))  # 300-499

# РФ 8-800
RU_TOLLFREE_CODES = {800}

# Короткие/экстренные номера РФ
RU_EMERGENCY_SHORT = {'101', '102', '103', '104', '112'}

# Общий паттерн: цифры из номера
DIGITS_RE = re.compile(r'\d')


def normalize_ru_phone(raw: str, reject_non_ru: bool = True) -> Optional[str]:
    """
    Нормализовать номер к +7XXXXXXXXXX.

    Возвращает None если:
    - номер не похож на телефонный
    - reject_non_ru=True и номер не российский
    """
    if not raw or not raw.strip():
        return None

    s = raw.strip()

    # Короткие экстренные номера
    digits = DIGITS_RE.findall(s)
    digit_str = ''.join(digits)

    if digit_str in RU_EMERGENCY_SHORT:
        return f'+7{digit_str}'

    # Убираем лидирующую 8 или 7 для 11-значных российских номеров
    if len(digit_str) == 11 and digit_str[0] in ('7', '8'):
        core = digit_str[1:]
        return f'+7{core}'

    # 10-значный номер без кода страны — предполагаем РФ
    if len(digit_str) == 10 and digit_str[0] in ('9', '3', '4', '8'):
        return f'+7{digit_str}'

    # Международный формат с +
    if s.startswith('+') and len(digit_str) >= 11:
        country_code = digit_str[:1] if digit_str[0] == '7' else digit_str[:2]
        if country_code == '7':
            return f'+7{digit_str[1:11]}'
        elif reject_non_ru:
            return None
        else:
            return f'+{digit_str}'

    # 7-9 цифр — может быть городской без кода
    if 7 <= len(digit_str) <= 9:
        return None  # недостаточно данных для нормализации

    # Не распознано
    return None


def is_russian_number(normalized: str) -> bool:
    """Проверить что нормализованный номер — российский."""
    if not normalized or not normalized.startswith('+7'):
        return False
    digits = normalized[2:]  # убираем +7
    if len(digits) < 3:
        return False
    def_code = int(digits[:3])
    return def_code in RU_MOBILE_DEF_CODES or def_code in RU_LANDLINE_ABC_CODES or def_code in RU_TOLLFREE_CODES


def is_mobile_ru(normalized: str) -> bool:
    """Мобильный РФ номер (DEF 9xx)."""
    if not normalized or not normalized.startswith('+7'):
        return False
    digits = normalized[2:]
    if len(digits) < 3:
        return False
    return int(digits[:3]) in RU_MOBILE_DEF_CODES


def is_landline_ru(normalized: str) -> bool:
    """Городской РФ номер (ABC 3xx-4xx)."""
    if not normalized or not normalized.startswith('+7'):
        return False
    digits = normalized[2:]
    if len(digits) < 3:
        return False
    return int(digits[:3]) in RU_LANDLINE_ABC_CODES


def is_tollfree_ru(normalized: str) -> bool:
    """8-800 номер."""
    if not normalized or not normalized.startswith('+7'):
        return False
    digits = normalized[2:]
    if len(digits) < 3:
        return False
    return int(digits[:3]) in RU_TOLLFREE_CODES


def is_short_code(normalized: str) -> bool:
    """Короткий/экстренный номер."""
    if not normalized or not normalized.startswith('+7'):
        return False
    digits = normalized[2:]
    return digits in RU_EMERGENCY_SHORT or (len(digits) <= 4 and digits.isdigit())


def get_def_code(normalized: str) -> Optional[int]:
    """Получить DEF/ABC код из нормализованного номера."""
    if not normalized or not normalized.startswith('+7'):
        return None
    digits = normalized[2:]
    if len(digits) < 3:
        return None
    return int(digits[:3])


if __name__ == '__main__':
    # Quick test
    test_numbers = [
        '+79854430013', '89854430013', '79854430013',
        '+79161234567', '+74957754747', '+78005553535',
        '88005553535', '103', '112', '+12125551234',
        '89161234567', '+79001234567', '89001234567',
    ]
    for n in test_numbers:
        norm = normalize_ru_phone(n)
        if norm:
            print(f'{n:20s} → {norm:15s} RU={is_russian_number(norm)} mobile={is_mobile_ru(norm)} landline={is_landline_ru(norm)} tollfree={is_tollfree_ru(norm)} short={is_short_code(norm)}')
        else:
            print(f'{n:20s} → None (rejected)')
