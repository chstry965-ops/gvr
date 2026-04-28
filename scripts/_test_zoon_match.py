"""Match zoon JSON-LD names with tel: links by position."""
import aiohttp, asyncio, re, json

LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
TEL_HREF_RE = re.compile(r'href="tel:([^"]+)"')

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0'
    }) as session:
        async with session.get('https://zoon.ru/msk/medical/', ssl=False) as r:
            html = await r.text()

    # Get names from JSON-LD
    blocks = LD_JSON_RE.findall(html)
    names = []
    for block in blocks:
        try:
            data = json.loads(block)
        except:
            continue
        if data.get('@type') == 'ItemList' and 'itemListElement' in data:
            for item in data['itemListElement']:
                biz = item.get('item', {})
                name = biz.get('name', '')
                if name:
                    names.append(name)

    # Get phones from tel: links
    tel_phones = TEL_HREF_RE.findall(html)

    print(f"Names: {len(names)}, Phones: {len(tel_phones)}")
    print(f"\nMatched (by index):")
    for i in range(min(len(names), len(tel_phones))):
        print(f"  {names[i][:50]:50s} → {tel_phones[i]}")

    # Also check if there are more phones than names (regex phones)
    PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}')
    all_phones = PHONE_RE.findall(html)
    print(f"\nTotal regex phones: {len(all_phones)}, tel: links: {len(tel_phones)}")
    # Extra phones not in tel: links
    tel_set = set(tel_phones)
    extra = [p for p in all_phones if p not in tel_set and len(p.replace(' ','').replace('-','').replace('(','').replace(')','')) >= 11]
    print(f"Extra phones (not in tel:): {len(extra)}")
    print(f"Sample extra: {extra[:10]}")

asyncio.run(main())
