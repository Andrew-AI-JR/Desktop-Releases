# -*- coding: utf-8 -*-
import sys
import time
import random
import json
import argparse
import os
import hashlib
import re
import subprocess
import traceback
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException
)
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import shutil

# Set default encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# === CONFIGURATION ===
# Load configuration from config.json
def load_config_from_file(config_path):
    """Load configuration from a JSON file."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

# Global config variable
CONFIG = None

def get_config():
    global CONFIG
    if CONFIG is None:
        CONFIG = load_config_from_args()
    return CONFIG

def load_config_from_args():
    """Load configuration from command line arguments, environment variables, and config file."""
    parser = argparse.ArgumentParser(description='LinkedIn Commenter')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--email', type=str, help='LinkedIn account email (overrides config file and env vars)')
    parser.add_argument('--password', type=str, help='LinkedIn account password (overrides config file and env vars)')
    parser.add_argument('--log_level', type=str, choices=['debug', 'info', 'warning', 'error'], help='Override log level from config/env')
    parser.add_argument('--debug', action='store_true', help='Enable full debug mode (overrides log_level from config/env)')
    parser.add_argument('--chrome-path', type=str, help='Path to custom Chrome/Chromium binary (overrides config file and system Chrome)')
    args = parser.parse_args()

    config = {}
    # Load from config file first
    if args.config:
        if os.path.exists(args.config):
            print(f"[DEBUG] Attempting to load config from file: {args.config}")
            file_config = load_config_from_file(args.config)
            if file_config:
                config.update(file_config) # This will load linkedin_credentials if present from file
            else:
                print(f"[WARN] Failed to load or parse configuration from {args.config}. File might be empty or malformed. Continuing with other sources.")
        else:
            print(f"[WARN] Config file specified but does not exist: {args.config}. Relying on CLI/env for all settings.")
    else:
        print("[INFO] No --config argument provided. Relying on CLI args or environment variables for settings.")

    # Ensure linkedin_credentials structure exists for overrides, even if not in file
    if 'linkedin_credentials' not in config:
        config['linkedin_credentials'] = {}

    # Environment variable overrides (middle priority)
    env_email = os.getenv('LINKEDIN_EMAIL')
    env_pass = os.getenv('LINKEDIN_PASSWORD')
    env_log_level = os.getenv('LOG_LEVEL')
    env_chrome_path = os.getenv('CHROME_PATH')

    # Populate linkedin_credentials if not already set by the config file
    if env_email and not config['linkedin_credentials'].get('email'):
        config['linkedin_credentials']['email'] = env_email
    if env_pass and not config['linkedin_credentials'].get('password'):
        config['linkedin_credentials']['password'] = env_pass 
    # Top-level keys from env if not set by file
    if env_log_level and not config.get('log_level'): 
        config['log_level'] = env_log_level
    if env_chrome_path and not config.get('chrome_path'):
        config['chrome_path'] = env_chrome_path
    
    # CLI overrides (highest priority)
    if args.email: # This will overwrite file/env values in linkedin_credentials
        config['linkedin_credentials']['email'] = args.email
    if args.password: # This will overwrite file/env values in linkedin_credentials
        config['linkedin_credentials']['password'] = args.password
    if args.chrome_path: # Top-level key
        config['chrome_path'] = args.chrome_path
    
    global LOG_LEVEL_OVERRIDE # Top-level keys for logging
    if args.debug:
        config['log_level'] = 'debug'
        config['debug_mode'] = True
        LOG_LEVEL_OVERRIDE = 'DEBUG'
    elif args.log_level:
        config['log_level'] = args.log_level
        LOG_LEVEL_OVERRIDE = args.log_level.upper()
    elif config.get('log_level'): # From file or env
        LOG_LEVEL_OVERRIDE = config['log_level'].upper()
    else: # Default
        config['log_level'] = 'info'
        LOG_LEVEL_OVERRIDE = 'INFO'

    # Ensure debug_mode reflects log_level if not explicitly set by --debug or in config file
    if 'debug_mode' not in config: 
        config['debug_mode'] = config.get('log_level', 'info').lower() == 'debug'
    
    # Warning if credentials are still missing after all loading stages
    creds_check = config.get('linkedin_credentials', {})
    if not args.config and not (creds_check.get('email') and creds_check.get('password')):
         print("[WARN] No config file specified, and LinkedIn credentials are not fully provided by CLI or environment variables. Ensure credentials are set for login if not in a config file.")

    return config

# Default configuration values
DEBUG_MODE = True
MAX_DAILY_COMMENTS = 50
MAX_SESSION_COMMENTS = 10
SCROLL_PAUSE_TIME = 8
MAX_SCROLL_CYCLES = 20
MAX_COMMENT_WORDS = 150
MAX_COMMENTS = 100
MIN_COMMENT_DELAY = 3
SHORT_SLEEP_SECONDS = 180
CALENDLY_LINK = ''
JOB_SEARCH_KEYWORDS = []
LINKEDIN_EMAIL = ''
LINKEDIN_PASSWORD = ''
USER_BIO = ''
SEARCH_URLS = []
# Stores CLI/env override for logging; used inside debug_log
LOG_LEVEL_OVERRIDE = None

def main():
    """Main execution function that continuously cycles through URLs while respecting limits."""
    global MAX_DAILY_COMMENTS, MAX_SESSION_COMMENTS, SCROLL_PAUSE_TIME, JOB_SEARCH_KEYWORDS
    global LINKEDIN_EMAIL, LINKEDIN_PASSWORD, DEBUG_MODE, SEARCH_URLS, CALENDLY_LINK, USER_BIO
    global comment_generator, MAX_SCROLL_CYCLES, MAX_COMMENT_WORDS, MIN_COMMENT_DELAY, SHORT_SLEEP_SECONDS
    
    # Initialize global CONFIG by calling get_config() which calls load_config_from_args()
    try:
        get_config() # This populates the global CONFIG variable
        if CONFIG is None:
            err_msg = "[FATAL] Global CONFIG is None after get_config(). Critical configuration error. Exiting."
            print(err_msg)
            try: debug_log(err_msg, "ERROR") # Attempt to log if debug_log is available
            except NameError: pass
            sys.exit(1)
        
        DEBUG_MODE = CONFIG.get('debug_mode', False) # Default to False if not in config
        debug_log(f"Starting main function. Loaded CONFIG keys: {list(CONFIG.keys()) if CONFIG else 'None'}", "DEBUG")

    except SystemExit: # Catch sys.exit calls from within get_config/load_config_from_args
        raise # Re-raise to ensure script terminates
    except Exception as config_error:
        err_msg = f"[FATAL] Unhandled error during configuration loading: {config_error}. Exiting."
        print(err_msg)
        try: debug_log(f"{err_msg} Traceback: {traceback.format_exc() if 'traceback' in globals() else ''}", "ERROR")
        except NameError: pass 
        sys.exit(1)

    # Populate essential global variables from CONFIG
    # Credentials are now expected under 'linkedin_credentials'
    linkedin_creds_from_config = CONFIG.get('linkedin_credentials', {})
    LINKEDIN_EMAIL = linkedin_creds_from_config.get('email', LINKEDIN_EMAIL) # Use global as fallback
    LINKEDIN_PASSWORD = linkedin_creds_from_config.get('password', LINKEDIN_PASSWORD) # Use global as fallback
    
    # Other keys are top-level
    USER_BIO = CONFIG.get('user_bio', USER_BIO)
    JOB_SEARCH_KEYWORDS = CONFIG.get('job_keywords', []) 
    CALENDLY_LINK = CONFIG.get('calendly_link', CALENDLY_LINK)
    SEARCH_URLS = CONFIG.get('search_urls', [])

    # Critical: Validate essential configuration
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        error_msg = "LinkedIn email or password not found in the configuration (expected under 'linkedin_credentials'). Script cannot proceed."
        debug_log(f"[FATAL] {error_msg} Please check your configuration. Exiting.", "ERROR")
        print(f"[FATAL] {error_msg} Please check your configuration. Exiting.")
        sys.exit(1)
    
    debug_log(f"LinkedIn Email: {'Set' if LINKEDIN_EMAIL else 'Not Set'}", "DEBUG")
    debug_log(f"User Bio length: {len(USER_BIO) if USER_BIO else 'Not Set'}", "DEBUG")
    debug_log(f"Job Keywords: {JOB_SEARCH_KEYWORDS}", "DEBUG")
    debug_log(f"Calendly Link: {CALENDLY_LINK if CALENDLY_LINK else 'Not Set'}", "DEBUG")
    debug_log(f"Direct Search URLs from config: {SEARCH_URLS}", "DEBUG")

    # If specific search URLs are not provided directly in config, try to generate them from keywords
    if not SEARCH_URLS and JOB_SEARCH_KEYWORDS:
        debug_log(f"No direct 'search_urls' in config. Generating from 'job_keywords': {JOB_SEARCH_KEYWORDS}", "INFO")
        SEARCH_URLS = get_search_urls_for_keywords(JOB_SEARCH_KEYWORDS)
        debug_log(f"Generated SEARCH_URLS: {SEARCH_URLS}", "DEBUG")
    
    # Critical check: If no SEARCH_URLS are available now (neither direct nor generated), script cannot proceed.
    if not SEARCH_URLS:
        error_msg = "No 'search_urls' found in config and no 'job_keywords' provided/effective to generate them. Script cannot proceed."
        debug_log(f"[FATAL] {error_msg} Please check your configuration file. Exiting.", "ERROR")
        print(f"[FATAL] {error_msg} Please check your configuration file. Exiting.")
        sys.exit(1)
    
    debug_log(f"Final SEARCH_URLS to be used (before optimization): {SEARCH_URLS}", "INFO")
    
    # Add restart counter to prevent infinite restart loops
    restart_count = 0
    max_restarts = 10
    
    # Define cycle_break to control the sleep duration between cycles
    cycle_break = 1  # Default value, adjust as needed
    
    while restart_count < max_restarts:  # Outer loop for automatic restarts with limit
        restart_count += 1
        debug_log(f"Restart attempt {restart_count}/{max_restarts}", "INFO")
        driver = None
        try:
            debug_log("[START] Starting LinkedIn Commenter", "INFO")
            
            # Initialize search performance tracker
            try:
                search_tracker = SearchPerformanceTracker()
                debug_log("[INIT] Initialized search performance tracker", "INFO")
            except Exception as tracker_error:
                debug_log(f"[ERROR] Failed to initialize search tracker: {tracker_error}", "ERROR")
                raise
            
            # Initialize comment generator
            try:
                debug_log("[INIT] Initializing comment generator", "DEBUG")
                comment_generator = CommentGenerator(USER_BIO)
                debug_log("[INIT] Comment generator initialized", "DEBUG")
            except Exception as gen_error:
                debug_log(f"[ERROR] Failed to initialize comment generator: {gen_error}", "ERROR")
                raise
            
            # Initialize browser driver
            try:
                debug_log("[INIT] Initializing browser driver", "DEBUG")
                driver = initialize_driver()
                debug_log("[INIT] Browser driver initialized successfully", "DEBUG")
            except Exception as driver_error:
                debug_log(f"[ERROR] Failed to initialize browser driver: {driver_error}", "ERROR")
                debug_log(f"[ERROR] Driver error details: {traceback.format_exc()}", "ERROR")
                raise
            
            # Verify login
            debug_log("[LOGIN] Verifying LinkedIn login status...", "INFO")
            print("Verifying LinkedIn login status...")
            
            while True:  # Inner loop for normal operation
                try:
                    # Check if browser is still responsive
                    try:
                        driver.current_url
                    except Exception:
                        debug_log("Browser connection lost, reinitializing...", "WARN")
                        if driver:
                            try:
                                driver.quit()
                            except:
                                pass
                        driver = initialize_driver()
                        time.sleep(5)
                        continue
                    
                    # Verify login status
                    debug_log("Verifying LinkedIn login status...", "LOGIN")
                    print("[APP_OUT]Verifying LinkedIn login status...")
                    verify_active_login(driver)

                    # Get active URLs from the tracker
                    current_hour = datetime.now().hour
                    active_urls = search_tracker.optimize_search_urls(SEARCH_URLS, current_hour)

                    # Process each URL
                    for url in active_urls:
                        if session_comments >= MAX_SESSION_COMMENTS:
                            debug_log(f"Session comment limit reached ({MAX_SESSION_COMMENTS})", "LIMIT")
                            break

                        if daily_comments >= MAX_DAILY_COMMENTS:
                            debug_log(f"Daily comment limit reached ({MAX_DAILY_COMMENTS})", "LIMIT")
                            sleep_until_midnight_edt()
                            daily_comments = 0  # Reset counter at midnight
                            continue

                        # Navigate to the URL with retry logic
                        retry_count = 0
                        while retry_count < 3:
                            try:
                                driver.get(url)
                                time.sleep(SHORT_SLEEP_SECONDS)  # Wait for page load
                                break  # Successful navigation, exit retry loop
                            except Exception as nav_e:
                                retry_count += 1
                                debug_log(f"Error navigating to {url} (attempt {retry_count}): {nav_e}", "ERROR")
                                if retry_count >= 3:
                                    debug_log(f"Failed to navigate to {url} after 3 attempts.", "ERROR")
                                    search_tracker.record_url_performance(url, success=False, comments_made=0)
                                    break
                                time.sleep(5 * retry_count)  # Exponential backoff

                        try:
                            # Process posts on the current page
                            posts_processed = process_posts(driver)
                            if posts_processed > 0:
                                session_comments += posts_processed
                                daily_comments += posts_processed
                            search_tracker.record_url_performance(url, success=True, comments_made=posts_processed)
                            
                            # Random delay between URLs
                            time.sleep(random.uniform(MIN_COMMENT_DELAY, MIN_COMMENT_DELAY * 2))

                        except Exception as e_url_processing:
                            debug_log(f"Error processing URL {url}: {e_url_processing}", "ERROR")
                            debug_log(traceback.format_exc(), "ERROR")
                            search_tracker.record_url_performance(url, success=False, comments_made=0, error=True)
                            continue  # to next URL in the for loop

                    # Sleep between cycles
                    cycle_sleep = random.uniform(cycle_break * 60, cycle_break * 120)
                    debug_log(f"Sleeping for {int(cycle_sleep/60)} minutes between cycles", "SLEEP")
                    time.sleep(cycle_sleep)

                except Exception as e:
                    debug_log(f"Error in main loop: {e}", "ERROR")
                    debug_log(traceback.format_exc(), "ERROR")
                    time.sleep(30)  # Longer sleep on error
                    continue

        except KeyboardInterrupt:
            debug_log("Received keyboard interrupt", "INFO")
            break  # Break outer loop
        except Exception as e:
            debug_log(f"[FATAL] Fatal error: {e}", "FATAL")
            debug_log(f"[ERROR] Error details: {traceback.format_exc()}", "ERROR")
            
            # Add a cooldown period to prevent rapid restarts
            cooldown = 30  # seconds
            debug_log(f"[COOLDOWN] Waiting {cooldown} seconds before restart", "INFO")
            time.sleep(cooldown)
            
            if DEBUG_MODE:
                traceback.print_exc()
                time.sleep(60)  # Sleep before restart
        finally:
            if driver:
                debug_log("Cleaning up and closing browser", "CLEANUP")
                try:
                    driver.quit()
                except:
                    pass
                time.sleep(5)  # Wait for cleanup
            debug_log("Script execution completed - will restart automatically", "END")
            print("[APP_OUT]LinkedIn automation completed a cycle. Restarting automatically...")
            time.sleep(10)  # Wait before restarting

def construct_linkedin_search_url(keywords, time_filter="past_month"):
    """
    Construct a LinkedIn search URL for posts with proper date filtering.
    
    Args:
        keywords (str or list): Search keywords or list of keywords
        time_filter (str): One of "past_24h", "past_week", "past_month", "past_year"
    
    Returns:
        str: Constructed LinkedIn search URL
    """
    # Convert keywords to proper format
    if isinstance(keywords, list):
        # Use the first keyword for the main search
        # LinkedIn works better with single focused searches
        keyword_query = keywords[0]
    else:
        keyword_query = keywords
    
    # Base URL for content search
    base_url = "https://www.linkedin.com/search/results/content/"
    
    # Map time filter to LinkedIn's datePosted parameter format
    time_map = {
        "past_24h": "past-24h",
        "past_week": "past-week",
        "past_month": "past-month",
        "past_year": "past-year"
    }
    
    # Construct the query parameters
    params = {
        "keywords": keyword_query,
        "origin": "FACETED_SEARCH",
        "sid": "tnP",
        "datePosted": f'"{time_map.get(time_filter, "past-month")}"'  # Wrap in quotes as required by LinkedIn
    }
    
    # Construct the final URL
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{base_url}?{query_string}"

def get_search_urls_for_keywords(keywords):
    """
    Generate search URLs for given keywords with different time filters.
    Each keyword gets its own search URL to maximize results.
    Always includes both 'hiring' and 'recruiting' search combinations.
    Prioritizes 24-hour content over monthly content.
    
    Args:
        keywords (str or list): Search keywords or list of keywords
    
    Returns:
        list: List of search URLs with different time filters, 24h URLs first
    """
    urls_24h = []
    urls_monthly = []
    
    # Convert single keyword to list for consistent processing
    if isinstance(keywords, str):
        keywords = [keywords]
    
    # Process each keyword - collect 24h and monthly URLs separately
    for keyword in keywords:
        # Past 24h searches (highest priority)
        urls_24h.extend([
            # Keyword with hiring
            construct_linkedin_search_url(f"{keyword} hiring", "past_24h"),
            # Keyword with recruiting
            construct_linkedin_search_url(f"{keyword} recruiting", "past_24h")
        ])
        
        # Past month searches (lower priority)
        urls_monthly.extend([
            # Keyword with hiring
            construct_linkedin_search_url(f"{keyword} hiring", "past_month"),
            # Keyword with recruiting
            construct_linkedin_search_url(f"{keyword} recruiting", "past_month")
        ])
    
    # Return 24h URLs first, then monthly URLs for maximum recency priority
    return urls_24h + urls_monthly

# Global variable for search URLs
SEARCH_URLS = []

# === SYSTEM PROMPT ===
SYSTEM_PROMPT = """You are a professional LinkedIn commenter who writes thoughtful, relevant comments on posts.

