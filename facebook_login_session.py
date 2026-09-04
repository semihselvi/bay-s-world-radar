from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright


_local_root = Path(os.getenv("LOCALAPPDATA") or str(Path.home()))
STATE_DIR = Path(os.getenv("BAYS_FACEBOOK_STATE_DIR") or (_local_root / "BAY-S" / "WorldRadar"))
PROFILE_DIR = Path(os.getenv("FACEBOOK_PROFILE_DIR") or (STATE_DIR / "facebook-profile"))
FACEBOOK_HOME = "https://www.facebook.com/"


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    requested = os.getenv("FACEBOOK_BROWSER_CHANNEL", "chrome").strip()
    channels = [requested] + [x for x in ("chrome", "msedge") if x != requested]

    with sync_playwright() as playwright:
        context = None
        last_error = None
        for channel in channels:
            try:
                print(f"Opening browser channel: {channel}")
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE_DIR),
                    channel=channel,
                    headless=False,
                    viewport={"width": 1440, "height": 1000},
                    args=["--disable-notifications"],
                )
                break
            except Exception as exc:
                last_error = exc

        if context is None:
            raise RuntimeError(f"Could not open Chrome/Edge. Last error: {last_error}")

        try:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(FACEBOOK_HOME, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                # Facebook can redirect during login/2FA; keep the browser open so
                # the user can finish the verification manually.
                pass

            print("")
            print("FACEBOOK LOGIN / 2FA SETUP")
            print("1) Complete Facebook login in the browser window.")
            print("2) Complete ALL two-factor / checkpoint verification steps.")
            print("3) Wait until the normal Facebook HOME PAGE is fully open.")
            input("4) ONLY THEN press ENTER here to save the session: ")

            print(f"Current page: {page.url}")
            low = page.url.lower()
            blocked = any(x in low for x in ("/login", "two_step_verification", "two_factor", "/checkpoint"))
            if blocked:
                print("")
                print("Verification is still open. Finish it in the browser before closing this window.")
                input("When the normal Facebook home page is open, press ENTER again: ")
                print(f"Current page: {page.url}")
                low = page.url.lower()
                blocked = any(x in low for x in ("/login", "two_step_verification", "two_factor", "/checkpoint"))

            if blocked:
                raise RuntimeError("Facebook login/2FA is still not complete.")

            print("")
            print("LOGIN SESSION SAVED. You can now run facebook_discover_groups.bat")
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nFACEBOOK_LOGIN_ERROR: {exc}")
        raise SystemExit(1)
