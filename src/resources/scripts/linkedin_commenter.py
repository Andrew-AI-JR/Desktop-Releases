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
import requests
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
    # Try to load backend URL from .env file if not in config
    if not config.get('backend_url'):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            backend_url = os.getenv('BACKEND_URL')
            if backend_url:
                config['backend_url'] = backend_url
        except ImportError:
            pass  # dotenv not available, continue without it
    # Backend URL is only loaded from config file
    
    # CLI overrides (highest priority)
    if args.email: # This will overwrite file/env values in linkedin_credentials
        config['linkedin_credentials']['email'] = args.email
    if args.password: # This will overwrite file/env values in linkedin_credentials
        config['linkedin_credentials']['password'] = args.password
    if args.chrome_path: # Top-level key
        config['chrome_path'] = args.chrome_path
    # Backend URL is only loaded from config file
    
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

# === POST SCORING CONFIGURATION ===
POST_SCORING_CONFIG = {
    'internal_hiring': {
        'weight': 8.0,  # HIGHEST weight - internal hiring managers are most likely to book calls
        'keywords': [
            'hiring for my team',
            'hiring for our team',
            'expanding our team',
            'scaling our team',
            'growing the team',
            'building the team',
            'leading the team',
            'my team is hiring',
            'our team is looking',
            'adding to my team',
            'building out my team',
            'expanding my organization'
            # Note: Role-specific keywords will be added dynamically
        ]
    },
    'direct_hiring': {
        'weight': 6.0,  # Very high weight - direct hiring signals from decision makers
        'keywords': [
            "i'm hiring",
            "we're hiring",
            'hiring for',
            'looking to hire',
            'actively hiring',
            'now hiring',
            'hiring now',
            'open position',
            'job opening',
            'position available',
            'role available',
            'opportunity available',
            'seeking candidates',
            'recruiting for',
            'filling a position'
        ]
    },
    'decision_maker_titles': {
        'weight': 5.0,  # High weight for titles that indicate hiring authority
        'keywords': [
            'ceo', 'cto', 'cfo', 'vp', 'vice president', 'director',
            'head of', 'chief', 'founder', 'co-founder', 'president',
            'hiring manager', 'engineering manager', 'product manager',
            'data science manager', 'ai director', 'ml director',
            'lead', 'principal', 'senior director'
        ]
    },
    'company_tier': {
        'weight': 4.0,  # High weight for quality companies
        'keywords': [
            'faang', 'meta', 'facebook', 'apple', 'amazon', 'netflix', 'google', 'microsoft',
            'fortune 500', 'fortune 100', 'series a', 'series b', 'series c', 'unicorn',
            'nasdaq', 'nyse', 'public company', 'industry leader', 'market leader',
            'well-funded', 'venture backed', 'enterprise', 'saas'
        ]
    },
    'tech_relevance': {
        'weight': 3.0,  # Important for matching your skills
        'keywords': [
            'python', 'machine learning', 'data science', 'ai', 'artificial intelligence',
            'deep learning', 'nlp', 'natural language processing', 'computer vision',
            'neural networks', 'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy',
            'data analysis', 'data engineering', 'data pipeline', 'etl', 'sql', 'database',
            'cloud', 'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'microservices',
            'rest api', 'api development', 'full stack', 'backend', 'frontend',
            'web development', 'software engineering', 'devops', 'ci/cd', 'git',
            'generative ai', 'llm', 'chatgpt', 'openai'
        ]
    },
    'urgency_indicators': {
        'weight': 4.0,  # High weight for urgent hiring needs
        'keywords': [
            'urgent', 'asap', 'immediately', 'right away', 'looking immediately',
            'need someone fast', 'start immediately', 'urgent need',
            'critical hire', 'key hire', 'must fill', 'priority hire'
        ]
    },
    'work_mode': {
        'weight': 2.0,  # Medium weight for work flexibility
        'keywords': [
            'remote', 'remote-first', 'remote friendly', 'work from home', 'wfh',
            'hybrid', 'flexible location', 'flexible work', 'anywhere in us',
            'us-based remote', 'fully remote', 'distributed team'
        ]
    },
    'external_recruiter': {
        'weight': 1.0,  # LOWEST weight - external recruiters less likely to lead to direct hires
        'keywords': [
            'recruitment consultant', 'talent acquisition specialist', 'technical recruiter',
            'staffing specialist', 'recruiting agency', 'talent partner',
            'sourcing specialist', 'recruiting firm', 'placement agency',
            'contract recruiter', 'third party recruiter'
        ]
    },
    'post_details': {
        'weight': 1.5,  # Low weight for post quality indicators
        'keywords': [
            'requirements:', 'qualifications:', 'experience:',
            'skills:', 'responsibilities:', 'salary:', 'location:',
            'stack:', 'technologies:', 'benefits:', 'compensation:'
        ]
    }
}

