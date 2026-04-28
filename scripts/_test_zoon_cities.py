"""Quick test: which zoon city slugs actually work and return phones."""
import aiohttp, asyncio, re, json

LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
TEL_HREF_RE = re.compile(r'href="tel:([^"]+)"')

SLUGS = [
    'msk', 'spb', 'ekb', 'kzn', 'nnov', 'rnd', 'ufa', 'krasnodar',
    'voronezh', 'chelyabinsk', 'samara', 'perm', 'volgograd', 'barnaul',
    'tyumen', 'krasnoyarsk', 'izhevsk', 'yaroslavl', 'ryazan', 'tula',
    'omsk', 'nabchelny', 'vladivostok', 'novosibirsk', 'nizhnevartovsk',
    'saratov', 'tolyatti', 'ulyanovsk', 'irkutsk', 'habarovsk',
    'smolensk', 'kaliningrad', 'kursk', 'belgorod', 'lipetsk',
    'orol', 'bryansk', 'vladimir', 'ivanovo', 'kostroma',
]

async def test(session, slug):
    url = f'https://zoon.ru/{slug}/medical/'
    try:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return slug, 0, r.status
            html = await r.text()
            names = 0
            for block in LD_JSON_RE.findall(html):
                try:
                    data = json.loads(block)
                except: continue
                if data.get('@type') == 'ItemList':
                    names = len(data.get('itemListElement', []))
            tel = len(TEL_HREF_RE.findall(html))
            return slug, names, tel
    except Exception as e:
        return slug, 0, str(e)[:40]

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0'
    }) as session:
        for slug in SLUGS:
            s, names, tel = await test(session, slug)
            if names > 0 or (isinstance(tel, int) and tel > 0):
                print(f"  ✅ {s:20s}: names={names}, tel={tel}")
            elif isinstance(tel, int):
                print(f"  ❌ {s:20s}: HTTP {tel}")
            else:
                print(f"  ❌ {s:20s}: {tel}")
            await asyncio.sleep(0.3)

asyncio.run(main())
