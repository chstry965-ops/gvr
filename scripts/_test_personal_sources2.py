"""Deep test: find phones in JSON/API/hidden data of Avito, CIAN, HH."""
import aiohttp, asyncio, re, json

PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()\xa0]*\d{3}[\s\-()\xa0]*\d{3}[\s\-()\xa0]*\d{2}[\s\-()\xa0]*\d{2}')
TEL_HREF_RE = re.compile(r'href="tel:([^"]+)"')

URLS = [
    # Авито — try item pages with real IDs
    ("avito_api_search", "https://www.avito.ru/api/1/items?locationId=621540&categoryId=114&query=ремонт&page=1"),
    ("avito_item_example", "https://www.avito.ru/moskva/uslugi/remont_i_stroitelstvo/remont_kvartiry_pod_klyuch-1234567890"),
    # Авито — check __NEXT_DATA__ or similar
    # ЦИАН — try API
    ("cian_api", "https://www.cian.ru/api/rent/cat/?deal_type=rent&engine_version=2&offer_type=flat&region=1"),
    ("cian_sale_page2", "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&p=2"),
    # HH.ru — resume pages with contacts
    ("hh_resume_page", "https://hh.ru/resume/1234567890abcdef"),
    # Auto.ru — sellers
    ("autoru_msk", "https://auto.ru/moskva/cars/all/"),
    ("autoru_api", "https://auto.ru/api/v1/search/cars?geo_id=213&page=1"),
    # Drom.ru — car sellers (personal numbers)
    ("drom_msk", "https://auto.drom.ru/region77/"),
    ("drom_region", "https://baza.drom.ru/phone/"),
    # Irr.ru — classifieds
    ("irr_msk", "https://irr.ru/real-estate/rent/moskva/"),
    ("irr_sale_msk", "https://irr.ru/real-estate/sale/moskva/"),
    # Kufar (Беларусь, но много РФ)
    ("kufar", "https://kufar.by/l"),
    # OLX (Казахстан, но есть РФ)
    ("olx_kz", "https://www.olx.kz/"),
    # Slando/Avito alternatives
    ("slando_msk", "https://moskva.slando.ru/"),
    # Hands.ru — freelance
    ("hands_ru", "https://hands.ru/"),
    # Fl.ru — freelance
    ("fl_ru", "https://www.fl.ru/"),
    # Freelance.ru
    ("freelance_ru", "https://freelance.ru/"),
    # Kwork.ru
    ("kwork_ru", "https://kwork.ru/"),
    # Profi.ru — try different URL patterns
    ("profi_repetitor_api", "https://profi.ru/api/v2/search?query=репетитор&location=moskva"),
    ("profi_profile", "https://profi.ru/profile/12345/"),
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
            # Check for __NEXT_DATA__
            next_data = re.findall(r'__NEXT_DATA__\s*=\s*({.*?})\s*</script>', html, re.DOTALL)
            next_phones = 0
            if next_data:
                phone_matches = PHONE_RE.findall(next_data[0])
                next_phones = len(phone_matches)
            # Check scripts for phone patterns
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            script_phones = 0
            for s in scripts:
                if 'phone' in s.lower() and len(s) > 100:
                    pm = PHONE_RE.findall(s)
                    script_phones += len(pm)
            
            total = len(phones) + len(tel_links) + next_phones + script_phones
            if total > 0:
                print(f"  {name}: ✅ total={total} (html={len(phones)}, tel={len(tel_links)}, next={next_phones}, script={script_phones})")
                all_p = phones[:3] + tel_links[:3]
                if all_p: print(f"    sample: {all_p}")
            else:
                has_next = bool(next_data)
                print(f"  {name}: ❌ 0 phones, html_len={len(html)}, __NEXT_DATA__={has_next}")
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
