"""Find org names near phone numbers in zoon HTML."""
import aiohttp, asyncio, re

TEL_HREF_RE = re.compile(r'href="tel:([^"]+)"')
PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}')

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0'
    }) as session:
        async with session.get('https://zoon.ru/msk/medical/', ssl=False) as r:
            html = await r.text()

        # Find tel: links and surrounding context
        tel_positions = [(m.start(), m.group(1)) for m in TEL_HREF_RE.finditer(html)]
        print(f"Found {len(tel_positions)} tel: links")

        for pos, phone in tel_positions[:15]:
            # Get 500 chars before the tel: link
            context = html[max(0, pos-500):pos+50]
            # Look for org name patterns nearby
            # Pattern 1: <a class="...">Name</a> before phone
            name_a = re.findall(r'<a[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</a>', context)
            name_b = re.findall(r'<a[^>]*class="[^"]*name[^"]*"[^>]*>([^<]+)</a>', context)
            name_c = re.findall(r'class="[^"]*org[^"]*"[^>]*>([^<]{3,})<', context)
            name_d = re.findall(r'<strong[^>]*>([^<]+)</strong>', context)
            name_e = re.findall(r'<h[2-4][^>]*>([^<]+)</h[2-4]>', context)
            # Clean context
            clean = re.sub(r'<[^>]+>', ' ', context)
            clean = re.sub(r'\s+', ' ', clean).strip()[-200:]

            names = name_a + name_b + name_c + name_d + name_e
            print(f"\n  tel:{phone}")
            if names:
                print(f"    names found: {names[:3]}")
            print(f"    context tail: ...{clean[-100:]}")

        # Also check for JSON-LD structured data
        ld_json = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
        if ld_json:
            print(f"\n\nJSON-LD blocks: {len(ld_json)}")
            for i, block in enumerate(ld_json[:3]):
                print(f"  Block {i}: {block[:300]}")

        # Check for data-zoom attributes
        data_zoom = re.findall(r'data-zoom="([^"]+)"', html)
        if data_zoom:
            print(f"\n\ndata-zoom attrs: {len(data_zoom)}")
            for dz in data_zoom[:3]:
                print(f"  {dz[:200]}")

        # Check for data-item attributes
        data_items = re.findall(r'data-item-id="([^"]+)"', html)
        if data_items:
            print(f"\n\ndata-item-id attrs: {len(data_items)}")
            print(f"  sample: {data_items[:10]}")

asyncio.run(main())
