"""
Playwright + Stealth browser automation for Instagram.

Drop-in replacement for instagrapi-based IGAccount. Uses a real headless
Chromium browser with stealth patches so Instagram sees a normal human session.

Key features:
- Persistent browser profiles (cookies/localStorage survive restarts)
- Human-like typing with variable keystroke delays
- Natural mouse movements and scrolling
- Per-account device fingerprints (viewport, timezone, locale, user-agent)
- Proxy support per account
- Session encryption at rest (reuses Fernet helpers from dm_sender_service)
- Screenshot capture on errors for debugging
"""

import asyncio
import json
import logging
import random
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

MAX_SEND_ATTEMPTS = 3

# ---------------------------------------------------------------------------
# Browser fingerprint profiles — one per account (deterministic via username)
# ---------------------------------------------------------------------------
_BROWSER_PROFILES = [
    {
        "viewport": {"width": 1366, "height": 768},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "timezone": "America/New_York",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "platform": "Win32",
        "color_depth": 24,
        "hardware_concurrency": 8,
        "device_memory": 8,
        "webgl_vendor": "Google Inc. (NVIDIA)",
        "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "timezone": "America/Los_Angeles",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "platform": "MacIntel",
        "color_depth": 30,
        "hardware_concurrency": 10,
        "device_memory": 16,
        "webgl_vendor": "Google Inc. (Apple)",
        "webgl_renderer": "ANGLE (Apple, Apple M1 Pro, OpenGL 4.1)",
    },
    {
        "viewport": {"width": 1440, "height": 900},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "timezone": "Europe/London",
        "locale": "en-GB",
        "languages": ["en-GB", "en"],
        "platform": "Win32",
        "color_depth": 24,
        "hardware_concurrency": 12,
        "device_memory": 16,
        "webgl_vendor": "Google Inc. (Intel)",
        "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    },
    {
        "viewport": {"width": 1536, "height": 864},
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "timezone": "Europe/Berlin",
        "locale": "de-DE",
        "languages": ["de-DE", "de", "en"],
        "platform": "Linux x86_64",
        "color_depth": 24,
        "hardware_concurrency": 8,
        "device_memory": 8,
        "webgl_vendor": "Google Inc. (AMD)",
        "webgl_renderer": "ANGLE (AMD, AMD Radeon RX 6700 XT, OpenGL 4.6)",
    },
    {
        "viewport": {"width": 1280, "height": 720},
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "timezone": "America/Chicago",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "platform": "MacIntel",
        "color_depth": 30,
        "hardware_concurrency": 8,
        "device_memory": 8,
        "webgl_vendor": "Google Inc. (Apple)",
        "webgl_renderer": "ANGLE (Apple, Apple M2, OpenGL 4.1)",
    },
]

# ---------------------------------------------------------------------------
# Encryption helpers (reuse Fernet from dm_sender_service)
# ---------------------------------------------------------------------------

def _get_fernet():
    key = settings.IG_SESSION_ENCRYPTION_KEY
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.warning(f"Fernet init failed: {e}")
        return None


def _encrypt_file(path: Path):
    fernet = _get_fernet()
    if not fernet or not path.exists():
        return
    try:
        data = path.read_bytes()
        if data.startswith(b"gAAAAA"):
            return
        path.write_bytes(fernet.encrypt(data))
    except Exception as e:
        logger.warning(f"Encrypt failed {path.name}: {e}")


def _decrypt_file(path: Path) -> bytes | None:
    if not path.exists():
        return None
    data = path.read_bytes()
    fernet = _get_fernet()
    if fernet and data.startswith(b"gAAAAA"):
        try:
            return fernet.decrypt(data)
        except Exception:
            return None
    return data


# ---------------------------------------------------------------------------
# Human-like helpers
# ---------------------------------------------------------------------------

async def _human_type(page, selector: str, text: str):
    """Type text character-by-character with variable delays like a real human."""
    element = page.locator(selector)
    await element.click()
    await asyncio.sleep(random.uniform(0.2, 0.5))

    for char in text:
        await element.press(char if len(char) == 1 else char)
        delay_ms = random.randint(
            settings.PW_TYPING_MIN_DELAY,
            settings.PW_TYPING_MAX_DELAY,
        )
        await asyncio.sleep(delay_ms / 1000)

    # Brief pause after finishing typing
    await asyncio.sleep(random.uniform(0.3, 0.8))


async def _human_click(page, selector: str, timeout: int = 10000):
    """Click an element with a small random delay to mimic human hesitation."""
    await asyncio.sleep(random.uniform(0.3, 1.0))
    await page.locator(selector).click(timeout=timeout)
    await asyncio.sleep(random.uniform(0.5, 1.5))


async def _random_scroll(page, min_scrolls: int = 1, max_scrolls: int = 3):
    """Scroll the page randomly like a human browsing."""
    scrolls = random.randint(min_scrolls, max_scrolls)
    for _ in range(scrolls):
        delta = random.randint(100, 400)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.5, 1.5))


