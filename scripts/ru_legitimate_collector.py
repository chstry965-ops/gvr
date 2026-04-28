"""
Сбор легитимных номеров РФ для SpamBlocker.

Источники сгруппированы по уверенности и категории:
  org (high confidence):
    zoon.ru, spravker.ru, rusprofile.ru, mosgorzdrav.ru, mos.ru
  delivery (high confidence):
    eda.yandex, lavka, samokat, sbermarket, dostavista, cdek, boxberry,
    dpd, pecom, delovye-linii, kuper
  freelancer / private (medium):
    fl.ru, hands.ru, freelance.ru, profi.ru, youdo, remontnik, drom, cian
  classified (low):
    irr.ru, farpost.ru, barahla.net
  background (very low): обычные мобильные из плана нумерации
    включается явно через --add-user-numbers

Output: datasets/ru/raw/legitimate_numbers.csv
Format: normalized_number,name,category,source,city,url,source_confidence

Usage:
    python scripts/ru_legitimate_collector.py --profile smart
    python scripts/ru_legitimate_collector.py --profile broad --max-urls 5000
    python scripts/ru_legitimate_collector.py --profile org
    python scripts/ru_legitimate_collector.py --add-user-numbers 2000
"""

import argparse
import asyncio
import csv
import html as html_lib
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote, unquote, urlparse, urljoin

try:
    import aiohttp
except ImportError:
    print("Требуется aiohttp:  pip install aiohttp")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))
from ru_number_normalizer import normalize_ru_phone, is_russian_number

# ── Config ──────────────────────────────────────────────────────────────────

CONCURRENCY = 20
PER_HOST_CONCURRENCY = 12      # parallel requests allowed per host
PER_HOST_CONCURRENCY_STRICT = 3  # for hosts that ban quickly (rusprofile, cian)
DELAY_MIN = 0.0               # base inter-request delay (seconds)
DELAY_MAX = 0.3
MAX_PAGES = 30

# Aggressive timeouts: dead URLs (e.g. irr.ru pages that hang) stop wasting time.
FETCH_TIMEOUT_TOTAL = 10.0
FETCH_TIMEOUT_SOCK = 6.0
FETCH_RETRIES = 2

# Hosts that ban quickly under load — apply per-host cap = STRICT and inter-request
# delay. Add a host here only if you've actually seen it return 403/429 under
# the default per-host concurrency.
STRICT_HOSTS = ('rusprofile',)
OUTPUT_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'datasets', 'ru', 'raw', 'legitimate_numbers.csv'
))
STATE_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'datasets', 'ru', 'raw', 'legitimate_collector_state.json'
))

# ── Spravker: city subdomains (tested working) ─────────────────────────────

SPRAVKER_CITIES = {
    'msk': 'msk.spravker.ru', 'spb': 'spb.spravker.ru',
    'ekb': 'ekaterinburg.spravker.ru', 'kzn': 'kazan.spravker.ru',
    'nnov': 'nizhnij-novgorod.spravker.ru', 'rnd': 'rostov-na-donu.spravker.ru',
    'ufa': 'ufa.spravker.ru', 'krasnodar': 'krasnodar.spravker.ru',
    'voronezh': 'voronezh.spravker.ru', 'chelyabinsk': 'chelyabinsk.spravker.ru',
    'samara': 'samara.spravker.ru', 'perm': 'perm.spravker.ru',
    'volgograd': 'volgograd.spravker.ru', 'barnaul': 'barnaul.spravker.ru',
    'tyumen': 'tyumen.spravker.ru',
    'novgorod': 'novgorod.spravker.ru',
}

# Spravker subcategories that have phones in listing pages (tested)
SPRAVKER_SUBCATEGORIES = [
    'bolnicy', 'stomatologicheskie-kliniki-i-tsentryi',
    'stomatologicheskie-polikliniki', 'medtsentryi-i-kliniki',
    'diagnosticheskie-tsentryi', 'apteki',
    'banki', 'strahovanye-kompanii',
    'universitetyi', 'shkolyi',
    'avtoservisyi', 'avtosalonyi',
    'notariusyi', 'advokatskije-kollegii',
    'turisticheskiye-agentstva', 'gostinitsyi',
    'salonyi-krasotyi', 'parikmaherskiye',
    'fitnes-klubyi', 'sportivnyje-klubyi',
    'magazinyi-produktov', 'supermarketyi',
    'restoranyi', 'kafe',
    'remont-kvartir', 'okna',
    'agentstva-nedvizhimosti', 'rieltorskiye-agentstva',
    'logisticheskiye-kompanii', 'gruzoperevozki',
    'internet-provaideryi', 'mobilnyje-operatoryi',
    'veterinarnyje-kliniki', 'detskiye-sadyi',
]

# ── Zoon: cities and categories ────────────────────────────────────────────

ZOON_CITIES = {
    'msk': 'msk', 'spb': 'spb', 'ekb': 'ekb',
    'ufa': 'ufa', 'krasnodar': 'krasnodar', 'voronezh': 'voronezh',
    'chelyabinsk': 'chelyabinsk', 'samara': 'samara', 'perm': 'perm',
    'volgograd': 'volgograd', 'barnaul': 'barnaul', 'tyumen': 'tyumen',
    'krasnoyarsk': 'krasnoyarsk', 'izhevsk': 'izhevsk', 'yaroslavl': 'yaroslavl',
    'ryazan': 'ryazan', 'tula': 'tula', 'omsk': 'omsk',
    'vladivostok': 'vladivostok', 'nizhnevartovsk': 'nizhnevartovsk',
    'saratov': 'saratov', 'ulyanovsk': 'ulyanovsk', 'irkutsk': 'irkutsk',
    'smolensk': 'smolensk', 'kaliningrad': 'kaliningrad', 'kursk': 'kursk',
    'belgorod': 'belgorod', 'lipetsk': 'lipetsk', 'bryansk': 'bryansk',
    'vladimir': 'vladimir', 'ivanovo': 'ivanovo', 'kostroma': 'kostroma',
}

ZOON_CATEGORIES = [
    'medical', 'beauty', 'fitness', 'education', 'home',
    'pets', 'finance', 'legal', 'travel', 'auto',
    'food', 'children', 'entertainment', 'photo', 'music',
    'it', 'marketing', 'design', 'repair', 'cleaning',
]

# ── Rusprofile: search queries ────────────────────────────────────────────

RUSPROFILE_QUERIES = [
    'клиника', 'стоматология', 'больница', 'аптека',
    'школа', 'университет', 'детский сад', 'колледж',
    'автосервис', 'автомойка', 'шиномонтаж', 'автосалон',
    'страховая компания', 'банк отделение',
    'нотариус', 'адвокат', 'юридическая компания',
    'салон красоты', 'парикмахерская', 'барбершоп',
    'ресторан', 'кафе', 'пиццерия', 'столовая',
    'строительная компания', 'ремонт квартир', 'электрик', 'сантехник',
    'риелтор', 'агентство недвижимости', 'застройщик',
    'ветеринарная клиника', 'зоомагазин',
    'фитнес клуб', 'спортивный клуб', 'бассейн',
    'доставка еды', 'логистическая компания', 'такси',
    'супермаркет', 'магазин продуктов', 'аптека',
    'интернет провайдер', 'телекоммуникации',
    'гостиница', 'хостел', 'туристическое агентство',
    'жкх', 'управляющая компания', 'мфц',
    'поликлиника', 'диагностический центр', 'лаборатория',
    'окна установка', 'мебель на заказ', 'кухни на заказ',
    'клининг', 'прачечная', 'химчистка',
    'кредит', 'микрофинансовая', 'ломбард',
    'церковь', 'мечеть', 'храм',
]

SMART_ZOON_CATEGORIES = [
    'home', 'repair', 'cleaning', 'it', 'marketing', 'design',
    'auto', 'finance', 'legal', 'travel', 'pets', 'children',
]