1. Your Task:
   - Analyze the given LinkedIn post
   - Generate a natural, conversational comment that adds value
   - Tailor your response based on the user's background
   - Keep comments concise (30-70 words)

2. Content Guidelines:
   - Focus on specific points from the original post
   - Share relevant insights from user's experience
   - Avoid generic phrases or clichés
   - No disclaimers, signatures, or meta-commentary

3. Professional Standards:
   - Be respectful and constructive
   - Maintain professional tone
   - Avoid controversial topics unless directly relevant
   - Never be overly promotional
"""

# === MESSAGE PROMPT TEMPLATE ===
MESSAGE_PROMPT_TEMPLATE = """
Post to comment on:
{post_text}

Author: {author_name}

Your background information:
{user_background}

Write a thoughtful, professional comment for this LinkedIn post. Be conversational and authentic.
"""

def get_message_prompt(config):
    """Generate a message prompt from the user's bio.
    This is used to personalize comments based on the user's background."""
    user_bio = config.get('user_bio', '')
    if not user_bio:
        return None

    return f"""
Background:
{user_bio}
"""

# === POST CLASSIFICATION PROMPT ===
CLASSIFICATION_PROMPT = """You are a LinkedIn post classifier. Your task is to analyze the given post and classify it into exactly one of these categories AND identify if the author is a recruiter:
- business_growth
- ai_interest
- job_search
- industry_news
- personal_story
- other

Rules for post category:
1. Choose the most relevant category based on the post's main topic
2. If the post mentions hiring, recruiting, job openings, or career opportunities, classify it as job_search
3. If the post contains job titles or position descriptions, classify it as job_search
4. If the post links to a job posting or application, classify it as job_search

Rules for recruiter identification:
1. Identify if the post author appears to be a recruiter or hiring manager
2. Look for terms like "recruiter", "talent acquisition", "hiring manager", "HR", "sourcing", or "staffing" in their title or post content
3. Check if they mention recruiting activities like sourcing candidates, filling positions, or working with hiring teams

Output format:
- First line: Just the category name (one of the six categories above)
- Second line: "recruiter: yes" if the author is a recruiter, or "recruiter: no" if not

Do not include any additional text, thinking, or explanations.

Post to classify:
{post_text}

Classification:"""

