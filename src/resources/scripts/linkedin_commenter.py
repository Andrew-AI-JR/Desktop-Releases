import sys
import time
import random
import json
import os
import hashlib
import re
import subprocess
import traceback
import requests
import argparse
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

# === CONFIGURATION ===
DEBUG_MODE = True
SCROLL_PAUSE_TIME = random.randint(3, 15)
MAX_SCROLL_CYCLES = random.randint(6, 35)  # Random between 25-35 scroll cycles
MAX_COMMENT_WORDS = 200

# API configuration
API_BASE_URL = None  # Will be set from config
SESSION_ID = None

# === PRODUCTION SCORING SYSTEM ===
def build_scoring_config():
    """Build scoring configuration with dynamic tech relevance based on user config."""
    
    # Base scoring categories with FIXED scoring weights
    scoring_config = {
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
                'chief', 'head of', 'manager seeking', 'my team is hiring',
                'our team is hiring', 'i am hiring', "i'm hiring"
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
        
        # Urgency signals (25 points max)
        'urgency': {
            'weight': 5.0,
            'keywords': [
                'urgent', 'immediate', 'asap', 'start immediately',
                'fast-track', 'fast track', 'quick hire', 'quick start',
                'urgent requirement', 'high priority'
            ]
        },
        
        # Tech relevance (15 points max) - basic keywords
        'tech_relevance': {
            'weight': 3.0,
            'keywords': [
                'data science', 'machine learning', 'ai', 'artificial intelligence',
                'python', 'nlp', 'genai', 'ml engineer', 'data scientist',
                'deep learning', 'neural networks', 'analytics', 'big data'
            ]
        }
    }
    
    return scoring_config

def calculate_post_score(post_text, author_name=None):
    """
    Calculate a score for a post based on various factors to prioritize posts from hiring managers.
    Uses FIXED scoring method without problematic normalization.
    
    Returns:
        float: A score between 0 and 100, with higher scores indicating higher priority
    """
    if not post_text:
        return 0
    
    # Build scoring configuration
    scoring_config = build_scoring_config()
    
    total_score = 0
    post_text_lower = post_text.lower()
    
    # Log scoring details for debugging
    score_breakdown = {
        'metadata': {
            'text_length': len(post_text),
            'word_count': len(post_text.split()),
            'has_author': bool(author_name)
        }
    }
    
    # Calculate scores for each category - FIXED scoring method
    for category, config_data in scoring_config.items():
        weight = config_data['weight']
        keywords = config_data['keywords']
        
        # Skip author check if no author name provided
        if 'author' in category and not author_name:
            continue
            
        # Determine text to search in based on category
        search_text = author_name.lower() if 'author' in category and author_name else post_text_lower
        
        # Count keyword matches
        matches = sum(1 for kw in keywords if kw.lower() in search_text)
        
        # Calculate score - give full weight for ANY match, bonus for multiple
        if matches > 0:
            # Base score for having ANY match in this category
            category_score = weight * 5  # Base multiplier
            # Small bonus for multiple matches (diminishing returns)
            if matches > 1:
                category_score += weight * min(matches - 1, 2)  # Max 2 bonus matches
        else:
            category_score = 0
        
        total_score += category_score
        
        # Store breakdown for logging
        score_breakdown[category] = {
            'matches': matches,
            'score': category_score,
            'weight': weight
        }
    
    # Add length bonus (not penalty)
    words = len(post_text.split())
    if words >= 50:
        total_score += 5  # Bonus for substantial posts
    
    score_breakdown['length'] = {
        'words': words,
        'score': 5 if words >= 50 else 0
    }
    
    # FIXED: Direct scoring - no normalization to avoid the problem
    final_score = min(100, total_score)  # Cap at 100
    
    # Log scoring breakdown with analysis
    score_analysis = {
        'breakdown': score_breakdown,
        'final_score': final_score,
        'categories_hit': sum(1 for cat in score_breakdown.values() if isinstance(cat, dict) and cat.get('matches', 0) > 0),
        'total_matches': sum(cat.get('matches', 0) for cat in score_breakdown.values() if isinstance(cat, dict))
    }
    
    if DEBUG_MODE:
        debug_log(f"Post scoring analysis: {json.dumps(score_analysis, indent=2)}", "SCORE")
    
    return final_score