SMART_SPRAVKER_SUBCATEGORIES = [
    'avtoservisyi', 'avtosalonyi',
    'notariusyi', 'advokatskije-kollegii',
    'turisticheskiye-agentstva', 'gostinitsyi',
    'salonyi-krasotyi', 'parikmaherskiye',
    'fitnes-klubyi', 'sportivnyje-klubyi',
    'magazinyi-produktov', 'supermarketyi',
    'remont-kvartir', 'okna',
    'agentstva-nedvizhimosti', 'rieltorskiye-agentstva',
    'logisticheskiye-kompanii', 'gruzoperevozki',
    'internet-provaideryi', 'mobilnyje-operatoryi',
    'veterinarnyje-kliniki',
]

DELIVERY_PUBLIC_URLS = [
    ('https://eda.yandex.ru/', 'Яндекс Еда', 'delivery'),
    ('https://eda.yandex.ru/contacts', 'Яндекс Еда', 'delivery'),
    ('https://lavka.yandex.ru/', 'Яндекс Лавка', 'delivery'),
    ('https://samokat.ru/', 'Самокат', 'delivery'),
    ('https://kuper.ru/', 'Купер', 'delivery'),
    ('https://sbermarket.ru/', 'СберМаркет', 'delivery'),
    ('https://dostavista.ru/', 'Достависта', 'delivery'),
    ('https://www.cdek.ru/ru/contacts', 'СДЭК', 'delivery'),
    ('https://www.cdek.ru/ru/offices', 'СДЭК офисы', 'delivery'),
    ('https://boxberry.ru/contacts', 'Boxberry', 'delivery'),
    ('https://boxberry.ru/find-an-office/', 'Boxberry офисы', 'delivery'),
    ('https://www.dpd.ru/', 'DPD', 'delivery'),
    ('https://www.dpd.ru/ols/contact.do2', 'DPD контакты', 'delivery'),
    ('https://pecom.ru/contacts/', 'ПЭК', 'delivery'),
    ('https://pecom.ru/services/', 'ПЭК услуги', 'delivery'),
    ('https://www.delovye-linii.ru/contacts/', 'Деловые линии', 'delivery'),
    ('https://www.delovye-linii.ru/offices/', 'Деловые линии офисы', 'delivery'),
    ('https://www.pochta.ru/support', 'Почта России', 'delivery'),
    ('https://www.pochta.ru/offices', 'Почта России офисы', 'delivery'),
    ('https://www.dellin.ru/contacts/', 'Деловые линии Деллин', 'delivery'),
    ('https://strazhcourier.ru/', 'Страж курьер', 'delivery'),
    ('https://www.energogaz.com/contacts/', 'Энергогаз доставка', 'delivery'),
    ('https://www.gett.com/ru/cities/', 'Gett такси', 'delivery'),
    ('https://citymobil.ru/', 'Ситимобил', 'delivery'),
    ('https://taximaxim.ru/', 'Максим такси', 'delivery'),
]

SERVICE_MARKETPLACE_URLS = [
    ('https://www.fl.ru/freelancers/', 'FL.ru', 'freelancer'),
    ('https://www.fl.ru/freelancers/programmer/', 'FL.ru программисты', 'freelancer'),
    ('https://www.fl.ru/freelancers/design/', 'FL.ru дизайнеры', 'freelancer'),
    ('https://www.fl.ru/freelancers/copywriting/', 'FL.ru копирайтеры', 'freelancer'),
    ('https://www.fl.ru/freelancers/translation/', 'FL.ru переводчики', 'freelancer'),
    ('https://www.fl.ru/projects/', 'FL.ru проекты', 'freelancer'),
    ('https://freelance.ru/', 'Freelance.ru', 'freelancer'),
    ('https://freelance.ru/projects/', 'Freelance.ru проекты', 'freelancer'),
    ('https://freelance.ru/freelancers/', 'Freelance.ru фрилансеры', 'freelancer'),
    ('https://www.remontnik.ru/', 'Remontnik.ru', 'private_seller'),
    ('https://www.remontnik.ru/masters/', 'Remontnik.ru мастера', 'private_seller'),
    ('https://www.remontnik.ru/masters/elektrik/', 'Remontnik электрики', 'private_seller'),
    ('https://www.remontnik.ru/masters/santehnik/', 'Remontnik сантехники', 'private_seller'),
    ('https://www.remontnik.ru/masters/plotnik/', 'Remontnik плотники', 'private_seller'),
    ('https://www.remontnik.ru/masters/dizayner/', 'Remontnik дизайнеры', 'private_seller'),
    ('https://profi.ru/remont/', 'Профи ремонт', 'private_seller'),
    ('https://profi.ru/repetitor/', 'Профи репетиторы', 'private_seller'),
    ('https://profi.ru/uborka/', 'Профи уборка', 'private_seller'),
    ('https://profi.ru/krasota/', 'Профи красота', 'private_seller'),
    ('https://profi.ru/transport/', 'Профи транспорт', 'private_seller'),
    ('https://profi.ru/avto/', 'Профи авто', 'private_seller'),
    ('https://youdo.com/', 'YouDo', 'private_seller'),
    ('https://youdo.com/tasks-all-opened/', 'YouDo задания', 'private_seller'),
    ('https://youdo.com/repair/', 'YouDo ремонт', 'private_seller'),
    ('https://youdo.com/cleaning/', 'YouDo уборка', 'private_seller'),
    ('https://youdo.com/courier/', 'YouDo курьеры', 'private_seller'),
    ('https://hands.ru/programmers/', 'Hands программисты', 'freelancer'),
    ('https://hands.ru/designers/', 'Hands дизайнеры', 'freelancer'),
    ('https://hands.ru/translators/', 'Hands переводчики', 'freelancer'),
    ('https://hands.ru/copywriters/', 'Hands копирайтеры', 'freelancer'),
    ('https://hands.ru/photographers/', 'Hands фотографы', 'freelancer'),
    ('https://hands.ru/composers/', 'Hands композиторы', 'freelancer'),
]

FAST_SERVICE_MARKETPLACE_URLS = [
    item for item in SERVICE_MARKETPLACE_URLS
    if 'remontnik.ru' not in item[0] and 'profi.ru' not in item[0]
]

FREELANCE_QUERIES = [
    'разработчик', 'дизайнер', 'копирайтер', 'маркетолог',
    'фотограф', 'видеограф', 'репетитор', 'переводчик',
    'сантехник', 'электрик', 'ремонт', 'курьер',
    'программист', 'верстальщик', 'таргетолог', 'smm',
    'грузчик', 'няня', 'сиделка', 'мастер на час',
]