def clean_post_text(text):
    """
    Clean and normalize post text for better classification.
    
    Args:
        text (str): Raw post text
        
    Returns:
        str: Cleaned post text
    """
    try:
        # Remove hashtags but keep the text
        text = re.sub(r'#(\w+)', r'\1', text)
        
        # Remove URLs but keep the text
        text = re.sub(r'https?://\S+', '', text)
        
        # Remove special characters but keep spaces and basic punctuation
        text = re.sub(r'[^\w\s.,!?-]', ' ', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Remove common noise words
        noise_words = ['follow', 'view job', 'view profile', 'more', 'less']
        for word in noise_words:
            text = text.replace(word, '')
            
        return text.strip()
        
    except Exception as e:
        debug_log(f"Error cleaning post text: {e}")
        return text

class CommentGenerator:
    def __init__(self, debug_mode=True):
        self.debug_mode = debug_mode
        self.ollama_initialized = False
        # Use global USER_BIO instead of loading config directly
        global USER_BIO
        self.message_prompt = f"\nBackground:\n{USER_BIO}\n" if USER_BIO else ''
        if not self.message_prompt:
            self.debug_log("Warning: No user bio found in config. Comments may be less personalized.", "WARN")
        
    def debug_log(self, message, level="INFO"):
        """Print debug messages if debug mode is enabled."""
        if self.debug_mode:
            debug_log(message, level)
            
    def start_ollama(self):
        """Start the Ollama server if not already running."""
        if self.ollama_initialized:
            return True
            
        try:
            # Check if Ollama is already running
            result = subprocess.run(
                ['ollama', 'list'],
                capture_output=True,
                text=True,
                check=False,
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                # Verify required models are pulled
                models = result.stdout.lower()
                if 'qwen3:8b' not in models:
                    self.debug_log("Pulling qwen3:8b model for classification...")
                    subprocess.run(['ollama', 'pull', 'qwen3:8b'], check=True, encoding='utf-8')
                if 'mistral:latest' not in models:
                    self.debug_log("Pulling mistral model for comment generation...")
                    subprocess.run(['ollama', 'pull', 'mistral:latest'], check=True, encoding='utf-8')
                self.debug_log("Ollama is running with required models")
                self.ollama_initialized = True
                return True
                
            # If not running, try to start it
            self.debug_log("Starting Ollama server...")
            process = subprocess.Popen(
                ['ollama', 'serve'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                encoding='utf-8'
            )
            
            # Give it a moment to start
            time.sleep(5)
            
            # Pull required models
            self.debug_log("Pulling required models...")
            subprocess.run(['ollama', 'pull', 'qwen3:8b'], check=True, encoding='utf-8')
            subprocess.run(['ollama', 'pull', 'mistral:latest'], check=True, encoding='utf-8')
            
            self.ollama_initialized = True
            return True
            
        except Exception as e:
            self.debug_log(f"Error starting Ollama: {e}")
            return False
            
    def classify_post_type(self, post_text):
        """
        Classify a LinkedIn post into a specific category and identify if the author is a recruiter.
        
        Args:
            post_text (str): The text content of the LinkedIn post
            
        Returns:
            tuple: (post_category, is_recruiter) where post_category is a string and is_recruiter is a boolean
        """
        try:
            # Clean the post text first
            cleaned_text = clean_post_text(post_text)
            self.debug_log(f"Cleaned post text: {cleaned_text}")
            
            # Additional keyword-based checks
            text_lower = cleaned_text.lower()
            
            # Check for hiring indicators
            hiring_keywords = ['hiring', 'open position', 'job opening', 'looking for', 'seeking', 'join our team', 'is hiring', 'we are hiring', 'we\'re hiring', 'we are looking', 'we\'re looking']
            leadership_titles = ['director', 'manager', 'lead', 'head', 'chief', 'founder', 'president', 'vp', 'vice president', 'associate director', 'talent', 'people ops', 'recruiter', 'hr', 'hiring manager']
            team_indicators = ['my team', 'our team', 'the team', 'department', 'group', 'join us', 'join our']
            
            # Log the detection of keywords
            found_hiring = [kw for kw in hiring_keywords if kw in text_lower]
            found_titles = [title for title in leadership_titles if title in text_lower]
            found_team = [ind for ind in team_indicators if ind in text_lower]
            
            if found_hiring:
                self.debug_log(f"Found hiring keywords: {found_hiring}", "CLASSIFY")
            if found_titles:
                self.debug_log(f"Found leadership titles: {found_titles}", "CLASSIFY")
            if found_team:
                self.debug_log(f"Found team indicators: {found_team}", "CLASSIFY")
            
            has_hiring_keywords = any(keyword in text_lower for keyword in hiring_keywords)
            has_leadership_title = any(title in text_lower for title in leadership_titles)
            has_team_reference = any(indicator in text_lower for indicator in team_indicators)
            
            # Format the prompt with the cleaned text
            prompt = CLASSIFICATION_PROMPT.format(post_text=cleaned_text)
            
            # Run the classification
            result = subprocess.run(
                ['ollama', 'run', 'qwen3:8b', prompt],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8'
            )
            
            if result.returncode != 0:
                self.debug_log(f"Classification failed: {result.stderr}")
                return ("job_search" if has_hiring_keywords else "other", has_leadership_title)
                
            # Clean and validate the response
            response = self.clean_llm_response(result.stdout)
            if not response:
                self.debug_log("Invalid classification response")
                return ("job_search" if has_hiring_keywords else "other", has_leadership_title)
            
            # Parse the response lines
            response_lines = response.strip().split('\n')
            if len(response_lines) < 1:
                self.debug_log("Invalid classification response format: not enough lines")
                return ("job_search" if has_hiring_keywords else "other", has_leadership_title)
                
            # Extract information from response lines
            post_info = {}
            for line in response_lines:
                line = line.lower().strip()
                if line.startswith('category:'):
                    post_info['category'] = line.replace('category:', '').strip()
                elif line.startswith('recruiter:'):
                    post_info['is_recruiter'] = 'yes' in line
                elif line.startswith('shared_post:'):
                    post_info['is_shared'] = 'yes' in line
                elif line.startswith('original_author:'):
                    post_info['original_author'] = line.replace('original_author:', '').strip()
                elif line.startswith('hiring_post:'):
                    post_info['is_hiring'] = 'yes' in line
                    
            # Override based on keyword analysis
            if has_hiring_keywords and (has_leadership_title or has_team_reference):
                post_info['is_hiring'] = True
                post_info['is_recruiter'] = True
                
            # Validate the category
            valid_categories = [
                "business_growth",
                "ai_interest",
                "job_search",
                "industry_news",
                "personal_story",
                "other"
            ]
            
            category = post_info.get('category', 'other')
            if category not in valid_categories:
                self.debug_log(f"Invalid category: {category}")
                category = "other"
            
            # Determine if this is a recruiter post
            is_recruiter = post_info.get('is_recruiter', False)
            
            # Additional context for shared hiring posts
            self.post_context = {
                'is_shared': post_info.get('is_shared', False),
                'original_author': post_info.get('original_author', ''),
                'is_hiring': post_info.get('is_hiring', False)
            }
            
            self.debug_log(f"Post analysis: {post_info}")
            
            # If it's a shared hiring post, mark as job_search
            if post_info.get('is_shared', False) and post_info.get('is_hiring', False):
                category = 'job_search'
                is_recruiter = True  # Treat shared hiring posts as recruiter posts
            
            return (category, is_recruiter)
            
        except subprocess.TimeoutExpired:
            self.debug_log("Classification timed out")
            return ("other", False)
        except Exception as e:
            self.debug_log(f"Error in classification: {e}")
            return ("other", False)

    def generate_comment(self, post_text, author_name=None):
        """Generate a comment for a post using the message prompt and the post content."""
        if not self.message_prompt:
            self.debug_log("No message prompt available for personalized comments", "WARN")
            return None
        try:
            self.start_ollama()
            # Get category and recruiter status from the classification
            post_type, is_recruiter = self.classify_post_type(post_text)
            self.debug_log(f"Classified post type: {post_type}, Recruiter: {is_recruiter}")
            
            # Determine if this is a job posting
            is_job_posting = False
            job_company = None
            
            # Check for job posting indicators
            job_indicators = [
                'job opening', 'job opportunity', "we're hiring", 'we are hiring',
                'open position', 'open role', 'looking for', 'join our team',
                'apply', 'application', 'resume', 'cv', 'position is', 'job link',
                'job description', 'requirements:', 'qualifications:', 'experience required'
            ]
            
            for indicator in job_indicators:
                if indicator.lower() in post_text.lower():
                    is_job_posting = True
                    break
            
            # Try to extract company name
            company_patterns = [
                r'@\s*([A-Z][A-Za-z0-9\s&]+)',  # @Company
                r'at\s+([A-Z][A-Za-z0-9\s&]+)',  # at Company
                r'join\s+([A-Z][A-Za-z0-9\s&]+)',  # join Company
                r'([A-Z][A-Za-z0-9]+)\s+is\s+hiring',  # Company is hiring
                r'position\s+at\s+([A-Z][A-Za-z0-9\s&]+)'  # position at Company
            ]
            
            for pattern in company_patterns:
                match = re.search(pattern, post_text)
                if match:
                    job_company = match.group(1).strip()
                    break
            
            # Check for "do not contact directly" instructions
            do_not_contact = any(phrase in post_text.lower() for phrase in [
                "do not reach out", "do not contact", "no direct messages",
                "all applications must be submitted", "apply through the link"
            ])
            
            # Prepare the appropriate prompt based on post type and context
            if is_recruiter or (hasattr(self, 'post_context') and self.post_context.get('is_hiring')):
                # Check if this is a shared hiring post
                is_shared = hasattr(self, 'post_context') and self.post_context.get('is_shared')
                original_author = self.post_context.get('original_author', '') if is_shared else ''
                
                # Don't include Calendly link if the post explicitly says not to contact directly
                include_calendly = not do_not_contact
                
                # Use a default Calendly link if none is provided in the config
                calendly_link = CALENDLY_LINK or 'https://calendly.com/andrew-malinow/30min'
                
                formatted_prompt = MESSAGE_PROMPT_TEMPLATE.format(
                    post_text=post_text,
                    author_name=author_name or 'Unknown',
                    user_background=self.message_prompt or 'No background provided'
                )
                
                full_prompt = f"""
                {SYSTEM_PROMPT}

                {formatted_prompt}

                {'This is a shared hiring post. ' + author_name + ' shared a job opportunity from ' + original_author + '.' if is_shared else f'The post is authored by a recruiter{" for " + job_company if job_company else ""}.'}
                {'The post explicitly asks not to contact directly.' if do_not_contact else ''}

                Write a professional comment that follows these strict guidelines:
                1. Keep the comment between 30-60 words
                2. {'Thank ' + author_name + ' for sharing and acknowledge ' + original_author + "'s opportunity" if is_shared else 'Position yourself as a senior AI/ML expert interested in networking with quality recruiters'}
                3. Briefly mention your experience in AI/ML and data science
                4. {'If mentioning scheduling, direct it to ' + original_author if is_shared else 'Include a direct call-to-action to schedule a call'}
                5. Be professional, confident, and concise
                6. If the post mentions a specific role or industry, acknowledge it
                7. {'Respect the "do not contact directly" instruction and DO NOT include any scheduling link or direct contact request.' if do_not_contact else f'End with: "Happy to discuss further: {calendly_link}"'}
                8. No special characters, formatting, or meta-commentary
                
                Write ONLY the comment text - nothing else.
                """
            elif is_job_posting or post_type == 'job_search':
                self.debug_log(f"Detected job posting{' for ' + job_company if job_company else ''}")
                
                full_prompt = f"""
                {SYSTEM_PROMPT}

                {MESSAGE_PROMPT_TEMPLATE}

                The post is a job posting{' for ' + job_company if job_company else ''}.
                {'The post explicitly asks not to contact directly.' if do_not_contact else ''}
                {'Include this Calendly link at the end of your comment: ' + calendly_link if include_calendly else ''}

                Write a professional comment for this job posting that follows these strict guidelines:
                1. Keep the comment between 20-50 words
                2. DO NOT position yourself as a candidate for the job
                3. Instead, comment as a professional acknowledging the opportunity
                4. Mention something specific about the role or company if mentioned
                5. {'DO NOT include your Calendly link or ask to connect directly' if do_not_contact else f'Include this Calendly link at the end: {calendly_link}'}
                6. If the post says not to contact directly, respect that instruction
                7. Wish success in finding the right candidate
                8. Keep tone professional and supportive
                9. No special characters, formatting, or meta-commentary
                
                Write ONLY the comment text - nothing else.
                """
            else:
                # Original prompt for non-job posts
                formatted_prompt = MESSAGE_PROMPT_TEMPLATE.format(
                    post_text=post_text,
                    author_name=author_name or 'Unknown',
                    user_background=self.message_prompt or 'No background provided'
                )
                
                full_prompt = f"""
                {SYSTEM_PROMPT}

                {formatted_prompt}

                The post type is: {post_type}

                Write a genuine, empathetic comment that is tailored for a post of this type.
                Follow these strict guidelines:
                1. Keep the comment between 15-50 words
                2. Write in complete, grammatically correct sentences
                3. Focus on one main point from their post
                4. Share one relevant insight from your experience
                5. End with a constructive note
                6. Do not use any special characters or formatting
                7. Do not include any meta-commentary or disclaimers
                8. Do not use any placeholders or incomplete thoughts

                Comment structure:
                - Opening: Reference one specific point from their post
                - Middle: Share one relevant insight from your experience
                - Closing: End with a constructive note

                Write ONLY the comment text - nothing else.
                """
            
            prompt = f"{full_prompt}\n\nPost content:\n{post_text}"
            if author_name:
                prompt += f"\n\nAuthor name: {author_name}"
            
            result = subprocess.run(
                ['ollama', 'run', 'qwen3:8b', prompt],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
                encoding='utf-8'
            )
            
            comment = self.clean_llm_response(result.stdout.strip())
            if not self.verify_comment(comment):
                self.debug_log("Generated comment failed verification")
                return None
                
            # Final check to ensure no quotes remain
            if comment.startswith('"') and comment.endswith('"'):
                comment = comment[1:-1]
            elif comment.startswith("'") and comment.endswith("'"):
                comment = comment[1:-1]
                
            return comment
            
        except Exception as e:
            self.debug_log(f"Error generating comment: {e}")
            return None

    def clean_llm_response(self, response):
        """
        Clean and validate the LLM response.
        
        Args:
            response (str): Raw response from the LLM
            
        Returns:
            str: Cleaned response or None if invalid
        """
        try:
            # Remove any thinking tags or markers
            cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
            cleaned = re.sub(r'\[.*?\]', '', cleaned)
            
            # Remove extra whitespace and newlines
            cleaned = ' '.join(cleaned.split())
            
            # Remove surrounding quotes (single, double, or triple)
            if cleaned.startswith('"""') and cleaned.endswith('"""'):
                cleaned = cleaned[3:-3]
            elif cleaned.startswith("'''") and cleaned.endswith("'''"):
                cleaned = cleaned[3:-3]
            elif cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            elif cleaned.startswith("'") and cleaned.endswith("'"):
                cleaned = cleaned[1:-1]
                
            # Use regex to catch any remaining quote patterns
            cleaned = re.sub(r'^["\']|["\']$', '', cleaned)
            
            # Basic validation
            if not cleaned or len(cleaned) < 10:
                self.debug_log("Response too short or empty")
                return None
                
            return cleaned
            
        except Exception as e:
            self.debug_log(f"Error cleaning response: {e}")
            return None
            
    def generate_tech_relevance_keywords(self, config):
        """Generate tech relevance keywords based on user's configured keywords."""
        # Extract keywords from config
        user_keywords = config.get('keywords', '')
        if isinstance(user_keywords, str):
            keywords_list = [k.strip() for k in user_keywords.split(',')]
        else:
            keywords_list = user_keywords if isinstance(user_keywords, list) else []
        
        # Generate variations and related terms
        relevance_keywords = []
        for keyword in keywords_list:
            # Add the original keyword
            relevance_keywords.append(keyword.lower())
            
            # Add common variations for multi-word keywords
            if ' ' in keyword:
                relevance_keywords.append(keyword.lower().replace(' ', '-'))
                relevance_keywords.append(keyword.lower().replace(' ', ''))
        
        # Remove duplicates
        return list(set(relevance_keywords))

    def build_scoring_config(self, config):
        """Build scoring configuration with dynamic tech relevance based on user config."""
        if hasattr(self, 'scoring_config') and self.scoring_config is not None:
            return self.scoring_config
            
        self.scoring_config = {
            # Recency signals (20 points max)
            'recency': {
                'weight': 4.0,
                'keywords': [
                    'just now', 'minutes ago', '1 hour ago', 'today', 'this morning',
                    'posted today', 'new opening', 'just posted', 'urgent opening',
                    'immediate start', 'immediate opening', 'urgent requirement'
                ]
            },
            
            # Direct hiring manager signals (40 points max)
            'hiring_manager': {
                'weight': 8.0,
                'keywords': [
                    'hiring for my team', 'expanding my team', 'growing my team',
                    'building my team', 'looking to add', 'need someone to join',
                    'hiring manager', 'engineering manager', 'tech lead',
                    'team lead', 'department head', 'director of', 'vp of',
                    'chief', 'head of', 'manager seeking'
                ]
            },
            
            # Job posting indicators (15 points max)
            'job_posting': {
                'weight': 3.0,
                'keywords': [
                    'job opening', 'open position', 'open role', 'job opportunity',
                    "we're hiring", 'we are hiring', 'now hiring', 'apply now',
                    'join our team', 'looking for', 'seeking a', 'requirements:',
                    'qualifications:', 'responsibilities:', 'apply at', 'apply through'
                ]
            },
            
            # Work mode preferences (5 points max)
            'work_mode': {
                'weight': 2.5,
                'keywords': [
                    'remote', 'remote-first', 'remote friendly', 'work from home',
                    'wfh', 'hybrid', 'flexible location', 'flexible work',
                    'anywhere in us', 'us-based remote', 'fully remote', 'distributed team'
                ]
            },
            
            # Urgency signals (5 points max)
            'urgency': {
                'weight': 5.0,
                'keywords': [
                    'urgent', 'immediate', 'asap', 'start immediately',
                    'fast-track', 'fast track', 'quick hire', 'quick start',
                    'urgent requirement', 'high priority'
                ]
            }
        }
        
        # Add tech relevance category with dynamically generated keywords
        tech_keywords = self.generate_tech_relevance_keywords(config)
        scoring_config['tech_relevance'] = {
            'weight': 3.0,
            'keywords': tech_keywords
        }

    def calculate_post_score(self, post_text, author_name=None):
        """
        Calculate a score for a post based on various factors to prioritize posts from hiring managers.
        Uses FIXED scoring method without normalization.
        Returns:
            float: A score between 0 and 100, with higher scores indicating higher priority
        """
        if not post_text:
            self.debug_log('[SCORE] Empty post text, returning 0')
            return 0
            
        # Get or build scoring config
        scoring_config = self.build_scoring_config(get_config())
        if scoring_config is None:
            self.debug_log('[SCORE] Failed to build scoring config, returning 0')
            return 0
            
        total_score = 0
        post_text_lower = post_text.lower()
        score_breakdown = {
            'metadata': {
                'text_length': len(post_text),
                'word_count': len(post_text.split()),
                'has_author': bool(author_name)
            }
        }
        
        # Calculate scores for each category - FIXED scoring method
        for category, config_data in scoring_config.items():
            if not isinstance(config_data, dict) or 'weight' not in config_data or 'keywords' not in config_data:
                continue
                
            weight = config_data['weight']
            keywords = config_data['keywords']
            
            # Determine text to search in based on category
            search_text = author_name.lower() if 'author' in category and author_name else post_text_lower
            
            # Count keyword matches
            matches = sum(1 for kw in keywords if kw.lower() in search_text)
            
            # Give full weight for ANY match, small bonus for multiple matches (up to 2 extra)
            category_score = 0
            if matches > 0:
                category_score = weight * 5
                if matches > 1:
                    category_score += weight * min(matches - 1, 2)  # Max 2 bonus matches
                    
            total_score += category_score
            # Store breakdown for logging
            score_breakdown[category] = {
                'matches': matches,
                'score': category_score,
                'weight': weight
            }
            
        # Add length bonus (not penalty)
        words = len(post_text.split())
        length_bonus = 5 if words >= 50 else 0
        total_score += length_bonus
        score_breakdown['length'] = {
            'words': words,
            'score': length_bonus
        }
        
        # FIXED: Direct scoring - no normalization
        final_score = min(100, total_score)
        score_breakdown['final_score'] = final_score
        
        self.debug_log(f'[SCORE] Post scoring breakdown: {json.dumps(score_breakdown)}')
        return final_score


    def verify_comment(self, comment):
        """
        Verify that a generated comment meets our requirements.
        
        Args:
            comment (str): The comment to verify
            
        Returns:
            bool: True if comment is valid, False otherwise
        """
        if not comment:
            self.debug_log("Comment is empty")
            return False
            
        # Check length
        words = comment.split()
        if len(words) < 5 or len(words) > MAX_COMMENT_WORDS:
            self.debug_log(f"Comment length invalid: {len(words)} words")
            return False
            
        # Check if comment contains Calendly link when it shouldn't
        if "job" in comment.lower() and CALENDLY_LINK in comment:
            self.debug_log("Comment for job post should not contain Calendly link")
            return False
            
        # Check for common issues
        issues = [
            "I am an AI",
            "as an AI",
            "I cannot",
            "I don't have",
            "I don't know",
            "<think>",
            "[",
            "]",
            "Hi Micantly",  # Example of garbled text
            "fiheers",
            "Cackground",
            "Ggy",
            "reat",
            "I would be interested",  # Phrases that position the commenter as a job candidate
            "I am interested",
            "I would like to apply",
            "I would be a good fit",
            "my resume",
            "my CV",
            "my experience",
            "my background",
            "my skills"
        ]
        
        if any(issue.lower() in comment.lower() for issue in issues):
            self.debug_log("Comment contains invalid phrases")
            return False
            
        # Check for incomplete sentences
        if comment.count('.') < 1:
            self.debug_log("Comment lacks complete sentences")
            return False
            
        # Check for minimum word length - only check for obviously invalid words
        invalid_words = [word for word in words if len(word) < 2 and word not in ['a', 'I', '&']]
        if invalid_words:
            self.debug_log(f"Comment contains invalid words: {invalid_words}")
            return False
            
        self.debug_log("Comment passed all validation checks")
        return True

# Search URL performance tracking
class SearchPerformanceTracker:
    def __init__(self, config_path='search_performance.json'):
        self.config_path = config_path
        self.performance_data = self.load_data()
    
    def load_data(self):
        """Load search performance data from disk."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            return {
                'urls': {},
                'keywords': {},
                'time_periods': {
                    'morning': {'posts': 0, 'hiring_posts': 0},
                    'afternoon': {'posts': 0, 'hiring_posts': 0},
                    'evening': {'posts': 0, 'hiring_posts': 0}
                },
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            debug_log(f"Error loading search performance data: {e}", "ERROR")
            return {
                'urls': {},
                'keywords': {},
                'time_periods': {
                    'morning': {'posts': 0, 'hiring_posts': 0},
                    'afternoon': {'posts': 0, 'hiring_posts': 0},
                    'evening': {'posts': 0, 'hiring_posts': 0}
                },
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def save_data(self):
        """Save search performance data to disk."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.performance_data, f, indent=2)
        except Exception as e:
            debug_log(f"Error saving search performance data: {e}", "ERROR")
    
    def record_url_performance(self, url, posts_found, hiring_posts_found):
        """Record performance metrics for a search URL."""
        if url not in self.performance_data['urls']:
            self.performance_data['urls'][url] = {
                'total_posts': 0,
                'hiring_posts': 0,
                'searches': 0,
                'last_search': None,
                'efficiency': 0.0
            }
        
        data = self.performance_data['urls'][url]
        data['total_posts'] += posts_found
        data['hiring_posts'] += hiring_posts_found
        data['searches'] += 1
        data['last_search'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Calculate efficiency (hiring posts per search)
        if data['searches'] > 0:
            data['efficiency'] = data['hiring_posts'] / data['searches']
        
        # Record time period performance
        hour = datetime.now().hour
        period = 'morning' if hour < 12 else 'afternoon' if hour < 18 else 'evening'
        self.performance_data['time_periods'][period]['posts'] += posts_found
        self.performance_data['time_periods'][period]['hiring_posts'] += hiring_posts_found
        
        # Extract and record keyword performance
        keywords = self.extract_keywords_from_url(url)
        for keyword in keywords:
            if keyword not in self.performance_data['keywords']:
                self.performance_data['keywords'][keyword] = {
                    'total_posts': 0,
                    'hiring_posts': 0,
                    'searches': 0,
                    'efficiency': 0.0
                }
            
            kw_data = self.performance_data['keywords'][keyword]
            kw_data['total_posts'] += posts_found
            kw_data['hiring_posts'] += hiring_posts_found
            kw_data['searches'] += 1
            
            if kw_data['searches'] > 0:
                kw_data['efficiency'] = kw_data['hiring_posts'] / kw_data['searches']
        
        self.performance_data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.save_data()
    
    def extract_keywords_from_url(self, url):
        """Extract search keywords from a LinkedIn search URL."""
        try:
            if 'keywords=' in url:
                parsed_url = urllib.parse.urlparse(url)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                if 'keywords' in query_params:
                    return [kw.strip().lower() for kw in query_params['keywords'][0].split(',')]
            return []
        except Exception:
            return []
    
    def get_best_performing_urls(self, limit=5):
        """Get the best performing search URLs based on hiring post efficiency."""
        urls = list(self.performance_data['urls'].items())
        urls.sort(key=lambda x: x[1]['efficiency'], reverse=True)
        return urls[:limit]
    
    def optimize_search_urls(self, urls, current_hour=None):
        """Optimize the order of search URLs based on performance data."""
        if current_hour is None:
            current_hour = datetime.now().hour
        
        # Determine current time period
        period = 'morning' if current_hour < 12 else 'afternoon' if current_hour < 18 else 'evening'
        
        # Get best performing URLs
        best_urls = [url for url, _ in self.get_best_performing_urls(limit=len(urls))]
        
        # Create a set of original URLs to ensure we don't lose any
        original_urls = set(urls)
        
        # Create optimized list starting with best performers
        optimized_urls = []
        
        # Add best performing URLs first
        for url in best_urls:
            if url in original_urls:
                optimized_urls.append(url)
                original_urls.remove(url)
        
        # Add remaining URLs
        optimized_urls.extend(list(original_urls))
        
        return optimized_urls

def initialize_driver():
    """Initialize and return a configured Chrome/Chromium WebDriver instance.
    First tries system Chrome with WebDriver Manager, then falls back to bundled Chromium.
    Always runs in headless mode for production."""
    chrome_options = Options()
    config = get_config()
    
    # Common browser options - always headless for production
    # Use the older headless flag for better compatibility
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-popup-blocking')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
    chrome_options.add_experimental_option('detach', False)
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Get Chrome profile path from config or environment
    chrome_profile = config.get('chrome_profile_path') or os.environ.get('LINKEDIN_CHROME_PROFILE_PATH')
    if chrome_profile and chrome_profile.strip():
        debug_log(f"Using Chrome profile at: {chrome_profile}", "INFO")
        chrome_options.add_argument(f'--user-data-dir={chrome_profile}')
    
    # First try: Use system Chrome with WebDriver Manager
    try:
        debug_log("Attempting to use system Chrome with WebDriver Manager", "INFO")
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        import socket
        
        # Find an available port - use a fixed port if dynamic allocation fails
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('localhost', 0))
            port = sock.getsockname()[1]
            sock.close()
            debug_log(f"Using dynamic port: {port}", "INFO")
        except Exception as port_error:
            # Use a fixed port as fallback
            port = 9222
            debug_log(f"Dynamic port allocation failed: {port_error}. Using fixed port {port}", "INFO")
        
        # Use the available port
        chrome_options.add_argument(f'--remote-debugging-port={port}')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Wait for browser to be ready
        driver.implicitly_wait(10)
        debug_log("Successfully initialized system Chrome in headless mode", "INFO")
        return driver
    except Exception as e:
        debug_log(f"System Chrome failed: {e}. Falling back to bundled Chromium.", "INFO")
    
    # Fallback: Use bundled Chromium with matching ChromeDriver
    try:
        # Try multiple possible locations for bundled Chromium
        possible_root_dirs = [
            # Production path (in resources directory)
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'resources'),
            # Development path (in junior-desktop directory)
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            # Alternative path (3 levels up from script)
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            # Direct parent of script directory
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ]
        
        # Platform-specific paths
        if sys.platform == 'win32':
            chromium_dir = 'chromium-stable-win64'
            chromium_subdir = 'chrome-win64'
            chromedriver_subdir = 'chromedriver-win64'
            chromium_exe = 'chrome.exe'
            chromedriver_exe = 'chromedriver.exe'
        else:
            raise NotImplementedError("Only Windows is supported for bundled Chromium at this time")
        
        # Try to find Chromium in possible locations
        chromium_path = None
        chromedriver_path = None
        
        for root_dir in possible_root_dirs:
            # Try with junior-desktop subdirectory
            candidate_chromium = os.path.join(root_dir, 'junior-desktop', chromium_dir, chromium_subdir, chromium_exe)
            candidate_chromedriver = os.path.join(root_dir, 'junior-desktop', chromium_dir, chromedriver_subdir, chromedriver_exe)
            
            # Try without junior-desktop subdirectory
            alt_candidate_chromium = os.path.join(root_dir, chromium_dir, chromium_subdir, chromium_exe)
            alt_candidate_chromedriver = os.path.join(root_dir, chromium_dir, chromedriver_subdir, chromedriver_exe)
            
            debug_log(f"Checking for Chromium at: {candidate_chromium}", "INFO")
            debug_log(f"Checking for Chromium at: {alt_candidate_chromium}", "INFO")
            
            if os.path.exists(candidate_chromium) and os.path.exists(candidate_chromedriver):
                chromium_path = candidate_chromium
                chromedriver_path = candidate_chromedriver
                debug_log(f"Found Chromium at: {chromium_path}", "INFO")
                debug_log(f"Found ChromeDriver at: {chromedriver_path}", "INFO")
                break
            elif os.path.exists(alt_candidate_chromium) and os.path.exists(alt_candidate_chromedriver):
                chromium_path = alt_candidate_chromium
                chromedriver_path = alt_candidate_chromedriver
                debug_log(f"Found Chromium at: {chromium_path}", "INFO")
                debug_log(f"Found ChromeDriver at: {chromedriver_path}", "INFO")
                break
        
        if not chromium_path or not chromedriver_path:
            debug_log("Could not find bundled Chromium in any expected location", "ERROR")
            raise FileNotFoundError("Bundled Chromium or ChromeDriver not found in any expected location")
            
        # Point Chrome options to bundled binary
        chrome_options.binary_location = chromium_path
        
        # Create service with bundled ChromeDriver
        service = Service(executable_path=chromedriver_path)
        
        # Initialize driver with bundled components
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            debug_log("Successfully initialized bundled Chromium in headless mode", "INFO")
            return driver
        except OSError as os_error:
            if "[Errno 22] Invalid argument" in str(os_error):
                # Try with minimal options as a last resort
                debug_log("Encountered [Errno 22] Invalid argument. Trying with minimal options.", "WARN")
                minimal_options = Options()
                minimal_options.add_argument('--headless')
                minimal_options.add_argument('--no-sandbox')
                minimal_options.add_argument('--disable-dev-shm-usage')
                
                try:
                    # Try with system Chrome and minimal options
                    debug_log("Attempting to initialize Chrome with minimal options", "INFO")
                    driver = webdriver.Chrome(options=minimal_options)
                    debug_log("Successfully initialized Chrome with minimal options", "INFO")
                    return driver
                except Exception as min_error:
                    debug_log(f"Failed with minimal options: {min_error}", "ERROR")
                    
                    # One final attempt with absolute minimal options
                    debug_log("Attempting with absolute minimal options", "INFO")
                    final_options = Options()
                    final_options.add_argument('--headless')
                    final_options.add_argument('--no-sandbox')
                    driver = webdriver.Chrome(options=final_options)
                    debug_log("Successfully initialized Chrome with absolute minimal options", "INFO")
                    return driver
            else:
                raise
    except Exception as e:
        debug_log(f"Fatal error initializing Chrome/Chromium: {e}", "FATAL")
        user_message = (
            f"Failed to initialize both system Chrome and bundled Chromium in headless mode: {e}\n"
            "If the problem persists, please contact support and provide this log file."
        )
        raise RuntimeError(user_message)
        print(user_message)
        debug_log(user_message, "ERROR")
        sys.exit(1)

def debug_log(message, level="INFO"):
    """Enhanced debug logging with timestamps and levels."""
    try:
        # Clean message
        message = str(message).encode('ascii', 'ignore').decode()
        
        # Get current log level
        config = get_config()
        current_level = (config.get('log_level', 'info') if config else 'info').upper()
        
        # Format timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}"
        
        # Always print to console
        print(log_line)
        
        # Send to UI
        print(f"[APP_OUT]{log_line}")
        
        # Write to log file if enabled
        if DEBUG_MODE or LOG_LEVEL_OVERRIDE:
            try:
                # Use log_file_path from config if available
                log_path = config.get('log_file_path', 'linkedin_commenter.log')
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(log_line + '\n')
            except OSError as e:
                print(f"[APP_OUT][{timestamp}] [WARN] Failed to write to log file: {e}")
    except Exception as e:
        # Absolute fallback - print raw error
        print(f"Critical error in debug_log: {e}")

def load_log():
    """Load processed post IDs from disk, excluding posts from the last hour."""
    try:
        if os.path.exists("comment_log.json"):
            with open("comment_log.json", "r") as f:
                log = json.load(f)
                
                # Filter out posts from the last hour
                one_hour_ago = datetime.now() - timedelta(hours=1)
                filtered_log = []
                
                for entry in log:
                    if isinstance(entry, dict) and 'timestamp' in entry:
                        try:
                            post_time = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                            if post_time < one_hour_ago:
                                filtered_log.append(entry)
                        except (ValueError, TypeError):
                            # If timestamp is invalid, keep the entry
                            filtered_log.append(entry)
                    else:
                        # If entry doesn't have timestamp, keep it
                        filtered_log.append(entry)
                
                debug_log(f"Filtered out {len(log) - len(filtered_log)} recent posts", "DATA")
                return filtered_log
        return []
    except Exception as e:
        debug_log(f"Error loading log: {e}", "DATA")
        return []

def save_log(log):
    """Save processed post IDs to disk."""
    try:
        with open("comment_log.json", "w") as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        debug_log(f"Error saving log: {e}", "DATA")

def load_comment_history():
    """Load history of comments that were successfully posted."""
    try:
        if os.path.exists("comment_history.json"):
            with open("comment_history.json", "r") as f:
                return json.load(f)
        return {}
    except Exception as e:
        debug_log(f"Error loading comment history: {e}", "DATA")
        return {}

def save_comment_history(history):
    """Save history of comments that were successfully posted."""
    try:
        with open("comment_history.json", "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        debug_log(f"Error saving comment history: {e}", "DATA")

def find_posts(driver):
    """Find all post elements currently visible on the screen with multiple selectors (from Local_Test.py)."""
    debug_log("Searching for posts...", "SEARCH")
    try:
        # Use multiple selectors to find posts
        selectors = [
            "div.feed-shared-update-v2",
            "div.feed-shared-card",
            "div.update-components-actor",
            "div[data-urn]",
            "div.relative.ember-view.occludable-update"
        ]
        all_posts = []
        for selector in selectors:
            try:
                posts = driver.find_elements(By.CSS_SELECTOR, selector)
                if posts:
                    debug_log(f"Found {len(posts)} posts with selector: {selector}", "SEARCH")
                    all_posts.extend(posts)
            except Exception as e:
                debug_log(f"Error with selector {selector}: {e}", "SEARCH")
        # Filter out duplicates by comparing elements
        unique_posts = []
        seen_elements = set()
        for post in all_posts:
            try:
                element_id = id(post)
                if element_id not in seen_elements:
                    seen_elements.add(element_id)
                    unique_posts.append(post)
            except Exception:
                continue
        debug_log(f"Found {len(unique_posts)} unique posts", "SEARCH")
        return unique_posts
    except Exception as e:
        debug_log(f"Error finding posts: {e}", "SEARCH")
        return []

def compute_post_id(post):
    """
    Compute a unique ID for a post using multiple attributes.
    Returns a tuple of (post_id, id_method) where id_method indicates how we got the ID.
    """
    try:
        # Method 1: data-urn attribute
        urn = post.get_attribute("data-urn")
        if urn:
            return (urn, "data-urn")
        # Method 2: data-id attribute
        data_id = post.get_attribute("data-id")
        if data_id:
            return (data_id, "data-id")
        # Method 3: id attribute directly
        element_id = post.get_attribute("id")
        if element_id and not element_id.startswith("ember"):
            return (element_id, "element-id")
        # Method 4: Check for a permalink element
        try:
            permalink = post.find_element(By.CSS_SELECTOR, "a.app-aware-link[data-tracking-control-name='detail_page']")
            if permalink:
                href = permalink.get_attribute("href")
                if href and "activity" in href:
                    import re
                    match = re.search(r'activity:(\d+)', href)
                    if match:
                        return (f"activity:{match.group(1)}", "permalink")
        except Exception:
            pass
        # Method 5: Try to find author name and timestamp
        try:
            author = post.find_element(By.CSS_SELECTOR, "span.feed-shared-actor__name")
            timestamp = post.find_element(By.CSS_SELECTOR, "span.feed-shared-actor__sub-description")
            if author and timestamp:
                author_text = author.text.strip()
                timestamp_text = timestamp.text.strip()
                if author_text and timestamp_text:
                    combined = f"{author_text}:{timestamp_text}"
                    import hashlib
                    return (hashlib.sha256(combined.encode()).hexdigest(), "author-timestamp")
        except Exception:
            pass
        # Method 6: Last resort - use inner HTML hash
        post_html = post.get_attribute("innerHTML")
        if post_html:
            truncated_html = post_html[:500]
            import hashlib
            return (hashlib.sha256(truncated_html.encode()).hexdigest(), "html-hash")
        # If all fails, use a random hash based on current time
        import time, hashlib
        return (hashlib.sha256(str(time.time()).encode()).hexdigest(), "fallback")
    except Exception as e:
        debug_log(f"Error computing post ID: {e}", "DATA")
        import time, hashlib
        return (hashlib.sha256(str(time.time()).encode()).hexdigest(), "error")

def has_already_commented(driver, post):
    """Check if we have already commented on this post."""
    debug_log("Checking if post already has our comment...", "CHECK")
    try:
        # First check our comment history
        comment_history = load_comment_history()
        post_id, _ = compute_post_id(post)
        if post_id in comment_history:
            debug_log("Found post ID in our comment history", "CHECK")
            return True

        # Try to find comments section
        comments_section = None
        comment_selectors = [
            ".//div[contains(@class, 'comments-comment-item')]",
            ".//div[contains(@class, 'comments-comments-list')]",
            ".//ul[contains(@class, 'comments-comment-item')]",
            ".//div[contains(@class, 'comments-comment-item__main-content')]",
            ".//div[contains(@class, 'comments-comment-item__inline-show-more-text')]"
        ]

        # Check each comment for indicators it might be from us
        for selector in comment_selectors:
            try:
                elements = post.find_elements(By.XPATH, selector)
                if elements:
                    for comment in elements:
                        comment_text = comment.text.lower()
                        # Check for various indicators that this might be from us
                        indicators = [
                            "andrew malinow",  # Your name or unique phrase
                            "phd",
                            "cognitive psychologist",
                            "data science",
                            "ai leadership"
                        ]
                        if any(indicator in comment_text for indicator in indicators):
                            debug_log("Found a comment that appears to be from us", "CHECK")
                            # Store this in our comment history
                            comment_history[post_id] = {
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "message": comment_text,
                                "detected": True
                            }
                            save_comment_history(comment_history)
                            return True
            except Exception:
                continue

        debug_log("No evidence we've already commented", "CHECK")
        return False
    except Exception as e:
        debug_log(f"Error checking for existing comments: {e}")
        return False  # If we can't check, assume we haven't commented

# Dynamic role patterns for scoring
ROLE_PATTERNS = [
    '{role} at',  # e.g. 'engineering manager at'
    '{role} for',  # e.g. 'tech lead for'
    '{role} in',   # e.g. 'data scientist in'
    'senior {role}',  # e.g. 'senior engineer'
    'lead {role}',    # e.g. 'lead developer'
    '{role} lead',    # e.g. 'engineering lead'
]

# Function to generate role-based keywords from user's bio
def generate_role_keywords(user_role):
    """Generate variations of role-based keywords from user's role."""
    if not user_role:
        return []
    keywords = []
    for pattern in ROLE_PATTERNS:
        keywords.append(pattern.format(role=user_role.lower()))
    return keywords

# Keyword configurations for post scoring
POST_SCORING_CONFIG = {
    'internal_hiring': {
        'weight': 5.0,  # Highest weight for internal hiring managers
        'keywords': [
            'hiring for my team',
            'hiring for our team',
            'expanding our team',
            'scaling our team',
            'growing the team',
            'building the team',
            'leading the team',
            # Note: Role-specific keywords will be added dynamically
        ]
    },
    'direct_hiring': {
        'weight': 4.0,  # High weight for direct hiring signals
        'keywords': [
            'i\'m hiring',
            'we\'re hiring',
            'hiring for',
            'looking to hire',
            'actively hiring',
            'now hiring',
            'hiring now',
            'open position',
            'job opening',
            'position available',
            'role available',
            'opportunity available'
        ]
    },
    'external_recruiter': {
        'weight': 2.0,  # Lower weight for external recruiters
        'keywords': [
            'recruitment consultant',
            'talent acquisition specialist',
            'technical recruiter',
            'staffing specialist',
            'recruiting agency',
            'talent partner',
            'sourcing specialist',
            'recruiting firm'
        ]
    },
    'tech_relevance': {
        'weight': 2.0,  # Medium weight for technical relevance
        'keywords': [
            'python',
            'machine learning',
            'data science',
            'ai',
            'artificial intelligence',
            'deep learning',
            'nlp',
            'natural language processing',
            'computer vision',
            'neural networks',
            'tensorflow',
            'pytorch',
            'scikit-learn',
            'pandas',
            'numpy',
            'data analysis',
            'data engineering',
            'data pipeline',
            'etl',
            'sql',
            'database',
            'cloud',
            'aws',
            'azure',
            'gcp',
            'docker',
            'kubernetes',
            'microservices',
            'rest api',
            'api development',
            'full stack',
            'backend',
            'frontend',
            'web development',
            'software engineering',
            'devops',
            'ci/cd',
            'git'
        ]
    },
    'company_tier': {
        'weight': 3.0,  # High weight for company quality
        'keywords': [
            'faang',
            'meta',
            'facebook',
            'apple',
            'amazon',
            'netflix',
            'google',
            'microsoft',
            'fortune 500',
            'fortune 100',
            'series a',
            'series b',
            'series c',
            'unicorn',
            'nasdaq',
            'nyse',
            'public company',
            'industry leader',
            'market leader'
        ]
    },
    'work_mode': {
        'weight': 2.0,  # Medium weight for work flexibility
        'keywords': [
            'remote',
            'remote-first',
            'remote friendly',
            'work from home',
            'wfh',
            'hybrid',
            'flexible location',
            'flexible work',
            'anywhere in us',
            'us-based remote',
            'fully remote',
            'distributed team'
        ]
    },
    'post_details': {
        'weight': 1.0,  # Lower weight for post quality indicators
        'keywords': [
            'requirements:', 'qualifications:', 'experience:',
            'skills:', 'responsibilities:', 'salary:', 'location:',
            'stack:', 'technologies:', 'benefits:'
        ]
    }
}

# Initialize comment_generator variable (will be set in main after config loads)
comment_generator = None

def extract_author_name(post):
    """Try to extract the author name from the post element."""
    try:
        selectors = [
            ".//span[contains(@class, 'feed-shared-actor__name')]",
            ".//span[contains(@class, 'update-components-actor__name')]",
            ".//a[contains(@class, 'profile-rail-card__actor-link')]"
        ]
        for selector in selectors:
            try:
                element = post.find_element(By.XPATH, selector)
                if element:
                    name = element.text.strip()
                    if name:
                        return name
            except Exception:
                continue
        return None
    except Exception:
        return None

# Default user configuration
DEFAULT_USER_CONFIG = {
    'timezone': 'US/Eastern',  # User's local timezone
    'active_start_hour': 0,    # Start hour in 24-hour format (0 = midnight)
    'active_end_hour': 23,     # End hour in 24-hour format (23 = 11 PM)
    'sleep_start_hour': 0,     # Hour to start sleeping (0 = midnight)
    'sleep_duration_hours': 6   # How long to sleep
}

def get_user_config():
    """Get user configuration from loaded config or defaults."""
    config = get_config()
    return config.get('user_config', DEFAULT_USER_CONFIG) if config else DEFAULT_USER_CONFIG

def is_active_hours():
    """Check if current time is within user's active hours."""
    user_config = get_user_config()
    user_tz = pytz.timezone(user_config['timezone'])
    now = datetime.now(user_tz)
    current_hour = now.hour
    
    # If we're between active_start_hour and active_end_hour
    return user_config['active_start_hour'] <= current_hour < user_config['active_end_hour']

def sleep_during_inactive_hours():
    """Sleep during inactive hours based on user's timezone."""
    user_config = get_user_config()
    user_tz = pytz.timezone(user_config['timezone'])
    now = datetime.now(user_tz)
    
    if now.hour >= user_config['sleep_start_hour']:
        # Calculate sleep duration
        sleep_hours = user_config['sleep_duration_hours']
        debug_log(f"Starting sleep period for {sleep_hours} hours in {user_config['timezone']}", "SLEEP")
        time.sleep(sleep_hours * 3600)  # Convert hours to seconds
        debug_log("Sleep period completed", "SLEEP")
        return True
        
    return False

def rephrase_comment_shorter(comment, post_text):
    """Rephrase the comment to be shorter than the post text using LLM. If LLM fails, return original comment."""
    try:
        # Start Ollama if needed
        if not hasattr(comment_generator, 'ollama_initialized') or not comment_generator.ollama_initialized:
            comment_generator.start_ollama()
            
        prompt = (
            "Rephrase the following LinkedIn comment to be shorter than the post it is replying to. "
            "Keep the tone professional, personal, and natural. Do not remove key points, but make the comment concise and impactful. "
            "Do not reference AI, LLM, or automation. Only output the rephrased comment.\n\n"
            f"Post:\n{post_text}\n\nComment:\n{comment}"
        )
        
        result = subprocess.run(
            ['ollama', 'run', 'mistral:latest', prompt],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            encoding='utf-8'
        )
        
        output = result.stdout.strip()
        
        # Remove surrounding quotes (single, double, or triple)
        if output.startswith('\"\"\"') and output.endswith('\"\"\"'):
            output = output[3:-3]
        elif output.startswith("'''") and output.endswith("'''"):
            output = output[3:-3]
        elif output.startswith('\"') and output.endswith('\"'):
            output = output[1:-1]
        elif output.startswith("'") and output.endswith("'"):
            output = output[1:-1]
            
        # Use regex to catch any remaining quote patterns
        output = re.sub(r'^[\"\']|[\"\']$', '', output)
        
        # Fallback if LLM output is empty or not shorter
        if not output or len(output.split()) >= len(comment.split()):
            debug_log("LLM did not produce a shorter comment, using original.")
            return comment
            
        debug_log(f"Rephrased comment is {len(output.split())} words (was {len(comment.split())})")
        return output
        
    except Exception as e:
        debug_log(f"Error in rephrase_comment_shorter: {e}")
        return comment

def process_posts(driver):
    """Process visible posts on the current page."""
    debug_log("Starting post processing", "PROCESS")
    print("[APP_OUT]Processing LinkedIn posts...")
    posts_processed = 0
    hiring_posts_found = 0
    posts_commented = 0
    try:
        debug_log("[COMMENT] Beginning comment posting loop", "COMMENT")
        debug_log("Loading processed post IDs", "DATA")
        processed_log = load_log()
        comment_history = load_comment_history()
        debug_log(f"Loaded {len(processed_log)} processed posts and {len(comment_history)} comments", "DATA")
        debug_log("Searching for visible posts", "SEARCH")
        posts = find_posts(driver)
        if not posts:
            debug_log("No posts found on current page", "WARNING")
            return posts_processed, hiring_posts_found
            
        # Score and sort posts
        scored_posts = []
        for post in posts:
            try:
                post_text = get_post_text(driver, post)
                author_name = extract_author_name(post)
                post_id, _ = compute_post_id(post)
                
                # Skip already processed posts early
                if post_id in processed_log or post_id in comment_history:
                    continue
                    
                score = comment_generator.calculate_post_score(post_text, author_name)
                scored_posts.append((score, post, post_text, author_name))
            except Exception as e:
                debug_log(f"Error scoring post: {e}", "ERROR")
                continue
                
        # Sort posts by score (highest first)
        scored_posts.sort(reverse=True, key=lambda x: x[0])
        
        # Log scoring distribution
        if scored_posts:
            scores = [score for score, _, _, _ in scored_posts]
            score_stats = {
                'count': len(scores),
                'min_score': min(scores),
                'max_score': max(scores),
                'avg_score': sum(scores) / len(scores),
                'score_distribution': {
                    '90-100': len([s for s in scores if s >= 90]),
                    '70-89': len([s for s in scores if 70 <= s < 90]),
                    '50-69': len([s for s in scores if 50 <= s < 70]),
                    '30-49': len([s for s in scores if 30 <= s < 50]),
                    '0-29': len([s for s in scores if s < 30])
                }
            }
            debug_log(f"Scoring distribution: {json.dumps(score_stats, indent=2)}", "STATS")
            
        debug_log(f"Found {len(scored_posts)} new posts to process, sorted by score", "SEARCH")
        for post_index, (score, post, post_text, author_name) in enumerate(scored_posts, 1):
            try:
                debug_log(f"Processing post {post_index}/{len(scored_posts)} (score: {score})", "PROCESS")
                post_id, id_method = compute_post_id(post)
                debug_log(f"Post ID: {post_id} (Method: {id_method}, Score: {score})", "DATA")
                
                posts_processed += 1
                processed_log.append(post_id)
                debug_log(f"Added post {post_id} to processed log", "DATA")
                
                debug_log("Scrolling post into view", "ACTION")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post)
                time.sleep(1)
                
                debug_log("Attempting to expand post content", "ACTION")
                expand_post(driver, post)
                
                # Double-check for existing comments after expanding
                if has_already_commented(driver, post):
                    debug_log("Already commented on this post after expand, skipping", "SKIP")
                    continue
                debug_log("Generating comment", "GENERATE")
                max_retries = 3
                retry_count = 0
                custom_message = None
                
                while retry_count < max_retries:
                    custom_message = comment_generator.generate_comment(post_text, author_name)
                    debug_log(f"Generated comment (attempt {retry_count + 1}): {custom_message}", "DATA")
                    
                    if custom_message is not None:
                        break
                        
                    retry_count += 1
                    debug_log(f"Comment generation failed, attempt {retry_count} of {max_retries}", "RETRY")
                    time.sleep(2)  # Brief pause between retries
                
                if custom_message is None:
                    debug_log("No valid comment generated after all retries, skipping", "SKIP")
                    continue
                debug_log(f"Generated comment length: {len(custom_message)} characters", "DATA")
                debug_log("Attempting to post comment", "ACTION")
                debug_log(f"[COMMENT] Posting comment to post_id: {compute_post_id(post)[0]}", "COMMENT")
                try:
                    success = post_comment(driver, post, custom_message)
                except Exception as e:
                    debug_log(f"[COMMENT] Exception during comment posting: {e}", "ERROR")
                    success = False
                if success:
                    debug_log("Successfully posted comment", "COMMENT")
                    posts_commented += 1
                    # Log comment to history
                    post_id, _ = compute_post_id(post)
                    comment_history[post_id] = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "message": custom_message
                    }
                    save_comment_history(comment_history)
                else:
                    debug_log("Failed to post comment", "COMMENT")
                    save_log(processed_log)
                    save_comment_history(comment_history)
                    debug_log("Sleeping between comments", "WAIT")
                    time.sleep(3)
                    if posts_commented >= MAX_COMMENTS:
                        debug_log(f"Reached max comments limit ({MAX_COMMENTS})", "LIMIT")
                        return posts_commented, hiring_posts_found
            except Exception as e:
                debug_log(f"Error processing post: {str(e)}", "ERROR")
                debug_log(traceback.format_exc(), "ERROR")
                try:
                    take_screenshot(driver, f"error_post_{posts_processed}")
                    debug_log("Screenshot taken for error", "DEBUG")
                except Exception:
                    debug_log("Failed to take error screenshot", "ERROR")
                continue
        debug_log("Saving final logs", "DATA")
        save_log(processed_log)
        save_comment_history(comment_history)
        debug_log(f"Processed {posts_processed} posts, commented on {posts_commented}", "SUMMARY")
        return posts_processed, hiring_posts_found
    except Exception as e:
        debug_log(f"Error in process_posts: {str(e)}", "ERROR")
        debug_log(traceback.format_exc(), "ERROR")
        return 0, 0  # Return tuple of zeros on error

def verify_active_login(driver):
    """Automatically verify and perform LinkedIn login without manual intervention."""
    debug_log("Verifying LinkedIn login status...", "LOGIN")
    print("[APP_OUT]Verifying LinkedIn login status...")
    
    try:
        # Go to LinkedIn homepage
        driver.get("https://www.linkedin.com/")
        time.sleep(3)

        # Check if we're already logged in
        logged_in_indicators = [
            (By.CLASS_NAME, "global-nav__me-photo"),
            (By.CLASS_NAME, "feed-identity-module"),
            (By.CLASS_NAME, "share-box-feed-entry__trigger"),
            (By.CLASS_NAME, "global-nav__content"),
            (By.CSS_SELECTOR, "[data-control-name='nav.settings_signout']")
        ]

        for by, value in logged_in_indicators:
            try:
                element = driver.find_element(by, value)
                if element.is_displayed():
                    debug_log(f"Already logged in - found indicator: {value}", "LOGIN")
                    return True
            except Exception:
                continue

        # Check if we're on the feed page (another login indicator)
        if "feed" in driver.current_url.lower() and "login" not in driver.current_url.lower():
            debug_log("Already on feed page - assuming logged in", "LOGIN")
            return True

        # If not logged in, attempt automatic login
        debug_log("Not logged in - attempting automatic login", "LOGIN")
        
        if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
            debug_log("ERROR: LinkedIn credentials not found in config", "ERROR")
            debug_log("Please ensure linkedin_credentials.email and linkedin_credentials.password are set in config.json", "ERROR")
            return False

        # Navigate to login page if not already there
        if "login" not in driver.current_url.lower():
            debug_log("Navigating to LinkedIn login page", "LOGIN")
            driver.get("https://www.linkedin.com/login")
            time.sleep(3)

        # Perform automatic login
        max_login_attempts = 3
        for attempt in range(max_login_attempts):
            debug_log(f"Login attempt {attempt + 1}/{max_login_attempts}", "LOGIN")
            
            try:
                # Find and fill username field
                username_field = None
                username_selectors = ["#username", "input[name='session_key']", "input[type='email']"]
                
                for selector in username_selectors:
                    try:
                        username_field = driver.find_element(By.CSS_SELECTOR, selector)
                        if username_field.is_displayed():
                            break
                    except Exception:
                        continue
                
                if not username_field:
                    debug_log("Could not find username field", "ERROR")
                    continue

                # Find and fill password field
                password_field = None
                password_selectors = ["#password", "input[name='session_password']", "input[type='password']"]
                
                for selector in password_selectors:
                    try:
                        password_field = driver.find_element(By.CSS_SELECTOR, selector)
                        if password_field.is_displayed():
                            break
                    except Exception:
                        continue
                
                if not password_field:
                    debug_log("Could not find password field", "ERROR")
                    continue

                # Clear and fill credentials
                username_field.clear()
                password_field.clear()
                
                # Type credentials with human-like delays
                for char in LINKEDIN_EMAIL:
                    username_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))
                
                time.sleep(random.uniform(0.5, 1.0))
                
                for char in LINKEDIN_PASSWORD:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))

                time.sleep(random.uniform(1.0, 2.0))

                # Find and click submit button
                submit_button = None
                submit_selectors = [
                    "button[type='submit']",
                    "input[type='submit']",
                    ".login__form_action_container button",
                    "button[data-litms-control-urn]"
                ]
                
                for selector in submit_selectors:
                    try:
                        submit_button = driver.find_element(By.CSS_SELECTOR, selector)
                        if submit_button.is_displayed() and submit_button.is_enabled():
                            break
                    except Exception:
                        continue
                
                if not submit_button:
                    debug_log("Could not find submit button", "ERROR")
                    continue

                # Click submit button
                submit_button.click()
                debug_log("Submitted login form", "LOGIN")
                
                # Wait for login to process
                time.sleep(5)
                
                # Check for successful login
                current_url = driver.current_url.lower()
                
                # Check if we're redirected to feed or home
                if any(indicator in current_url for indicator in ["feed", "home"]) and "login" not in current_url:
                    debug_log("Login successful - redirected to main page", "LOGIN")
                    print("[APP_OUT]LinkedIn login successful!")
                    return True
                
                # Check for login indicators again
                for by, value in logged_in_indicators:
                    try:
                        element = driver.find_element(by, value)
                        if element.is_displayed():
                            debug_log(f"Login successful - found indicator: {value}", "LOGIN")
                            return True
                    except Exception:
                        continue
                
                # Check for security challenge or verification
                if any(keyword in driver.page_source.lower() for keyword in ["challenge", "verification", "security", "captcha"]):
                    debug_log("Security challenge detected - may require manual intervention", "WARNING")
                    time.sleep(10)  # Wait longer for potential manual intervention
                    
                    # Check again after waiting
                    for by, value in logged_in_indicators:
                        try:
                            element = driver.find_element(by, value)
                            if element.is_displayed():
                                debug_log("Login successful after security challenge", "LOGIN")
                                return True
                        except Exception:
                            continue
                
                # Check for error messages
                error_indicators = [
                    "error",
                    "incorrect",
                    "invalid",
                    "try again"
                ]
                
                page_text = driver.page_source.lower()
                if any(error in page_text for error in error_indicators):
                    debug_log("Login error detected - credentials may be incorrect", "ERROR")
                    break
                
                debug_log(f"Login attempt {attempt + 1} did not succeed, retrying...", "LOGIN")
                time.sleep(3)
                
            except Exception as e:
                debug_log(f"Error during login attempt {attempt + 1}: {e}", "ERROR")
                time.sleep(3)
                continue
        
        debug_log("All automatic login attempts failed", "ERROR")
        return False
        
    except Exception as e:
        debug_log(f"Error in verify_active_login: {e}", "ERROR")
        return False

