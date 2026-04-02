# In this file, you can set the configurations of the app.

from src.utils.constants import DEBUG, ERROR, LLM_MODEL, OPENAI

#config related to logging must have prefix LOG_
LOG_LEVEL = 'DEBUG'
LOG_SELENIUM_LEVEL = ERROR
LOG_TO_FILE = False
LOG_TO_CONSOLE = True

MINIMUM_WAIT_TIME_IN_SECONDS = 120   # 2 minutes
MAXIMUM_WAIT_TIME_IN_SECONDS = 600   # 10 minutes

JOB_APPLICATIONS_DIR = "job_applications"
JOB_SUITABILITY_SCORE = 7

JOB_MAX_APPLICATIONS = 5
JOB_MIN_APPLICATIONS = 1

# Ban-prevention limits — tracked across sessions in session_guard.json
DAILY_APPLICATION_LIMIT = 20   # hard cap per calendar day
MAX_SESSIONS_PER_DAY = 3       # max bot runs per day

LLM_MODEL_TYPE = 'claude'
LLM_MODEL = 'claude-sonnet-4-6'
# Only required for OLLAMA models
LLM_API_URL = ''