CLASSIFIED_PUBLIC_URLS = [
    ('https://www.irr.ru/real-estate/', 'Из рук в руки недвижимость', 'private_seller'),
    ('https://www.irr.ru/real-estate/apartments-sale/', 'Из рук в руки квартиры', 'private_seller'),
    ('https://www.irr.ru/real-estate/apartments-rent/', 'Из рук в руки аренда', 'private_seller'),
    ('https://www.irr.ru/cars/used/', 'Из рук в руки авто', 'private_seller'),
    ('https://www.irr.ru/cars/new/', 'Из рук в руки новые авто', 'private_seller'),
    ('https://www.irr.ru/services/', 'Из рук в руки услуги', 'private_seller'),
    ('https://www.irr.ru/services/repair/', 'Из рук в руки ремонт', 'private_seller'),
    ('https://www.irr.ru/services/transport/', 'Из рук в руки транспорт', 'private_seller'),
    ('https://www.irr.ru/services/educational/', 'Из рук в руки образование', 'private_seller'),
    ('https://www.irr.ru/work/', 'Из рук в руки работа', 'private_seller'),
    ('https://www.farpost.ru/auto/', 'FarPost авто', 'private_seller'),
    ('https://www.farpost.ru/realty/', 'FarPost недвижимость', 'private_seller'),
    ('https://www.farpost.ru/service/', 'FarPost услуги', 'private_seller'),
    ('https://www.farpost.ru/work/', 'FarPost работа', 'private_seller'),
    ('https://barahla.net/services/', 'Barahla услуги', 'private_seller'),
    ('https://barahla.net/realty/', 'Barahla недвижимость', 'private_seller'),
    ('https://barahla.net/transport/', 'Barahla транспорт', 'private_seller'),
    ('https://barahla.net/work/', 'Barahla работа', 'private_seller'),
    ('https://www.youla.ru/all/uslugi', 'Юла услуги', 'private_seller'),
    ('https://www.youla.ru/all/transport', 'Юла транспорт', 'private_seller'),
    ('https://www.youla.ru/all/nedvizhimost', 'Юла недвижимость', 'private_seller'),
    ('https://www.avito.ru/rossiya/uslugi', 'Авито услуги', 'private_seller'),
    ('https://www.avito.ru/rossiya/transport', 'Авито транспорт', 'private_seller'),
    ('https://www.avito.ru/rossiya/nedvizhimost', 'Авито недвижимость', 'private_seller'),
]

# ── Category inference ─────────────────────────────────────────────────────

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    'bank':        ['банк', 'финанс', 'сбер', 'тинькофф', 'втб', 'альфа', 'кредит', 'ломбард', 'микрофинанс'],
    'government':  ['госуслуг', 'мфц', 'министерств', 'полиц', 'налог', 'мвд', 'жкх', 'управляющ'],
    'telecom':     ['мтс', 'билайн', 'мегафон', 'tele2', 'ростелеком', 'провайдер', 'телеком'],
    'medical':     ['больниц', 'клиник', 'стоматолог', 'аптек', 'медиц', 'госпитал', 'диагност', 'ветеринар', 'поликлиник', 'лаборатор'],
    'education':   ['университет', 'школ', 'колледж', 'институт', 'лицей', 'гимназ', 'детский сад'],
    'retail':      ['магазин', 'супермаркет', 'пятёрочк', 'магнит', 'лента', 'зоомагазин'],
    'delivery':    ['доставк', 'логист', 'перевозк', 'такси'],
    'insurance':   ['страх'],
    'transport':   ['автосервис', 'автомобил', 'автомойк', 'шиномонтаж', 'автосалон', 'гостиниц', 'хостел', 'турист'],
    'utility':     ['ремонт', 'строительн', 'электрик', 'сантехник', 'окна', 'мебель', 'кухн', 'клининг', 'прачечн', 'химчистк'],
    'legal':       ['юридич', 'нотариус', 'адвокат'],
    'realestate':  ['риелтор', 'недвижим', 'застройщик'],
    'restaurant':  ['ресторан', 'кафе', 'пиццер', 'столов'],
    'beauty':      ['салон', 'красот', 'парикмахер', 'барбершоп'],
    'fitness':     ['фитнес', 'спортивн', 'бассейн'],
    'religious':   ['церковь', 'мечеть', 'храм'],
    'other':       [],
}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Safari/605.1.15',
]

# ── Regex patterns ─────────────────────────────────────────────────────────

PHONE_RE = re.compile(r'(?:\+7|8)[\s\-().\xa0]*\d{3}[\s\-().\xa0]*\d{3}[\s\-().\xa0]*\d{2}[\s\-().\xa0]*\d{2}')
PHONE_COMPACT_RE = re.compile(r'(?<!\d)(?:\+?7|8)\d{10}(?!\d)')
TEL_HREF_RE = re.compile(r'''href\s*=\s*["']tel:([^"']+)["']''', re.IGNORECASE)
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)
TAG_STRIP_RE = re.compile(r'<[^>]+>')
WHITESPACE_RE = re.compile(r'\s+')
# Spravker .htm org page links
SPRAVKER_ORG_RE = re.compile(r'''href\s*=\s*["']([^"']*\.htm)["']''', re.IGNORECASE)
HREF_RE = re.compile(r'''href\s*=\s*["']([^"']+)["']''', re.IGNORECASE)
# Rusprofile company page links from search results
RUSPROFILE_ORG_RE = re.compile(r'href="(/id/\d+)"')
# Zoon JSON-LD
LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('legit_collector')


# ── Data ───────────────────────────────────────────────────────────────────

@dataclass
class LegitEntry:
    normalized_number: str
    name: str
    category: str
    source: str
    city: str
    url: str
    source_confidence: float = 0.70


# ── Helpers ────────────────────────────────────────────────────────────────

def infer_category(text: str) -> str:
    lower = text.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if cat == 'other':
            continue
        for kw in keywords:
            if kw in lower:
                return cat
    return 'other'


def is_plausible_phone(norm: Optional[str]) -> bool:
    if not norm or len(norm) != 12:
        return False
    if not is_russian_number(norm):
        return False
    digits = norm[2:]
    if digits == digits[0] * len(digits):
        return False
    if digits in {'1234567890', '9876543210', '0000000000'}:
        return False
    return True


def extract_phones(html: str) -> List[str]:
    """Extract and normalize Russian phone numbers from HTML."""
    results = []
    text = html_lib.unescape(html or '')
    # 1. href="tel:" links (most reliable)
    for raw in TEL_HREF_RE.findall(text):
        norm = normalize_ru_phone(unquote(raw).strip(), reject_non_ru=True)
        if is_plausible_phone(norm) and norm not in results:
            results.append(norm)
    # 2. Regex phones in text (including \xa0 non-breaking spaces)
    for raw in PHONE_RE.findall(text):
        norm = normalize_ru_phone(raw.replace('\xa0', ' '), reject_non_ru=True)
        if is_plausible_phone(norm) and norm not in results:
            results.append(norm)
    # 3. Compact numbers in JSON/JS blobs: +79001234567, 89001234567, 79001234567
    for raw in PHONE_COMPACT_RE.findall(text):
        norm = normalize_ru_phone(raw, reject_non_ru=True)
        if is_plausible_phone(norm) and norm not in results:
            results.append(norm)
    return results


_STATIC_EXT = (
    '.css', '.js', '.ico', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp',
    '.woff', '.woff2', '.ttf', '.otf', '.eot', '.mp4', '.webm', '.mp3',
    '.pdf', '.zip', '.rar', '.xml', '.json', '.webmanifest', '.map',
)