def scroll_page(driver):
    """Scroll down the page incrementally to load more content with human-like behavior."""
    debug_log("Scrolling page...", "SCROLL")
    try:
        # Get current position
        old_position = driver.execute_script("return window.pageYOffset;")
        # Scroll by a random amount
        scroll_amount = random.randint(600, 1000)
        driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        time.sleep(random.uniform(1.0, 2.0))
        # Get new position
        new_position = driver.execute_script("return window.pageYOffset;")
        debug_log(f"Scrolled from {old_position} to {new_position} ({new_position - old_position} pixels)", "SCROLL")
        return new_position > old_position
    except Exception as e:
        debug_log(f"Error scrolling page: {e}", "SCROLL")
        return False

def expand_post(driver, post):
    """Expand the post by clicking 'see more' if present, using robust multi-selector logic."""
    debug_log("[expand_post] Attempting to expand post...", "EXPAND")
    try:
        pre_text = post.text or ""
        debug_log(f"[expand_post] Pre-expand text length: {len(pre_text)}", "EXPAND")
        see_more_selectors = [
            # XPath selectors only (no CSS :contains)
            ".//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'see more')]",
            ".//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'see more')]",
            ".//div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'see more')]",
            ".//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'see more')]"
        ]
        found = False
        for selector in see_more_selectors:
            try:
                elements = post.find_elements(By.XPATH, selector)
                for btn in elements:
                    if btn.is_displayed():
                        debug_log(f"[expand_post] Found 'see more' using {selector}", "EXPAND")
                        safe_click(driver, btn)
                        time.sleep(1)
                        found = True
                        break
                if found:
                    break
            except Exception as e:
                debug_log(f"[expand_post] Error with selector {selector}: {e}", "EXPAND")
                continue
        if not found:
            debug_log("[expand_post] Trying JavaScript fallback for 'see more'", "EXPAND")
            try:
                driver.execute_script('''
                    var post = arguments[0];
                    var buttons = post.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.toLowerCase().includes('see more')) {
                            buttons[i].click();
                            return true;
                        }
                    }
                    return false;
                ''', post)
                time.sleep(1)
                found = True
            except Exception as e:
                debug_log(f"[expand_post] JS fallback failed: {e}", "EXPAND")
        post_text_after = post.text or ""
        debug_log(f"[expand_post] Post text after expand: {len(post_text_after)}", "EXPAND")
        if found or len(post_text_after) > len(pre_text):
            debug_log("[expand_post] Expansion attempted or not needed.", "EXPAND")
            return True
        debug_log("[expand_post] No 'see more' found or expansion failed.", "EXPAND")
        return False
    except Exception as e:
        debug_log(f"[expand_post] Error expanding post: {e}", "EXPAND")
        return False

