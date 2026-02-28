#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OBWLauto
"""

import os
import re
import sys
import time
import base64
import random
import urllib.request
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Tuple, Optional

# ========== КОНФИГУРАЦИЯ ==========
CONFIG = {
    'OUTPUT_FILE': 'ru_all_configs.txt',              # Все конфиги
    'VLESS_REALITY_FILE': 'ru_vless_reality.txt',      # Только VLESS Reality
    'HYSTERIA_FILE': 'ru_hysteria2.txt',                # Только Hysteria2
    'TUIC_FILE': 'ru_tuic.txt',                         # Только TUIC
    'MAX_CONFIGS': 60,                                   # Максимум конфигов (~60)
    'TIMEOUT': 15,
    'MAX_WORKERS': 5,
    'COLORS': {
        'GREEN': '\033[92m',
        'YELLOW': '\033[93m',
        'RED': '\033[91m',
        'BLUE': '\033[94m',
        'CYAN': '\033[96m',
        'NC': '\033[0m'
    }
}

# ========== РОССИЙСКИЕ ИСТОЧНИКИ ==========

# 1. GitHub репозитории с фокусом на РФ 
GITHUB_RU_SOURCES = [
    # igareck/vpn-configs-for-russia - проверенные для белых списков
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_VLESS_RUS_mobile.txt',
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_VLESS_RUS.txt',
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_SS+All_RUS.txt',
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-checked.txt',
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-SNI-RU-all.txt',
    
    # nikita29a/FreeProxyList - ежедневное обновление 
    *[f'https://raw.githubusercontent.com/nikita29a/FreeProxyList/raw/refs/heads/main/mirror/{i}.txt' for i in range(1, 26)],
    
    # kort0881/vpn-vless-configs-russia 
    'https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/ru-sni/vless_ru.txt',
    'https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/clean/vless.txt',
    'https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/clean/vmess.txt',
]

# 2. Cloudflare Workers подписки 
WORKER_SUBSCRIPTIONS = [
    'https://vlesstrojan.alexanderyurievich88.workers.dev?token=sub',
    'https://vlesstrojan.alexanderyurievich88.workers.dev?token=sub&filter=vless',
    'https://thedarkghostsvpn.hohlov2006362018.workers.dev/',
]

# 3. Прямые подписки
SUBSCRIPTION_URLS = [
    'https://raw.githubusercontent.com/MhdiTaheri/V2rayCollector/main/sub/normal/vless',
    'https://raw.githubusercontent.com/MhdiTaheri/V2rayCollector/main/sub/normal/vmess',
    'https://raw.githubusercontent.com/MhdiTaheri/V2rayCollector/main/sub/normal/trojan',
]

# 4. CIDR и SNI подписки для обхода белых списков 
WHITELIST_BYPASS = [
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt',
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt',
    'https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-all.txt',
]

# 5. Дополнительные источники
ADDITIONAL_RU_SOURCES = [
    'https://raw.githubusercontent.com/4n0nymou3/multi-proxy-config-fetcher/refs/heads/main/configs/proxy_configs.txt',
]

# Собираем все источники
ALL_SOURCES = (
    GITHUB_RU_SOURCES + 
    WORKER_SUBSCRIPTIONS + 
    SUBSCRIPTION_URLS + 
    WHITELIST_BYPASS + 
    ADDITIONAL_RU_SOURCES
)

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def log(msg: str, level: str = 'INFO'):
    """Красивый вывод"""
    colors = CONFIG['COLORS']
    timestamp = datetime.now().strftime('%H:%M:%S')
    
    color_map = {
        'INFO': colors['BLUE'],
        'SUCCESS': colors['GREEN'],
        'WARN': colors['YELLOW'],
        'ERROR': colors['RED'],
        'HEADER': colors['CYAN']
    }
    
    color = color_map.get(level, colors['NC'])
    print(f"{color}[{timestamp}] [{level}]{colors['NC']} {msg}")

def fetch_url(url: str) -> Optional[str]:
    """Загружает содержимое URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=CONFIG['TIMEOUT']) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        log(f"Ошибка загрузки {url[:50]}...: {e}", 'ERROR')
        return None

