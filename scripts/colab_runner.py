#!/usr/bin/env python3
"""Best-effort UI runner for an already authenticated Colab browser profile."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


async def run(url: str, profile: Path, timeout: int) -> None:
    from playwright.async_api import async_playwright

    profile.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(profile), headless=False, args=["--disable-blink-features=AutomationControlled"]
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        print("Colab opened. Complete Google sign-in interactively if requested.")
        try:
            await page.get_by_role("button", name="Run all").click(timeout=15_000)
        except Exception:
            try:
                await page.get_by_text("Run all", exact=True).click(timeout=10_000)
            except Exception as exc:
                print(f"Run all was not clicked automatically: {exc}")
                print("Use Runtime -> Run all in the visible browser window.")
        await page.wait_for_timeout(5_000)
        await context.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notebook-url", required=True)
    parser.add_argument("--profile", default=".auth/colab")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    asyncio.run(run(args.notebook_url, Path(args.profile), args.timeout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
