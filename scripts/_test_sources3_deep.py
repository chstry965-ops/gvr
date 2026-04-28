"""Deep test: find phones in JS/JSON blobs, API endpoints, pagination."""
import aiohttp, asyncio, re, json, sys

PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}')
TEL_LINK_RE = re.compile(r'href="tel:([^"]+)"')
# JSON phone fields
JSON_PHONE_RE = re.compile(r'"(?:phone|phones|telephone|tel|mobile|number|contact_phone|work_phone)"\s*:\s*"([^"]+)"')
# Numbers in data attributes
DATA_PHONE_RE = re.compile(r'data-(?:phone|tel|number)="([^"]+)"')

SITES = [
    # ── firmika.ru — 200 OK, 0 phones — investigate ──
    ("firmika_msk", "https://firmika.ru/moskva"),
    ("firmika_msk_banks", "https://firmika.ru/moskva/banki"),
    ("firmika_msk_banks2", "https://firmika.ru/moskva/bank/"),
    ("firmika_msk_clinics", "https://firmika.ru/moskva/kliniki/"),
    ("firmika_msk_stomat", "https://firmika.ru/moskva/stomatologiya/"),
    ("firmika_msk_apteki", "https://firmika.ru/moskva/apteki/"),
    ("firmika_msk_auto", "https://firmika.ru/moskva/avtoservisy/"),
    ("firmika_msk_food", "https://firmika.ru/moskva/restorany/"),
    ("firmika_msk_beauty", "https://firmika.ru/moskva/salony-krasoty/"),
    # ── prodoctorov.ru — 200 OK, 0 phones — investigate ──
    ("prodoctorov_msk", "https://prodoctorov.ru/moskva/"),
    ("prodoctorov_msk_clinics", "https://prodoctorov.ru/moskva/kliniki/"),
    ("prodoctorov_msk_dentists", "https://prodoctorov.ru/moskva/stomatologi/"),
    ("prodoctorov_msk_hospitals", "https://prodoctorov.ru/moskva/bolnicy/"),
    ("prodoctorov_clinic_page", "https://prodoctorov.ru/moskva/kliniki/medsi-klinika-1"),
    # ── zoon.ru — pagination ──
    ("zoon_msk_medical_p1", "https://zoon.ru/msk/medical/?page=1"),
    ("zoon_msk_medical_p2", "https://zoon.ru/msk/medical/?page=2"),
    ("zoon_msk_medical_p3", "https://zoon.ru/msk/medical/?page=3"),
    ("zoon_msk_beauty_p1", "https://zoon.ru/msk/beauty/?page=1"),
    ("zoon_msk_auto_p1", "https://zoon.ru/msk/automotive/?page=1"),
    ("zoon_msk_food_p1", "https://zoon.ru/msk/food/?page=1"),
    ("zoon_spb_medical_p1", "https://zoon.ru/spb/medical/?page=1"),
    # ── spravker — more categories ──
    ("spravker_msk_auto", "https://msk.spravker.ru/avto/"),
    ("spravker_msk_education", "https://msk.spravker.ru/obrazovanie/"),
    ("spravker_msk_realty", "https://msk.spravker.ru/nedvizhimost/"),
    ("spravker_msk_insurance", "https://msk.spravker.ru/strahovanie/"),
    # ── rusprofile — pagination ──
    ("rusprofile_bank_p1", "https://www.rusprofile.ru/search?query=банк&page=1"),
    ("rusprofile_bank_p2", "https://www.rusprofile.ru/search?query=банк&page=2"),
    ("rusprofile_clinic_p1", "https://www.rusprofile.ru/search?query=клиника&page=1"),
    ("rusprofile_school_p1", "https://www.rusprofile.ru/search?query=школа&page=1"),
    ("rusprofile_auto_p1", "https://www.rusprofile.ru/search?query=автосервис&page=1"),
    # ── new candidates ──
    ("medportal", "https://medportal.ru/"),
    ("sberhealth_clinics", "https://sberhealth.ru/clinic/moskva/"),
    ("namemed_clinics", "https://www.nameemed.ru/moskva/kliniki"),
    ("gorod_gov", "https://mosgorzdrav.ru/"),
    ("mosru", "https://www.mos.ru/"),
]

async def deep_test(session, name, url):
    try:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                print(f"  {name}: HTTP {r.status}")
                return
            html = await r.text()

            # 1. Standard regex phones
            phones = PHONE_RE.findall(html)
            # 2. href="tel:" links
            tel_links = TEL_LINK_RE.findall(html)
            # 3. JSON phone fields
            json_phones = JSON_PHONE_RE.findall(html)
            # 4. data-phone attributes
            data_phones = DATA_PHONE_RE.findall(html)
            # 5. Check for <script> blocks with phone data
            script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            script_phones = []
            for block in script_blocks:
                if len(block) > 50 and ('phone' in block.lower() or 'tel' in block.lower()):
                    found = PHONE_RE.findall(block)
                    json_found = JSON_PHONE_RE.findall(block)
                    script_phones.extend(found)
                    script_phones.extend(json_found)

            total = len(phones) + len(tel_links) + len(json_phones) + len(data_phones) + len(script_phones)

            if total > 0:
                print(f"  {name}: ✅ TOTAL={total} (regex={len(phones)}, tel={len(tel_links)}, json={len(json_phones)}, data={len(data_phones)}, script={len(script_phones)})")
                all_phones = list(set(phones[:5] + tel_links[:5] + json_phones[:5] + data_phones[:5] + script_phones[:5]))
                print(f"    sample: {all_phones[:8]}")
            else:
                # Check for SPA indicators
                has_react = 'react' in html.lower() or '__NEXT_DATA__' in html
                has_vue = 'vue' in html.lower() or '__NUXT__' in html
                has_angular = 'ng-app' in html or 'ng-version' in html
                has_next_data = '__NEXT_DATA__' in html
                has_window_data = bool(re.search(r'window\.__[A-Z_]+__', html))
                spa = []
                if has_react: spa.append('React')
                if has_vue: spa.append('Vue')
                if has_angular: spa.append('Angular')
                if has_next_data: spa.append('Next.js')
                if has_window_data: spa.append('window.__DATA__')
                spa_str = ', '.join(spa) if spa else 'unknown'
                print(f"  {name}: ❌ 0 phones, SPA={spa_str}, html_len={len(html)}")

    except Exception as e:
        print(f"  {name}: ERROR {type(e).__name__}: {str(e)[:80]}")

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9',
    }) as session:
        for name, url in SITES:
            print(f"\n{name}: {url}")
            await deep_test(session, name, url)
            await asyncio.sleep(0.8)

asyncio.run(main())
