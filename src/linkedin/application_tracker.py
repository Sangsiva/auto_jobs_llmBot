"""
Application Tracker — records every job the bot touches, prevents duplicates,
and generates summary reports.

CSV columns:
  date, job_title, company, location, job_url, relevance_score,
  resume_used, status, notes
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path
from src.logging import logger

TRACKER_PATH = Path("job_applications/applications.csv")
FIELDNAMES = [
    "date", "job_title", "company", "location", "job_url",
    "relevance_score", "resume_used", "status", "notes"
]
STATUS_APPLIED  = "Applied"
STATUS_SKIPPED  = "Skipped - Not Relevant"
STATUS_FAILED   = "Failed"
STATUS_NO_EASY  = "Skipped - No Easy Apply"


def _ensure_file():
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not TRACKER_PATH.exists():
        with open(TRACKER_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        logger.info(f"Created application tracker: {TRACKER_PATH}")


def record(job_title: str, company: str, location: str, job_url: str,
           relevance_score: int, resume_used: str, status: str, notes: str = ""):
    """Append one row to the tracker CSV."""
    _ensure_file()
    row = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "job_title": job_title,
        "company": company,
        "location": location,
        "job_url": job_url,
        "relevance_score": relevance_score,
        "resume_used": resume_used,
        "status": status,
        "notes": notes,
    }
    with open(TRACKER_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(row)
    logger.debug(f"Tracked: {status} — {job_title} @ {company}")


def already_applied(company: str, job_title: str = None) -> bool:
    """
    Returns True if we've already applied to this company (or this exact job).
    Checks company name (case-insensitive). Optionally also checks job title.
    """
    if not TRACKER_PATH.exists():
        return False
    company_lower = company.lower().strip()
    with open(TRACKER_PATH, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] != STATUS_APPLIED:
                continue
            if row["company"].lower().strip() == company_lower:
                if job_title is None:
                    return True
                if row["job_title"].lower().strip() == job_title.lower().strip():
                    return True
    return False


def print_report(days: int = 7):
    """Print a summary report for the last N days."""
    if not TRACKER_PATH.exists():
        print("No application data found yet.")
        return

    cutoff = datetime.now() - timedelta(days=days)
    rows = []
    with open(TRACKER_PATH, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                row_date = datetime.strptime(row["date"], "%Y-%m-%d %H:%M")
                if row_date >= cutoff:
                    rows.append(row)
            except Exception:
                rows.append(row)  # include rows with unparseable dates

    if not rows:
        print(f"No applications in the last {days} days.")
        return

    applied   = [r for r in rows if r["status"] == STATUS_APPLIED]
    skipped   = [r for r in rows if "Skipped" in r["status"]]
    failed    = [r for r in rows if r["status"] == STATUS_FAILED]
    interview = [r for r in rows if r["status"] == "Interview"]
    rejected  = [r for r in rows if r["status"] == "Rejected"]
    offer     = [r for r in rows if r["status"] == "Offer"]

    print(f"\n{'='*60}")
    print(f"  Application Report — Last {days} days")
    print(f"{'='*60}")
    print(f"  Total processed : {len(rows)}")
    print(f"  Applied         : {len(applied)}")
    print(f"  Skipped         : {len(skipped)}")
    print(f"  Failed          : {len(failed)}")
    print(f"  Interviews      : {len(interview)}")
    print(f"  Rejected        : {len(rejected)}")
    print(f"  Offers          : {len(offer)}")
    print(f"{'='*60}")

    if applied:
        print(f"\n  Recent applications:")
        for r in applied[-10:]:  # last 10
            print(f"    [{r['date']}] {r['job_title']} @ {r['company']} "
                  f"(score: {r['relevance_score']}, resume: {r['resume_used']})")

    if interview:
        print(f"\n  Interviews scheduled:")
        for r in interview:
            print(f"    {r['job_title']} @ {r['company']} — {r['notes']}")

    if offer:
        print(f"\n  Offers received:")
        for r in offer:
            print(f"    {r['job_title']} @ {r['company']} — {r['notes']}")

    print(f"\n  Full log: {TRACKER_PATH.resolve()}\n")


def update_status(company: str, job_title: str, new_status: str, notes: str = ""):
    """Update the status of an existing application (e.g. Interview, Rejected, Offer)."""
    if not TRACKER_PATH.exists():
        print("No tracker file found.")
        return False

    rows = []
    updated = False
    with open(TRACKER_PATH, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        if (row["company"].lower().strip() == company.lower().strip() and
                row["job_title"].lower().strip() == job_title.lower().strip()):
            row["status"] = new_status
            if notes:
                row["notes"] = notes
            updated = True
            break

    if updated:
        with open(TRACKER_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Updated: {job_title} @ {company} → {new_status}")
    else:
        print(f"Not found: {job_title} @ {company}")

    return updated
