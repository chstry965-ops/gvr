"""Test pagination and subcategories for personal number sources."""
import aiohttp, asyncio, re, json

PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()\xa0]*\d{3}[\s\-()\xa0]*\d{3}[\s\-()\xa0]*\d{2}[\s\-()\xa0]*\d{2}')
TEL_HREF_RE = re.compile(r'href="tel:([^"]+)"')

URLS = [
    # CIAN — pagination + different deal types
    ("cian_sale_p1", "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&p=1"),
    ("cian_sale_p2", "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&p=2"),
    ("cian_sale_p3", "https://www.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=1&p=3"),
    ("cian_rent_p1", "https://www.cian.ru/cat.php?deal_type=rent&engine_version=2&offer_type=flat&region=1&p=1"),
    ("cian_rent_owner", "https://www.cian.ru/cat.php?deal_type=rent&engine_version=2&offer_type=flat&region=1&is_by_homeowner=1&p=1"),
    # hands.ru — categories
    ("hands_categories", "https://hands.ru/categories/"),
    ("hands_programmers", "https://hands.ru/programmers/"),
    ("hands_designers", "https://hands.ru/designers/"),
    ("hands_translators", "https://hands.ru/translators/"),
    ("hands_copywriters", "https://hands.ru/copywriters/"),
    # fl.ru — categories
    ("fl_projects", "https://www.fl.ru/projects/"),
    ("fl_freelancers", "https://www.fl.ru/freelancers/"),
    ("fl_portfolios", "https://www.fl.ru/portfolios/"),
    # freelance.ru
    ("freelance_projects", "https://freelance.ru/projects/"),
    ("freelance_profiles", "https://freelance.ru/profiles/"),
    # kwork.ru
    ("kwork_categories", "https://kwork.ru/categories"),
    ("kwork_graphics", "https://kwork.ru/graphics-design"),
    ("kwork_programming", "https://kwork.ru/programming"),
    ("kwork_texts", "https://kwork.ru/texts"),
    # Drom.ru — deeper
    ("drom_phone_baza", "https://baza.drom.ru/"),
    ("drom_sakhalin", "https://auto.drom.ru/sakhalin/"),
    ("drom_vladivostok", "https://auto.drom.ru/vladivostok/"),
    # Avito — try different categories that might have phones
    ("avito_uslugi_remont", "https://www.avito.ru/moskva/uslugi/remont_i_stroitelstvo"),
    ("avito_uslugi_krasota", "https://www.avito.ru/moskva/uslugi/krasota_zdorove"),
    ("avito_uslugi_obuchenie", "https://www.avito.ru/moskva/uslugi/obuchenie"),
    ("avito_uslugi_transport", "https://www.avito.ru/moskva/uslugi/transport"),
    ("avito_spb_uslugi", "https://www.avito.ru/sankt-peterburg/uslugi"),
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
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            script_phones = 0
            for s in scripts:
                if 'phone' in s.lower() and len(s) > 100:
                    script_phones += len(PHONE_RE.findall(s))
            total = len(phones) + len(tel_links) + script_phones
            if total > 0:
                print(f"  {name}: ✅ {total} (html={len(phones)}, tel={len(tel_links)}, script={script_phones})")
            else:
                print(f"  {name}: ❌ 0, len={len(html)}")
    except Exception as e:
        print(f"  {name}: ERROR {type(e).__name__}: {str(e)[:50]}")

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0',
    }) as session:
        for name, url in URLS:
            print(f"\n{name}: {url}")
            await test(session, name, url)
            await asyncio.sleep(0.5)

asyncio.run(main())
