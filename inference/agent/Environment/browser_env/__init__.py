from enum import Enum
from playwright.async_api import async_playwright
import os

class BrowserType(Enum):
    LOCAL = "local"
    BROWSERBASE = "browserbase"

class BrowserEnvironment:
    @staticmethod
    async def create_browser_instance(browser_type: str, headless: bool, slow_mo: int, viewport_size: dict, locale: str):
        if browser_type == BrowserType.LOCAL.value:
            return await LocalBrowserEnvironment.create(headless, slow_mo, viewport_size, locale)
        elif browser_type == BrowserType.BROWSERBASE.value:
            return await BrowserbaseBrowserEnvironment.create(headless, slow_mo, viewport_size, locale)
        else:
            raise ValueError(f"Unsupported browser type: {browser_type}")

class LocalBrowserEnvironment:
    @staticmethod
    async def create(headless: bool, slow_mo: int, viewport_size: dict, locale: str):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = await browser.new_context(viewport=viewport_size, locale=locale)
        return browser, context, playwright, None

class BrowserbaseBrowserEnvironment:
    @staticmethod
    async def create(headless: bool, slow_mo: int, viewport_size: dict, locale: str):
        playwright = await async_playwright().start()
        browserbase_api_key = os.environ.get('BROWSERBASE_API_KEY')
        if not browserbase_api_key:
            raise ValueError("BROWSERBASE_API_KEY not found in environment variables")
        
        browser_cdp_url = f"wss://connect.browserbase.com?apiKey={browserbase_api_key}"
        browser = await playwright.chromium.connect_over_cdp(browser_cdp_url)
        context = browser.contexts[0]
        return browser, context, playwright, None