def should_comment_on_post(post_text, author_name=None, hours_ago=999, min_score=60):
    """Determine if a post is worth commenting on based on score."""
    score = calculate_post_score(post_text, author_name)
    debug_log(f"Post score: {score} (min required: {min_score})", "SCORE")
    return score >= min_score, score

def extract_time_posted(post):
    """Extract when the post was made and convert to hours ago."""
    try:
        time_selectors = [
            ".//span[contains(@class, 'feed-shared-actor__sub-description')]//span",
            ".//time",
            ".//span[contains(text(), 'ago')]",
            ".//span[contains(@class, 'visually-hidden') and contains(text(), 'ago')]"
        ]
        
        for selector in time_selectors:
            try:
                time_elements = post.find_elements(By.XPATH, selector)
                for elem in time_elements:
                    time_text = elem.text.strip().lower()
                    if 'ago' in time_text:
                        # Parse time text like "2 hours ago", "1 day ago", "3 weeks ago"
                        if 'minute' in time_text or 'min' in time_text:
                            return 0.5  # Less than an hour
                        elif 'hour' in time_text:
                            hours = int(re.search(r'(\d+)', time_text).group(1)) if re.search(r'(\d+)', time_text) else 1
                            return hours
                        elif 'day' in time_text:
                            days = int(re.search(r'(\d+)', time_text).group(1)) if re.search(r'(\d+)', time_text) else 1
                            return days * 24
                        elif 'week' in time_text:
                            weeks = int(re.search(r'(\d+)', time_text).group(1)) if re.search(r'(\d+)', time_text) else 1
                            return weeks * 24 * 7
                        elif 'month' in time_text:
                            return 30 * 24  # Approximate
            except Exception:
                continue
        
        return 999  # Default to very old if can't determine
    except Exception as e:
        debug_log(f"Error extracting time: {e}", "TIME")
        return 999

def sort_posts_by_priority(driver, posts):
    """Sort posts by priority based on score."""
    posts_with_data = []
    
    for post in posts:
        try:
            # Extract post data
            hours_ago = extract_time_posted(post)
            author_name = extract_author_name(post)
            
            # Try to get post text for scoring (without expanding yet)
            post_text = post.text[:500] if post.text else ""  # Preview for scoring
            
            # Calculate score
            score = calculate_post_score(post_text, author_name)
            
            posts_with_data.append({
                'element': post,
                'hours_ago': hours_ago,
                'score': score,
                'author': author_name
            })
        except Exception as e:
            debug_log(f"Error processing post for sorting: {e}", "SORT")
            continue
    
    # Sort by score (descending)
    posts_with_data.sort(key=lambda x: -x['score'])
    
    debug_log(f"Sorted {len(posts_with_data)} posts by priority", "SORT")
    return posts_with_data