# ---------------------------------------------------------------------------
# IGBrowserAccount — Playwright-based Instagram account
# ---------------------------------------------------------------------------

class IGBrowserAccount:
    """
    A single Instagram account operated via a stealth Playwright browser.

    Interface is compatible with IGAccount from dm_sender_service so the
    DMSenderService/BrowserManager can swap implementations.
    """

    def __init__(self, username: str, password: str, proxy: str, session_dir: Path):
        self.username = username
        self.password = password
        self.proxy = proxy
        self._session_dir = session_dir
        self._session_dir.mkdir(parents=True, exist_ok=True)

        # Browser state
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

        # Health tracking (same fields as IGAccount)
        self.total_sent = 0
        self.total_failed = 0
        self.challenges = 0
        self.is_blocked = False
        self.created_at: datetime | None = None

        # Security: cooldown tracking
        self.last_challenge_at: datetime | None = None
        self.last_block_at: datetime | None = None
        self.challenges_today = 0
        self._challenges_today_date: str | None = None

        # Hourly rate tracking
        self._hourly_sends: list[float] = []

        # Fingerprint
        self._profile = _BROWSER_PROFILES[hash(username) % len(_BROWSER_PROFILES)]

    # -- Paths --

    @property
    def profile_dir(self) -> Path:
        """Persistent browser profile directory (cookies, localStorage)."""
        return self._session_dir / f"pw_{self.username}"

    @property
    def health_file(self) -> Path:
        return self._session_dir / f"{self.username}_health.json"

    @property
    def screenshot_dir(self) -> Path:
        d = self._session_dir / "screenshots"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -- Cooldowns (identical logic to IGAccount) --

    def is_in_cooldown(self) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        if self.last_challenge_at:
            end = self.last_challenge_at + timedelta(minutes=settings.CHALLENGE_COOLDOWN_MINUTES)
            if now < end:
                remaining = int((end - now).total_seconds() / 60)
                return True, f"Challenge cooldown ({remaining}min remaining)"
        if self.last_block_at:
            end = self.last_block_at + timedelta(hours=settings.BLOCK_COOLDOWN_HOURS)
            if now < end:
                remaining = int((end - now).total_seconds() / 3600)
                return True, f"Block cooldown ({remaining}h remaining)"
        today = now.strftime("%Y-%m-%d")
        if self._challenges_today_date == today and self.challenges_today >= settings.MAX_CHALLENGES_BEFORE_PAUSE:
            return True, f"Too many challenges today ({self.challenges_today})"
        return False, ""

    def _check_hourly_limit(self) -> bool:
        now = time.time()
        self._hourly_sends = [t for t in self._hourly_sends if t > now - 3600]
        return len(self._hourly_sends) < settings.HOURLY_DM_LIMIT

    def _record_send(self):
        self._hourly_sends.append(time.time())

    def _record_challenge(self):
        now = datetime.now(timezone.utc)
        self.challenges += 1
        self.last_challenge_at = now
        today = now.strftime("%Y-%m-%d")
        if self._challenges_today_date != today:
            self._challenges_today_date = today
            self.challenges_today = 0
        self.challenges_today += 1
        self._save_health()

    def _record_block(self):
        self.is_blocked = True
        self.last_block_at = datetime.now(timezone.utc)
        self._save_health()

    # -- Health persistence --

    def _save_health(self):
        try:
            data = {
                "total_sent": self.total_sent,
                "total_failed": self.total_failed,
                "challenges": self.challenges,
                "is_blocked": self.is_blocked,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "last_challenge_at": self.last_challenge_at.isoformat() if self.last_challenge_at else None,
                "last_block_at": self.last_block_at.isoformat() if self.last_block_at else None,
                "challenges_today": self.challenges_today,
                "challenges_today_date": self._challenges_today_date,
            }
            raw = json.dumps(data).encode()
            fernet = _get_fernet()
            if fernet:
                raw = fernet.encrypt(raw)
            self.health_file.write_bytes(raw)
        except Exception:
            pass

    def _load_health(self):
        if not self.health_file.exists():
            return
        try:
            raw = _decrypt_file(self.health_file)
            if raw is None:
                return
            data = json.loads(raw)
            self.total_sent = data.get("total_sent", 0)
            self.total_failed = data.get("total_failed", 0)
            self.challenges = data.get("challenges", 0)
            self.is_blocked = data.get("is_blocked", False)
            if data.get("created_at"):
                self.created_at = datetime.fromisoformat(data["created_at"])
            if data.get("last_challenge_at"):
                self.last_challenge_at = datetime.fromisoformat(data["last_challenge_at"])
            if data.get("last_block_at"):
                self.last_block_at = datetime.fromisoformat(data["last_block_at"])
            self.challenges_today = data.get("challenges_today", 0)
            self._challenges_today_date = data.get("challenges_today_date")
        except Exception as e:
            logger.warning(f"Health load failed for @{self.username}: {e}")

    def get_warmup_limit(self) -> int:
        if self.created_at is None:
            return settings.IG_WARMUP_START_LIMIT
        days_active = (datetime.now(timezone.utc) - self.created_at).days
        if days_active >= settings.IG_WARMUP_DAYS:
            return settings.DAILY_DM_LIMIT
        progress = days_active / settings.IG_WARMUP_DAYS
        return int(settings.IG_WARMUP_START_LIMIT + (settings.DAILY_DM_LIMIT - settings.IG_WARMUP_START_LIMIT) * progress)

    def get_health(self) -> dict:
        total = self.total_sent + self.total_failed
        success_rate = (self.total_sent / total * 100) if total > 0 else 100.0
        in_cooldown, cooldown_reason = self.is_in_cooldown()
        return {
            "username": self.username,
            "logged_in": self._logged_in,
            "is_blocked": self.is_blocked,
            "in_cooldown": in_cooldown,
            "cooldown_reason": cooldown_reason,
            "total_sent": self.total_sent,
            "total_failed": self.total_failed,
            "challenges": self.challenges,
            "challenges_today": self.challenges_today,
            "success_rate": round(success_rate, 1),
            "warmup_limit": self.get_warmup_limit(),
            "hourly_sends": len(self._hourly_sends),
            "hourly_limit": settings.HOURLY_DM_LIMIT,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "engine": "playwright",
        }

    def validate_proxy(self) -> bool:
        if not self.proxy:
            return True
        try:
            import httpx
            with httpx.Client(proxy=self.proxy, timeout=10) as client:
                resp = client.get("https://httpbin.org/ip")
                if resp.status_code == 200:
                    ip = resp.json().get("origin", "unknown")
                    logger.info(f"Proxy validated for @{self.username}: IP={ip}")
                    return True
            return False
        except Exception as e:
            logger.warning(f"Proxy validation failed for @{self.username}: {e}")
            return False

    # -- Browser lifecycle --

    async def _launch_browser(self):
        """Launch Playwright browser with stealth and persistent profile."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # Proxy config
        proxy_config = None
        if self.proxy:
            # Parse proxy URL: http://user:pass@host:port
            proxy_config = {"server": self.proxy}

        # Persistent context = cookies & localStorage survive restarts
        profile = self._profile
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=settings.PW_HEADLESS,
            slow_mo=settings.PW_SLOW_MO,
            proxy=proxy_config,
            viewport=profile["viewport"],
            user_agent=profile["user_agent"],
            locale=profile["locale"],
            timezone_id=profile["timezone"],
            color_scheme="light",
            # Anti-detection flags
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )

        # Apply stealth patches
        try:
            from playwright_stealth import stealth_async
            for page in self._context.pages:
                await stealth_async(page)
        except ImportError:
            logger.warning("playwright-stealth not installed, running without stealth patches")

        # Get or create page
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

        # Apply stealth to current page
        try:
            from playwright_stealth import stealth_async
            await stealth_async(self._page)
        except ImportError:
            pass

        # Comprehensive anti-detection: stealth patches for all fingerprinting vectors
        await self._page.add_init_script(self._build_stealth_script(profile))

        logger.info(f"Browser launched for @{self.username} (headless={settings.PW_HEADLESS})")

    @staticmethod
    def _build_stealth_script(profile: dict) -> str:
        """Build comprehensive anti-detection JavaScript patches.

        Covers: navigator properties, WebGL fingerprint spoofing, canvas noise,
        hardware info, languages, plugins, permissions API, Chrome runtime.
        """
        platform = profile["platform"]
        color_depth = profile["color_depth"]
        hw_concurrency = profile.get("hardware_concurrency", 8)
        device_memory = profile.get("device_memory", 8)
        webgl_vendor = profile.get("webgl_vendor", "Google Inc. (NVIDIA)")
        webgl_renderer = profile.get("webgl_renderer", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)")
        languages = profile.get("languages", ["en-US", "en"])
        languages_js = ", ".join(f'"{lang}"' for lang in languages)

        return f"""
        // ===== 1. NAVIGATOR PROPERTY OVERRIDES =====
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
        Object.defineProperty(navigator, 'platform', {{ get: () => '{platform}' }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hw_concurrency} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {device_memory} }});
        Object.defineProperty(navigator, 'languages', {{ get: () => Object.freeze([{languages_js}]) }});
        Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => 0 }});

        // ===== 2. SCREEN PROPERTIES =====
        Object.defineProperty(screen, 'colorDepth', {{ get: () => {color_depth} }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => {color_depth} }});

        // ===== 3. CHROME RUNTIME (pass Chrome API presence checks) =====
        if (!window.chrome) window.chrome = {{}};
        window.chrome.runtime = {{
            OnInstalledReason: {{ CHROME_UPDATE: "chrome_update", INSTALL: "install", SHARED_MODULE_UPDATE: "shared_module_update", UPDATE: "update" }},
            OnRestartRequiredReason: {{ APP_UPDATE: "app_update", OS_UPDATE: "os_update", PERIODIC: "periodic" }},
            PlatformArch: {{ ARM: "arm", ARM64: "arm64", MIPS: "mips", MIPS64: "mips64", X86_32: "x86-32", X86_64: "x86-64" }},
            PlatformNaclArch: {{ ARM: "arm", MIPS: "mips", MIPS64: "mips64", X86_32: "x86-32", X86_64: "x86-64" }},
            PlatformOs: {{ ANDROID: "android", CROS: "cros", LINUX: "linux", MAC: "mac", OPENBSD: "openbsd", WIN: "win" }},
            RequestUpdateCheckStatus: {{ ALMOST_UP_TO_DATE: "almost_up_to_date", NO_UPDATE: "no_update", THROTTLED: "throttled", UPDATE_AVAILABLE: "update_available" }},
            connect: function() {{ return {{ onDisconnect: {{ addListener: function() {{}} }}, onMessage: {{ addListener: function() {{}} }}, postMessage: function() {{}} }} }},
            sendMessage: function() {{}},
            id: undefined,
        }};

        // ===== 4. WEBGL FINGERPRINT SPOOFING =====
        (function() {{
            const getParameterOrig = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {{
                // UNMASKED_VENDOR_WEBGL
                if (param === 0x9245) return '{webgl_vendor}';
                // UNMASKED_RENDERER_WEBGL
                if (param === 0x9246) return '{webgl_renderer}';
                return getParameterOrig.call(this, param);
            }};

            // Also patch WebGL2
            if (typeof WebGL2RenderingContext !== 'undefined') {{
                const getParam2Orig = WebGL2RenderingContext.prototype.getParameter;
                WebGL2RenderingContext.prototype.getParameter = function(param) {{
                    if (param === 0x9245) return '{webgl_vendor}';
                    if (param === 0x9246) return '{webgl_renderer}';
                    return getParam2Orig.call(this, param);
                }};
            }}

            // Patch getExtension to support debug info
            const getExtOrig = WebGLRenderingContext.prototype.getExtension;
            WebGLRenderingContext.prototype.getExtension = function(name) {{
                if (name === 'WEBGL_debug_renderer_info') {{
                    return {{ UNMASKED_VENDOR_WEBGL: 0x9245, UNMASKED_RENDERER_WEBGL: 0x9246 }};
                }}
                return getExtOrig.call(this, name);
            }};
        }})();

        // ===== 5. CANVAS FINGERPRINT NOISE =====
        (function() {{
            const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {{
                // Add subtle noise to canvas to defeat fingerprinting
                const ctx = this.getContext('2d');
                if (ctx && this.width > 0 && this.height > 0) {{
                    try {{
                        const imageData = ctx.getImageData(0, 0, Math.min(this.width, 16), Math.min(this.height, 16));
                        for (let i = 0; i < imageData.data.length; i += 4) {{
                            // Add ±1 noise to RGB channels (imperceptible)
                            imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + (Math.random() > 0.5 ? 1 : -1)));
                        }}
                        ctx.putImageData(imageData, 0, 0);
                    }} catch(e) {{}}
                }}
                return origToDataURL.apply(this, arguments);
            }};

            const origToBlob = HTMLCanvasElement.prototype.toBlob;
            HTMLCanvasElement.prototype.toBlob = function() {{
                const ctx = this.getContext('2d');
                if (ctx && this.width > 0 && this.height > 0) {{
                    try {{
                        const imageData = ctx.getImageData(0, 0, Math.min(this.width, 16), Math.min(this.height, 16));
                        for (let i = 0; i < imageData.data.length; i += 4) {{
                            imageData.data[i] = Math.max(0, Math.min(255, imageData.data[i] + (Math.random() > 0.5 ? 1 : -1)));
                        }}
                        ctx.putImageData(imageData, 0, 0);
                    }} catch(e) {{}}
                }}
                return origToBlob.apply(this, arguments);
            }};
        }})();

        // ===== 6. PLUGINS & MIME TYPES (realistic Chrome set) =====
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                const arr = [
                    {{ name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                    {{ name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: '' }},
                    {{ name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: '' }},
                    {{ name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: '' }},
                    {{ name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: '' }},
                ];
                arr.item = (i) => arr[i];
                arr.namedItem = (name) => arr.find(p => p.name === name) || null;
                arr.refresh = () => {{}};
                return arr;
            }}
        }});

        // ===== 7. PERMISSIONS API SPOOFING =====
        if (navigator.permissions) {{
            const origQuery = navigator.permissions.query;
            navigator.permissions.query = function(params) {{
                if (params.name === 'notifications') {{
                    return Promise.resolve({{ state: Notification.permission, onchange: null }});
                }}
                return origQuery.call(this, params);
            }};
        }}

        // ===== 8. REMOVE AUTOMATION INDICATORS =====
        // Remove Playwright/Puppeteer traces
        delete window.__playwright;
        delete window.__pw_manual;
        delete window.__PW_inspect;
        delete navigator.__proto__.webdriver;

        // Patch toString to hide overrides
        const nativeToString = Function.prototype.toString;
        const customFunctions = new Set();
        const origToString = Function.prototype.toString;
        Function.prototype.toString = function() {{
            if (customFunctions.has(this)) return 'function ' + (this.name || '') + '() {{ [native code] }}';
            return origToString.call(this);
        }};
        """

    async def _screenshot(self, name: str):
        """Save a debug screenshot if enabled."""
        if not settings.PW_SCREENSHOT_ON_ERROR or not self._page:
            return
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.screenshot_dir / f"{self.username}_{name}_{ts}.png"
            await self._page.screenshot(path=str(path))
            logger.debug(f"Screenshot saved: {path}")
        except Exception:
            pass

    # -- Login --

    async def login(self) -> bool:
        """Login to Instagram via the web interface. Returns True on success."""
        if self._logged_in:
            return True

        self._load_health()

        in_cooldown, reason = self.is_in_cooldown()
        if in_cooldown:
            logger.warning(f"@{self.username} in cooldown: {reason}")
            return False

        try:
            await self._launch_browser()
        except Exception as e:
            logger.error(f"Browser launch failed for @{self.username}: {e}")
            return False

        try:
            # Navigate to Instagram
            await self._page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))

            # Accept cookies dialog if present
            try:
                accept_btn = self._page.locator("button:has-text('Allow'), button:has-text('Accept'), button:has-text('Permitir')")
                if await accept_btn.count() > 0:
                    await accept_btn.first.click()
                    await asyncio.sleep(random.uniform(1, 2))
            except Exception:
                pass

            # Check if already logged in (persistent profile has cookies)
            if await self._is_logged_in():
                self._logged_in = True
                if self.created_at is None:
                    self.created_at = datetime.now(timezone.utc)
                    self._save_health()
                logger.info(f"Session restored for @{self.username} (cookies)")
                return True

            # Need to log in
            await self._page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))

            # Fill username
            username_input = 'input[name="username"]'
            await self._page.wait_for_selector(username_input, timeout=15000)
            await _human_type(self._page, username_input, self.username)

            # Fill password
            await _human_type(self._page, 'input[name="password"]', self.password)

            # Click login button
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await self._page.locator('button[type="submit"]').click()

            # Wait for navigation or error
            await asyncio.sleep(random.uniform(3, 6))

            # Check for challenge/checkpoint
            current_url = self._page.url
            page_content = await self._page.content()

            if "challenge" in current_url or "checkpoint" in current_url:
                logger.warning(f"@{self.username}: Instagram challenge detected")
                self._record_challenge()
                await self._screenshot("challenge")
                return False

            if "suspicious" in page_content.lower() or "we detected an unusual" in page_content.lower():
                logger.warning(f"@{self.username}: Suspicious login detected")
                self._record_challenge()
                await self._screenshot("suspicious")
                return False

            # Check for login errors
            error_el = self._page.locator("#slfErrorAlert, [data-testid='login-error-message']")
            if await error_el.count() > 0:
                error_text = await error_el.first.text_content()
                logger.error(f"@{self.username}: Login error: {error_text}")
                await self._screenshot("login_error")
                return False

            # Handle "Save Your Login Info?" dialog
            try:
                save_btn = self._page.locator("button:has-text('Save Info'), button:has-text('Save info'), button:has-text('Guardar')")
                if await save_btn.count() > 0:
                    await save_btn.first.click()
                    await asyncio.sleep(random.uniform(1, 2))
            except Exception:
                pass

            # Handle "Turn on Notifications?" dialog
            try:
                not_now = self._page.locator("button:has-text('Not Now'), button:has-text('Not now'), button:has-text('Ahora no')")
                if await not_now.count() > 0:
                    await not_now.first.click()
                    await asyncio.sleep(random.uniform(1, 2))
            except Exception:
                pass

            # Verify login succeeded
            if await self._is_logged_in():
                self._logged_in = True
                if self.created_at is None:
                    self.created_at = datetime.now(timezone.utc)
                self._save_health()
                logger.info(f"Fresh login successful for @{self.username}")
                return True

            logger.error(f"@{self.username}: Login verification failed")
            await self._screenshot("login_failed")
            return False

        except Exception as e:
            error_str = str(e).lower()
            if "challenge" in error_str or "checkpoint" in error_str:
                self._record_challenge()
            logger.error(f"@{self.username} login error: {type(e).__name__}: {e}")
            await self._screenshot("login_exception")
            return False

    async def _is_logged_in(self) -> bool:
        """Check if the current page shows a logged-in Instagram session."""
        try:
            # Check for common logged-in indicators
            # The home feed SVG icon, profile link, or direct inbox link
            indicators = [
                'a[href="/direct/inbox/"]',
                'svg[aria-label="Home"]',
                'svg[aria-label="Inicio"]',
                'a[href*="/direct/"]',
                'span[role="link"]:has-text("Profile")',
            ]
            for sel in indicators:
                if await self._page.locator(sel).count() > 0:
                    return True

            # Also check URL — if we're on the feed, we're logged in
            if self._page.url.rstrip("/") in ("https://www.instagram.com", "https://www.instagram.com/"):
                # Could be logged in or not; check for login form
                login_form = await self._page.locator('input[name="username"]').count()
                return login_form == 0

            return False
        except Exception:
            return False

    # -- Send DM --

    async def send_dm(self, username: str, message: str) -> dict:
        """Send a DM to @username via Instagram web. Returns same format as IGAccount.send_dm()."""
        if not self._logged_in:
            return {"success": False, "error": "Not logged in"}

        if not self._check_hourly_limit():
            return {
                "success": False,
                "error": f"Hourly DM limit reached ({settings.HOURLY_DM_LIMIT}/hour)",
                "is_rate_limited": True,
            }

        in_cooldown, reason = self.is_in_cooldown()
        if in_cooldown:
            return {"success": False, "error": f"Account in cooldown: {reason}", "is_cooldown": True}

        try:
            # Navigate to DM inbox
            await self._page.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))

            # Handle "Turn on Notifications?" dialog that sometimes appears
            try:
                not_now = self._page.locator("button:has-text('Not Now'), button:has-text('Not now'), button:has-text('Ahora no')")
                if await not_now.count() > 0:
                    await not_now.first.click()
                    await asyncio.sleep(random.uniform(0.5, 1.5))
            except Exception:
                pass

            # Click "New message" / compose button
            new_msg_selectors = [
                'svg[aria-label="New message"]',
                'svg[aria-label="Nuevo mensaje"]',
                '[aria-label="New message"]',
                '[aria-label="Nuevo mensaje"]',
            ]
            clicked = False
            for sel in new_msg_selectors:
                loc = self._page.locator(sel)
                if await loc.count() > 0:
                    await loc.first.click()
                    clicked = True
                    break

            if not clicked:
                # Fallback: try the compose icon/button by role
                compose = self._page.locator('div[role="button"]:has(svg)').filter(has=self._page.locator('svg[aria-label*="message" i], svg[aria-label*="mensaje" i]'))
                if await compose.count() > 0:
                    await compose.first.click()
                    clicked = True

            if not clicked:
                await self._screenshot("no_new_message_btn")
                return {"success": False, "error": "Could not find New Message button"}

            await asyncio.sleep(random.uniform(1.5, 3))

            # Search for the recipient
            search_input_selectors = [
                'input[name="queryBox"]',
                'input[placeholder*="Search"]',
                'input[placeholder*="Buscar"]',
                'input[placeholder*="search" i]',
            ]
            search_input = None
            for sel in search_input_selectors:
                loc = self._page.locator(sel)
                if await loc.count() > 0:
                    search_input = sel
                    break

            if not search_input:
                await self._screenshot("no_search_input")
                return {"success": False, "error": "Could not find recipient search input"}

            await _human_type(self._page, search_input, username)
            await asyncio.sleep(random.uniform(2, 4))

            # Select the user from results
            # Look for the exact username match in search results
            user_result = self._page.locator(f'span:text-is("{username}")').first
            try:
                await user_result.wait_for(timeout=8000)
                await user_result.click()
                await asyncio.sleep(random.uniform(0.5, 1.5))
            except Exception:
                # User not found in search results
                await self._screenshot(f"user_not_found_{username}")
                return {"success": False, "error": f"User @{username} not found", "is_not_found": True}

            # Click "Chat" / "Next" button to open conversation
            next_selectors = [
                'div[role="button"]:has-text("Chat")',
                'div[role="button"]:has-text("Next")',
                'div[role="button"]:has-text("Siguiente")',
                'button:has-text("Chat")',
                'button:has-text("Next")',
            ]
            for sel in next_selectors:
                loc = self._page.locator(sel)
                if await loc.count() > 0:
                    await loc.first.click()
                    break
            await asyncio.sleep(random.uniform(2, 3))

            # Type the message in the message box
            msg_input_selectors = [
                'div[role="textbox"][aria-label*="Message"]',
                'div[role="textbox"][aria-label*="Mensaje"]',
                'div[role="textbox"][contenteditable="true"]',
                'textarea[placeholder*="Message"]',
                'textarea[placeholder*="Mensaje"]',
            ]
            msg_input = None
            for sel in msg_input_selectors:
                loc = self._page.locator(sel)
                if await loc.count() > 0:
                    msg_input = sel
                    break

            if not msg_input:
                await self._screenshot("no_message_input")
                return {"success": False, "error": "Could not find message input"}

            # Type the message with human-like delays
            await _human_type(self._page, msg_input, message)
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # Send the message (press Enter)
            await self._page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(2, 4))

            # Verify the message was sent by checking for it in the conversation
            # Look for the message text in the conversation thread
            sent_msg = self._page.locator(f'div:has-text("{message[:50]}")').last
            try:
                await sent_msg.wait_for(timeout=5000)
            except Exception:
                # Message might still have been sent even if we can't verify
                logger.warning(f"Could not verify DM delivery to @{username}, assuming sent")

            self.total_sent += 1
            self._record_send()
            self._save_health()
            logger.info(f"[@{self.username}] DM sent to @{username} via Playwright")
            return {"success": True, "thread_id": None}

        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"{error_type}: {e}"
            error_lower = str(e).lower()
            logger.error(f"[@{self.username}] DM send failed to @{username}: {error_msg}")

            is_challenge = "challenge" in error_lower or "checkpoint" in error_lower
            is_block = "block" in error_lower or "feedback_required" in error_lower or "action_blocked" in error_lower
            is_not_found = "not found" in error_lower

            self.total_failed += 1
            if is_challenge:
                self._record_challenge()
            if is_block:
                self._record_block()

            await self._screenshot(f"send_error_{username}")

            return {
                "success": False,
                "error": error_msg[:500],
                "is_challenge": is_challenge,
                "is_block": is_block,
                "is_not_found": is_not_found,
            }

    # -- Pre-send public check --

    async def check_user_public(self, username: str) -> bool:
        """Check if @username has a public profile by visiting their profile page."""
        if not self._logged_in or not self._page:
            return False
        try:
            await self._page.goto(
                f"https://www.instagram.com/{username}/",
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(random.uniform(2, 3))

            # Check for "This account is private" indicator
            private_indicators = [
                'h2:has-text("This account is private")',
                'h2:has-text("Esta cuenta es privada")',
                'h2:text-is("This Account is Private")',
            ]
            for sel in private_indicators:
                if await self._page.locator(sel).count() > 0:
                    logger.info(f"Pre-send check: @{username} is private")
                    return False

            # Check for "Page Not Found"
            not_found_indicators = [
                'h2:has-text("Sorry, this page")',
                'h2:has-text("Esta página no")',
                'span:has-text("Sorry, this page")',
            ]
            for sel in not_found_indicators:
                if await self._page.locator(sel).count() > 0:
                    logger.info(f"Pre-send check: @{username} not found")
                    return False

            return True
        except Exception as e:
            logger.warning(f"Pre-send check failed for @{username}: {e}")
            return True  # Don't block on check failure

    # -- Inbox reading --

    async def check_inbox(self) -> list[dict]:
        """Read recent DM threads from Instagram inbox. Returns list of thread dicts."""
        if not self._logged_in or not self._page:
            return []

        try:
            await self._page.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))

            threads = []

            # Get conversation list items
            conversation_items = self._page.locator('div[role="listitem"], a[href*="/direct/t/"]')
            count = await conversation_items.count()
            count = min(count, 20)  # Limit to 20 most recent

            for i in range(count):
                try:
                    item = conversation_items.nth(i)
                    await item.click()
                    await asyncio.sleep(random.uniform(1.5, 3))

                    # Extract username from conversation header
                    header = self._page.locator('header span, div[role="heading"] span').first
                    thread_username = ""
                    try:
                        thread_username = (await header.text_content() or "").strip()
                    except Exception:
                        continue

                    if not thread_username:
                        continue

                    # Extract messages from the conversation
                    messages = []
                    msg_elements = self._page.locator('div[role="row"] div[dir="auto"], div[class*="message"] div[dir="auto"]')
                    msg_count = await msg_elements.count()
                    msg_count = min(msg_count, 10)  # Last 10 messages

                    for j in range(msg_count):
                        try:
                            text = await msg_elements.nth(j).text_content()
                            if text:
                                messages.append({
                                    "text": text.strip(),
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "is_me": False,  # We can't reliably determine this from DOM alone
                                })
                        except Exception:
                            continue

                    if thread_username and messages:
                        threads.append({
                            "thread_id": f"pw_{thread_username}",
                            "username": thread_username,
                            "messages": messages,
                        })
                except Exception:
                    continue

            return threads

        except Exception as e:
            logger.error(f"Inbox check failed for @{self.username}: {e}")
            return []

    # -- Session management --

    async def save_session(self):
        """Save browser state. Cookies are auto-persisted via launch_persistent_context."""
        self._save_health()
        logger.debug(f"Session state saved for @{self.username}")

    async def close(self):
        """Close browser and clean up."""
        try:
            if self._context:
                await self._context.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Browser close error for @{self.username}: {e}")
        finally:
            self._context = None
            self._page = None
            self._playwright = None
            self._browser = None
            self._logged_in = False
