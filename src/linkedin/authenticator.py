"""LinkedIn login handler."""
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from src.logging import logger


class LinkedInAuthenticator:
    def __init__(self, driver):
        self.driver = driver

    def _is_logged_in(self) -> bool:
        """Check if the browser is currently logged into LinkedIn."""
        try:
            # The global nav bar only exists when logged in
            self.driver.find_element(By.CSS_SELECTOR, "nav.global-nav, div.global-nav__me, .feed-identity-module")
            return True
        except Exception:
            return False

    def login(self, email: str, password: str):
        logger.info("Logging into LinkedIn...")
        self.driver.get("https://www.linkedin.com/feed")
        time.sleep(3)

        # If persistent profile already has a valid session, the nav bar will be present
        if self._is_logged_in():
            logger.info("Already logged in via persistent session — skipping login.")
            return

        logger.info("Not logged in — proceeding with credential login.")
        # Not logged in — go to login page and fill credentials
        self.driver.get("https://www.linkedin.com/login")
        time.sleep(3)

        # LinkedIn may redirect /login → /feed if a valid session cookie exists
        if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
            logger.info("Redirected to feed after /login — already authenticated via session cookie.")
            return

        # Screenshot + dump input fields so we can see what's available
        self.driver.save_screenshot("job_applications/screenshots/login_page.png")
        logger.info(f"Login page URL: {self.driver.current_url}")
        logger.info(f"Login page title: {self.driver.title}")
        inputs = self.driver.find_elements(By.TAG_NAME, "input")
        for i, inp in enumerate(inputs):
            logger.info(f"Input[{i}] id={inp.get_attribute('id')!r} name={inp.get_attribute('name')!r} type={inp.get_attribute('type')!r} class={inp.get_attribute('class')!r}")

        try:
            # LinkedIn has no id/name on inputs — find first VISIBLE text input
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[type='email']"))
            )
            all_text_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email']")
            email_field = next((el for el in all_text_inputs if el.is_displayed()), None)

            if not email_field:
                raise Exception("Could not find visible email field on login page")

            email_field.click()
            email_field.clear()
            email_field.send_keys(email)

            all_pw_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
            password_field = next((el for el in all_pw_inputs if el.is_displayed()), None)

            if not password_field:
                raise Exception("Could not find visible password field on login page")

            password_field.click()
            password_field.clear()
            password_field.send_keys(password)

            # Screenshot after filling — see what the submit button looks like
            self.driver.save_screenshot("job_applications/screenshots/login_filled.png")

            # Find the main "Sign in" button — exact text match to avoid "Sign in with Apple"
            submit_btn = None
            for btn in self.driver.find_elements(By.TAG_NAME, "button"):
                if btn.is_displayed() and btn.text.strip().lower() == "sign in":
                    submit_btn = btn
                    break
            if not submit_btn:
                raise Exception("Could not find Sign In submit button")
            submit_btn.click()
            time.sleep(3)

            # Check if login succeeded or needs 2FA / CAPTCHA
            current_url = self.driver.current_url
            if "checkpoint" in current_url or "challenge" in current_url:
                print("\n⚠️  LinkedIn requires verification (2FA/CAPTCHA).")
                print("Please complete it in the browser window, then press Enter here to continue...")
                input()
            elif "feed" in current_url or "mynetwork" in current_url:
                logger.info("Login successful.")
            else:
                print("\n⚠️  Login may have failed. Current URL:", current_url)
                print("If you are logged in, press Enter to continue. Otherwise Ctrl+C to abort.")
                input()

        except Exception as e:
            logger.error(f"Login error: {e}")
            raise