class BackendClient:
    """Client for interacting with the Junior backend API."""
    
    def __init__(self, base_url, username=None, password=None, access_token=None):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.access_token = access_token
        self.refresh_token = None
        self.session_id = None
        self.user_config = None
        self.tier_limits = None
    
    def authenticate(self, client_name="Desktop Client", client_version="1.0.0"):
        """Authenticate with the backend API using JWT tokens."""
        try:
            # If we already have an access token, verify it works
            if self.access_token:
                if self._verify_token():
                    debug_log("Using existing access token", "AUTH")
                    return True
                else:
                    debug_log("Existing token invalid, getting new one", "AUTH")
            
            # Get new access token using username/password
            if not self.username or not self.password:
                debug_log("No username/password provided for authentication", "ERROR")
                return False
            
            response = requests.post(
                f"{self.base_url}/api/users/token",
                data={
                    "username": self.username,
                    "password": self.password
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            self.refresh_token = token_data.get("refresh_token")
            
            if not self.access_token:
                debug_log("No access token received from authentication", "ERROR")
                return False
            
            debug_log("Successfully authenticated with JWT token", "AUTH")
            return True
            
        except Exception as e:
            debug_log(f"Authentication failed: {e}", "ERROR")
            return False
    
    def _verify_token(self):
        """Verify that the current access token is valid."""
        try:
            response = requests.get(
                f"{self.base_url}/api/users/me",
                headers=self._get_headers()
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def _refresh_access_token(self):
        """Refresh the access token using the refresh token."""
        try:
            if not self.refresh_token:
                debug_log("No refresh token available", "ERROR")
                return False
            
            response = requests.post(
                f"{self.base_url}/api/users/token/refresh",
                json={"refresh_token": self.refresh_token},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            
            if self.access_token:
                debug_log("Successfully refreshed access token", "AUTH")
                return True
            else:
                debug_log("No access token received from refresh", "ERROR")
                return False
                
        except Exception as e:
            debug_log(f"Failed to refresh access token: {e}", "ERROR")
            return False
    
    def _make_authenticated_request(self, method, url, **kwargs):
        """Make an authenticated request with automatic token refresh."""
        headers = kwargs.get('headers', {})
        headers.update(self._get_headers())
        kwargs['headers'] = headers
        
        try:
            response = requests.request(method, url, **kwargs)
            
            # If unauthorized, try to refresh token once
            if response.status_code == 401:
                debug_log("Received 401, attempting to refresh token", "AUTH")
                if self._refresh_access_token():
                    # Update headers with new token and retry
                    headers.update(self._get_headers())
                    kwargs['headers'] = headers
                    response = requests.request(method, url, **kwargs)
                else:
                    debug_log("Token refresh failed, re-authenticating", "AUTH")
                    if self.authenticate():
                        headers.update(self._get_headers())
                        kwargs['headers'] = headers
                        response = requests.request(method, url, **kwargs)
            
            return response
            
        except Exception as e:
            debug_log(f"Request failed: {e}", "ERROR")
            raise
    
    def get_config(self):
        """Get user configuration from backend."""
        # TODO: This endpoint doesn't exist in current API
        # May need to use /api/users/bio or /api/profile/ instead
        debug_log("get_config not implemented - endpoint missing", "WARNING")
        return {}
    
    def get_tier_limits(self):
        """Get user's tier limits including warmup calculations."""
        # TODO: This endpoint doesn't exist in current API
        debug_log("get_tier_limits not implemented - endpoint missing", "WARNING")
        return None
    
    def calculate_daily_limit(self):
        """Calculate today's comment limit based on tier and warmup period."""
        # TODO: Without subscription-limits endpoint, using default
        debug_log("Using default daily limit (no subscription endpoint)", "WARNING")
        return 20  # Default fallback
    
    def get_today_comment_count(self):
        """Get the number of comments already made today."""
        # TODO: This endpoint doesn't exist in current API
        debug_log("get_today_comment_count not implemented - endpoint missing", "WARNING")
        return 0  # Default fallback
    
    def start_session(self):
        """Start an analytics session."""
        # TODO: This endpoint doesn't exist in current API
        debug_log("start_session not implemented - endpoint missing", "WARNING")
        return True  # Always return true for now
    
    def add_comment_history(self, linkedin_urn, comment_text, post_text, success=True, failure_reason=None):
        """Record a comment in history."""
        # TODO: This endpoint doesn't exist in current API
        debug_log("add_comment_history not implemented - endpoint missing", "WARNING")
        return True  # Always return true for now
    
    def add_search_metrics(self, url, keyword, total_posts, hiring_posts, searches, efficiency):
        """Record search metrics."""
        # TODO: This endpoint doesn't exist in current API
        debug_log("add_search_metrics not implemented - endpoint missing", "WARNING")
        return True  # Always return true for now
    
    def generate_comment(self, post_text, author_name=None):
        """Generate a comment using the backend API."""
        try:
            response = self._make_authenticated_request(
                'POST',
                f"{self.base_url}/api/comments/generate",
                json={
                    "post_text": post_text,
                    "author_name": author_name
                }
            )
            response.raise_for_status()
            return response.json()["comment"]
        except Exception as e:
            debug_log(f"Failed to generate comment: {e}", "ERROR")
            return None
    
    def _get_headers(self):
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json"
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

def debug_log(message, level="INFO"):
    """Enhanced debug logging with timestamps and levels."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Replace problematic Unicode characters with ASCII alternatives
    message = (message.replace('\u274c', 'X')  # Replace ❌ with X
              .replace('✅', '+')  # Replace ✅ with +
              .replace('⚠️', '!')  # Replace ⚠️ with !
              .replace('🔄', '->')  # Replace 🔄 with ->
              .encode('ascii', 'replace').decode())  # Replace any other non-ASCII chars
    
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)
    
    # Try to write to log file but handle errors gracefully
    log_file = os.environ.get('LINKEDIN_LOG_FILE', "linkedin_commenter.log")
    try:
        # Ensure directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        with open(log_file, "a", encoding="ascii") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"Error writing to log file: {e}")

def initialize_driver():
    """Initialize and return a configured Chrome WebDriver instance."""
    try:
        chrome_options = Options()
        
        # Ensure headed mode (no headless)
        # chrome_options.add_argument('--headless')  # Commented out to ensure headed mode
        
        # Add persistent user data directory for Chrome profile
        chrome_profile_path = os.environ.get('LINKEDIN_CHROME_PROFILE_PATH', os.path.join(os.getcwd(), "chrome_profile"))
        chrome_options.add_argument(f"--user-data-dir={chrome_profile_path}")
        
        # Add common user agent
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
        
        # Disable notifications and other unnecessary features
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--no-sandbox")
        
        # IMPORTANT: Make browser visible and properly sized
        chrome_options.add_argument("--window-size=1200,900")
        chrome_options.add_argument("--window-position=50,50")
        
        # Initialize driver
        try:
            print("\nOpening Chrome browser window for LinkedIn login...\n")
            driver = webdriver.Chrome(options=chrome_options)
            
            # Maximize window for better visibility
            driver.maximize_window()
            print("Browser window maximized for better visibility")
            
            # Add debug logging
            print("\nDebug Information:")
            print("1. Browser is running in headed mode")
            print("2. Window is maximized")
            print("3. Chrome profile is being used")
            print("4. User agent is set to mimic regular Chrome")
            print("\nYou can now see the browser window and monitor interactions in real time")
            
            return driver
            
        except Exception as e:
            print(f"\nError initializing Chrome driver: {e}")
            print("\nTrying alternative Chrome driver initialization method...\n")
            try:
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                driver.maximize_window()
                return driver
            except Exception as e2:
                print(f"\nSecond error initializing Chrome: {e2}")
                print("\nERROR: Failed to open Chrome browser. Do you have Chrome installed?\n")
                raise Exception("Could not initialize Chrome. Please ensure Chrome is installed.")
                
    except Exception as e:
        print(f"Error in initialize_driver: {e}")
        raise

def verify_active_login(driver):
    """Robustly verify that we're logged in to LinkedIn, with auto/manual login and debug logging."""
    debug_log("Verifying LinkedIn login status...", "LOGIN")
    try:
        # Go to LinkedIn homepage
        driver.get("https://www.linkedin.com/")
        time.sleep(5)

        # Define indicators for logged-in state
        logged_in_indicators = {
            "profile photo": (By.CLASS_NAME, "global-nav__me-photo"),
            "feed module": (By.CLASS_NAME, "feed-identity-module"),
            "post box": (By.CLASS_NAME, "share-box-feed-entry__trigger"),
            "navigation bar": (By.CLASS_NAME, "global-nav__content")
        }

        # Check if we're already logged in
        for name, (by, value) in logged_in_indicators.items():
            try:
                element = driver.find_element(by, value)
                if element.is_displayed():
                    debug_log(f"Already logged in - found {name}", "LOGIN")
                    return True
            except Exception:
                debug_log(f"Logged-in indicator {name} not found", "LOGIN")

        # Try accessing the feed directly to confirm login status
        driver.get("https://www.linkedin.com/feed/")
        time.sleep(5)
        current_url = driver.current_url.lower()
        debug_log(f"Feed URL: {current_url}", "LOGIN")

        # If we're on the feed, we're logged in
        if "feed" in current_url and "login" not in current_url:
            for name, (by, value) in logged_in_indicators.items():
                try:
                    element = driver.find_element(by, value)
                    if element.is_displayed():
                        debug_log(f"Confirmed logged in on feed - found {name}", "LOGIN")
                        return True
                except Exception:
                    pass

        # If login form is detected, prompt for manual login
        debug_log("Prompting user for manual login", "LOGIN")
        print("\n===========================================================\n||                                                       ||\n||       PLEASE LOGIN TO LINKEDIN IN THE BROWSER         ||\n||                                                       ||\n||  1. Enter your email/phone and password               ||\n||  2. Click 'Sign in'                                   ||\n||  3. Complete any security verification if needed       ||\n||  4. Press ENTER in this console when you've logged in ||\n||                                                       ||\n===========================================================")
        input("\nPress ENTER after you've completed login: ")
        time.sleep(3)
        driver.refresh()
        time.sleep(5)
        
        # Check again for login
        for name, (by, value) in logged_in_indicators.items():
            try:
                element = driver.find_element(by, value)
                if element.is_displayed():
                    debug_log(f"Manual login successful - found {name}", "LOGIN")
                    return True
            except Exception:
                continue
        
        debug_log("Manual login not detected after prompt", "LOGIN")
        return False

    except Exception as e:
        debug_log(f"Error verifying login: {e}", "LOGIN")
        return False

def process_posts(driver, backend_client):
    """Process visible posts on the current page with prioritization and scoring."""
    debug_log("Starting post processing with prioritization", "PROCESS")
    posts_processed = 0
    posts_commented = 0
    
    # Get daily limit and check how many comments we've already made
    daily_limit = backend_client.calculate_daily_limit()
    today_count = backend_client.get_today_comment_count()
    remaining_daily = daily_limit - today_count
    
    # Get session limit from user config (default to 10 if not specified)
    session_limit = backend_client.user_config.get("session_limit", 10) if backend_client.user_config else 10
    
    # Check daily limit first
    if remaining_daily <= 0:
        debug_log(f"Daily limit of {daily_limit} comments reached. Stopping.", "WARNING")
        return 0
    
    # Enforce the lower of daily remaining or session limit
    remaining_comments = min(remaining_daily, session_limit)
    
    debug_log(f"Daily limit: {daily_limit}, Already made today: {today_count}, Remaining daily: {remaining_daily}", "INFO")
    debug_log(f"Session limit: {session_limit}, Will process up to: {remaining_comments} comments this session", "INFO")
    
    # Get minimum score threshold (default 55)
    min_score = 55
    
    try:
        debug_log("Searching for visible posts", "SEARCH")
        posts = find_posts(driver)
        if not posts:
            debug_log("No posts found on current page", "WARNING")
            return 0
        
        debug_log(f"Found {len(posts)} posts, sorting by priority", "SEARCH")
        
        # Sort posts by priority (score-based)
        sorted_posts = sort_posts_by_priority(driver, posts)
        
        # Filter to only high-scoring posts
        high_score_posts = [p for p in sorted_posts if p['score'] >= min_score]
        debug_log(f"Found {len(high_score_posts)} posts with score >= {min_score}", "FILTER")
        
        if not high_score_posts:
            debug_log("No posts meet minimum score threshold", "WARNING")
            return 0
        
        for post_data in high_score_posts:
            # Check if we've reached either daily or session limit
            if posts_commented >= remaining_comments:
                if remaining_comments == remaining_daily:
                    debug_log(f"Reached daily comment limit ({remaining_comments}). Stopping.", "WARNING")
                else:
                    debug_log(f"Reached session comment limit ({remaining_comments}). Stopping.", "WARNING")
                break
            
            post = post_data['element']
            hours_ago = post_data['hours_ago']
            score = post_data['score']
            author_name = post_data['author']
            
            try:
                debug_log(f"Processing post (score: {score}, {hours_ago:.1f}h ago, author: {author_name})", "PROCESS")
                post_id, id_method = compute_post_id(post)
                debug_log(f"Post ID: {post_id} (Method: {id_method})", "DATA")
                
                posts_processed += 1
                
                debug_log("Scrolling post into view", "ACTION")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post)
                time.sleep(1)
                
                debug_log("Attempting to expand post content", "ACTION")
                expand_post(driver, post)
                
                debug_log("Extracting full post text", "DATA")
                post_text = get_post_text(driver, post)
                debug_log(f"Post text length: {len(post_text)} characters", "DATA")
                
                if not post_text or len(post_text) < 10:
                    debug_log(f"Post text too short or empty (length: {len(post_text)}), skipping", "SKIP")
                    continue
                
                # Re-score with full text
                should_comment, final_score = should_comment_on_post(post_text, author_name, hours_ago, min_score)
                if not should_comment:
                    debug_log(f"Post score too low after full text analysis ({final_score} < {min_score}), skipping", "SKIP")
                    continue
                
                debug_log("Checking for existing comments", "CHECK")
                if has_already_commented(driver, post):
                    debug_log("Already commented on this post, skipping", "SKIP")
                    continue
                
                debug_log("Generating comment", "GENERATE")
                custom_message = backend_client.generate_comment(post_text, author_name)
                debug_log(f"Generated comment: {custom_message}", "DATA")
                
                if custom_message is None:
                    debug_log("No comment generated, skipping", "SKIP")
                    continue
                
                debug_log(f"Generated comment length: {len(custom_message)} characters", "DATA")
                if len(custom_message.split()) > len(post_text.split()):
                    debug_log("Comment longer than post, skipping", "SKIP")
                    continue
                
                debug_log("Attempting to post comment", "ACTION")
                comment_success = post_comment(driver, post, custom_message)
                if comment_success:
                    debug_log("Successfully posted comment", "SUCCESS")
                    posts_commented += 1
                    debug_log("Recording comment in history", "DATA")
                    backend_client.add_comment_history(
                        linkedin_urn=post_id,
                        comment_text=custom_message,
                        post_text=post_text,
                        success=True
                    )
                    
                    # Apply comment delay from config
                    delay_seconds = backend_client.user_config.get("comment_delay_seconds", 30) if backend_client.user_config else 30
                    debug_log(f"Sleeping {delay_seconds} seconds between comments", "WAIT")
                    time.sleep(delay_seconds)
                else:
                    debug_log("Failed to post comment", "ERROR")
                    backend_client.add_comment_history(
                        linkedin_urn=post_id,
                        comment_text=custom_message,
                        post_text=post_text,
                        success=False,
                        failure_reason="Failed to post comment"
                    )
            except Exception as e:
                debug_log(f"Error processing post: {str(e)}", "ERROR")
                debug_log(traceback.format_exc(), "ERROR")
                continue
        
        debug_log(f"Processed {posts_processed} posts, commented on {posts_commented}", "SUMMARY")
        return posts_commented
    except Exception as e:
        debug_log(f"Error in process_posts: {str(e)}", "ERROR")
        debug_log(traceback.format_exc(), "ERROR")
        return 0

def find_posts(driver):
    """Find all post elements currently visible on the screen with multiple selectors."""
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
    """Compute a unique ID for a post using multiple attributes."""
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
                    return (hashlib.sha256(combined.encode()).hexdigest(), "author-timestamp")
        except Exception:
            pass
        
        # Method 6: Last resort - use inner HTML hash
        post_html = post.get_attribute("innerHTML")
        if post_html:
            truncated_html = post_html[:500]
            return (hashlib.sha256(truncated_html.encode()).hexdigest(), "html-hash")
        
        # If all fails, use a random hash based on current time
        return (hashlib.sha256(str(time.time()).encode()).hexdigest(), "fallback")
    except Exception as e:
        debug_log(f"Error computing post ID: {e}", "DATA")
        return (hashlib.sha256(str(time.time()).encode()).hexdigest(), "error")

def expand_post(driver, post):
    """Expand the post by clicking 'see more' if present."""
    debug_log("[expand_post] Attempting to expand post...", "EXPAND")
    try:
        pre_text = post.text or ""
        debug_log(f"[expand_post] Pre-expand text length: {len(pre_text)}", "EXPAND")
        
        see_more_selectors = [
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
    """Extract the text content of a post with multiple fallback methods."""
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

def has_already_commented(driver, post):
    """Check if we have already commented on this post."""
    debug_log("Checking if post already has our comment...", "CHECK")
    try:
        # Try to find comments section
        comments_section = None
        comment_selectors = [
            ".//div[contains(@class, 'comments-comment-item')]",
            ".//div[contains(@class, 'comments-comments-list')]",
            ".//ul[contains(@class, 'comments-comment-item')]",
            ".//div[contains(@class, 'comments-comment-item__main-content')]",
            ".//div[contains(@class, 'comments-comment-item__inline-show-more-text')]"
        ]
        
        for selector in comment_selectors:
            try:
                elements = post.find_elements(By.XPATH, selector)
                if elements:
                    comments_section = elements
                    break
            except Exception:
                continue
        
        if not comments_section:
            debug_log("No comments section found, assuming we haven't commented", "CHECK")
            return False
        
        # Look for any comments that might be from us
        for comment in comments_section:
            try:
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
                    return True
            except Exception:
                continue
        
        debug_log("No evidence we've already commented", "CHECK")
        return False
    except Exception as e:
        debug_log(f"Error checking for existing comments: {e}", "CHECK")
        return False

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

def safe_click(driver, element):
    """Safely click an element using multiple methods."""
    try:
        # Try regular click first
        element.click()
        return True
    except Exception:
        try:
            # Try JavaScript click
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            try:
                # Try ActionChains click
                ActionChains(driver).move_to_element(element).click().perform()
                return True
            except Exception:
                return False

def post_comment(driver, post, message):
    """Post a comment on a post with extremely granular debug logging."""
    debug_log("[post_comment] Starting comment posting process...", "COMMENT")
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
                return False
        else:
            # Click the comment button
            try:
                comment_button.click()
                time.sleep(2)
            except Exception as e:
                debug_log(f"[post_comment] Failed to click comment button: {e}", "COMMENT")
                return False
        
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
            return False
        
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
            return False
        
        # Try to click the submit button
        try:
            submit_button.click()
            debug_log("[post_comment] Clicked submit button", "COMMENT")
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            debug_log(f"[post_comment] Failed to click submit button: {e}", "COMMENT")
            return False
        
        # Step 5: Verify the comment was posted by checking if input field is cleared/gone
        time.sleep(3)
        try:
            if comment_input.is_displayed():
                current_value = comment_input.get_attribute("value") or comment_input.text
                if current_value and message in current_value:
                    debug_log("[post_comment] Comment still in input field - submission failed", "COMMENT")
                    return False
        except Exception as e:
            debug_log(f"[post_comment] Error verifying comment submission: {e}", "COMMENT")
        
        # Final check - search for our comment in the post
        time.sleep(2)
        if has_already_commented(driver, post):
            debug_log("[post_comment] Verified our comment is now in the post!", "COMMENT")
            return True
        
        debug_log("[post_comment] Could not verify if comment was posted, assuming success", "COMMENT")
        return True
    except Exception as e:
        debug_log(f"[post_comment] Error posting comment: {e}", "COMMENT")
        debug_log(traceback.format_exc(), "COMMENT")
        return False

def generate_search_urls(config):
    """Generate search URLs from keywords + 'hiring' with time filters, just like Junior-Beta."""
    debug_log("Generating dynamic search URLs from keywords", "URL_GEN")
    
    # Get keywords from config (check multiple possible locations)
    keywords = config.get('keywords', [])
    
    # If keywords is a string (comma-separated), convert to list
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(',') if k.strip()]
    
    # Also check automation.keywords location (like Junior-Beta)
    if not keywords:
        automation_config = config.get('automation', {})
        keywords = automation_config.get('keywords', [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',') if k.strip()]
    
    if not keywords:
        debug_log("No keywords found in config, using default search URLs", "URL_GEN")
        return [{
            'url': "https://www.linkedin.com/feed/",
            'keyword': "feed",
            'time_filter': "none",
            'description': "LinkedIn Feed"
        }]
    
    search_urls = []
    
    # Time filters to use - 24 hours, week, month (same as Junior-Beta)
    time_filters = [
        ("past-24h", "Past 24 hours"),
        ("past-week", "Past week"),
        ("past-month", "Past month")
    ]
    
    # Generate URLs for each time filter, then each keyword
    for time_filter, time_desc in time_filters:
        for keyword in keywords:
            # Create simple LinkedIn search URL for "keyword hiring" with time filter
            search_query = f"{keyword} hiring"
            encoded_query = search_query.replace(' ', '%20')
            search_url = f"https://www.linkedin.com/search/results/content/?datePosted=%22{time_filter}%22&keywords={encoded_query}&origin=FACETED_SEARCH"
            search_urls.append({
                'url': search_url,
                'keyword': keyword,
                'time_filter': time_filter,
                'description': f"{keyword} hiring - {time_desc}"
            })
    
    # Add feed as a fallback (no time filter)
    search_urls.append({
        'url': "https://www.linkedin.com/feed/",
        'keyword': "feed",
        'time_filter': "none",
        'description': "LinkedIn Feed"
    })
    
    debug_log(f"Generated {len(search_urls)} search URLs from {len(keywords)} keywords", "URL_GEN")
    debug_log("Search URL order:", "URL_GEN")
    debug_log("1. Past 24 hours searches (freshest posts)", "URL_GEN")
    for item in search_urls:
        if item['time_filter'] == 'past-24h':
            debug_log(f"   - {item['description']}", "URL_GEN")
    debug_log("2. Past week searches", "URL_GEN")
    for item in search_urls:
        if item['time_filter'] == 'past-week':
            debug_log(f"   - {item['description']}", "URL_GEN")
    debug_log("3. Past month searches", "URL_GEN")
    for item in search_urls:
        if item['time_filter'] == 'past-month':
            debug_log(f"   - {item['description']}", "URL_GEN")
    
    return search_urls

def main():
    """Main execution function - backend only."""
    debug_log("="*50, "START")
    debug_log(f"Starting LinkedIn commenter at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "START")
    debug_log("Running in headed mode for real-time debugging", "START")
    debug_log("="*50, "START")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='LinkedIn Commenter - Backend Only')
    parser.add_argument('--config', type=str, help='Configuration file path')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()
    
    # Initialize backend client
    backend_client = None
    config = {}
    
    # Try to load local config file first
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
            debug_log(f"Local configuration loaded from: {args.config}", "CONFIG")
        except Exception as e:
            debug_log(f"Error reading config file: {e}", "ERROR")
            sys.exit(1)
    
    # Backend connection is required
    try:
        # Set global configuration for backend
        global API_BASE_URL
        API_BASE_URL = config.get('backend_url')
        username = config.get('username')
        password = config.get('password')
        access_token = config.get('access_token')  # Optional: can provide pre-generated token
        
        if not API_BASE_URL:
            debug_log("❌ Missing backend_url in configuration", "ERROR")
            debug_log("This script requires backend connection. Please provide valid backend configuration.", "ERROR")
            sys.exit(1)
        
        if not access_token and (not username or not password):
            debug_log("❌ Missing username/password or access_token in configuration", "ERROR")
            debug_log("This script requires either username/password or access_token for authentication.", "ERROR")
            sys.exit(1)
        
        debug_log("Attempting backend connection...", "BACKEND")
        backend_client = BackendClient(API_BASE_URL, username, password, access_token)
        
        # Try to authenticate
        if not backend_client.authenticate():
            debug_log("❌ Backend authentication failed", "ERROR")
            sys.exit(1)
        
        debug_log("✅ Backend connected successfully!", "BACKEND")
        
        # Start analytics session
        if backend_client.start_session():
            debug_log("✅ Analytics session started", "BACKEND")
        
        # Get backend configuration
        backend_config = backend_client.get_config()
        if backend_config:
            config.update(backend_config)
            debug_log("✅ Backend configuration loaded", "BACKEND")
            
    except Exception as e:
        debug_log(f"❌ Backend connection failed: {e}", "ERROR")
        debug_log("This script requires backend connection. Please check your configuration.", "ERROR")
        sys.exit(1)
    
    # Display current configuration
    debug_log("🌐 Mode: BACKEND ONLY", "CONFIG")
    debug_log(f"Comment delay: {config.get('comment_delay_seconds', 30)}s", "CONFIG")
    
    # Initialize browser
    debug_log("Initializing browser...", "INIT")
    driver = initialize_driver()
    
    try:
        # Verify login
        debug_log("Verifying LinkedIn login...", "LOGIN")
        if not verify_active_login(driver):
            debug_log("Failed to verify LinkedIn login", "ERROR")
            sys.exit(1)
        
        # Process search URLs
        search_urls = generate_search_urls(config)
        for url_data in search_urls:
            try:
                # Extract URL and metadata from the dictionary
                url = url_data['url'] if isinstance(url_data, dict) else url_data
                keyword = url_data.get('keyword', '') if isinstance(url_data, dict) else ''
                description = url_data.get('description', url) if isinstance(url_data, dict) else url
                
                debug_log(f"Processing URL: {description}", "URL")
                driver.get(url)
                time.sleep(random.uniform(3, 5))
                
                # Process posts with backend client
                processed_count = process_posts(driver, backend_client)
                
                if processed_count > 0:
                    debug_log(f"Successfully processed {processed_count} posts from {description}", "SUCCESS")
                    time.sleep(random.uniform(15, 30))
                
                # Record metrics with keyword information
                try:
                    backend_client.add_search_metrics(
                        url=url,
                        keyword=keyword,
                        total_posts=len(find_posts(driver)),
                        hiring_posts=0,
                        searches=1,
                        efficiency=processed_count / max(len(find_posts(driver)), 1)
                    )
                except Exception as e:
                    debug_log(f"Error recording metrics: {e}", "WARNING")
                    
            except Exception as e:
                debug_log(f"Error processing URL {description if 'description' in locals() else url}: {e}", "ERROR")
                continue
                
    except Exception as e:
        debug_log(f"Fatal error: {e}", "ERROR")
        debug_log(traceback.format_exc(), "ERROR")
    finally:
        debug_log("Cleaning up...", "CLEANUP")
        driver.quit()
    
    debug_log("Script execution completed", "END")

if __name__ == "__main__":
    main() 