def extract_configs_from_text(text: str) -> List[str]:
    """Извлекает все конфиги из текста"""
    if not text:
        return []
    
    # Паттерны для всех протоколов
    patterns = [
        r'vless://[^\s<>"\']+',
        r'vmess://[^\s<>"\']+',
        r'trojan://[^\s<>"\']+',
        r'ss://[^\s<>"\']+',
        r'hysteria2://[^\s<>"\']+',
        r'tuic://[^\s<>"\']+',
        r'hy2://[^\s<>"\']+',
    ]
    
    configs = []
    for pattern in patterns:
        found = re.findall(pattern, text)
        configs.extend(found)
    
    # Если ничего не нашли, возможно это base64 подписка
    if not configs and len(text) < 10000:  # Не пытаемся декодировать огромные файлы
        try:
            decoded = base64.b64decode(text.strip()).decode('utf-8', errors='ignore')
            for pattern in patterns:
                found = re.findall(pattern, decoded)
                configs.extend(found)
        except:
            pass
    
    return configs

def remove_duplicates(configs: List[str]) -> List[str]:
    """Удаляет дубликаты с сохранением порядка"""
    seen = set()
    unique = []
    
    for cfg in configs:
        # Создаем уникальный ключ (берем первые 100 символов для сравнения)
        key = cfg[:100]
        if key not in seen:
            seen.add(key)
            unique.append(cfg)
    
    removed = len(configs) - len(unique)
    if removed > 0:
        log(f"🗑️ Удалено дубликатов: {removed}", 'WARN')
    
    return unique

def categorize_config(config: str) -> str:
    """Определяет тип конфига"""
    if config.startswith('vless://'):
        if 'security=reality' in config:
            return 'vless_reality'
        return 'vless'
    elif config.startswith('vmess://'):
        return 'vmess'
    elif config.startswith('trojan://'):
        return 'trojan'
    elif config.startswith('ss://'):
        return 'shadowsocks'
    elif config.startswith('hysteria2://') or config.startswith('hy2://'):
        return 'hysteria2'
    elif config.startswith('tuic://'):
        return 'tuic'
    return 'other'

def prioritize_configs(configs: List[str]) -> List[str]:
    """Приоритизация конфигов (Reality > Hysteria2 > TUIC > остальные)"""
    priority_order = {
        'vless_reality': 1,
        'hysteria2': 2,
        'tuic': 3,
        'vless': 4,
        'trojan': 5,
        'vmess': 6,
        'shadowsocks': 7,
        'other': 8
    }
    
    # Группируем по типу
    grouped = {}
    for cfg in configs:
        ctype = categorize_config(cfg)
        if ctype not in grouped:
            grouped[ctype] = []
        grouped[ctype].append(cfg)
    
    # Сортируем по приоритету
    sorted_configs = []
    for ctype in sorted(priority_order.keys(), key=lambda x: priority_order[x]):
        if ctype in grouped:
            # Внутри группы случайным образом перемешиваем
            random.shuffle(grouped[ctype])
            sorted_configs.extend(grouped[ctype])
    
    return sorted_configs

def select_top_configs(configs: List[str], limit: int = CONFIG['MAX_CONFIGS']) -> List[str]:
    """Выбирает топ N конфигов с приоритетом"""
    if len(configs) <= limit:
        return configs
    
    # Приоритизируем
    prioritized = prioritize_configs(configs)
    
    # Берем первые limit
    selected = prioritized[:limit]
    
    log(f"🎯 Выбрано {len(selected)} лучших конфигов из {len(configs)}", 'SUCCESS')
    return selected

