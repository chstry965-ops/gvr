"""Test zoon pagination — find the real pagination pattern."""
import aiohttp, asyncio, re

TEL_HREF_RE = re.compile(r'href="tel:([^"]+)"')
PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}')
# Zoon org name patterns
ZOON_NAME_RE = re.compile(r'<a[^>]*class="[^"]*mini-title[^"]*"[^>]*>([^<]+)</a>', re.I)
ZOON_NAME2_RE = re.compile(r'"title"\s*:\s*"([^"]+)"', re.I)
ZOON_NAME3_RE = re.compile(r'data-title="([^"]+)"', re.I)

URLS = [
    ("zoon_msk_medical_p1", "https://zoon.ru/msk/medical/?page=1"),
    ("zoon_msk_medical_p2", "https://zoon.ru/msk/medical/?page=2"),
    ("zoon_msk_medical_p0", "https://zoon.ru/msk/medical/"),
    ("zoon_msk_medical_next", "https://zoon.ru/msk/medical/?m=listing&o=new"),
    ("zoon_msk_beauty_p1", "https://zoon.ru/msk/beauty/?page=1"),
    ("zoon_msk_auto_p1", "https://zoon.ru/msk/automotive/?page=1"),
    ("zoon_spb_medical_p1", "https://zoon.ru/spb/medical/?page=1"),
    # Try API-style endpoints
    ("zoon_api_search", "https://zoon.ru/api/v2/search?city=msk&category=medical"),
]

async def test(session, name, url):
    try:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                print(f"  {name}: HTTP {r.status}")
                return
            html = await r.text()
            phones = PHONE_RE.findall(html)
            tel_links = TEL_HREF_RE.findall(html)
            names1 = ZOON_NAME_RE.findall(html)
            names2 = ZOON_NAME2_RE.findall(html)
            names3 = ZOON_NAME3_RE.findall(html)
            print(f"  {name}: phones={len(phones)}, tel={len(tel_links)}, names1={len(names1)}, names2={len(names2)}, names3={len(names3)}")
            if names1: print(f"    names1: {names1[:5]}")
            if names2: print(f"    names2: {names2[:5]}")
            if names3: print(f"    names3: {names3[:5]}")
            # Check for JSON data blocks
            json_blocks = re.findall(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
            if json_blocks:
                print(f"    __INITIAL_STATE__ found, len={len(json_blocks[0])}")
            json_blocks2 = re.findall(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', html, re.DOTALL)
            if json_blocks2:
                print(f"    __PRELOADED_STATE__ found, len={len(json_blocks2[0])}")
            # Look for any large JSON with phone data
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            for i, s in enumerate(scripts):
                if 'phone' in s.lower() and len(s) > 200:
                    print(f"    script[{i}] has 'phone', len={len(s)}")
                    # Extract a sample
                    phone_jsons = re.findall(r'"phone[^"]*"\s*:\s*"([^"]+)"', s)
                    if phone_jsons:
                        print(f"      phone fields: {phone_jsons[:5]}")
                    name_jsons = re.findall(r'"title"\s*:\s*"([^"]+)"', s)
                    if name_jsons:
                        print(f"      title fields: {name_jsons[:5]}")
                    break
    except Exception as e:
        print(f"  {name}: ERROR {type(e).__name__}: {str(e)[:80]}")

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0'
    }) as session:
        for name, url in URLS:
            print(f"\n{name}: {url}")
            await test(session, name, url)
            await asyncio.sleep(1)

asyncio.run(main())
