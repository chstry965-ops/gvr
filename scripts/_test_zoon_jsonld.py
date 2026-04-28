"""Extract org names from zoon JSON-LD ItemList."""
import aiohttp, asyncio, re, json

LD_JSON_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0'
    }) as session:
        async with session.get('https://zoon.ru/msk/medical/', ssl=False) as r:
            html = await r.text()

    blocks = LD_JSON_RE.findall(html)
    print(f"Found {len(blocks)} JSON-LD blocks")

    for i, block in enumerate(blocks):
        try:
            data = json.loads(block)
        except:
            continue

        print(f"\nBlock {i}: type={data.get('@type')}")
        if data.get('@type') == 'ItemList' and 'itemListElement' in data:
            items = data['itemListElement']
            print(f"  Items: {len(items)}")
            for item in items[:20]:
                biz = item.get('item', {})
                name = biz.get('name', '?')
                phone = biz.get('telephone', '?')
                addr = biz.get('address', {})
                if isinstance(addr, dict):
                    addr_str = addr.get('addressLocality', '')
                else:
                    addr_str = str(addr)
                print(f"    {name[:45]:45s} | {phone:20s} | {addr_str}")
        elif data.get('@type') == 'LocalBusiness':
            name = data.get('name', '?')
            phone = data.get('telephone', '?')
            print(f"  Single business: {name} | {phone}")

asyncio.run(main())
