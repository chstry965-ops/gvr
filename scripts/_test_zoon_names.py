"""Extract org names from zoon script[6] JSON block."""
import aiohttp, asyncio, re, json

async def main():
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0'
    }) as session:
        async with session.get('https://zoon.ru/msk/medical/', ssl=False) as r:
            html = await r.text()

        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        for i, s in enumerate(scripts):
            if 'phone' in s.lower() and len(s) > 200:
                print(f"=== Script block {i}, len={len(s)} ===")
                # Try to parse as JSON
                # Find the JSON object
                try:
                    data = json.loads(s)
                    print(f"  Parsed as JSON! Keys: {list(data.keys())[:10]}")
                except:
                    # Try to find assignment
                    m = re.match(r'window\.\w+\s*=\s*(\{.*\})\s*;?\s*$', s.strip(), re.DOTALL)
                    if m:
                        try:
                            data = json.loads(m.group(1))
                            print(f"  Parsed window.X = JSON! Keys: {list(data.keys())[:10]}")
                        except:
                            print(f"  Not valid JSON, first 500 chars:")
                            print(s[:500])
                    else:
                        print(f"  Not JSON assignment, first 500 chars:")
                        print(s[:500])

                # Extract name-phone pairs
                name_phone = re.findall(r'"title"\s*:\s*"([^"]+)".*?"phone"\s*:\s*"([^"]+)"', s)
                if name_phone:
                    print(f"\n  name-phone pairs: {len(name_phone)}")
                    for n, p in name_phone[:10]:
                        print(f"    {n[:50]:50s} → {p}")

                phone_name = re.findall(r'"phone"\s*:\s*"([^"]+)".*?"title"\s*:\s*"([^"]+)"', s)
                if phone_name:
                    print(f"\n  phone-name pairs: {len(phone_name)}")
                    for p, n in phone_name[:10]:
                        print(f"    {p} → {n[:50]}")

                # Look for any structured data
                items = re.findall(r'\{[^{}]*"title"\s*:\s*"([^"]+)"[^{}]*"phone"\s*:\s*"([^"]+)"[^{}]*\}', s)
                if items:
                    print(f"\n  Structured items: {len(items)}")
                    for n, p in items[:10]:
                        print(f"    {n[:50]:50s} → {p}")

                break

asyncio.run(main())
