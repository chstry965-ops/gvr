"""Test 5 sources for personal/individual phone numbers (not organizations, not fraud)."""
import aiohttp, asyncio, re, json

PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()\xa0]*\d{3}[\s\-()\xa0]*\d{3}[\s\-()\xa0]*\d{2}[\s\-()\xa0]*\d{2}')
TEL_HREF_RE = re.compile(r'href="tel:([^"]+)"')
LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)

URLS = [
    # ── Авито ──
    ("avito_search_phone_msk", "https://www.avito.ru/moskva/telefony/q-"),
    ("avito_uslugi_msk", "https://www.avito.ru/moskva/uslugi"),
    ("avito_repair_msk", "https://www.avito.ru/moskva/uslugi/remont_i_stroitelstvo"),
    ("avito_realty_msk", "https://www.avito.ru/moskva/nedvizhimost"),
    ("avito_transport_msk", "https://www.avito.ru/moskva/transport"),
    ("avito_item_page", "https://www.avito.ru/moskva/telefony/iphone_15_3456789012"),
    # ── Профи.ру ──
    ("profi_main", "https://profi.ru/"),
    ("profi_repetitor_msk", "https://profi.ru/repetitor/moskva/"),
    ("profi_master_msk", "https://profi.ru/master/moskva/"),
    ("profi_remont_msk", "https://profi.ru/remont-kvartir/moskva/"),
    ("profi_krasota_msk", "https://profi.ru/kosmetolog/moskva/"),
    # ── Яндекс Услуги ──
    ("yandex_uslugi_msk", "https://uslugi.yandex.ru/moskva"),
    ("yandex_uslugi_remont", "https://uslugi.yandex.ru/moskva/remont-kvartir"),
    ("yandex_uslugi_kraska", "https://uslugi.yandex.ru/moskva/pokraska"),
    ("yandex_uslugi_clean", "https://uslugi.yandex.ru/moskva/uborka"),
    # ── ЦИАН ──
    ("cian_rent_msk", "https://www.cian.ru/cat.php?deal_type=rent&engine_version=2&offer_type=flat&region=1"),
    ("cian_sale_msk", "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1"),
    ("cian_owner_msk", "https://www.cian.ru/cat.php?deal_type=rent&engine_version=2&offer_type=flat&region=1&is_by_homeowner=1"),
    # ── Домклик ──
    ("domclick_sale_msk", "https://domclick.ru/search/sale/moskva"),
    ("domclick_rent_msk", "https://domclick.ru/search/rent/moskva"),
    # ── VK объявления ──
    ("vk_market_msk", "https://vk.com/market-123456"),
    ("vk_search_flea", "https://vk.com/search?c%5Bsection%5D=market&c%5Bq%5D=продам+телефон&c%5Bcity%5D=1"),
    # ── Bonus: YouDo ──
    ("youdo_msk", "https://youdo.com/moskva/"),
    ("youdo_remont", "https://youdo.com/moskva/remont-kvartir/"),
    # ── Bonus: HH.ru (резюме с телефонами) ──
    ("hh_resume_search", "https://hh.ru/search/resume?area=1&text=менеджер"),
]

async def test(session, name, url):
    try:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=12)) as r:
            if r.status != 200:
                print(f"  {name}: HTTP {r.status}")
                return
            html = await r.text()
            phones = PHONE_RE.findall(html)
            tel_links = TEL_HREF_RE.findall(html)
            # JSON-LD
            json_names = 0
            for block in LD_JSON_RE.findall(html):
                try:
                    data = json.loads(block)
                    if isinstance(data, dict) and data.get('@type') in ('ItemList', 'Product', 'Person', 'Service'):
                        json_names += 1
                except: pass
            # SPA detection
            has_next = '__NEXT_DATA__' in html
            has_nuxt = '__NUXT__' in html
            has_react = 'react' in html.lower()[:2000]
            spa = 'Next' if has_next else 'Nuxt' if has_nuxt else 'React' if has_react else ''
            
            total = len(phones) + len(tel_links)
            if total > 0:
                print(f"  {name}: ✅ phones={len(phones)}, tel={len(tel_links)}, json_ld={json_names}")
                if tel_links:
                    print(f"    tel sample: {tel_links[:5]}")
            else:
                print(f"  {name}: ❌ 0 phones, SPA={spa}, html_len={len(html)}, json_ld={json_names}")
    except Exception as e:
        print(f"  {name}: ERROR {type(e).__name__}: {str(e)[:60]}")

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }) as session:
        for name, url in URLS:
            print(f"\n{name}: {url}")
            await test(session, name, url)
            await asyncio.sleep(0.5)

asyncio.run(main())
