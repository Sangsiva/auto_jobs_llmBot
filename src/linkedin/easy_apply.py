"""LinkedIn Easy Apply form filler."""
import time
import re
from pathlib import Path
from anthropic import Anthropic
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from src.logging import logger


class EasyApplyFiller:
    def __init__(self, driver, api_key: str, profile: dict, resume_pdf_path: Path,
                 cover_letter_text: str = None):
        self.driver = driver
        self.client = Anthropic(api_key=api_key)
        self.profile = profile
        self.resume_pdf_path = resume_pdf_path
        self.cover_letter_text = cover_letter_text
        self.wait = WebDriverWait(driver, 10)

    _PROFILE_SUMMARY = """\
Name: Sivakumar | Email: sivaeee1992@gmail.com | Phone: +6586077943
Location: Singapore (open to relocate UK/Europe) | Experience: 10+ years
Current role: AI Data Engineer at Tookitaki (Jun 2022-present) | Notice: Immediate
Visa: Singapore work auth | Salary: USD 100000 annual / GBP 80000 / SGD 8500/month
Skills: Spark, Scala, Python, Kafka, LangChain, LangGraph, AWS, EKS, Docker, K8s, Airflow, SparkML"""

    def _claude_answer(self, question: str, field_type: str = "text", options: list = None) -> str:
        """Single-question fallback — prefer _claude_answer_batch for multiple questions."""
        options_text = f"\nOptions: {options}" if options else ""
        prompt = (
            f"Profile: {self._PROFILE_SUMMARY}\n\n"
            f"Q: {question}\nType: {field_type}{options_text}\n\n"
            "Rules: concise, no fabrication, numbers only for numeric fields, "
            "exact option text for dropdowns, salary=100000 USD or 8500 SGD.\n"
            "Answer only:"
        )
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()

    def _claude_answer_batch(self, questions: list) -> dict:
        """
        Answer multiple questions in ONE API call.
        questions: list of dicts with keys: id, question, field_type, options
        Returns: dict mapping id → answer string
        """
        if not questions:
            return {}

        q_lines = []
        for q in questions:
            opt = f" [Options: {q['options']}]" if q.get('options') else ""
            q_lines.append(f"Q{q['id']} ({q['field_type']}): {q['question']}{opt}")

        prompt = (
            f"Profile: {self._PROFILE_SUMMARY}\n\n"
            "Answer each question for a job application form. Rules: concise, no fabrication, "
            "numbers only for numeric fields, exact option text for dropdowns, "
            "salary=100000 USD or 8500 SGD, textarea answers ≤100 words.\n\n"
            + "\n".join(q_lines)
            + "\n\nReply with one line per question in format:\nQ1: <answer>\nQ2: <answer>"
        )
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        answers = {}
        for line in response.content[0].text.strip().splitlines():
            line = line.strip()
            if line.startswith("Q") and ":" in line:
                try:
                    qid_str, answer = line.split(":", 1)
                    qid = int(qid_str[1:].strip())
                    answers[qid] = answer.strip()
                except Exception:
                    pass
        return answers

    def _fill_text_field(self, element, question_text: str):
        """Fill a text input field."""
        current_val = element.get_attribute("value") or ""
        if current_val.strip():
            return  # already filled

        # Check common fields by label text
        q_lower = question_text.lower()
        answer = None

        if any(k in q_lower for k in ["first name", "given name"]):
            answer = "Sivakumar"
        elif any(k in q_lower for k in ["last name", "surname", "family name"]):
            answer = ""
        elif "email" in q_lower:
            answer = "sivaeee1992@gmail.com"
        elif "phone" in q_lower or "mobile" in q_lower:
            answer = "+6586077943"
        elif any(k in q_lower for k in ["city", "location"]):
            answer = "Singapore"
        elif "linkedin" in q_lower:
            answer = "https://linkedin.com/in/siva-kumar-51853222"
        elif "github" in q_lower:
            answer = "https://github.com/Sangsiva"
        elif any(k in q_lower for k in ["salary", "compensation", "ctc", "expected"]):
            answer = "100000"
        elif any(k in q_lower for k in ["notice", "start", "available", "join"]):
            answer = "Immediate"
        elif any(k in q_lower for k in ["year", "experience"]) and "spark" in q_lower:
            answer = "10"
        elif any(k in q_lower for k in ["year", "experience"]) and "python" in q_lower:
            answer = "10"
        elif any(k in q_lower for k in ["year", "experience"]):
            answer = "10"
        else:
            answer = self._claude_answer(question_text, "text")

        element.clear()
        element.send_keys(answer)
        time.sleep(0.3)

    def _fill_dropdown(self, element, question_text: str):
        """Fill a select dropdown."""
        select = Select(element)
        options = [o.text for o in select.options if o.text.strip() and o.text != "Select an option"]

        q_lower = question_text.lower()
        answer = None

        if any(k in q_lower for k in ["country", "location", "citizenship"]):
            answer = next((o for o in options if "singapore" in o.lower()), None)
        elif any(k in q_lower for k in ["experience", "level", "seniority"]):
            answer = next((o for o in options if any(k in o.lower() for k in ["senior", "lead", "principal", "10", "7", "8"])), None)
        elif any(k in q_lower for k in ["education", "degree", "qualification"]):
            answer = next((o for o in options if any(k in o.lower() for k in ["bachelor", "undergraduate", "degree"])), None)
        elif any(k in q_lower for k in ["sponsor", "visa", "authoriz"]):
            answer = next((o for o in options if "no" in o.lower()), None)
        elif any(k in q_lower for k in ["relocat"]):
            answer = next((o for o in options if "yes" in o.lower()), None)
        elif any(k in q_lower for k in ["remote", "hybrid", "onsite"]):
            answer = next((o for o in options if any(k in o.lower() for k in ["yes", "hybrid", "remote", "flexible"])), None)

        if not answer:
            answer = self._claude_answer(question_text, "dropdown", options)
            # Match to closest option
            answer = next((o for o in options if answer.lower() in o.lower()), options[0] if options else None)

        if answer:
            try:
                select.select_by_visible_text(answer)
            except Exception:
                try:
                    select.select_by_index(1)
                except Exception:
                    pass

    def _handle_radio_checkbox(self, elements, question_text: str):
        """Handle radio buttons and checkboxes."""
        labels = []
        for el in elements:
            try:
                label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{el.get_attribute('id')}']")
                labels.append((el, label.text.strip()))
            except Exception:
                labels.append((el, el.get_attribute("value") or ""))

        if not labels:
            return

        options = [l[1] for l in labels]
        answer = self._claude_answer(question_text, "radio", options)

        matched = next(((el, txt) for el, txt in labels if answer.lower() in txt.lower()), None)
        if matched:
            if not matched[0].is_selected():
                matched[0].click()
        else:
            # Click first option as fallback
            if not labels[0][0].is_selected():
                labels[0][0].click()

    def _upload_resume(self):
        """Upload resume PDF if a file input exists."""
        try:
            file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            for fi in file_inputs:
                if fi.is_displayed() or True:
                    fi.send_keys(str(self.resume_pdf_path.resolve()))
                    time.sleep(2)
                    logger.info(f"Resume uploaded: {self.resume_pdf_path.name}")
                    return True
        except Exception as e:
            logger.warning(f"Resume upload skipped: {e}")
        return False

    def _get_question_label(self, element) -> str:
        """Try to find the label text for a form element."""
        try:
            el_id = element.get_attribute("id")
            if el_id:
                label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{el_id}']")
                return label.text.strip()
        except Exception:
            pass
        try:
            parent = self.driver.execute_script("return arguments[0].closest('.jobs-easy-apply-form-section__grouping, .fb-dash-form-element, .artdeco-form-item')", element)
            if parent:
                label = parent.find_element(By.CSS_SELECTOR, "label, legend, span.artdeco-text")
                return label.text.strip()
        except Exception:
            pass
        return ""

    _COVER_LETTER_KEYWORDS = [
        "cover letter", "cover_letter", "why do you want", "why are you interested",
        "additional information", "anything else", "message to hiring", "tell us about yourself",
    ]

    def fill_form_page(self):
        """
        Fill all form fields on the current Easy Apply page.
        Two-pass strategy:
          Pass 1 — fill known fields with hardcoded rules (zero API calls)
          Pass 2 — collect all remaining unknown questions and batch into ONE Haiku call
        """
        time.sleep(1)
        self._upload_resume()

        # ── Pass 1: hardcoded text inputs (no API) ────────────────────────
        for el in self.driver.find_elements(
            By.CSS_SELECTOR,
            "input[type='text'], input[type='tel'], input[type='email'], input[type='number']"
        ):
            try:
                if not el.is_displayed():
                    continue
                label = self._get_question_label(el)
                self._fill_text_field(el, label)
            except Exception as e:
                logger.debug(f"Text field error: {e}")

        # ── Collect unknown questions for batch Claude call ────────────────
        pending = []   # list of {id, el, field_type, question, options?, el_data}
        qid = 0

        # Textareas
        for el in self.driver.find_elements(By.CSS_SELECTOR, "textarea"):
            try:
                if not el.is_displayed():
                    continue
                if el.get_attribute("value") or el.text:
                    continue
                label = self._get_question_label(el)
                label_lower = label.lower()
                if self.cover_letter_text and any(k in label_lower for k in self._COVER_LETTER_KEYWORDS):
                    # Fill immediately with pre-generated letter — no API call
                    el.clear()
                    el.send_keys(self.cover_letter_text)
                    logger.info("Filled cover letter textarea with generated letter")
                else:
                    pending.append({"id": qid, "el": el, "field_type": "textarea", "question": label})
                    qid += 1
            except Exception as e:
                logger.debug(f"Textarea scan error: {e}")

        # Dropdowns — handled by _fill_dropdown (has its own heuristics, only falls back to Claude)
        for el in self.driver.find_elements(By.CSS_SELECTOR, "select"):
            try:
                if not el.is_displayed():
                    continue
                label = self._get_question_label(el)
                select = __import__('selenium.webdriver.support.ui', fromlist=['Select']).Select(el)
                options = [o.text for o in select.options if o.text.strip() and o.text != "Select an option"]
                pending.append({"id": qid, "el": el, "field_type": "dropdown",
                                "question": label, "options": options})
                qid += 1
            except Exception as e:
                logger.debug(f"Dropdown scan error: {e}")

        # Radio buttons
        handled_names = set()
        for el in self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio']"):
            try:
                name = el.get_attribute("name")
                if name in handled_names:
                    continue
                handled_names.add(name)
                group = self.driver.find_elements(By.CSS_SELECTOR, f"input[type='radio'][name='{name}']")
                label = self._get_question_label(el)
                opts = []
                for r in group:
                    try:
                        lbl = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{r.get_attribute('id')}']")
                        opts.append(lbl.text.strip())
                    except Exception:
                        opts.append(r.get_attribute("value") or "")
                pending.append({"id": qid, "el": group, "field_type": "radio",
                                "question": label, "options": opts})
                qid += 1
            except Exception as e:
                logger.debug(f"Radio scan error: {e}")

        if not pending:
            return

        # ── Pass 2: ONE batched Haiku call for all unknowns ────────────────
        batch_input = [
            {"id": p["id"], "question": p["question"],
             "field_type": p["field_type"], "options": p.get("options")}
            for p in pending
        ]
        answers = self._claude_answer_batch(batch_input)

        # Apply answers
        for p in pending:
            answer = answers.get(p["id"], "")
            if not answer:
                continue
            try:
                if p["field_type"] == "textarea":
                    p["el"].clear()
                    p["el"].send_keys(answer)

                elif p["field_type"] == "dropdown":
                    from selenium.webdriver.support.ui import Select as _Select
                    select = _Select(p["el"])
                    options = p.get("options", [])
                    matched = next((o for o in options if answer.lower() in o.lower()), None)
                    if matched:
                        select.select_by_visible_text(matched)
                    elif options:
                        select.select_by_index(1)

                elif p["field_type"] == "radio":
                    group = p["el"]
                    opts_labels = []
                    for r in group:
                        try:
                            lbl = self.driver.find_element(
                                By.CSS_SELECTOR, f"label[for='{r.get_attribute('id')}']")
                            opts_labels.append((r, lbl.text.strip()))
                        except Exception:
                            opts_labels.append((r, r.get_attribute("value") or ""))
                    matched = next(
                        ((r, t) for r, t in opts_labels if answer.lower() in t.lower()), None)
                    target = matched[0] if matched else (opts_labels[0][0] if opts_labels else None)
                    if target and not target.is_selected():
                        target.click()
            except Exception as e:
                logger.debug(f"Apply answer error ({p['field_type']}): {e}")

    def _click_next_or_submit(self) -> str:
        """Click Next, Review, or Submit button. Returns: 'next', 'review', 'submit', or 'done'."""
        time.sleep(1)
        buttons = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label], footer button")

        for btn in buttons:
            label = (btn.get_attribute("aria-label") or btn.text or "").lower()
            if "submit application" in label:
                btn.click()
                return "submit"
            elif "review" in label:
                btn.click()
                return "review"
            elif "next" in label or "continue" in label:
                btn.click()
                return "next"

        return "done"

    def _handle_safety_reminder(self):
        """Dismiss LinkedIn's 'Job search safety reminder' popup by clicking 'Continue applying'."""
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "continue applying" in btn.text.lower():
                    btn.click()
                    logger.info("Dismissed safety reminder — clicked Continue applying")
                    time.sleep(1)
                    return
        except Exception:
            pass

    def _handle_save_dialog(self, action: str = "discard"):
        """
        Handle the 'Save this application?' dialog.
        action: 'discard' to abandon, 'save' to save for later.
        """
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if btn.text.lower().strip() == action:
                    btn.click()
                    logger.info(f"Save dialog: clicked '{action}'")
                    time.sleep(1)
                    return
        except Exception:
            pass

    def run(self) -> bool:
        """Run the full Easy Apply flow. Returns True if submitted successfully."""
        # Handle safety reminder that sometimes appears right after clicking Easy Apply
        self._handle_safety_reminder()
        time.sleep(1)

        max_pages = 10
        for page in range(max_pages):
            logger.info(f"Easy Apply page {page + 1}")

            # Handle safety reminder that can appear on any page
            self._handle_safety_reminder()

            self.fill_form_page()
            result = self._click_next_or_submit()
            time.sleep(2)

            # Handle save dialog if it appeared (e.g. accidental dismiss trigger)
            self._handle_save_dialog("discard")

            if result == "submit":
                logger.info("Application submitted!")
                # Dismiss post-submit confirmation modal
                try:
                    for label in ["Dismiss", "Done", "Close"]:
                        try:
                            btn = self.driver.find_element(By.CSS_SELECTOR,
                                f"button[aria-label='{label}']")
                            btn.click()
                            break
                        except Exception:
                            pass
                except Exception:
                    pass
                return True
            elif result == "done":
                logger.warning("Could not find Next/Submit button.")
                return False

        logger.warning("Max pages reached without submission.")
        return False
