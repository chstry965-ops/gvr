"""Test round 2: detailed check of each potential source."""
import aiohttp, asyncio, re, sys

PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}')
TEL_LINK_RE = re.compile(r'tel:([0-9+\-()\s]+)')

URLS = [
    # Spravker — different subdomains and categories
    ("spravker_msk_banks", "https://msk.spravker.ru/banki/"),
    ("spravker_msk_stomat", "https://msk.spravker.ru/stomatologicheskie-kliniki-i-tsentryi/"),
    ("spravker_spb_banks", "https://spb.spravker.ru/banki/"),
    ("spravker_ekb_banks", "https://ekaterinburg.spravker.ru/banki/"),
    ("spravker_msk_gov", "https://msk.spravker.ru/gosudarstvo-i-obschestvo/"),
    ("spravker_msk_transport", "https://msk.spravker.ru/transport/"),
    # Rusprofile — search and company pages
    ("rusprofile_search_bank", "https://www.rusprofile.ru/search?query=сбербанк"),
    ("rusprofile_search_clinic", "https://www.rusprofile.ru/search?query=клиника"),
    ("rusprofile_search_school", "https://www.rusprofile.ru/search?query=школа"),
    ("rusprofile_id10027", "https://www.rusprofile.ru/id/10027"),
    ("rusprofile_id30210", "https://www.rusprofile.ru/id/30210"),
    # Firmika — try different URL patterns
    ("firmika_msk_banks", "https://firmika.ru/moskva/banki"),
    ("firmika_msk_clinics", "https://firmika.ru/moskva/kliniki"),
    ("firmika_msk", "https://firmika.ru/moskva"),
    # Zoon
    ("zoon_msk_medical", "https://zoon.ru/msk/medical/"),
    ("zoon_msk_beauty", "https://zoon.ru/msk/beauty/"),
    # Yell
    ("yell_msk_medical", "https://yell.ru/moskva/medical/"),
    ("yell_msk_banks", "https://yell.ru/moskva/finance/"),
    # Prodoctorov
    ("prodoctorov_msk", "https://prodoctorov.ru/moskva/"),
    # 2GIS API
    ("2gis_msk_clinic", "https://2gis.ru/moskva/search/клиника"),
    ("2gis_api", "https://catalog.api.2gis.ru/search?q=клиника&region_id=32&fields=items.contact_options&key=demo"),
    # Otzovik
    ("otzovik_msk", "https://otzovik.com/r/medical_services/moskva/"),
]

async def test_url(session, name, url):
    try:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                print(f"  {name}: HTTP {r.status}")
                return
            html = await r.text()
            phones = PHONE_RE.findall(html)
            tel_links = TEL_LINK_RE.findall(html)
            print(f"  {name}: OK len={len(html)}, phones={len(phones)}, tel_links={len(tel_links)}")
            if phones:
                print(f"    sample phones: {phones[:8]}")
            if tel_links:
                print(f"    sample tel: {tel_links[:8]}")
            # Check for JSON/API patterns
            if '"phone"' in html or '"phones"' in html or '"contact"' in html:
                print(f"    HAS JSON phone/contact fields!")
            # Check for obfuscated phones
            if 'tel:' in html.lower():
                tel_matches = re.findall(r'href="tel:([^"]+)"', html)
                print(f"    href=tel links: {tel_matches[:8]}")
    except Exception as e:
        print(f"  {name}: ERROR {type(e).__name__}: {str(e)[:100]}")

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }) as session:
        for name, url in URLS:
            print(f"\n{name}: {url}")
            await test_url(session, name, url)
            await asyncio.sleep(1)

asyncio.run(main())