def get_post_text(driver, post):
    """Extract the text content of a post with multiple fallback methods (from Local_Test.py)."""
    debug_log("Extracting post text...", "TEXT")
    try:
        # Try direct text extraction first
        text = post.text
        if text and len(text) > 50:  # Reasonable post length
            debug_log(f"Got post text (direct): {len(text)} chars", "TEXT")
            return text
        # Try specific content elements
        selectors = [
            ".//div[contains(@class, 'feed-shared-update-v2__description')]",
            ".//span[contains(@class, 'break-words')]",
            ".//div[contains(@class, 'feed-shared-text')]",
            ".//div[contains(@class, 'update-components-text')]"
        ]
        for selector in selectors:
            try:
                element = post.find_element(By.XPATH, selector)
                if element:
                    content = element.text
                    if content and len(content) > 0:
                        debug_log(f"Got post text ({selector}): {len(content)} chars", "TEXT")
                        return content
            except Exception:
                continue
        # JavaScript fallback
        js_text = driver.execute_script('''
            var extractText = function(element) {
                var text = '';
                if (element.childNodes) {
                    for (var i = 0; i < element.childNodes.length; i++) {
                        var child = element.childNodes[i];
                        if (child.nodeType === 3) {  // Text node
                            text += child.textContent;
                        } else if (child.nodeType === 1) {  // Element node
                            text += extractText(child);
                        }
                    }
                }
                return text;
            };
            return extractText(arguments[0]);
        ''', post)
        if js_text and len(js_text) > 0:
            debug_log(f"Got post text (JS): {len(js_text)} chars", "TEXT")
            return js_text
        debug_log("Could not extract meaningful text from post", "TEXT")
        return ""
    except Exception as e:
        debug_log(f"Error getting post text: {e}", "TEXT")
        return ""