class SearchPerformanceTracker:
    """Tracks and optimizes search URL performance."""
    def __init__(self):
        self.url_stats = {}  # Store performance metrics for each URL
        self.hourly_stats = {}  # Store hourly performance data
        
    def record_url_performance(self, url, success=True, comments_made=0, error=False):
        """Record the performance of a URL search."""
        if url not in self.url_stats:
            self.url_stats[url] = {
                'total_attempts': 0,
                'successful_attempts': 0,
                'total_comments': 0,
                'errors': 0,
                'last_attempt': None
            }
            
        stats = self.url_stats[url]
        stats['total_attempts'] += 1
        if success:
            stats['successful_attempts'] += 1
            stats['total_comments'] += comments_made
        if error:
            stats['errors'] += 1
        stats['last_attempt'] = datetime.now()
        
        # Record hourly stats
        current_hour = datetime.now().hour
        if current_hour not in self.hourly_stats:
            self.hourly_stats[current_hour] = {}
        if url not in self.hourly_stats[current_hour]:
            self.hourly_stats[current_hour][url] = {
                'attempts': 0,
                'comments': 0
            }
        self.hourly_stats[current_hour][url]['attempts'] += 1
        self.hourly_stats[current_hour][url]['comments'] += comments_made
        
    def optimize_search_urls(self, urls, current_hour):
        """Optimize the order of search URLs based on performance."""
        if not urls:
            return []
            
        # Score each URL based on its performance
        scored_urls = []
        for url in urls:
            if not url:  # Skip None or empty URLs
                continue
                
            score = 0
            if url in self.url_stats:
                stats = self.url_stats[url]
                # Calculate success rate
                if stats['total_attempts'] > 0:
                    success_rate = stats['successful_attempts'] / stats['total_attempts']
                    score += success_rate * 10
                    
                # Consider comment yield
                if stats['total_attempts'] > 0:
                    comment_yield = stats['total_comments'] / stats['total_attempts']
                    score += comment_yield * 5
                    
                # Penalize recent errors
                if stats['errors'] > 0:
                    score -= stats['errors'] * 2
                    
            # Consider hourly performance
            if current_hour in self.hourly_stats and url in self.hourly_stats[current_hour]:
                hour_stats = self.hourly_stats[current_hour][url]
                if hour_stats['attempts'] > 0:
                    hour_score = hour_stats['comments'] / hour_stats['attempts']
                    score += hour_score * 3
                    
            scored_urls.append((url, score))
            
        # Sort URLs by score (highest first)
        scored_urls.sort(key=lambda x: x[1], reverse=True)
        return [url for url, _ in scored_urls]

