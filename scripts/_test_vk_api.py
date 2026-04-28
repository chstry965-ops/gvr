"""Test VK API for public phone numbers from community market listings."""
import aiohttp, asyncio, json, re

PHONE_RE = re.compile(r'(?:\+7|8)[\s\-()\xa0]*\d{3}[\s\-()\xa0]*\d{3}[\s\-()\xa0]*\d{2}[\s\-()\xa0]*\d{2}')

# VK API method: market.search — returns items from community market
# No auth needed for public communities
# Test with popular flea market / classified groups

GROUPS = [
    # Moscow flea markets / classifieds
    ('avito_podpiska_msk', -12345678),  # placeholder
]

# Real approach: search VK for communities with market items
SEARCH_QUERIES = [
    'продам телефон москва',
    'ремонт квартир москва',
    'репетитор москва',
    'куплю продам спб',
]

async def test_vk(session):
    # 1. Search communities
    for q in SEARCH_QUERIES[:2]:
        url = f'https://api.vk.com/method/groups.search?q={q}&count=5&access_token=anonymous&v=5.131'
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                if 'response' in data:
                    for g in data['response']['items'][:3]:
                        print(f"  Group: {g['name']} (id={g['id']})")
                else:
                    print(f"  Search '{q}': {data.get('error', {}).get('error_msg', 'unknown')}")
        except Exception as e:
            print(f"  Error: {e}")
        await asyncio.sleep(0.3)

    # 2. Try market.get from a known public group
    # Popular: "Отдам даром Москва" etc
    test_group_ids = [
        -339925,   # Авито Москва (large classifieds)
        -172833,   # Куплю-Продам Москва
        -2943,     # Доска объявлений
    ]
    
    for gid in test_group_ids:
        url = f'https://api.vk.com/method/market.get?owner_id={gid}&count=10&access_token=anonymous&v=5.131'
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                if 'response' in data:
                    items = data['response'].get('items', [])
                    print(f"\n  Group {gid}: {len(items)} items")
                    for item in items[:5]:
                        desc = item.get('description', '')
                        phones = PHONE_RE.findall(desc)
                        title = item.get('title', '')[:40]
                        if phones:
                            print(f"    ✅ {title}: phones={phones}")
                        else:
                            print(f"    ❌ {title}: no phone in desc")
                else:
                    err = data.get('error', {}).get('error_msg', '')
                    print(f"  Group {gid}: {err}")
        except Exception as e:
            print(f"  Error: {e}")
        await asyncio.sleep(0.3)

    # 3. Try wall.get — posts often have phone numbers
    for gid in test_group_ids[:2]:
        url = f'https://api.vk.com/method/wall.get?owner_id={gid}&count=10&access_token=anonymous&v=5.131'
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                if 'response' in data:
                    posts = data['response'].get('items', [])
                    phones_found = 0
                    for post in posts[:10]:
                        text = post.get('text', '')
                        phones = PHONE_RE.findall(text)
                        phones_found += len(phones)
                    print(f"\n  Wall {gid}: {len(posts)} posts, {phones_found} phones")
                else:
                    err = data.get('error', {}).get('error_msg', '')
                    print(f"  Wall {gid}: {err}")
        except Exception as e:
            print(f"  Error: {e}")
        await asyncio.sleep(0.3)

async def main():
    async with aiohttp.ClientSession() as session:
        await test_vk(session)

asyncio.run(main())