def save_configs_by_type(configs: List[str], output_dir: str = '.'):
    """Сохраняет конфиги по типам в отдельные файлы"""
    by_type = {}
    
    for cfg in configs:
        ctype = categorize_config(cfg)
        if ctype not in by_type:
            by_type[ctype] = []
        by_type[ctype].append(cfg)
    
    # Сохраняем каждый тип в отдельный файл
    type_to_file = {
        'vless_reality': CONFIG['VLESS_REALITY_FILE'],
        'hysteria2': CONFIG['HYSTERIA_FILE'],
        'tuic': CONFIG['TUIC_FILE'],
    }
    
    for ctype, filename in type_to_file.items():
        if ctype in by_type:
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(by_type[ctype]))
            log(f"💾 Сохранено {len(by_type[ctype])} {ctype} конфигов в {filename}", 'SUCCESS')

def main():
    """Основная функция"""
    print(f"\n{CONFIG['COLORS']['CYAN']}{'='*60}{CONFIG['COLORS']['NC']}")
    print(f"{CONFIG['COLORS']['CYAN']}   RUSSIAN VPN CONFIG AGGREGATOR (WHITELIST BYPASS){CONFIG['COLORS']['NC']}")
    print(f"{CONFIG['COLORS']['CYAN']}{'='*60}{CONFIG['COLORS']['NC']}\n")
    
    log(f"📡 Источников: {len(ALL_SOURCES)}", 'INFO')
    log(f"🎯 Лимит конфигов: ~{CONFIG['MAX_CONFIGS']}", 'INFO')
    log(f"⏰ Обновление: каждые 8 часов", 'INFO')
    print()
    
    # Загружаем все источники параллельно
    all_raw_configs = []
    
    with ThreadPoolExecutor(max_workers=CONFIG['MAX_WORKERS']) as executor:
        future_to_url = {
            executor.submit(fetch_url, url): url 
            for url in ALL_SOURCES
        }
        
        completed = 0
        for future in as_completed(future_to_url):
            completed += 1
            url = future_to_url[future]
            try:
                content = future.result()
                if content:
                    configs = extract_configs_from_text(content)
                    all_raw_configs.extend(configs)
                    log(f"✅ [{completed}/{len(ALL_SOURCES)}] {url[:50]}... -> {len(configs)} конфигов", 'SUCCESS')
                else:
                    log(f"❌ [{completed}/{len(ALL_SOURCES)}] {url[:50]}... -> пусто", 'ERROR')
            except Exception as e:
                log(f"❌ [{completed}/{len(ALL_SOURCES)}] {url[:50]}... -> ошибка", 'ERROR')
    
    print()
    log(f"📥 Сырых конфигов: {len(all_raw_configs)}", 'INFO')
    
    # Удаляем дубликаты
    unique_configs = remove_duplicates(all_raw_configs)
    
    # Выбираем топ ~60 конфигов
    final_configs = select_top_configs(unique_configs, CONFIG['MAX_CONFIGS'])
    
    # Сохраняем все конфиги в один файл
    with open(CONFIG['OUTPUT_FILE'], 'w', encoding='utf-8') as f:
        f.write('\n'.join(final_configs))
    
    # Сохраняем по типам
    save_configs_by_type(final_configs)
    
    # Статистика
    print()
    log("="*50, 'HEADER')
    log("📊 СТАТИСТИКА:", 'HEADER')
    log(f"   • Всего уникальных: {len(unique_configs)}", 'INFO')
    log(f"   • Отобрано (~{CONFIG['MAX_CONFIGS']}): {len(final_configs)}", 'SUCCESS')
    
    # Считаем по типам
    by_type = {}
    for cfg in final_configs:
        ctype = categorize_config(cfg)
        by_type[ctype] = by_type.get(ctype, 0) + 1
    
    log(f"   • По типам:", 'INFO')
    for ctype, count in by_type.items():
        log(f"     └─ {ctype}: {count}", 'INFO')
    
    print()
    log(f"✅ Готово! Файлы сохранены:", 'SUCCESS')
    log(f"   • {CONFIG['OUTPUT_FILE']} - все конфиги ({len(final_configs)})", 'INFO')
    log(f"   • {CONFIG['VLESS_REALITY_FILE']} - VLESS Reality", 'INFO')
    log(f"   • {CONFIG['HYSTERIA_FILE']} - Hysteria2", 'INFO')
    log(f"   • {CONFIG['TUIC_FILE']} - TUIC", 'INFO')
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        sys.exit(1)