def post_comment(driver, post, message):
    """Post a comment on a post with extremely granular debug logging and robust error handling."""
    debug_log("[post_comment] Starting comment posting process...", "COMMENT")
    take_screenshot(driver, "before_comment")
    try:
        # Step 1: Find and click the comment button
        comment_button = None
        comment_button_selectors = [
            ".//button[contains(@aria-label, 'comment')]",
            ".//span[normalize-space(text())='Comment']/parent::button",
            ".//li[contains(@class, 'comment')]/button",
            ".//button[contains(@class, 'comment-button')]",
            ".//button[contains(@class, 'comments-comment-box__submit-button')]",
            ".//span[contains(text(), 'Comment')]/ancestor::button"
        ]
        for selector in comment_button_selectors:
            try:
                buttons = post.find_elements(By.XPATH, selector)
                for btn in buttons:
                    if btn.is_displayed():
                        debug_log(f"[post_comment] Found comment button using {selector}", "COMMENT")
                        comment_button = btn
                        break
                if comment_button:
                    break
            except Exception as e:
                debug_log(f"[post_comment] Error with selector {selector}: {e}", "COMMENT")
                continue
        if not comment_button:
            # Try JavaScript approach
            debug_log("[post_comment] Using JavaScript to find comment button", "COMMENT")
            try:
                driver.execute_script('''
                    var post = arguments[0];
                    var buttons = post.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.toLowerCase().includes('comment') || 
                            (buttons[i].getAttribute('aria-label') && 
                             buttons[i].getAttribute('aria-label').toLowerCase().includes('comment'))) {
                            buttons[i].click();
                            return true;
                        }
                    }
                    return false;
                ''', post)
                time.sleep(2)
            except Exception as e:
                debug_log(f"[post_comment] JS click for comment button failed: {e}", "COMMENT")
                take_screenshot(driver, "comment_button_not_found")
                return False
        else:
            # Click the comment button
            try:
                comment_button.click()
                time.sleep(2)
            except Exception as e:
                debug_log(f"[post_comment] Failed to click comment button: {e}", "COMMENT")
                take_screenshot(driver, "comment_button_click_failed")
                return False
        take_screenshot(driver, "after_click_comment_button")
        # Step 2: Find the comment input field
        comment_input = None
        input_selectors = [
            ".//textarea[contains(@placeholder, 'Add a comment')]",
            ".//div[@contenteditable='true']",
            ".//div[@role='textbox']"
        ]
        for selector in input_selectors:
            try:
                inputs = post.find_elements(By.XPATH, selector)
                for inp in inputs:
                    if inp.is_displayed():
                        debug_log(f"[post_comment] Found comment input using {selector}", "COMMENT")
                        comment_input = inp
                        break
                if comment_input:
                    break
            except Exception as e:
                debug_log(f"[post_comment] Error with input selector {selector}: {e}", "COMMENT")
                continue
        if not comment_input:
            # Try to find by generic selectors
            try:
                inputs = driver.find_elements(By.TAG_NAME, "textarea")
                for inp in inputs:
                    if inp.is_displayed() and "comment" in inp.get_attribute("placeholder").lower():
                        comment_input = inp
                        debug_log("[post_comment] Found comment input by tag name", "COMMENT")
                        break
            except Exception as e:
                debug_log(f"[post_comment] Error with tag name textarea: {e}", "COMMENT")
        if not comment_input:
            debug_log("[post_comment] Could not find comment input field", "COMMENT")
            take_screenshot(driver, "comment_input_not_found")
            return False
        # Step 3: Enter the comment text
        debug_log(f"[post_comment] Entering comment text: {message[:50]}... (length: {len(message)})", "COMMENT")
        try:
            # Click to ensure focus
            comment_input.click()
            time.sleep(0.5)
            # Clear any existing text
            try:
                comment_input.clear()
            except Exception:
                pass
            # Enter text character by character for reliability
            for chunk in [message[i:i+50] for i in range(0, len(message), 50)]:
                comment_input.send_keys(chunk)
                time.sleep(0.2)
            time.sleep(1)
            # Verify text entry
            actual_text = comment_input.get_attribute("value") or comment_input.text
            debug_log(f"[post_comment] Text verification - actual content: {actual_text[:50]}... (length: {len(actual_text) if actual_text else 0})", "COMMENT")
            if not actual_text or len(actual_text) < 10:
                debug_log("[post_comment] Text entry verification failed, trying send_keys method", "COMMENT")
                comment_input.clear()
                time.sleep(0.5)
                comment_input.send_keys(message)
            time.sleep(1)
        except Exception as e:
            debug_log(f"[post_comment] Error entering comment text: {e}", "COMMENT")
            take_screenshot(driver, "comment_text_error")
            return False
        take_screenshot(driver, "after_entering_comment")
        # Step 4: Submit the comment
        debug_log("[post_comment] Looking for submit button", "COMMENT")
        submit_button = None
        submit_button_selectors = [
            ".//button[normalize-space(text())='Post']",
            ".//button[normalize-space(text())='Comment']",
            ".//button[contains(@class, 'comments-comment-box__submit-button')]",
            ".//footer//button[not(@disabled)]",
            ".//form//button[not(@disabled)]"
        ]
        for selector in submit_button_selectors:
            try:
                buttons = driver.find_elements(By.XPATH, selector)
                for btn in buttons:
                    if btn.is_displayed():
                        debug_log(f"[post_comment] Found submit button using {selector}", "COMMENT")
                        submit_button = btn
                        break
                if submit_button:
                    break
            except Exception as e:
                debug_log(f"[post_comment] Error with submit selector {selector}: {e}", "COMMENT")
                continue
        if not submit_button:
            debug_log("[post_comment] Could not find submit button", "COMMENT")
            take_screenshot(driver, "submit_button_not_found")
            return False
        # Try to click the submit button
        try:
            submit_button.click()
            debug_log("[post_comment] Clicked submit button", "COMMENT")
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            debug_log(f"[post_comment] Failed to click submit button: {e}", "COMMENT")
            take_screenshot(driver, "submit_button_click_failed")
            return False
        take_screenshot(driver, "after_submit_attempt")
        # Step 5: Verify the comment was posted by checking if input field is cleared/gone
        time.sleep(3)
        try:
            if comment_input.is_displayed():
                current_value = comment_input.get_attribute("value") or comment_input.text
                if current_value and message in current_value:
                    debug_log("[post_comment] Comment still in input field - submission failed", "COMMENT")
                    take_screenshot(driver, "comment_still_in_input")
                    return False
        except Exception as e:
            debug_log(f"[post_comment] Error verifying comment submission: {e}", "COMMENT")
        # Final check - search for our comment in the post
        time.sleep(2)
        if has_already_commented(driver, post):
            # SUCCESS! Log this prominently for the desktop app
            debug_log("✅ COMMENT POSTED SUCCESSFULLY! Comment has been verified in the post.", "COMMENT")
            debug_log(f"📝 Comment content (first 100 chars): {message[:100]}{'...' if len(message) > 100 else ''}", "COMMENT")
            return True
        debug_log("✅ COMMENT POSTED! Could not verify but submission appears successful.", "COMMENT")
        debug_log(f"📝 Comment content (first 100 chars): {message[:100]}{'...' if len(message) > 100 else ''}", "COMMENT")
        return True
    except Exception as e:
        debug_log(f"[post_comment] Error posting comment: {e}", "COMMENT")
        debug_log(traceback.format_exc(), "COMMENT")
        take_screenshot(driver, "comment_error")
        return False

