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
            
            # Initialize comment counters
            session_comments = 0
            daily_comments = 0
            
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
                            posts_processed, hiring_posts_found = process_posts(driver)
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

def get_search_urls_for_keywords(keywords):
    """
    Generate search URLs for given keywords using 'hiring' with 24h and past_week filters.
    All 24h URLs are returned first, then all past_week URLs.
    Args:
        keywords (str or list): Search keywords or list of keywords
    Returns:
        list: List of search URLs (24h first, then past_week, all 'hiring' only)
    """
    urls_24h = []
    urls_past_week = []
    if isinstance(keywords, str):
        keywords = [keywords]
    for keyword in keywords:
        urls_24h.append(
            construct_linkedin_search_url(f"{keyword} hiring", "past_24h")
        )
        urls_past_week.append(
            construct_linkedin_search_url(f"{keyword} hiring", "past_week")
        )
    return urls_24h + urls_past_week

# ... (rest of the code remains the same)

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
                if score <= 55:
                    debug_log(f"Skipping post {post_index} (score: {score} <= 55)", "SKIP")
                    continue
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
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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