class CommentGenerator:
    """
    Generates comments for LinkedIn posts using a backend API.
    """
    def __init__(self, user_bio, config=None, job_keywords=None):
        self.user_bio = user_bio
        self.config = config or {}
        # First try to get from config, then from environment, then use default
        self.backend_url = self.config.get('backend_url') or os.getenv('BACKEND_URL') or 'http://localhost:3000/api/comments/generate'
        
        # Update tech_relevance keywords with job_keywords if provided
        if job_keywords and isinstance(job_keywords, list) and len(job_keywords) > 0:
            # Convert job_keywords to lowercase for case-insensitive matching
            tech_keywords = [keyword.lower() for keyword in job_keywords]
            # Update the tech_relevance section in the config
            if 'tech_relevance' in self.config:
                self.config['tech_relevance']['keywords'] = tech_keywords
            else:
                self.config['tech_relevance'] = {
                    'weight': 3.0,
                    'keywords': tech_keywords
                }

    def debug_log(self, message, level="INFO"):
        if 'debug_log' in globals():
            debug_log(message, level)
        else:
            print(f"[{level}] {message}")

    def clean_post_text(self, post_text):
        # Simple cleaning: strip, remove extra spaces, etc. (customize as needed)
        return ' '.join(post_text.strip().split())

    def classify_post(self, post_text):
        # ... existing code ...
        return super().classify_post(post_text)

    def generate_comment(self, post_text, post_url=None):
        if not post_text or len(post_text) < 10:
            return None
            
        try:
            # Prepare the request payload according to the expected API format
            payload = {
                'post_text': post_text,
                'source_linkedin_url': post_url or '',
                'comment_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            }
            
            self.debug_log(f"Sending request to comment API: {json.dumps(payload, indent=2)}", "DEBUG")
            
            # Make the API request
            response = requests.post(
                self.backend_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            # Get Calendly link from config with fallback
            calendly_link = self.config.get('calendly_link', '')
            
            # Check if the request was successful
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict) and 'comment' in data:
                        comment = data['comment']
                        # Append Calendly link if available and not already in comment
                        if calendly_link and calendly_link not in comment:
                            comment = f"{comment}\n\nIf you'd like to discuss this further, feel free to book a call with me: {calendly_link}"
                        return comment
                    elif isinstance(data, str):
                        # Handle case where the API directly returns the comment string
                        comment = data
                        if calendly_link and calendly_link not in comment:
                            comment = f"{comment}\n\nIf you'd like to discuss this further, feel free to book a call with me: {calendly_link}"
                        return comment
                except ValueError:
                    # If response is not JSON, return it as is with Calendly link
                    comment = response.text
                    if calendly_link and calendly_link not in comment:
                        comment = f"{comment}\n\nIf you'd like to discuss this further, feel free to book a call with me: {calendly_link}"
                    return comment
            
            # Log error if API call failed
            self.debug_log(
                f"Failed to generate comment. Status: {response.status_code}, Response: {response.text}",
                "ERROR"
            )
            
        except requests.exceptions.RequestException as e:
            self.debug_log(f"Network error while generating comment: {str(e)}", "ERROR")
        except Exception as e:
            self.debug_log(f"Unexpected error generating comment: {str(e)}", "ERROR")
        
        # Fallback to simple comment if API call fails, with Calendly link if available
        fallback_comment = f"Great post! As someone with experience in {self.user_bio[:50]}..., I found your insights valuable."
        calendly_link = self.config.get('calendly_link', '')
        if calendly_link and calendly_link not in fallback_comment:
            fallback_comment = f"{fallback_comment}\n\nIf you'd like to discuss this further, feel free to book a call with me: {calendly_link}"
        return fallback_comment

    def calculate_post_score(self, post_text, author_name=None, time_filter=None):
        if not post_text:
            return 0
            
        post_text_lower = post_text.lower()
        total_score = 0
        score_breakdown = {}
        
        # Apply time-based scoring based on the URL's time filter
        time_multiplier = get_time_based_score(time_filter) if time_filter else 1.0
        if time_filter:
            score_breakdown['time_relevance'] = {
                'time_filter': time_filter,
                'multiplier': time_multiplier,
                'score': 0  # Will be calculated in the multiplier
            }
        
        # Calculate base score from all categories
        for category, config in self.config.items():
            if config.get('time_based', False):
                # Skip time-based categories as they're handled separately
                continue
                
            weight = config['weight']
            keywords = config.get('keywords', [])
            matches = sum(1 for kw in keywords if kw.lower() in post_text_lower)
            
            if matches > 0:
                category_score = weight * matches
                total_score += category_score
                score_breakdown[category] = {
                    'matches': matches,
                    'score': category_score,
                    'weight': weight
                }
        
        # Add length bonus
        words = len(post_text.split())
        length_bonus = 5 if words >= 50 else 0
        total_score += length_bonus
        score_breakdown['length'] = {'words': words, 'score': length_bonus}
        
        # Apply time multiplier to the total score
        final_score = total_score * time_multiplier
        
        # Update time_relevance score in breakdown to show its impact
        if 'time_relevance' in score_breakdown:
            score_breakdown['time_relevance']['score'] = final_score - total_score
            
        score_breakdown['final_score'] = {
            'base_score': total_score,
            'time_multiplier': time_multiplier,
            'final_score': final_score
        }
        
        self.debug_log(f"Post scoring breakdown: {json.dumps(score_breakdown, indent=2, default=str)}", "SCORE")
        return final_score

def get_time_based_score(time_filter):
    """
    Calculate a score multiplier based on the time filter used in the URL.
    
    Args:
        time_filter (str): The time filter from the URL ('past-24h', 'past-week', 'past-month')
    
    Returns:
        float: Score multiplier based on recency
    """
    time_weights = {
        'past-24h': 2.0,    # Highest weight for most recent posts
        'past-week': 1.5,   # Medium weight for recent posts
        'past-month': 1.0   # Base weight for older posts
    }
    return time_weights.get(time_filter, 1.0)  # Default to 1.0 if unknown filter

def main():
    """Main execution function that continuously cycles through URLs while respecting limits."""
    global MAX_DAILY_COMMENTS, MAX_SESSION_COMMENTS, SCROLL_PAUSE_TIME, JOB_SEARCH_KEYWORDS
    global LINKEDIN_EMAIL, LINKEDIN_PASSWORD, DEBUG_MODE, SEARCH_URLS, CALENDLY_LINK, USER_BIO
    # ... rest of the code remains the same ...
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
            
            # Initialize comment generator with job keywords
            try:
                debug_log("[INIT] Initializing comment generator", "DEBUG")
                comment_generator = CommentGenerator(
                    user_bio=USER_BIO,
                    job_keywords=JOB_SEARCH_KEYWORDS
                )
                debug_log("[INIT] Comment generator initialized with job keywords", "DEBUG")
            except Exception as gen_error:
                debug_log(f"[ERROR] Failed to initialize comment generator: {gen_error}", "ERROR")
                raise
            
            # Initialize browser driver
            try:
                debug_log("[INIT] Initializing browser driver", "DEBUG")
                driver = setup_chrome_driver()
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
                    
            if not login_successful:
                debug_log("Login verification failed, retrying...", "ERROR")
                continue
                        
            debug_log("Login verified successfully", "LOGIN")
            print("[APP_OUT]Login successful, proceeding to search results...")

            # Get active URLs from the tracker
            current_hour = datetime.now().hour
            active_urls = search_tracker.optimize_search_urls(SEARCH_URLS, current_hour)
                    
            if not active_urls:
                debug_log("No active URLs to process, using default search URLs", "WARNING")
                active_urls = SEARCH_URLS
                        
            debug_log(f"Active URLs to process: {active_urls}", "DEBUG")
            print(f"[APP_OUT]Processing {len(active_urls)} search URLs...")

            # Process each URL
            for url in active_urls:
                debug_log(f"Navigating to search URL: {url}", "NAVIGATION")
                print(f"[APP_OUT]Navigating to: {url}")
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

def get_search_urls_for_keywords(keywords):
    """Generate search URLs from keywords."""
    if not keywords:
        return []
        
    # Convert keywords to proper format
    if isinstance(keywords, list):
        # Use the first keyword for the main search
        keyword_query = keywords[0]
    else:
        keyword_query = keywords
        
    # Generate URLs for different time filters
    urls = []
    time_filters = ["past-24h", "past-month"]
    for time_filter in time_filters:
        # Add hiring-focused URL
        hiring_url = construct_linkedin_search_url(
            f"{keyword_query} hiring",
            time_filter
        )
        if hiring_url:
            urls.append(hiring_url)
            
        # Add recruiting-focused URL
        recruiting_url = construct_linkedin_search_url(
            f"{keyword_query} recruiting",
            time_filter
        )
        if recruiting_url:
            urls.append(recruiting_url)
            
    return urls

def construct_linkedin_search_url(keywords, time_filter="past_month"):
    """
    Construct a LinkedIn search URL for posts with proper date filtering.
    
    Args:
        keywords (str): Search keywords
        time_filter (str): One of "past-24h", "past-week", "past-month", "past-year"
    
    Returns:
        str: Constructed LinkedIn search URL
    """
    try:
        # Encode keywords for URL
        encoded_keywords = urllib.parse.quote(keywords)
        
        # Construct the base URL
        base_url = "https://www.linkedin.com/search/results/content/"
        
        # Add query parameters
        params = {
            'keywords': encoded_keywords,
            'origin': 'FACETED_SEARCH',
            'sid': 'tnP',
            'datePosted': f'"{time_filter}"'
        }
        
        # Build the URL with parameters
        query_string = '&'.join(f"{k}={v}" for k, v in params.items())
        return f"{base_url}?{query_string}"
    except Exception as e:
        debug_log(f"Error constructing search URL: {e}", "ERROR")
        return None

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
        
        # Get current URL and extract time filter
        current_url = driver.current_url
        time_filter = None
        if 'datePosted=' in current_url:
            try:
                time_filter = current_url.split('datePosted=')[1].split('&')[0].strip('"\'')
                debug_log(f"Extracted time filter from URL: {time_filter}", "DEBUG")
            except Exception as e:
                debug_log(f"Error extracting time filter from URL: {e}", "WARNING")
        
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
                    
                score = comment_generator.calculate_post_score(post_text, author_name, time_filter)
                debug_log(f"Scored post with time filter '{time_filter}': {score}", "DEBUG")
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
                    '80+': len([s for s in scores if s >= 80]),
                    '70-79': len([s for s in scores if 70 <= s < 80]),
                    '60-69': len([s for s in scores if 60 <= s < 70]),
                    '50-59': len([s for s in scores if 50 <= s < 60]),
                    '40-49': len([s for s in scores if 40 <= s < 50]),
                    '30-39': len([s for s in scores if 30 <= s < 40]),
                    '20-29': len([s for s in scores if 20 <= s < 30]),
                    '0-19': len([s for s in scores if s < 20])
                }
            }
            debug_log(f"Scoring distribution: {json.dumps(score_stats, indent=2)}", "STATS")
            
        debug_log(f"Found {len(scored_posts)} new posts to process, sorted by score", "SEARCH")
        for post_index, (score, post, post_text, author_name) in enumerate(scored_posts, 1):
            try:
                if score < 50:  # Changed from 55 to 50 as per new threshold
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