def take_screenshot(driver, filename):
    """Take a screenshot for debugging purposes."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"debug_screenshots/{timestamp}_{filename}.png"
        os.makedirs("debug_screenshots", exist_ok=True)
        driver.save_screenshot(screenshot_path)
        debug_log(f"Screenshot saved to {screenshot_path}", "DEBUG")
    except Exception as e:
        debug_log(f"Failed to take screenshot: {e}", "DEBUG")

# Functions that were missing but needed
def safe_click(driver, element):
    """Safely click an element with fallback methods."""
    try:
        element.click()
        return True
    except Exception as e:
        debug_log(f"Regular click failed: {e}", "DEBUG")
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e2:
            debug_log(f"JS click also failed: {e2}", "DEBUG")
            return False

def clear_recent_logs(hours=3):
    """Clear recent entries from logs."""
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Clear comment log
        log = load_log()
        original_count = len(log)
        filtered_log = []
        
        for entry in log:
            if isinstance(entry, dict) and 'timestamp' in entry:
                try:
                    entry_time = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
                    if entry_time < cutoff_time:
                        filtered_log.append(entry)
                except (ValueError, TypeError):
                    filtered_log.append(entry)
            else:
                filtered_log.append(entry)
        
        save_log(filtered_log)
        return original_count - len(filtered_log)
    except Exception as e:
        debug_log(f"Error clearing logs: {e}")
        return 0

def sleep_until_midnight_edt():
    """Sleep until midnight in EDT timezone."""
    try:
        import pytz
        edt = pytz.timezone('US/Eastern')
        now = datetime.now(edt)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        sleep_seconds = (midnight - now).total_seconds()
        debug_log(f"Sleeping until midnight EDT ({sleep_seconds:.0f} seconds)", "SLEEP")
        time.sleep(sleep_seconds)
    except Exception as e:
        debug_log(f"Error calculating sleep time: {e}")
        time.sleep(3600)  # Fallback: sleep 1 hour

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript interrupted by user. Cleaning up...")
        if 'driver' in locals():
            driver.quit()
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
        print(traceback.format_exc())
        if 'driver' in locals():
            driver.quit()
    finally:
        print("\nScript execution completed") 