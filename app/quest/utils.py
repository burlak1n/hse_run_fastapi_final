import re


def normalize_text(text: str) -> set[str]:
    # Извлекаем слова и сразу возвращаем множество
    return set(re.findall(r'\b\w+\b', text.lower()))

def compare_strings(str1: str, str2: str) -> bool:
    # Сравниваем множества слов
    return normalize_text(str1) == normalize_text(str2)