def verify_active_login(driver, max_attempts=3):
    """
    Automatically verify and perform LinkedIn login without manual intervention.
    Args:
        driver: Selenium WebDriver instance
        max_attempts: Maximum number of login attempts
    Returns:
        bool: True if login was successful, False otherwise
    """
    debug_log("Verifying LinkedIn login status...", "LOGIN")
    print("[APP_OUT]Verifying LinkedIn login status...")

    for attempt in range(1, max_attempts + 1):
        debug_log(f"Login verification attempt {attempt}/{max_attempts}", "LOGIN")
        try:
            # Go to the LinkedIn feed, a reliable page to check login status
            driver.get("https://www.linkedin.com/feed/")
            time.sleep(random.uniform(3, 5))

            # Check for an element that reliably indicates a logged-in state.
            # The global navigation search bar is a good candidate.
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "global-nav-typeahead"))
                )
                debug_log("Login confirmed: Found main navigation search bar.", "LOGIN")
                return True  # Success, exit the function
            except TimeoutException:
                debug_log("Login check failed. Could not find a key element indicating a logged-in state.", "LOGIN")
                # If it fails, it could be a page load issue or we are logged out.
                # Let the loop retry.
                if attempt < max_attempts:
                    debug_log("Retrying login verification...", "LOGIN")
                    continue
                else:
                    debug_log("Final login verification attempt failed.", "ERROR")
                    return False

        except Exception as e:
            debug_log(f"An unexpected error occurred during login verification (attempt {attempt}): {e}", "ERROR")
            if attempt < max_attempts:
                time.sleep(5)  # Wait before the next attempt
    
    debug_log("Failed to verify active login after all attempts.", "ERROR")
    return False

