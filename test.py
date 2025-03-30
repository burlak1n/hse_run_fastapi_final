from thefuzz import fuzz
import re
from natasha import AddrExtractor, MorphVocab

morph_vocab = MorphVocab()
address_extractor = AddrExtractor(morph_vocab)

def normalize_address(address: str) -> str:
    matches = address_extractor(address)
    if not matches:
        return address.lower().strip()
    
    normalized_parts = []
    for match in matches:
        normalized_parts.append(match.fact.value)
    
    return ', '.join(normalized_parts).lower().strip()

def normalize_name(name):
    name = name.lower()
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Нормализация инициалов
    name = re.sub(r'\b([а-я])\.\s*([а-я])\.', r'\1\2', name)
    name = re.sub(r'\b([а-я])\.', r'\1', name)
    
    # Уточняем список стоп-слов
    stop_words = ["театр", "имени", "им.", "оперный"]
    for word in stop_words:
        name = re.sub(rf'\b{word}\b', '', name)
    
    return re.sub(r'\s+', ' ', name).strip()
    
def is_address_match(user_input, true_address, threshold=85):  # Повышен порог
    user_norm = normalize_address(user_input)
    true_norm = normalize_address(true_address)
    return fuzz.ratio(user_norm, true_norm) >= threshold

def is_name_match(user_input, true_name, threshold=80):
    user_norm = normalize_name(user_input)
    true_norm = normalize_name(true_name)
    
    # Проверка на минимальную длину совпадения
    min_length = min(len(user_norm), len(true_norm))
    if min_length < 10:
        return False
    
    # Проверка на ключевые слова
    required_keywords = ["московский", "пушкин"]
    if not any(keyword in user_norm for keyword in required_keywords):
        return False
    
    return fuzz.ratio(user_norm, true_norm) >= threshold

def is_correct_input(user_input, true_address, true_name):
    # Проверяем, похож ли ввод на адрес
    if is_address_match(user_input, true_address):
        return True
    
    # Проверяем, похож ли ввод на название
    if is_name_match(user_input, true_name):
        return True
    
    # Если ввод содержит и адрес, и название (например, через запятую)
    parts = [p.strip() for p in user_input.split(",") if p.strip()]
    if len(parts) >= 2:
        part1_is_address = is_address_match(parts[0], true_address)
        part2_is_name = is_name_match(parts[1], true_name)
        if part1_is_address and part2_is_name:
            return True
        
        part1_is_name = is_name_match(parts[0], true_name)
        part2_is_address = is_address_match(parts[1], true_address)
        if part1_is_name and part2_is_address:
            return True
    
    return False  # Возвращаем False, если ввод не соответствует ни адресу, ни названию

def is_valid_address(address: str) -> bool:
    normalized = preprocess_address(address)
    
    # Ключевые слова для адресов
    address_keywords = ['бульвар', 'улица', 'проспект', 'переулок', 'набережная']
    
    # Проверка наличия ключевых слов и номера дома
    if any(keyword in normalized for keyword in address_keywords):
        parts = normalized.split()
        if any(part.isdigit() for part in parts):
            return True
    
    # Fallback для Natasha
    matches = address_extractor(normalized)
    if matches:
        return True
    
    return False

# Примеры
TRUE_ADDRESS = "Тверской бульвар дом 23"
TRUE_NAME = "московский драматический театр имени а с пушкина"

inputs = [
    # Правильные адреса
    "Тверской бул., 23", # исходный адрес

    "Тверской бул., д. 23",
    "Тверской бул., дом 23",
    "Тверской бул., д 23",
    "тверской бул, 23",
    "тверской бул, д. 23",
    "тверской бул, д 23",
    "тверской бул, дом 23",
    "тверской бул 23",
    "тверской бул д 23",
    "тверской бул дом 23",
    "тверской бул д. 23",
    "тверской 23",
    "тверской д. 23",
    "тверской дом 23",
    "тверской д 23",
    "тверской, 23",
    "тверской, д 23",
    "тверской, дом 23",
    "тверской, д. 23",
    "тверской бульвар д 23",
    "тверской бульвар дом 23",
    "тверской бульвар д. 23",
    "тверской бульвар, 23",
    "тверской бульвар, д 23",
    "тверской бульвар, дом 23",
    "тверской бульвар, д. 23",
    
    # Правильные названия
    "Московский драматический театр имени Пушкина",
    "Московский драматический театр А.С. Пушкина",
    "Московский драматический театр Пушкина",
    "Московский театр Пушкина",
    "Московский театр имени А.С. Пушкина",
    "Московский театр имени Пушкина",
    "драматический театр имени А.С. Пушкина",
    "драматический театр имени Пушкина",
    "драматический театр Пушкина",
    "театр имени А.С. Пушкина",
    "театр имени Пушкина",
    "театр Пушкина",
    
    # Неправильные адреса
    "Тверской бульвар дом 25",
    "Пушкинская улица дом 23",
    "Бульвар Тверской, 23",
    "Москва, Тверской бульвар, 23",
    "Тверской б-р, 23",
    
    # Неправильные названия
    "Московский драматический театр имени Лермонтова",
    "Московский оперный театр имени Пушкина",
    "Санкт-Петербургский драматический театр имени Пушкина",
    "Московский театр П.",
    "Пушкинский театр Москвы",
]

for user_input in inputs:
    print(f"{user_input} → {is_correct_input(user_input, TRUE_ADDRESS, TRUE_NAME)}")