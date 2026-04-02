"""LinkedIn Easy Apply Bot — orchestrates job search and application."""
import time
import random
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, InvalidSessionIdException, WebDriverException
from anthropic import Anthropic
from src.linkedin.authenticator import LinkedInAuthenticator
from src.linkedin.easy_apply import EasyApplyFiller
from src.libs.jd_resume_matcher.jd_matcher import tailor_resume_for_jd, generate_cover_letter_for_jd
from src.linkedin.application_tracker import (
    record, already_applied, print_report,
    STATUS_APPLIED, STATUS_SKIPPED, STATUS_FAILED, STATUS_NO_EASY
)
from src.linkedin.session_guard import SessionGuard
from src.logging import logger
import config as cfg


class LinkedInBot:
    def __init__(self, driver, api_key: str, email: str, password: str,
                 preferences: dict, profile: dict, resume_pdf_path: Path = None):
        self.driver = driver
        self.api_key = api_key
        self.email = email
        self.password = password
        self.preferences = preferences
        self.profile = profile
        self.resume_pdf_path = resume_pdf_path  # fallback if tailoring fails
        self.wait = WebDriverWait(driver, 15)
        self.applied_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.session_guard = SessionGuard()

    def _login(self):
        auth = LinkedInAuthenticator(self.driver)
        auth.login(self.email, self.password)

    def _build_search_url(self, position: str, location: str) -> str:
        """Build LinkedIn job search URL with filters from preferences."""
        base = "https://www.linkedin.com/jobs/search/?"
        params = []

        params.append(f"keywords={position.replace(' ', '%20')}")
        params.append(f"location={location.replace(' ', '%20')}")
        params.append("f_LF=f_AL")  # Easy Apply filter

        # Date filter
        date = self.preferences.get("date", {})
        if date.get("24_hours"):
            params.append("f_TPR=r86400")
        elif date.get("week"):
            params.append("f_TPR=r604800")
        elif date.get("month"):
            params.append("f_TPR=r2592000")

        # Experience level
        exp_map = {
            "internship": "1", "entry": "2", "associate": "3",
            "mid_senior_level": "4", "director": "5", "executive": "6"
        }
        exp_levels = self.preferences.get("experience_level", {})
        selected = [v for k, v in exp_map.items() if exp_levels.get(k)]
        if selected:
            params.append(f"f_E={','.join(selected)}")

        # Remote/hybrid/onsite
        work_types = []
        if self.preferences.get("remote"):
            work_types.append("2")
        if self.preferences.get("hybrid"):
            work_types.append("3")
        if self.preferences.get("onsite"):
            work_types.append("1")
        if work_types:
            params.append(f"f_WT={','.join(work_types)}")

        params.append("sortBy=DD")  # Sort by date
        return base + "&".join(params)

    def _is_blacklisted(self, job_title: str, company: str) -> bool:
        title_blacklist = [t.lower() for t in self.preferences.get("title_blacklist", [])]
        company_blacklist = [c.lower() for c in self.preferences.get("company_blacklist", [])]
        if any(b in job_title.lower() for b in title_blacklist):
            return True
        if any(b in company.lower() for b in company_blacklist):
            return True
        return False

    def _human_scroll(self):
        """Scroll the page in a human-like way before interacting with job cards."""
        try:
            scroll_amount = random.randint(200, 600)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.5, 1.5))
            self.driver.execute_script(f"window.scrollBy(0, -{random.randint(50, 150)});")
            time.sleep(random.uniform(0.3, 0.8))
        except Exception:
            pass

    def _get_job_cards(self):
        """Get all job cards on the current search results page."""
        try:
            return self.driver.find_elements(
                By.CSS_SELECTOR,
                "li.jobs-search-results__list-item, div.job-card-container"
            )
        except Exception:
            return []

    def _close_modal(self):
        """Safely close any open Easy Apply modal, handling the save/discard dialog."""
        try:
            # Click the X / Dismiss button
            for sel in ["button[aria-label='Dismiss']", "button[aria-label='Close']"]:
                try:
                    self.driver.find_element(By.CSS_SELECTOR, sel).click()
                    time.sleep(1)
                    break
                except Exception:
                    pass

            # If "Save this application?" dialog appears, click Discard
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if btn.text.lower().strip() == "discard":
                    btn.click()
                    time.sleep(1)
                    return
        except Exception:
            pass

    def _get_jd_text(self) -> str:
        """Extract job description text from the current job detail page."""
        try:
            selectors = [
                "div.jobs-description__content",
                "div.jobs-box__html-content",
                "article.jobs-description__container",
                "div#job-details",
            ]
            for sel in selectors:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    text = el.text.strip()
                    if text:
                        return text[:6000]
                except Exception:
                    continue
            # Fallback: grab visible body text
            return self.driver.find_element(By.TAG_NAME, "body").text[:6000]
        except Exception as e:
            logger.warning(f"Could not extract JD text: {e}")
            return ""

    def _click_easy_apply(self) -> bool:
        """Click the Easy Apply button on a job detail page. Returns True if found."""
        # Try CSS selectors first
        css_selectors = [
            "button.jobs-apply-button[aria-label*='Easy Apply']",
            "button[aria-label*='Easy Apply']",
            "button.jobs-apply-button",
            ".jobs-s-apply button",
            "button.artdeco-button--primary[aria-label*='Easy Apply']",
        ]
        for sel in css_selectors:
            try:
                btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                btn.click()
                time.sleep(2)
                return True
            except Exception:
                continue

        # Fallback: find any button whose text contains "Easy Apply"
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "easy apply" in btn.text.lower():
                    btn.click()
                    time.sleep(2)
                    return True
        except Exception:
            pass

        return False

    def _apply_to_job(self, job_card) -> str:
        """Click a job card and attempt to apply. Returns: 'applied', 'skipped', 'failed'."""
        try:
            # Click the job card to load details
            job_card.click()
            time.sleep(4)  # wait for detail panel to fully load

            # Get job title — try multiple selectors for LinkedIn UI resilience
            job_title = "Unknown Role"
            for sel in [
                "h1.job-details-jobs-unified-top-card__job-title",
                "h1.t-24",
                "h1",
                "div.job-details-jobs-unified-top-card__job-title h1",
                ".jobs-unified-top-card__job-title",
                ".t-24.t-bold",
            ]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    text = el.text.strip()
                    if text:
                        job_title = text
                        break
                except Exception:
                    continue

            # Get company name
            company = "Unknown Company"
            for sel in [
                "div.job-details-jobs-unified-top-card__company-name a",
                ".jobs-unified-top-card__company-name a",
                "a.ember-view.t-black.t-normal",
                ".job-details-jobs-unified-top-card__primary-description a",
                ".jobs-unified-top-card__subtitle-primary-grouping a",
            ]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    text = el.text.strip()
                    if text:
                        company = text
                        break
                except Exception:
                    continue

            logger.info(f"Job: {job_title} @ {company}")

            # Get job URL for tracking
            job_url = self.driver.current_url

            # Get location
            location = "Unknown"
            for sel in [
                ".jobs-unified-top-card__bullet",
                ".job-details-jobs-unified-top-card__primary-description span",
            ]:
                try:
                    location = self.driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                    if location:
                        break
                except Exception:
                    continue

            # Check blacklist
            if self._is_blacklisted(job_title, company):
                logger.info(f"Blacklisted — skipping: {job_title} @ {company}")
                record(job_title, company, location, job_url, 0, "-", STATUS_SKIPPED, "Blacklisted")
                return "skipped"

            # Duplicate check
            if already_applied(company, job_title):
                print(f"  Already applied — skipping: {job_title} @ {company}")
                return "skipped"

            # Click Easy Apply
            if not self._click_easy_apply():
                logger.info(f"No Easy Apply button — skipping: {job_title}")
                record(job_title, company, location, job_url, 0, "-", STATUS_NO_EASY)
                return "skipped"

            # Relevance check
            jd_text = self._get_jd_text()
            relevance_score = 0
            if jd_text:
                client = Anthropic(api_key=self.api_key)
                try:
                    from anthropic import Anthropic as _A
                    resp = _A(api_key=self.api_key).messages.create(
                        model="claude-haiku-4-5-20251001", max_tokens=5,
                        messages=[{"role": "user", "content":
                            f"Score 0-10 relevance for a Senior Data/AI/ML Engineer with Spark, Python, LLM skills.\n"
                            f"Job: {job_title}\nJD: {jd_text[:1000]}\nReply with single integer only."}]
                    )
                    relevance_score = int(resp.content[0].text.strip())
                except Exception:
                    relevance_score = 5  # default if check fails

            if relevance_score < cfg.JOB_SUITABILITY_SCORE:
                print(f"  Not relevant (score {relevance_score}/10) — skipping: {job_title}")
                record(job_title, company, location, job_url, relevance_score, "-",
                       STATUS_SKIPPED, f"Relevance score {relevance_score}/10")
                self._close_modal()
                return "skipped"

            # Tailor resume
            tailored_pdf = None
            resume_used = "fallback"
            output_dir = None
            if jd_text:
                print(f"  Tailoring resume for {company}...")
                tailored_pdf = tailor_resume_for_jd(
                    api_key=self.api_key, jd_text=jd_text, company_name=company,
                )
                if tailored_pdf:
                    resume_used = tailored_pdf.parent.name  # company folder name
                    output_dir = tailored_pdf.parent

            resume_to_use = tailored_pdf or self.resume_pdf_path

            # Generate cover letter only if the form has a textarea that could use it
            cover_letter_text = None
            if jd_text:
                has_textarea = bool(self.driver.find_elements(
                    By.CSS_SELECTOR, "textarea"
                ))
                if has_textarea:
                    print(f"  Generating cover letter for {company}...")
                    cover_letter_text = generate_cover_letter_for_jd(
                        api_key=self.api_key,
                        jd_text=jd_text,
                        company_name=company,
                        job_title=job_title,
                        output_dir=output_dir,
                    )
                else:
                    logger.info("No textarea on form — skipping cover letter generation")

            # Fill and submit
            filler = EasyApplyFiller(
                driver=self.driver, api_key=self.api_key,
                profile=self.profile, resume_pdf_path=resume_to_use,
                cover_letter_text=cover_letter_text,
            )
            success = filler.run()

            if success:
                print(f"  ✓ Applied: {job_title} @ {company}")
                record(job_title, company, location, job_url, relevance_score,
                       resume_used, STATUS_APPLIED)
                return "applied"
            else:
                print(f"  ✗ Failed: {job_title} @ {company}")
                record(job_title, company, location, job_url, relevance_score,
                       resume_used, STATUS_FAILED)
                self._close_modal()
                return "failed"

        except Exception as e:
            logger.error(f"Error applying to job: {e}")
            return "failed"

    def _next_page(self) -> bool:
        """Click the next page button. Returns False if no next page."""
        try:
            next_btn = self.driver.find_element(
                By.CSS_SELECTOR, "button[aria-label='Next']"
            )
            if next_btn.is_enabled():
                next_btn.click()
                time.sleep(3)
                return True
        except NoSuchElementException:
            pass
        return False

    def run(self):
        """Main bot loop."""
        max_applications = cfg.JOB_MAX_APPLICATIONS

        # Check daily limits before starting
        print(f"\n{self.session_guard.status()}")
        if not self.session_guard.start_session():
            print("Daily limit reached. Exiting to protect account.")
            return

        # Cap max_applications to whatever's left today
        remaining = self.session_guard.remaining_today()
        if remaining < max_applications:
            print(f"Capping session to {remaining} applications (daily limit).")
            max_applications = remaining

        self._login()
        print("\nLogged in to LinkedIn.\n")

        positions = self.preferences.get("positions", [])
        locations = self.preferences.get("locations", [])

        applied_companies = set()

        for position in positions:
            for location in locations:
                print(f"\nSearching: '{position}' in '{location}'")
                url = self._build_search_url(position, location)
                self.driver.get(url)
                time.sleep(3)

                page = 1
                while self.applied_count < max_applications:
                    print(f"  Page {page} — Applied: {self.applied_count}/{max_applications}")
                    job_cards = self._get_job_cards()

                    if not job_cards:
                        print("  No job cards found on this page.")
                        break

                    browser_alive = True
                    for card in job_cards:
                        if self.applied_count >= max_applications:
                            break
                        if not self.session_guard.can_apply():
                            print("  Daily application limit reached mid-session. Stopping.")
                            break

                        # Human-like scroll before clicking each card
                        self._human_scroll()

                        # Check apply_once_at_company
                        company_name = ""
                        if self.preferences.get("apply_once_at_company"):
                            try:
                                company_el = card.find_element(
                                    By.CSS_SELECTOR, ".job-card-container__primary-description, .artdeco-entity-lockup__subtitle"
                                )
                                company_name = company_el.text.strip()
                                if company_name in applied_companies:
                                    continue
                            except Exception:
                                pass

                        try:
                            result = self._apply_to_job(card)
                        except (InvalidSessionIdException, WebDriverException) as e:
                            if "invalid session id" in str(e).lower() or "no such window" in str(e).lower():
                                print("\n  Browser session lost (Chrome may have been closed or slept).")
                                print("  Applications recorded so far are saved. Run again to continue.")
                                browser_alive = False
                                break
                            raise

                        if result == "applied":
                            self.applied_count += 1
                            self.session_guard.record_application()
                            if company_name:
                                applied_companies.add(company_name)
                            wait_time = self.session_guard.next_wait_seconds()
                            print(f"  Waiting {wait_time}s ({wait_time // 60}m {wait_time % 60}s) before next application...")
                            try:
                                time.sleep(wait_time)
                            except KeyboardInterrupt:
                                print("\n  Wait interrupted. Moving to next job.")
                        elif result == "skipped":
                            self.skipped_count += 1
                            time.sleep(random.randint(3, 8))
                        elif result == "failed":
                            self.failed_count += 1
                            time.sleep(random.randint(10, 20))

                    if not browser_alive:
                        break

                    try:
                        if not self._next_page():
                            break
                    except (InvalidSessionIdException, WebDriverException):
                        print("\n  Browser session lost during page navigation.")
                        break
                    page += 1

                if not browser_alive:
                    break
                if self.applied_count >= max_applications:
                    print(f"\nReached max applications limit ({max_applications}).")
                    break

        print(f"\n{'='*50}")
        print(f"Session complete:")
        print(f"  Applied:  {self.applied_count}")
        print(f"  Skipped:  {self.skipped_count}")
        print(f"  Failed:   {self.failed_count}")
        print(f"{'='*50}")