def _looks_static(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(_STATIC_EXT)


def extract_links(html: str, base_url: str, limit: int = 25) -> List[str]:
    links: List[str] = []
    base_host = urlparse(base_url).netloc
    for raw in HREF_RE.findall(html or ''):
        href = html_lib.unescape(raw).strip()
        if not href or href.startswith(('tel:', 'mailto:', 'javascript:', '#', 'data:')):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme not in {'http', 'https'} or parsed.netloc != base_host:
            continue
        if _looks_static(full):
            continue
        clean = full.split('#', 1)[0]
        if clean not in links:
            links.append(clean)
        if len(links) >= limit:
            break
    return links


def extract_title(html: str) -> str:
    m = TITLE_RE.search(html)
    if not m:
        return ''
    text = TAG_STRIP_RE.sub(' ', m.group(1))
    text = WHITESPACE_RE.sub(' ', text).strip()
    return text[:200]


def parse_confidence(value: str, default: float = 0.70) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def default_source_confidence(category: str, source: str) -> float:
    if source in {'official_whitelist', 'official_hotline'}:
        return 0.95
    if category == 'personal_mobile' or source.startswith('numbering_plan'):
        return 0.25
    if category in {'private_seller', 'realestate_owner'}:
        return 0.55
    if category in {'freelancer', 'realestate_agent'}:
        return 0.60
    if category in {'delivery', 'government', 'bank', 'medical'}:
        return 0.85
    return 0.70


# ── Async HTTP ─────────────────────────────────────────────────────────────

class AsyncScraper:
    def __init__(self, concurrency: int = CONCURRENCY,
                 per_host_concurrency: int = PER_HOST_CONCURRENCY):
        self.sem = asyncio.Semaphore(concurrency)
        self.session: Optional[aiohttp.ClientSession] = None
        self.seen: Set[str] = set()
        self.results: List[LegitEntry] = []
        self.host_sems: Dict[str, asyncio.Semaphore] = {}
        self.host_last: Dict[str, float] = {}
        self.visited_urls: Set[str] = set()  # skip already-fetched URLs
        self._resumed_fetched: int = 0  # fetched count from previous runs
        self.stats = {'fetched': 0, 'failed': 0, 'phones_found': 0, 'skipped': 0}
        self.blacklist: Set[str] = set()  # numbers from fraud/suspect databases
        self._per_host_concurrency = per_host_concurrency
        self._progress_lock = asyncio.Lock()

    async def start(self):
        # Bigger TCP connector with per-host cap → more parallel sockets.
        connector = aiohttp.TCPConnector(
            limit=max(128, self._per_host_concurrency * 12),
            limit_per_host=max(8, self._per_host_concurrency),
            ssl=False,
            ttl_dns_cache=300,
        )
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=FETCH_TIMEOUT_TOTAL, sock_read=FETCH_TIMEOUT_SOCK,
            ),
            headers={'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.5'},
            connector=connector,
        )

    async def close(self):
        if self.session:
            await self.session.close()

    def _get_host_sem(self, host: str) -> asyncio.Semaphore:
        sem = self.host_sems.get(host)
        if sem is None:
            cap = (PER_HOST_CONCURRENCY_STRICT
                   if any(s in host for s in STRICT_HOSTS)
                   else self._per_host_concurrency)
            sem = asyncio.Semaphore(max(1, cap))
            self.host_sems[host] = sem
        return sem

    async def fetch(self, url: str, allow_status: Set[int] = None) -> Optional[str]:
        # Skip already visited
        if url in self.visited_urls:
            self.stats['skipped'] += 1
            return None
        # URL limit check (count only new fetches this session)
        max_urls = getattr(self, '_max_urls', 0)
        new_fetched = self.stats['fetched'] - self._resumed_fetched
        if max_urls > 0 and new_fetched >= max_urls:
            return None
        host = urlparse(url).netloc
        host_sem = self._get_host_sem(host)
        self.visited_urls.add(url)

        # Progress counter (sloppy under parallelism but informative)
        new_fetched = self.stats['fetched'] - self._resumed_fetched + 1
        if max_urls > 0 and new_fetched % 25 == 0:
            log.info(f"[{new_fetched}/{max_urls}] {url}")
        elif new_fetched % 100 == 0:
            log.info(f"[{new_fetched}] fetched, {len(self.results)} numbers")

        # Optional small per-host inter-request delay (no global lock, so doesn't
        # block other hosts). Only applied to strict hosts to respect rate limits.
        is_strict = any(s in host for s in STRICT_HOSTS)
        min_delay = 0.5 if is_strict else DELAY_MIN

        headers = {'User-Agent': random.choice(USER_AGENTS)}
        allow = allow_status or {200}

        for attempt in range(FETCH_RETRIES):
            try:
                # Both global and per-host caps. HTTP runs OUTSIDE any per-host
                # lock so different URLs on the same host fetch concurrently.
                async with self.sem, host_sem:
                    if min_delay > 0:
                        last = self.host_last.get(host, 0)
                        wait = (last + min_delay) - time.monotonic()
                        if wait > 0:
                            await asyncio.sleep(wait)
                        self.host_last[host] = time.monotonic()
                    async with self.session.get(url, headers=headers, ssl=False) as resp:
                        if resp.status in allow:
                            text = await resp.text(errors='replace')
                            self.stats['fetched'] += 1
                            return text
                        elif resp.status in {404, 410}:
                            return None
                        else:
                            self.stats['failed'] += 1
                            return None
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt < FETCH_RETRIES - 1:
                    await asyncio.sleep(0.3 * (attempt + 1))
                else:
                    self.stats['failed'] += 1
                    return None
        return None

    async def fetch_many(self, urls: List[str],
                         allow_status: Set[int] = None) -> List[Optional[str]]:
        """Fetch many URLs concurrently. Order of results matches `urls`."""
        if not urls:
            return []
        tasks = [self.fetch(u, allow_status=allow_status) for u in urls]
        return await asyncio.gather(*tasks)

    def load_blacklist(self):
        """Load suspect/fraud numbers from ru_reputation_raw.csv."""
        csv_path = os.path.normpath(os.path.join(
            os.path.dirname(__file__), '..', 'datasets', 'ru', 'raw', 'ru_reputation_raw.csv'
        ))
        if not os.path.exists(csv_path):
            return
        with open(csv_path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                n = row.get('normalized_number', '').strip()
                if n:
                    self.blacklist.add(n)
        log.info(f"  Loaded {len(self.blacklist)} suspect numbers from reputation_raw")

    def add(self, entry: LegitEntry) -> bool:
        key = entry.normalized_number
        if key in self.seen:
            return False
        # Block known fraud/suspect numbers (unless from official_whitelist)
        if key in self.blacklist and entry.source != 'official_whitelist' and entry.source != 'official_hotline':
            return False
        self.seen.add(key)
        self.results.append(entry)
        return True

    def add_phones(self, phones: List[str], name: str, category: str,
                   source: str, city: str, url: str, source_confidence: float = 0.70) -> int:
        added = 0
        confidence = source_confidence if source_confidence != 0.70 else default_source_confidence(category, source)
        for phone in phones:
            if self.add(LegitEntry(phone, name, category, source, city, url, confidence)):
                added += 1
        self.stats['phones_found'] += len(phones)
        return added


# ── Source 1: zoon.ru ──────────────────────────────────────────────────────

async def scrape_zoon(scraper: AsyncScraper, cities: Dict[str, str],
                      categories: List[str]) -> int:
    """zoon.ru — JSON-LD ItemList gives 30 named orgs + 31 tel: links per page.
    Pages fetched in parallel across (city, category) pairs."""
    pairs = [(ck, cs, cat) for ck, cs in cities.items() for cat in categories]
    urls = [f'https://zoon.ru/{cs}/{cat}/' for _, cs, cat in pairs]
    htmls = await scraper.fetch_many(urls)

    total = 0
    for (city_key, city_slug, cat), url, html in zip(pairs, urls, htmls):
        if not html:
            continue

        # Extract names from JSON-LD ItemList
        names: List[str] = []
        for block in LD_JSON_RE.findall(html):
            try:
                data = json.loads(block)
            except (json.JSONDecodeError, ValueError):
                continue
            if data.get('@type') == 'ItemList' and 'itemListElement' in data:
                for item in data['itemListElement']:
                    biz = item.get('item', {})
                    name = biz.get('name', '')
                    if name:
                        names.append(name)

        # Extract phones from tel: links
        tel_phones: List[str] = []
        for raw in TEL_HREF_RE.findall(html):
            norm = normalize_ru_phone(raw.strip(), reject_non_ru=True)
            if norm and len(norm) == 12:
                tel_phones.append(norm)

        if names and tel_phones:
            offset = 1 if len(tel_phones) > len(names) else 0
            matched = min(len(names), len(tel_phones) - offset)
            for i in range(matched):
                phone = tel_phones[offset + i]
                digits = phone[2:]
                if digits == digits[0] * 10:
                    continue
                cat_inferred = infer_category(f'{cat} {names[i]}')
                if scraper.add(LegitEntry(phone, names[i], cat_inferred, 'zoon', city_key, url)):
                    total += 1
    return total


# ── Source 2: spravker.ru ─────────────────────────────────────────────────

async def scrape_spravker(scraper: AsyncScraper, cities: Dict[str, str],
                           subcategories: List[str]) -> int:
    """Spravker: fetch all listing pages in parallel, then all org pages in parallel."""
    total = 0
    pairs = [(ck, host, subcat) for ck, host in cities.items() for subcat in subcategories]
    listing_urls = [f'https://{host}/{subcat}/' for _, host, subcat in pairs]
    listings = await scraper.fetch_many(listing_urls)

    org_jobs: List[Tuple[str, str, str, str]] = []  # (city_key, subcat, listing_url, org_url)
    for (city_key, host, subcat), url, html in zip(pairs, listing_urls, listings):
        if not html:
            continue
        listing_phones: List[str] = []
        for raw in TEL_HREF_RE.findall(html):
            norm = normalize_ru_phone(raw.strip(), reject_non_ru=True)
            if norm and len(norm) == 12 and norm not in listing_phones:
                listing_phones.append(norm)
        if not listing_phones:
            listing_phones = extract_phones(html)
        if listing_phones:
            title = extract_title(html)
            cat_inferred = infer_category(f'{subcat} {title}')
            total += scraper.add_phones(listing_phones, title or subcat, cat_inferred,
                                        'spravker', city_key, url)

        for link in SPRAVKER_ORG_RE.findall(html)[:10]:
            if link.startswith('/'):
                full = f'https://{host}{link}'
            elif link.startswith('http'):
                full = link
            else:
                full = f'https://{host}/{subcat}/{link}'
            org_jobs.append((city_key, subcat, url, full))

    log.info(f"  spravker: {len(listings)} listings fetched, {len(org_jobs)} org pages queued")

    # Phase 2 — fetch all org pages in parallel
    org_htmls = await scraper.fetch_many([j[3] for j in org_jobs])
    for (city_key, subcat, _listing, org_url), html in zip(org_jobs, org_htmls):
        if not html:
            continue
        org_phones: List[str] = []
        for raw in TEL_HREF_RE.findall(html):
            norm = normalize_ru_phone(raw.strip(), reject_non_ru=True)
            if norm and len(norm) == 12:
                org_phones.append(norm)
        if org_phones:
            title = extract_title(html)
            cat_inferred = infer_category(f'{subcat} {title}')
            total += scraper.add_phones(org_phones, title or subcat, cat_inferred,
                                        'spravker', city_key, org_url)
    return total


# ── Source 3: rusprofile.ru ────────────────────────────────────────────────

async def scrape_rusprofile(scraper: AsyncScraper, queries: List[str]) -> int:
    """Rusprofile: parallel search across queries × 2 pages, then parallel org pages.

    Per-host concurrency for rusprofile is limited (STRICT) so we won't hammer it.
    """
    # Phase 1 — search pages
    search_urls = [f'https://www.rusprofile.ru/search?query={q}&page={p}'
                   for q in queries for p in (1, 2)]
    search_html = await scraper.fetch_many(search_urls, allow_status={200, 403})

    # Map query → ids
    query_ids: Dict[str, Set[str]] = {q: set() for q in queries}
    for url, html in zip(search_urls, search_html):
        if not html:
            continue
        # Extract query from URL
        q = url.split('query=')[1].split('&')[0]
        for cid in RUSPROFILE_ORG_RE.findall(html):
            query_ids.setdefault(q, set()).add(cid)

    # Phase 2 — fetch up to 5 company pages per query (in parallel)
    org_jobs: List[Tuple[str, str, str]] = []  # (query, cid, url)
    for q, ids in query_ids.items():
        for cid in list(ids)[:5]:
            org_jobs.append((q, cid, f'https://www.rusprofile.ru{cid}'))

    if not org_jobs:
        return 0

    log.info(f"  rusprofile: {len(org_jobs)} org pages queued across {len(queries)} queries")
    org_htmls = await scraper.fetch_many([j[2] for j in org_jobs], allow_status={200, 403})

    total = 0
    for (query, cid, url), html in zip(org_jobs, org_htmls):
        if not html:
            continue
        tel_phones: List[str] = []
        for raw in TEL_HREF_RE.findall(html):
            norm = normalize_ru_phone(raw.strip(), reject_non_ru=True)
            if norm and len(norm) == 12:
                tel_phones.append(norm)
        if tel_phones:
            title = extract_title(html)
            cat_inferred = infer_category(f'{query} {title}')
            total += scraper.add_phones(tel_phones, title or query, cat_inferred,
                                        'rusprofile', '', url)
    return total


# ── Source 4: mosgorzdrav.ru ───────────────────────────────────────────────

async def scrape_mosgorzdrav(scraper: AsyncScraper) -> int:
    total = 0
    for page_url in [
        'https://mosgorzdrav.ru/',
        'https://mosgorzdrav.ru/ru/healthcare/',
        'https://mosgorzdrav.ru/ru/contacts/',
    ]:
        html = await scraper.fetch(page_url)
        if not html:
            continue
        phones = extract_phones(html)
        if phones:
            added = scraper.add_phones(phones, 'Мосгорздрав', 'medical', 'mosgorzdrav', 'msk', page_url)
            total += added
    return total


# ── Source 5: mos.ru ──────────────────────────────────────────────────────

async def scrape_mos_ru(scraper: AsyncScraper) -> int:
    total = 0
    for page_url in [
        'https://www.mos.ru/',
        'https://www.mos.ru/contacts/',
        'https://www.mos.ru/government/contacts/',
    ]:
        html = await scraper.fetch(page_url)
        if not html:
            continue
        phones = extract_phones(html)
        if phones:
            added = scraper.add_phones(phones, 'mos.ru', 'government', 'mos_ru', 'msk', page_url)
            total += added
    return total


# ── Source 6: cian.ru — real estate agents/owners ──────────────────────────

async def scrape_cian(scraper: AsyncScraper, max_pages: int = 30) -> int:
    """ЦИАН — телефоны агентов и собственников недвижимости.

    Все URL ставятся в очередь и фетчатся параллельно (per-host cap=STRICT).
    Это даёт огромный выигрыш по сравнению с прежним последовательным циклом.
    """
    regions = [1, 2, 4593, 4597, 4601, 4605, 4609, 4612, 4615, 4618]
    deal_types = ['sale', 'rent']
    offer_types = ['flat', 'house', 'commercial']

    urls: List[Tuple[str, str]] = []  # (url, category)
    for region in regions:
        for deal in deal_types:
            for offer in offer_types:
                for page in range(1, max_pages + 1):
                    u = (f'https://www.cian.ru/cat.php?deal_type={deal}'
                         f'&engine_version=2&offer_type={offer}&region={region}&p={page}')
                    urls.append((u, 'realestate_agent'))
    for region in regions:
        for page in range(1, min(max_pages, 10) + 1):
            u = (f'https://www.cian.ru/cat.php?deal_type=rent&engine_version=2'
                 f'&offer_type=flat&region={region}&is_by_homeowner=1&p={page}')
            urls.append((u, 'realestate_owner'))

    htmls = await scraper.fetch_many([u for u, _ in urls])
    total = 0
    for (url, cat), html in zip(urls, htmls):
        if not html:
            continue
        phones = extract_phones(html)
        if phones:
            name = 'ЦИАН собственник' if cat == 'realestate_owner' else 'ЦИАН'
            total += scraper.add_phones(phones, name, cat, 'cian', '', url)
    return total


async def scrape_public_url_list(scraper: AsyncScraper, source: str,
                                 urls: List[Tuple[str, str, str]],
                                 link_limit: int = 8,
                                 confidence: float = 0.70) -> int:
    """Two-phase parallel scrape: all listings concurrently, then all detail links."""
    total = 0
    listings = await scraper.fetch_many([u for u, _, _ in urls])

    detail_jobs: List[Tuple[str, str, str, str]] = []  # (page_url, name, category, link, title)
    page_titles: List[Optional[str]] = []
    for (page_url, name, category), html in zip(urls, listings):
        if not html:
            page_titles.append(None)
            continue
        title = extract_title(html)
        page_titles.append(title)
        phones = extract_phones(html)
        if phones:
            added = scraper.add_phones(phones, title or name, category, source, '', page_url, confidence)
            total += added
        for link in extract_links(html, page_url, limit=link_limit):
            detail_jobs.append((page_url, name, category, link))

    if detail_jobs:
        detail_htmls = await scraper.fetch_many([j[3] for j in detail_jobs])
        for (page_url, name, category, link), html2 in zip(detail_jobs, detail_htmls):
            if not html2:
                continue
            phones2 = extract_phones(html2)
            if phones2:
                title2 = extract_title(html2)
                added = scraper.add_phones(phones2, title2 or name, category,
                                           source, '', link, confidence)
                total += added
    return total


async def scrape_delivery_public(scraper: AsyncScraper) -> int:
    return await scrape_public_url_list(scraper, 'delivery_public', DELIVERY_PUBLIC_URLS, link_limit=5, confidence=0.85)


async def scrape_service_marketplaces(scraper: AsyncScraper) -> int:
    urls = list(SERVICE_MARKETPLACE_URLS)
    for query in FREELANCE_QUERIES:
        urls.append((f'https://freelance.ru/search/?q={quote(query)}', f'Freelance.ru {query}', 'freelancer'))
        urls.append((f'https://www.fl.ru/search/?type=users&search_string={quote(query)}', f'FL.ru {query}', 'freelancer'))
    return await scrape_public_url_list(scraper, 'service_marketplace', urls, link_limit=10, confidence=0.60)


async def scrape_service_marketplaces_fast(scraper: AsyncScraper) -> int:
    urls = list(FAST_SERVICE_MARKETPLACE_URLS)
    for query in FREELANCE_QUERIES:
        urls.append((f'https://freelance.ru/search/?q={quote(query)}', f'Freelance.ru {query}', 'freelancer'))
        urls.append((f'https://www.fl.ru/search/?type=users&search_string={quote(query)}', f'FL.ru {query}', 'freelancer'))
    return await scrape_public_url_list(scraper, 'service_marketplace_fast', urls, link_limit=6, confidence=0.60)


async def scrape_classified_public(scraper: AsyncScraper) -> int:
    return await scrape_public_url_list(scraper, 'classified_public', CLASSIFIED_PUBLIC_URLS, link_limit=24, confidence=0.55)


# ── Source 7: fl.ru — freelancers with public contacts ────────────────────

async def scrape_fl_ru(scraper: AsyncScraper) -> int:
    """fl.ru — фрилансеры с публичными контактами."""
    total = 0
    for page_url in [
        'https://www.fl.ru/freelancers/',
        'https://www.fl.ru/projects/',
    ]:
        html = await scraper.fetch(page_url)
        if not html:
            continue
        phones = extract_phones(html)
        if phones:
            added = scraper.add_phones(phones, 'FL.ru', 'freelancer', 'fl_ru', '', page_url)
            total += added
    return total


# ── Source 8: hands.ru — freelancers / masters ────────────────────────────

async def scrape_hands_ru(scraper: AsyncScraper) -> int:
    """hands.ru — фрилансеры и мастера с публичными контактами."""
    total = 0
    for page_url in [
        'https://hands.ru/',
        'https://hands.ru/programmers/',
        'https://hands.ru/designers/',
        'https://hands.ru/translators/',
        'https://hands.ru/copywriters/',
    ]:
        html = await scraper.fetch(page_url)
        if not html:
            continue
        phones = extract_phones(html)
        if phones:
            added = scraper.add_phones(phones, 'Hands.ru', 'freelancer', 'hands_ru', '', page_url)
            total += added
    return total


# ── Source 9: freelance.ru — freelancers ──────────────────────────────────

async def scrape_freelance_ru(scraper: AsyncScraper) -> int:
    """freelance.ru — фрилансеры с публичными контактами."""
    total = 0
    for page_url in [
        'https://freelance.ru/',
        'https://freelance.ru/projects/',
        'https://freelance.ru/search/?q=разработчик',
        'https://freelance.ru/search/?q=дизайнер',
    ]:
        html = await scraper.fetch(page_url)
        if not html:
            continue
        phones = extract_phones(html)
        if phones:
            added = scraper.add_phones(phones, 'Freelance.ru', 'freelancer', 'freelance_ru', '', page_url)
            total += added
    return total


# ── Source 10: drom.ru — car sellers / baza ──────────────────────────────

async def scrape_drom(scraper: AsyncScraper) -> int:
    """drom.ru / baza.drom.ru — частные продавцы авто."""
    total = 0
    for page_url in [
        'https://baza.drom.ru/',
        'https://auto.drom.ru/region77/',
        'https://auto.drom.ru/moskva/',
        'https://auto.drom.ru/sankt-peterburg/',
    ]:
        html = await scraper.fetch(page_url)
        if not html:
            continue
        phones = extract_phones(html)
        if phones:
            added = scraper.add_phones(phones, 'Drom.ru', 'private_seller', 'drom', '', page_url)
            total += added
    return total


# ── Bonus: official numbers ────────────────────────────────────────────────

def load_official_whitelist() -> List[LegitEntry]:
    entries = []
    csv_path = os.path.normpath(os.path.join(
        os.path.dirname(__file__), '..', 'datasets', 'ru', 'raw', 'whitelist_official_ru.csv'
    ))
    if not os.path.exists(csv_path):
        return entries
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = row.get('normalized_number', '').strip()
            if num:
                entries.append(LegitEntry(
                    normalized_number=num,
                    name=row.get('name', ''),
                    category=row.get('category', 'other'),
                    source='official_whitelist',
                    city='',
                    url='',
                    source_confidence=0.95
                ))
    return entries


OFFICIAL_HOTLINES: List[Tuple[str, str, str]] = [
    ('+78005503355', 'Яндекс Еда', 'delivery'),
    ('+78005551333', 'Delivery Club', 'delivery'),
    ('+78005004003', 'Самокат', 'delivery'),
    ('+78005553300', 'СберМаркет', 'delivery'),
    ('+78002000900', 'Росгосстрах', 'insurance'),
    ('+78003330999', 'АльфаСтрахование', 'insurance'),
    ('+78002341802', 'РЕСО-Гарантия', 'insurance'),
    ('+78007550001', 'Согласие', 'insurance'),
    ('+78001007755', 'Ингосстрах', 'insurance'),
    ('+78005555505', 'Пятёрочка', 'retail'),
    ('+78002009002', 'Магнит', 'retail'),
    ('+78007004111', 'Лента', 'retail'),
    ('+78002009555', 'Перекрёсток', 'retail'),
    ('+78001007010', 'Госуслуги', 'government'),
    ('+78005554904', 'Роспотребнадзор', 'government'),
    ('+78006000443', 'Пенсионный фонд', 'government'),
    ('+78005500222', 'ФСС', 'government'),
    ('+78007750000', 'РЖД', 'transport'),
    ('+78004445555', 'Аэрофлот', 'transport'),
    ('+78003330890', 'МТС', 'telecom'),
    ('+78007000611', 'Билайн', 'telecom'),
    ('+78005500500', 'МегаФон', 'telecom'),
    ('+78005550607', 'Tele2', 'telecom'),
    ('+78001000800', 'Ростелеком', 'telecom'),
]


# ── Source 6: synthetic user numbers from numbering plan ─────────────────

def generate_user_numbers(scraper: AsyncScraper, count: int = 5000) -> int:
    """Generate weak background mobile numbers from the official numbering plan.
    
    Uses DEF/ABC ranges from ru_numbering_plan.csv to create numbers that
    are guaranteed to be valid (existing operator + region combinations).
    Cross-checked against blacklist to exclude known fraud numbers. These rows are
    intentionally low-confidence and should not be treated like verified org phones.
    """
    plan_path = os.path.normpath(os.path.join(
        os.path.dirname(__file__), '..', 'datasets', 'ru', 'raw', 'ru_numbering_plan.csv'
    ))
    if not os.path.exists(plan_path):
        log.warning(f"  Numbering plan not found at {plan_path}, run ru_numbering_plan.py first")
        return 0

    # Load ranges — mobile only (16K ranges, fast)
    ranges = []
    with open(plan_path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            ntype = row.get('number_type', '')
            if ntype != 'mobile':
                continue
            def_code = row.get('def_code', '').strip()
            start = int(row.get('start_number', '0'))
            end = int(row.get('end_number', '0'))
            operator = row.get('operator', '').strip()
            region = row.get('region', '').strip()
            capacity = end - start + 1
            if capacity > 0 and def_code:
                ranges.append({
                    'def_code': def_code,
                    'start': start, 'end': end,
                    'operator': operator, 'region': region,
                    'type': ntype, 'capacity': capacity,
                })

    if not ranges:
        log.warning("  No mobile ranges loaded from numbering plan")
        return 0

    log.info(f"  Loaded {len(ranges)} mobile ranges from numbering plan")

    # Pre-compute cumulative distribution for fast sampling
    import bisect
    cum_weights = []
    total = 0
    for r in ranges:
        total += r['capacity']
        cum_weights.append(total)

    # Generate numbers
    added = 0
    attempts = 0
    max_attempts = count * 3

    while added < count and attempts < max_attempts:
        attempts += 1
        # Pick a range using binary search on cumulative weights
        pick = random.randint(1, total)
        idx = bisect.bisect_left(cum_weights, pick)
        r = ranges[idx]
        # Pick a random subscriber number within the range
        subscriber = random.randint(r['start'], r['end'])
        # Build full number
        number = f'+7{r["def_code"]}{subscriber:07d}'

        # Validate
        if len(number) != 12:
            continue
        if number in scraper.seen:
            continue
        if number in scraper.blacklist:
            continue

        # Category and name from operator/region
        cat = 'personal_mobile'
        name = f'{r["operator"]}, {r["region"]}' if r['operator'] else r['region']

        if scraper.add(LegitEntry(number, name, cat, 'numbering_plan_background', r['region'], '', 0.25)):
            added += 1

    log.info(f"  Generated {added} user numbers ({attempts} attempts, {len(scraper.blacklist)} blacklist filtered)")
    return added


# ── Main ───────────────────────────────────────────────────────────────────

async def run_all(scraper: AsyncScraper, spravker_cities: Dict[str, str],
                  zoon_cities: Dict[str, str], profile: str = 'smart',
                  source_timeout: float = 0.0):
    if profile == 'weak':
        sources = [
            ('delivery_public',      lambda: scrape_delivery_public(scraper)),
            ('service_marketplace_fast',  lambda: scrape_service_marketplaces_fast(scraper)),
            ('classified_public',    lambda: scrape_classified_public(scraper)),
            ('cian',                 lambda: scrape_cian(scraper, max_pages=50)),
            ('hands_ru',             lambda: scrape_hands_ru(scraper)),
            ('freelance_ru',         lambda: scrape_freelance_ru(scraper)),
            ('fl_ru',                lambda: scrape_fl_ru(scraper)),
            ('drom',                 lambda: scrape_drom(scraper)),
        ]
    elif profile == 'org':
        sources = [
            ('zoon',        lambda: scrape_zoon(scraper, zoon_cities, ZOON_CATEGORIES)),
            ('spravker',    lambda: scrape_spravker(scraper, spravker_cities, SPRAVKER_SUBCATEGORIES)),
            ('rusprofile',  lambda: scrape_rusprofile(scraper, RUSPROFILE_QUERIES)),
            ('mosgorzdrav', lambda: scrape_mosgorzdrav(scraper)),
            ('mos_ru',      lambda: scrape_mos_ru(scraper)),
        ]
    elif profile == 'broad':
        sources = [
            ('delivery_public',      lambda: scrape_delivery_public(scraper)),
            ('service_marketplace',  lambda: scrape_service_marketplaces(scraper)),
            ('classified_public',    lambda: scrape_classified_public(scraper)),
            ('cian',                 lambda: scrape_cian(scraper)),
            ('fl_ru',                lambda: scrape_fl_ru(scraper)),
            ('hands_ru',             lambda: scrape_hands_ru(scraper)),
            ('freelance_ru',         lambda: scrape_freelance_ru(scraper)),
            ('drom',                 lambda: scrape_drom(scraper)),
            ('zoon',                 lambda: scrape_zoon(scraper, zoon_cities, ZOON_CATEGORIES)),
            ('spravker',             lambda: scrape_spravker(scraper, spravker_cities, SPRAVKER_SUBCATEGORIES)),
            ('rusprofile',           lambda: scrape_rusprofile(scraper, RUSPROFILE_QUERIES)),
            ('mosgorzdrav',          lambda: scrape_mosgorzdrav(scraper)),
            ('mos_ru',               lambda: scrape_mos_ru(scraper)),
        ]
    else:
        sources = [
            ('delivery_public',      lambda: scrape_delivery_public(scraper)),
            ('service_marketplace',  lambda: scrape_service_marketplaces(scraper)),
            ('classified_public',    lambda: scrape_classified_public(scraper)),
            ('cian',                 lambda: scrape_cian(scraper, max_pages=8)),
            ('hands_ru',             lambda: scrape_hands_ru(scraper)),
            ('freelance_ru',         lambda: scrape_freelance_ru(scraper)),
            ('fl_ru',                lambda: scrape_fl_ru(scraper)),
            ('drom',                 lambda: scrape_drom(scraper)),
            ('zoon_smart',           lambda: scrape_zoon(scraper, zoon_cities, SMART_ZOON_CATEGORIES)),
            ('spravker_smart',       lambda: scrape_spravker(scraper, spravker_cities, SMART_SPRAVKER_SUBCATEGORIES)),
            ('mos_ru',               lambda: scrape_mos_ru(scraper)),
        ]

    source_stats: Dict[str, Tuple[int, float]] = {}

    async def _run_source(name: str, fn) -> None:
        log.info(f"▶ Source: {name}")
        t0 = time.monotonic()
        try:
            if source_timeout > 0:
                count = await asyncio.wait_for(fn(), timeout=source_timeout)
            else:
                count = await fn()
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            log.warning(f"  ⏱ {name}: aborted after {elapsed:.1f}s (--source-timeout={source_timeout}s)")
            source_stats[name] = (0, elapsed)
            return
        except Exception as e:  # noqa: BLE001 — log and continue
            log.error(f"  Source {name} failed: {e}")
            count = 0
        elapsed = time.monotonic() - t0
        source_stats[name] = (count, elapsed)
        log.info(f"  ✓ {name}: {count} numbers in {elapsed:.1f}s")

    # Periodic background autosave so data persists even with concurrent sources.
    autosave_stop = asyncio.Event()

    async def _autosave():
        while not autosave_stop.is_set():
            try:
                await asyncio.wait_for(autosave_stop.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            try:
                save_results(scraper.results, scraper._output_path)
                save_state(scraper, scraper._output_path)
                log.info(
                    f"  💾 Autosave: {len(scraper.results)} numbers | "
                    f"fetched={scraper.stats['fetched']} skipped={scraper.stats['skipped']}"
                )
            except Exception as e:  # noqa: BLE001
                log.warning(f"  autosave failed: {e}")

    autosave_task = asyncio.create_task(_autosave())
    try:
        # Run all sources in parallel — they share scraper state safely
        # (single-threaded asyncio + dedup via scraper.seen).
        await asyncio.gather(
            *[_run_source(name, fn) for name, fn in sources],
            return_exceptions=True,
        )
    finally:
        autosave_stop.set()
        try:
            await autosave_task
        except Exception:
            pass

    return source_stats


def save_results(results: List[LegitEntry], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # Write to temp file first, then rename (atomic — no data loss on crash)
    tmp_path = output_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['normalized_number', 'name', 'category', 'source', 'city', 'url', 'source_confidence'])
        for entry in sorted(results, key=lambda e: (e.category, e.normalized_number)):
            writer.writerow([entry.normalized_number, entry.name, entry.category,
                             entry.source, entry.city, entry.url, f'{entry.source_confidence:.2f}'])
    # Atomic rename
    if os.path.exists(output_path):
        os.replace(tmp_path, output_path)
    else:
        os.rename(tmp_path, output_path)
    return len(results)


def save_state(scraper: AsyncScraper, output_path: str):
    """Save visited URLs to state file for resume."""
    state_path = STATE_PATH
    state = {
        'visited_urls': sorted(scraper.visited_urls),
        'fetched': scraper.stats['fetched'],
    }
    tmp = state_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f)
    if os.path.exists(state_path):
        os.replace(tmp, state_path)
    else:
        os.rename(tmp, state_path)


def load_state(scraper: AsyncScraper):
    """Load visited URLs from state file."""
    if not os.path.exists(STATE_PATH):
        return
    with open(STATE_PATH, encoding='utf-8') as f:
        state = json.load(f)
    visited = state.get('visited_urls', [])
    scraper.visited_urls = set(visited)
    scraper.stats['fetched'] = state.get('fetched', 0)
    scraper._resumed_fetched = scraper.stats['fetched']
    log.info(f"  Resumed state: {len(visited)} visited URLs, {scraper.stats['fetched']} fetched")


async def main():
    parser = argparse.ArgumentParser(description='Сбор легитимных номеров РФ')
    parser.add_argument('--cities', nargs='+', default=['msk', 'spb', 'ekb', 'kzn', 'nnov', 'rnd', 'ufa', 'krasnodar', 'voronezh', 'chelyabinsk'],
                        help='Города (ключи: msk, spb, ekb, kzn, ...)'),
    parser.add_argument('--profile', choices=['smart', 'broad', 'org', 'weak'], default='smart',
                        help='smart=сначала слабые/потом org, broad=всё, org=только организации, weak=только слабые категории')
    parser.add_argument('--concurrency', type=int, default=CONCURRENCY,
                        help='Макс. одновременных HTTP-запросов (глобальный лимит)')
    parser.add_argument('--per-host-concurrency', type=int, default=PER_HOST_CONCURRENCY,
                        help='Макс. параллельных запросов к одному хосту')
    parser.add_argument('--max-urls', type=int, default=0,
                        help='Макс. HTTP-запросов (0=без лимита)')
    parser.add_argument('--add-user-numbers', type=int, default=0,
                        help='Добавить N низкоуверенных обычных мобильных номеров из официального плана нумерации')
    parser.add_argument('--no-resume', action='store_true',
                        help='Игнорировать state-файл: переобойти все URL заново (сайты обновляются, новые номера будут). CSV с уже найденными номерами всё равно подхватывается для дедупа.')
    parser.add_argument('--reset-state', action='store_true',
                        help='Удалить state-файл перед стартом.')
    parser.add_argument('--source-timeout', type=float, default=120.0,
                        help='Макс. секунд на один источник (0=без лимита). '
                             'Если источник (напр. rusprofile) висит на банах/таймаутах — он будет отменён, '
                             'другие продолжат работу.')
    parser.add_argument('--output', default=OUTPUT_PATH,
                        help='Выходной CSV файл')
    args = parser.parse_args()

    spravker_cities = {k: v for k, v in SPRAVKER_CITIES.items() if k in args.cities}
    zoon_cities = {k: v for k, v in ZOON_CITIES.items() if k in args.cities}

    log.info(f"🚀 Starting legitimate number collector")
    log.info(f"  Cities: {args.cities}")
    log.info(f"  Spravker cities: {list(spravker_cities.keys())}")
    log.info(f"  Zoon cities: {list(zoon_cities.keys())}")
    log.info(f"  Profile: {args.profile}")
    log.info(f"  Concurrency: {args.concurrency} (per-host: {args.per_host_concurrency})")

    scraper = AsyncScraper(concurrency=args.concurrency,
                           per_host_concurrency=args.per_host_concurrency)
    scraper._output_path = args.output  # for incremental saves
    scraper._max_urls = args.max_urls   # 0 = unlimited
    await scraper.start()

    try:
        # 0a. Resume state (visited URLs)
        if args.reset_state and os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)
            log.info("  🗑  Removed state file (--reset-state)")
        if not args.no_resume:
            load_state(scraper)
        else:
            log.info("  ⏭  Skipping state resume (--no-resume): all URLs will be re-fetched")

        # 0b. Resume: load existing CSV so data isn't lost on restart
        if os.path.exists(args.output):
            with open(args.output, encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    num = row.get('normalized_number', '')
                    if num and num not in scraper.seen:
                        scraper.seen.add(num)
                        scraper.results.append(LegitEntry(
                            num,
                            row.get('name', ''),
                            row.get('category', ''),
                            row.get('source', ''),
                            row.get('city', ''),
                            row.get('url', ''),
                            parse_confidence(row.get('source_confidence'), 0.70),
                        ))
            log.info(f"  Resumed {len(scraper.results)} existing entries from {args.output}")

        # 1. Load existing whitelist
        official = load_official_whitelist()
        for entry in official:
            scraper.add(entry)
        log.info(f"  Loaded {len(official)} official whitelist entries")

        # 2. Add hardcoded hotlines
        for num, name, cat in OFFICIAL_HOTLINES:
            scraper.add(LegitEntry(num, name, cat, 'official_hotline', '', '', 0.95))
        log.info(f"  Added {len(OFFICIAL_HOTLINES)} hardcoded hotlines")

        # 3. Load blacklist (fraud/suspect numbers to exclude)
        scraper.load_blacklist()

        # 4. Scrape all sources
        stats = await run_all(
            scraper, spravker_cities, zoon_cities,
            profile=args.profile, source_timeout=args.source_timeout,
        )

        if args.add_user_numbers > 0:
            log.info(f"▶ Source: numbering_plan_background ({args.add_user_numbers})")
            t0 = time.monotonic()
            count = generate_user_numbers(scraper, args.add_user_numbers)
            stats['numbering_plan_background'] = (count, time.monotonic() - t0)
            save_results(scraper.results, scraper._output_path)
            log.info(f"  💾 Saved {len(scraper.results)} numbers after background users")

        # 4. Save
        total = save_results(scraper.results, args.output)
        log.info(f"\n{'='*60}")
        log.info(f"✅ Done! {total} unique legitimate numbers saved to {args.output}")
        log.info(f"   HTTP: {scraper.stats['fetched']} fetched, {scraper.stats['failed']} failed")
        log.info(f"\n   Source breakdown:")
        for name, (count, elapsed) in sorted(stats.items(), key=lambda x: -x[1][0]):
            log.info(f"     {name:20s}: {count:5d} numbers ({elapsed:.1f}s)")

        cats: Dict[str, int] = {}
        for e in scraper.results:
            cats[e.category] = cats.get(e.category, 0) + 1
        log.info(f"\n   Category breakdown:")
        for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
            log.info(f"     {cat:20s}: {count:5d}")

    finally:
        # Always save what we have
        save_results(scraper.results, args.output)
        save_state(scraper, args.output)
        log.info(f"💾 Final save: {len(scraper.results)} numbers | {len(scraper.visited_urls)} URLs visited")
        await scraper.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠ Interrupted — data already saved incrementally")
