"""
 █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗
██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝
███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗
██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║
██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝

 █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ 
██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝ 
scripts/preview_flow.py
Helper script to render Always Attend flow screenshots.
"""

from pathlib import Path
from urllib.parse import urljoin
import asyncio

from playwright.async_api import async_playwright


async def main():
    root = Path(__file__).resolve().parents[1]
    page_path = root / "docs" / "flow.html"
    if not page_path.exists():
        raise SystemExit(f"Not found: {page_path}")

    file_url = urljoin("file:", str(page_path))

    sizes = [
        (1200, 900),
        (1024, 900),
        (768, 1200),
        (480, 1200),
    ]

    out_dir = root / "docs"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(color_scheme="light", reduced_motion="no-preference")
        page = await context.new_page()
        for w, h in sizes:
            await page.set_viewport_size({"width": w, "height": h})
            await page.goto(file_url)
            # Wait a tick for layout
            await page.wait_for_timeout(150)
            out = out_dir / f"flow-{w}.png"
            await page.screenshot(path=str(out), full_page=True)
            print(f"Saved {out}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