def has_already_commented(driver, post):
    """Check if the user has already commented on a post."""
    # ... existing code ...

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

def get_default_log_path():
    """Get a default log path that will work on any system."""
    try:
        # Try to use the user's home directory
        home_dir = os.path.expanduser("~")
        log_dir = os.path.join(home_dir, "Documents", "JuniorAI", "logs")
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, "linkedin_commenter.log")
    except Exception as e:
        # Fallback to current directory
        print(f"Warning: Could not create log directory in Documents: {e}")
        return "linkedin_commenter.log"

def load_log():
    """
    Load processed post IDs from a JSON file in the default log directory.
    Returns an empty list if the file does not exist.
    """
    try:
        log_file = os.path.join(get_default_log_path(), "processed_log.json")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        debug_log(f"Error loading processed log: {e}", level="ERROR")
    return []

def debug_log(message, level="INFO"):
    """
    Enhanced debug logging with timestamps and levels.
    Also sends logs to Electron GUI when level is INFO or higher.
    """
    # Get log level from config or use default
    log_level = CONFIG.get('log_level', 'info').upper() if CONFIG else 'INFO'
    level = level.upper()
    
    # Map of log levels to numeric values
    level_map = {
        'DEBUG': 0,
        'INFO': 1,
        'WARNING': 2,
        'ERROR': 3,
        'FATAL': 4
    }
    
    # Only log if message level is >= configured level
    if level_map.get(level, 0) < level_map.get(log_level, 1):
        return
        
    timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')
    log_message = f"{timestamp} [{level}] {message}"
    
    # Send to Electron GUI if level is INFO or higher
    if level in ['INFO', 'WARNING', 'ERROR', 'FATAL']:
        print(f"[APP_OUT]{level}: {message}", flush=True)
    
    # Get log file path from config or use default
    log_file = CONFIG.get('log_file_path') if CONFIG else None
    if not log_file:
        log_file = get_default_log_path()
    
    try:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            
        # Write to log file
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
            
        # Also print to console in debug mode
        if DEBUG_MODE or level in ['WARNING', 'ERROR', 'FATAL']:
            print(log_message)
    except Exception as e:
        print(f"Error writing to log file: {e}")
        print(log_message)  # Fallback to console

