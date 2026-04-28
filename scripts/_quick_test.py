"""Quick integration test of the real collector script."""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from ru_legitimate_collector import AsyncScraper, scrape_zoon, scrape_spravker, scrape_rusprofile, ZOON_CITIES, SPRAVKER_CITIES, ZOON_CATEGORIES, SPRAVKER_SUBCATEGORIES, RUSPROFILE_QUERIES

async def main():
    scraper = AsyncScraper(concurrency=10)
    await scraper.start()

    # Test zoon — just 2 pages, 1 city, 1 category
    print("=== ZOON TEST (msk, medical, 2 pages) ===")
    count = await scrape_zoon(scraper, {'msk': 'msk'}, ['medical'], 2)
    print(f"Zoon result: {count} numbers\n")

    # Test spravker — 1 city, 2 subcategories, 2 pages
    print("=== SPRAVKER TEST (msk, 2 subcats, 2 pages) ===")
    count = await scrape_spravker(
        scraper,
        {'msk': 'msk.spravker.ru'},
        ['bolnicy', 'stomatologicheskie-kliniki-i-tsentryi'],
        2
    )
    print(f"Spravker result: {count} numbers\n")

    # Test rusprofile — 1 query, 2 pages
    print("=== RUSPROFILE TEST (1 query, 2 pages) ===")
    count = await scrape_rusprofile(scraper, ['клиника'], 2)
    print(f"Rusprofile result: {count} numbers\n")

    print(f"\nTOTAL unique numbers: {len(scraper.results)}")
    print(f"HTTP stats: {scraper.stats}")

    # Show sample
    for entry in scraper.results[:20]:
        print(f"  {entry.normalized_number} | {entry.name[:40]:40s} | {entry.category:12s} | {entry.source}")

    await scraper.close()

asyncio.run(main())
