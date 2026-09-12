"""Best-effort UI runner for an already authenticated Colab browser profile.

Google authentication is intentionally interactive. Do not store Google cookies
or browser profiles in GitHub Actions artifacts, secrets, or source control.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


async def run(url: str, profile: Path, timeout: int, headless: bool) -> None:
    from playwright.async_api import async_playwright

    profile.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        print("Colab opened. Complete Google sign-in interactively if requested.")
        try:
            await page.get_by_role("button", name="Run all").click(timeout=15_000)
            print("Run all clicked.")
        except Exception as exc:
            print(f"Run all was not clicked automatically: {exc}")
            print("Use Runtime -> Run all in the browser.")
        if not headless:
            print("Browser remains open for the Colab session. Press Ctrl+C to stop the runner.")
            try:
                await page.wait_for_timeout(24 * 60 * 60 * 1000)
            except KeyboardInterrupt:
                pass
        else:
            await page.wait_for_timeout(5_000)
        await context.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notebook-url", required=True)
    parser.add_argument("--profile", default=".auth/colab")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--headless", action="store_true", help="Best-effort mode; Google UI may require visible browser")
    args = parser.parse_args()
    asyncio.run(run(args.notebook_url, Path(args.profile), args.timeout, args.headless))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