def setup_chrome_driver(max_retries=3, retry_delay=5):
    """
    Set up and return a Chrome WebDriver instance with robust error handling.
    
    Args:
        max_retries (int): Maximum number of retry attempts
        retry_delay (int): Delay between retries in seconds
        
    Returns:
        WebDriver: Configured Chrome WebDriver instance
        
    Raises:
        Exception: If all retry attempts fail
    """
    attempt = 0
    last_error = None
    
    while attempt < max_retries:
        attempt += 1
        driver = None
        try:
            debug_log(f"Setting up Chrome WebDriver (Attempt {attempt}/{max_retries})")
            
            # Initialize Chrome options
            chrome_options = Options()
            config = get_config()
            debug_mode = config.get('debug_mode', False)

            # Configure headless mode
            if not debug_mode:
                chrome_options.add_argument('--headless=new')
                chrome_options.add_argument('--disable-gpu')
                debug_log("Running Chrome in headless mode")
            else:
                debug_log("Debug mode enabled: running Chrome in headed mode")

            # Common Chrome options
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--window-size=1200,900")
            chrome_options.add_argument("--window-position=50,50")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
            
            # Disable automation flags that might trigger bot detection
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            # Try to find Chrome/Chromium binary
            chrome_path = os.getenv('CHROME_PATH') or config.get('chrome_path')
            
            # Common Chrome/Chromium paths to check
            possible_chrome_paths = [
                chrome_path,
                r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../dist/win-unpacked/resources/chrome-win/chrome.exe')),
                "/usr/bin/google-chrome",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            ]
            
            # Remove None and non-existent paths
            possible_chrome_paths = [p for p in possible_chrome_paths if p and os.path.exists(p)]
            
            if not possible_chrome_paths:
                debug_log("No Chrome/Chromium binary found. Using webdriver_manager default.", "WARNING")
                chrome_options.binary_location = None
            else:
                # Use the first valid path
                chrome_options.binary_location = possible_chrome_paths[0]
                debug_log(f"Using Chrome/Chromium at: {chrome_options.binary_location}")
            
            # Set up ChromeDriver service
            service = None
            chromedriver_path = None
            
            # If using bundled Chromium, try to use its chromedriver
            if chrome_options.binary_location and 'chrome-win' in chrome_options.binary_location.replace('\\', '/'):
                chromedriver_path = os.path.join(os.path.dirname(chrome_options.binary_location), 'chromedriver.exe')
                if os.path.exists(chromedriver_path):
                    debug_log(f"Using bundled chromedriver: {chromedriver_path}")
                    service = Service(executable_path=chromedriver_path)
            
            # Initialize WebDriver
            debug_log("Initializing Chrome WebDriver...")
            
            try:
                if service:
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                else:
                    # Use webdriver_manager to handle ChromeDriver
                    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                
                # Test Chrome is responsive
                driver.set_page_load_timeout(30)
                driver.get("about:blank")
                debug_log("Chrome WebDriver initialized successfully")
                return driver
                
            except Exception as e:
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                raise
                
        except Exception as e:
            last_error = str(e)
            debug_log(f"Chrome WebDriver initialization failed (Attempt {attempt}/{max_retries}): {last_error}", "WARNING")
            
            # Clean up any remaining Chrome processes
            try:
                if sys.platform == 'win32':
                    os.system('taskkill /f /im chrome.exe >nul 2>&1')
                    os.system('taskkill /f /im chromedriver.exe >nul 2>&1')
                else:
                    os.system('pkill -f chrome >/dev/null 2>&1')
                    os.system('pkill -f chromedriver >/dev/null 2>&1')
            except:
                pass
                
            if attempt < max_retries:
                debug_log(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                debug_log("Maximum retry attempts reached. Giving up.", "ERROR")
                raise Exception(f"Failed to initialize Chrome WebDriver after {max_retries} attempts. Last error: {last_error}")
    
    # This should never be reached due to the raise in the else clause above
    raise Exception("Failed to initialize Chrome WebDriver")

if __name__ == "__main__":
    driver = None
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript interrupted by user. Cleaning up...")
        if 'driver' in locals() and driver is not None:
            try:
                driver.quit()
            except:
                pass
    except Exception as e:
        error_msg = f"\nFatal error: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        debug_log(error_msg, "FATAL")
        if 'driver' in locals() and driver is not None:
            try:
                driver.quit()
            except:
                pass
    finally:
        # Make one final attempt to clean up any remaining Chrome processes
        try:
            if sys.platform == 'win32':
                os.system('taskkill /f /im chrome.exe >nul 2>&1')
                os.system('taskkill /f /im chromedriver.exe >nul 2>&1')
            else:
                os.system('pkill -f chrome >/dev/null 2>&1')
                os.system('pkill -f chromedriver >/dev/null 2>&1')
        except:
            pass
            
        print("\nScript execution completed") 