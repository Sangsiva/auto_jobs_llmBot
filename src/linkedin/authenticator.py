"""LinkedIn login handler."""
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from src.logging import logger


class LinkedInAuthenticator:
    def __init__(self, driver):
        self.driver = driver

    def login(self, email: str, password: str):
        logger.info("Logging into LinkedIn...")
        self.driver.get("https://www.linkedin.com/login")
        time.sleep(2)

        try:
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            email_field.clear()
            email_field.send_keys(email)

            password_field = self.driver.find_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(password)

            self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
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
