"""Quick test: check real HTML structure of each source for phone extraction."""
import aiohttp, asyncio, re, sys

PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}')
TEL_LINK_RE = re.compile(r'tel:([0-9+\-()\s]+)')
PHONE_CLASS_RE = re.compile(r'class="[^"]*phone[^"]*"[^>]*>([^<]+)', re.I)

URLS = [
    ("spravker_detail", "https://msk.spravker.ru/bolnicy/ekomed-2.htm"),
    ("spravker_category", "https://msk.spravker.ru/bolnicy/"),
    ("rusprofile_search", "https://www.rusprofile.ru/search?query=клиника"),
    ("rusprofile_company", "https://www.rusprofile.ru/id/10000"),
    ("2gis", "https://2gis.ru/moskva/search/клиника"),
    ("yandex_maps", "https://yandex.ru/maps/213/moskva/search/клиника/"),
    ("zvonki_info", "https://zvonki.info/"),
    ("ktozvonit", "https://ktozvonit.ru/"),
    ("orgpage", "https://orgpage.ru/moskva/banki"),
    ("rosfirm", "https://rosfirm.ru/moskva/bank"),
    ("spravochnik_tv", "https://spravochnik-telefonov.ru/moskva"),
    ("biznes_afisha", "https://biznes-afisha.ru/moskva/banki"),
    ("firmika", "https://firmika.ru/moskva/банки"),
]

async def test_url(session, name, url):
    try:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                print(f"  {name}: HTTP {r.status}")
                return
            html = await r.text()
            phones = PHONE_RE.findall(html)
            tel_links = TEL_LINK_RE.findall(html)
            phone_classes = PHONE_CLASS_RE.findall(html)
            print(f"  {name}: len={len(html)}, phones={phones[:5]}, tel_links={tel_links[:5]}, phone_cls={phone_classes[:5]}")
    except Exception as e:
        print(f"  {name}: ERROR {e}")

async def main():
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0 Chrome/125.0'}) as session:
        for name, url in URLS:
            print(f"Testing {name}: {url}")
            await test_url(session, name, url)
            await asyncio.sleep(1)

asyncio.run(main())
