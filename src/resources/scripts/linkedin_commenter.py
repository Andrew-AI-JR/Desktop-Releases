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

# Load environment variables from .env file (for production builds)
try:
    from dotenv import load_dotenv
    # For PyInstaller bundled apps, the .env file will be in the executable's directory
    # load_dotenv() automatically looks for .env in the current working directory
    load_dotenv()
except ImportError:
    # dotenv not available, continue without it
    pass

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
    # Try to load backend URL from environment if not in config (dotenv already loaded at top)
    if not config.get('backend_url'):
        backend_url = os.getenv('BACKEND_URL')
        if backend_url:
            config['backend_url'] = backend_url
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
# Dynamic keyword expansion for tech relevance
def expand_tech_keywords(base_keywords):
    """
    Expand tech keywords with synonyms and related terms for better post matching.
    
    Args:
        base_keywords (list): Base keywords from configuration
        
    Returns:
        list: Expanded keywords including synonyms and related terms
    """
    
    # Keyword expansion mapping - add synonyms and related terms
    expansion_map = {
        # Data Science & Analytics
        'data science': ['machine learning', 'data analysis', 'data analytics', 'predictive analytics', 'statistical analysis', 'data mining', 'business intelligence', 'data scientist', 'data analyst'],
        'data scientist': ['data science', 'machine learning', 'data analysis', 'analytics', 'statistical modeling', 'data mining'],
        'data analysis': ['data science', 'analytics', 'data analytics', 'business intelligence', 'statistical analysis', 'data visualization'],
        'analytics': ['data analytics', 'business analytics', 'predictive analytics', 'data analysis', 'business intelligence', 'metrics'],
        
        # Machine Learning & AI
        'machine learning': ['ml', 'data science', 'artificial intelligence', 'ai', 'deep learning', 'neural networks', 'predictive modeling', 'statistical learning'],
        'ml': ['machine learning', 'data science', 'artificial intelligence', 'ai', 'deep learning', 'predictive modeling'],
        'artificial intelligence': ['ai', 'machine learning', 'ml', 'deep learning', 'neural networks', 'cognitive computing', 'intelligent systems'],
        'ai': ['artificial intelligence', 'machine learning', 'ml', 'deep learning', 'neural networks', 'cognitive computing'],
        'deep learning': ['neural networks', 'ai', 'artificial intelligence', 'machine learning', 'ml', 'deep neural networks', 'cnn', 'rnn'],
        'neural networks': ['deep learning', 'ai', 'artificial intelligence', 'machine learning', 'neural nets', 'deep neural networks'],
        
        # Programming Languages
        'python': ['python programming', 'python developer', 'python development', 'django', 'flask', 'pandas', 'numpy', 'scikit-learn', 'tensorflow', 'pytorch'],
        'javascript': ['js', 'node.js', 'nodejs', 'react', 'angular', 'vue', 'javascript developer', 'frontend', 'backend'],
        'java': ['java developer', 'java programming', 'spring', 'spring boot', 'jvm', 'java development'],
        'c++': ['cpp', 'c plus plus', 'c++ developer', 'c++ programming'],
        'r': ['r programming', 'r language', 'rstudio', 'statistical computing'],
        'sql': ['database', 'mysql', 'postgresql', 'oracle', 'sql server', 'data querying', 'database management'],
        
        # Cloud & Infrastructure
        'cloud': ['cloud computing', 'aws', 'azure', 'gcp', 'google cloud', 'cloud infrastructure', 'cloud services', 'cloud platform'],
        'aws': ['amazon web services', 'cloud', 'ec2', 's3', 'lambda', 'aws cloud', 'amazon cloud'],
        'azure': ['microsoft azure', 'cloud', 'azure cloud', 'microsoft cloud'],
        'gcp': ['google cloud platform', 'google cloud', 'cloud', 'google cloud services'],
        'kubernetes': ['k8s', 'container orchestration', 'docker', 'containers', 'microservices', 'devops'],
        'docker': ['containers', 'containerization', 'kubernetes', 'microservices', 'devops'],
        
        # Web Development
        'web development': ['frontend', 'backend', 'full stack', 'web developer', 'web programming', 'web design', 'web applications'],
        'frontend': ['front-end', 'ui', 'user interface', 'javascript', 'react', 'angular', 'vue', 'css', 'html'],
        'backend': ['back-end', 'server-side', 'api', 'database', 'web services', 'microservices'],
        'full stack': ['fullstack', 'full-stack', 'web development', 'frontend', 'backend', 'web developer'],
        'react': ['reactjs', 'react.js', 'frontend', 'javascript', 'ui', 'web development'],
        'angular': ['angularjs', 'frontend', 'javascript', 'typescript', 'web development'],
        
        # DevOps & Infrastructure
        'devops': ['dev ops', 'ci/cd', 'continuous integration', 'continuous deployment', 'infrastructure', 'automation', 'docker', 'kubernetes'],
        'ci/cd': ['continuous integration', 'continuous deployment', 'devops', 'automation', 'pipeline', 'jenkins'],
        'automation': ['devops', 'ci/cd', 'scripting', 'infrastructure automation', 'test automation'],
        
        # Data Engineering
        'data engineering': ['data pipeline', 'etl', 'data infrastructure', 'big data', 'data warehouse', 'data processing'],
        'etl': ['extract transform load', 'data pipeline', 'data processing', 'data engineering', 'data integration'],
        'big data': ['data engineering', 'hadoop', 'spark', 'data processing', 'distributed computing'],
        
        # Mobile Development
        'mobile development': ['ios', 'android', 'mobile app', 'mobile developer', 'mobile programming', 'app development'],
        'ios': ['iphone', 'ipad', 'swift', 'objective-c', 'mobile development', 'apple'],
        'android': ['mobile development', 'kotlin', 'java', 'mobile app', 'google'],
        
        # Databases
        'database': ['sql', 'mysql', 'postgresql', 'mongodb', 'nosql', 'database management', 'data storage'],
        'mongodb': ['nosql', 'database', 'document database', 'json'],
        'postgresql': ['postgres', 'sql', 'database', 'relational database'],
        'mysql': ['sql', 'database', 'relational database', 'mariadb'],
        
        # Software Engineering
        'software engineering': ['software development', 'programming', 'software engineer', 'coding', 'software design'],
        'software development': ['software engineering', 'programming', 'coding', 'application development'],
        'programming': ['coding', 'software development', 'software engineering', 'developer'],
        
        # Emerging Technologies
        'blockchain': ['cryptocurrency', 'bitcoin', 'ethereum', 'smart contracts', 'web3', 'defi'],
        'iot': ['internet of things', 'embedded systems', 'sensors', 'connected devices'],
        'cybersecurity': ['security', 'information security', 'cyber security', 'infosec', 'penetration testing'],
        
        # Business & Product
        'product management': ['product manager', 'pm', 'product development', 'product strategy', 'product owner'],
        'project management': ['project manager', 'pmp', 'agile', 'scrum', 'project coordination'],
        'agile': ['scrum', 'agile methodology', 'sprint', 'kanban', 'project management'],
        'scrum': ['agile', 'scrum master', 'sprint', 'product owner', 'project management']
    }
    
    expanded_keywords = set()
    
    # Add original keywords
    for keyword in base_keywords:
        if keyword:  # Skip empty keywords
            keyword_lower = keyword.lower().strip()
            expanded_keywords.add(keyword_lower)
            
            # Add expanded terms if available
            if keyword_lower in expansion_map:
                expanded_keywords.update(expansion_map[keyword_lower])
                debug_log(f"KEYWORD_EXPANSION: '{keyword}' expanded with {len(expansion_map[keyword_lower])} related terms", "CONFIG")
    
    # Convert back to sorted list for consistency
    result = sorted(list(expanded_keywords))
    debug_log(f"KEYWORD_EXPANSION: {len(base_keywords)} base keywords expanded to {len(result)} total keywords", "CONFIG")
    
    return result

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
        'search_author': True,  # Search author name/title, not post content
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
        'keywords': []  # Will be populated dynamically from config with keyword expansion
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
        'search_author': True,  # Search author name/title, not post content
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

def initialize_tech_relevance_keywords(job_keywords):
    """
    Initialize the tech_relevance keywords from config with expansion.
    
    Args:
        job_keywords (list): Job keywords from configuration
    """
    global POST_SCORING_CONFIG
    
    if job_keywords and isinstance(job_keywords, list) and len(job_keywords) > 0:
        # Expand the job keywords with synonyms and related terms
        expanded_keywords = expand_tech_keywords(job_keywords)
        POST_SCORING_CONFIG['tech_relevance']['keywords'] = expanded_keywords
        print(f"[APP_OUT]🔍 Tech relevance initialized: {len(job_keywords)} base keywords → {len(expanded_keywords)} expanded keywords")
        debug_log(f"Tech relevance keywords expanded from {job_keywords} to {len(expanded_keywords)} total keywords", "CONFIG")
    else:
        # Fallback to a minimal set if no job keywords provided
        fallback_keywords = ['software engineering', 'programming', 'technology']
        expanded_keywords = expand_tech_keywords(fallback_keywords)
        POST_SCORING_CONFIG['tech_relevance']['keywords'] = expanded_keywords
        print(f"[APP_OUT]⚠️ No job keywords provided, using fallback tech keywords: {len(expanded_keywords)} keywords")
        debug_log(f"Using fallback tech keywords: {fallback_keywords} expanded to {len(expanded_keywords)} keywords", "CONFIG")

# NEW ULTRA-STEALTH ADDITION: Advanced Behavioral Pattern Manager
class BehavioralPatternManager:
    """
    Manages advanced behavioral patterns to simulate realistic human usage cycles.
    """
    def __init__(self):
        self.session_start_time = datetime.now()
        self.daily_activity_pattern = self._generate_daily_pattern()
        self.weekly_activity_pattern = self._generate_weekly_pattern()
        self.session_characteristics = self._generate_session_characteristics()
        self.behavior_history = []
        
    def _generate_daily_pattern(self):
        """Generate realistic daily activity patterns based on professional work hours."""
        # Professional work hours with realistic variations
        patterns = {
            'early_bird': {  # 7 AM - 6 PM peak
                'peak_hours': [(7, 10), (13, 15), (17, 19)],
                'low_hours': [(0, 6), (11, 12), (20, 23)],
                'activity_multiplier': 1.2
            },
            'standard': {  # 9 AM - 5 PM peak
                'peak_hours': [(9, 11), (14, 16), (18, 20)],
                'low_hours': [(0, 8), (12, 13), (21, 23)],
                'activity_multiplier': 1.0
            },
            'night_owl': {  # Later hours peak
                'peak_hours': [(10, 12), (15, 17), (20, 22)],
                'low_hours': [(0, 9), (13, 14), (23, 24)],
                'activity_multiplier': 0.9
            }
        }
        selected_pattern = random.choice(list(patterns.keys()))
        debug_log(f"BEHAVIORAL: Selected daily pattern: {selected_pattern}", "BEHAVIORAL")
        return patterns[selected_pattern]
    
    def _generate_weekly_pattern(self):
        """Generate realistic weekly activity patterns."""
        return {
            'monday': 1.1,      # Strong start to week
            'tuesday': 1.2,     # Peak activity
            'wednesday': 1.0,   # Steady
            'thursday': 0.9,    # Slight decline
            'friday': 0.7,      # Wind down
            'saturday': 0.3,    # Low weekend activity
            'sunday': 0.4       # Preparation for week
        }
    
    def _generate_session_characteristics(self):
        """Generate characteristics for this specific session."""
        session_types = [
            {
                'type': 'focused',
                'duration_range': (45, 90),     # 45-90 minutes
                'comment_rate': 1.2,            # Higher comment rate
                'break_frequency': 0.15,        # Less frequent breaks
                'distraction_chance': 0.1       # Low distraction
            },
            {
                'type': 'casual',
                'duration_range': (20, 45),     # 20-45 minutes
                'comment_rate': 1.0,            # Normal comment rate
                'break_frequency': 0.25,        # Moderate breaks
                'distraction_chance': 0.3       # Higher distraction
            },
            {
                'type': 'brief',
                'duration_range': (10, 25),     # 10-25 minutes
                'comment_rate': 0.8,            # Lower comment rate
                'break_frequency': 0.35,        # Frequent breaks
                'distraction_chance': 0.4       # High distraction
            }
        ]
        
        # Weight selection based on time of day
        current_hour = datetime.now().hour
        if 9 <= current_hour <= 17:  # Work hours
            weights = [0.5, 0.4, 0.1]  # Favor focused sessions
        elif 18 <= current_hour <= 22:  # Evening
            weights = [0.3, 0.5, 0.2]  # Favor casual sessions
        else:  # Off hours
            weights = [0.2, 0.3, 0.5]  # Favor brief sessions
        
        selected = random.choices(session_types, weights=weights)[0]
        debug_log(f"BEHAVIORAL: Session type: {selected['type']}", "BEHAVIORAL")
        return selected
    
    def get_current_activity_multiplier(self):
        """Get activity multiplier based on current time and patterns."""
        now = datetime.now()
        current_hour = now.hour
        current_day = now.strftime('%A').lower()
        
        # Get daily multiplier
        daily_mult = self.daily_activity_pattern['activity_multiplier']
        
        # Adjust for peak/low hours
        for start_hour, end_hour in self.daily_activity_pattern['peak_hours']:
            if start_hour <= current_hour < end_hour:
                daily_mult *= 1.3
                break
        
        for start_hour, end_hour in self.daily_activity_pattern['low_hours']:
            if start_hour <= current_hour < end_hour:
                daily_mult *= 0.6
                break
        
        # Get weekly multiplier
        weekly_mult = self.weekly_activity_pattern.get(current_day, 1.0)
        
        # Get session multiplier
        session_mult = self.session_characteristics['comment_rate']
        
        # Combined multiplier
        total_multiplier = daily_mult * weekly_mult * session_mult
        
        debug_log(f"BEHAVIORAL: Activity multiplier: {total_multiplier:.2f} (daily: {daily_mult:.2f}, weekly: {weekly_mult:.2f}, session: {session_mult:.2f})", "BEHAVIORAL")
        return total_multiplier
    
    def should_take_break(self):
        """Determine if a break should be taken based on behavioral patterns."""
        session_duration = (datetime.now() - self.session_start_time).total_seconds() / 60
        break_chance = self.session_characteristics['break_frequency']
        
        # Increase break chance with session duration
        duration_factor = min(session_duration / 60, 2.0)  # Cap at 2x
        adjusted_break_chance = break_chance * duration_factor
        
        should_break = random.random() < adjusted_break_chance
        if should_break:
            debug_log(f"BEHAVIORAL: Break triggered (chance: {adjusted_break_chance:.2f}, duration: {session_duration:.1f}m)", "BEHAVIORAL")
        
        return should_break
    
    def get_break_duration(self):
        """Get appropriate break duration based on patterns."""
        base_duration = random.uniform(30, 120)  # 30 seconds to 2 minutes
        
        # Adjust based on session type
        if self.session_characteristics['type'] == 'focused':
            return base_duration * random.uniform(0.7, 1.0)
        elif self.session_characteristics['type'] == 'casual':
            return base_duration * random.uniform(1.0, 1.5)
        else:  # brief
            return base_duration * random.uniform(1.2, 2.0)
    
    def should_show_distraction(self):
        """Determine if a distraction activity should be performed."""
        return random.random() < self.session_characteristics['distraction_chance']
    
    def get_typing_speed_multiplier(self):
        """Get typing speed variation based on behavioral patterns."""
        base_multiplier = 1.0
        
        # Time of day affects typing speed
        current_hour = datetime.now().hour
        if 6 <= current_hour <= 10:  # Morning - slower, getting warmed up
            base_multiplier *= random.uniform(1.1, 1.3)
        elif 10 <= current_hour <= 16:  # Peak hours - normal to fast
            base_multiplier *= random.uniform(0.8, 1.1)
        elif 16 <= current_hour <= 20:  # Afternoon - moderate
            base_multiplier *= random.uniform(0.9, 1.2)
        else:  # Evening/night - slower, tired
            base_multiplier *= random.uniform(1.2, 1.5)
        
        # Session type affects speed
        session_type = self.session_characteristics['type']
        if session_type == 'focused':
            base_multiplier *= random.uniform(0.8, 1.0)  # Faster, more focused
        elif session_type == 'casual':
            base_multiplier *= random.uniform(1.0, 1.2)  # Normal to slightly slower
        else:  # brief
            base_multiplier *= random.uniform(1.1, 1.4)  # Slower, more hurried
        
        return max(0.5, min(2.0, base_multiplier))  # Cap between 0.5x and 2.0x
    
    def log_behavior(self, action_type, details=None):
        """Log behavioral actions for pattern analysis."""
        behavior_entry = {
            'timestamp': datetime.now(),
            'action': action_type,
            'details': details or {}
        }
        self.behavior_history.append(behavior_entry)
        
        # Keep only last 100 entries to manage memory
        if len(self.behavior_history) > 100:
            self.behavior_history = self.behavior_history[-100:]

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
        # First try to get from config, then from environment, then use production default
        backend_base = self.config.get('backend_url') or os.getenv('BACKEND_URL') or 'https://junior-api-915940312680.us-west1.run.app'
        # Ensure the URL includes the comment generation endpoint
        if not backend_base.endswith('/api/comments/generate'):
            if backend_base.endswith('/'):
                self.backend_url = f"{backend_base}api/comments/generate"
            else:
                self.backend_url = f"{backend_base}/api/comments/generate"
        else:
            self.backend_url = backend_base
        
        # Log the backend URL being used for transparency
        print(f"[APP_OUT]🔗 Backend API configured: {self.backend_url}")
        self.debug_log(f"Comment generation backend URL: {self.backend_url}", "INFO")
        
        # Note: Tech relevance keywords are now initialized globally via initialize_tech_relevance_keywords()
        # This ensures consistent keyword expansion across all components
        self.debug_log(f"CommentGenerator initialized with job keywords: {job_keywords}", "DEBUG")

    def debug_log(self, message, level="INFO"):
        if 'debug_log' in globals():
            debug_log(message, level)
        else:
            print(f"[{level}] {message}")

    def clean_post_text(self, post_text):
        # Simple cleaning: strip, remove extra spaces, etc. (customize as needed)
        return ' '.join(post_text.strip().split())

    def classify_post(self, post_text):
        """Classify post type for targeted commenting."""
        if not post_text:
            return "unknown"
        
        text_lower = post_text.lower()
        
        # Check for hiring posts
        hiring_indicators = [
            "hiring", "recruiting", "job opening", "position available",
            "we're looking for", "join our team", "now hiring"
        ]
        if any(indicator in text_lower for indicator in hiring_indicators):
            return "hiring"
        
        # Check for tech/industry posts
        tech_indicators = [
            "ai", "machine learning", "data science", "python", "software",
            "engineering", "developer", "programming"
        ]
        if any(indicator in text_lower for indicator in tech_indicators):
            return "tech"
        
        return "general"

    def generate_comment(self, post_text, post_url=None):
        if not post_text or len(post_text) < 10:
            return None
            
        try:
            # Clean the post text before processing
            cleaned_post_text = self.clean_post_text(post_text)
            
            # Prepare the request payload according to the expected API format
            payload = {
                'post_text': cleaned_post_text,
                'source_linkedin_url': post_url or '',
                'comment_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            }
            
            self.debug_log(f"Sending request to comment API: {json.dumps(payload, indent=2)}", "DEBUG")
            print(f"[APP_OUT]🌐 Calling backend API: {self.backend_url}")
            print(f"[APP_OUT]📤 Request payload: {json.dumps(payload, indent=2)}")
            
            # Make the API request
            response = requests.post(
                self.backend_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            print(f"[APP_OUT]📨 API Response: Status {response.status_code}")
            
            # Get Calendly link from config with fallback
            calendly_link = self.config.get('calendly_link', '')
            
            # Check if the request was successful
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict) and 'comment' in data:
                        comment = data['comment']
                        print(f"[APP_OUT]✅ Generated comment: {comment[:100]}...")
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
            print(f"[APP_OUT]❌ API call failed: Status {response.status_code}")
            print(f"[APP_OUT]📄 Response: {response.text}")
            self.debug_log(
                f"Failed to generate comment. Status: {response.status_code}, Response: {response.text}",
                "ERROR"
            )
            
        except requests.exceptions.RequestException as e:
            print(f"[APP_OUT]🌐 Network error calling backend: {str(e)}")
            self.debug_log(f"Network error while generating comment: {str(e)}", "ERROR")
        except Exception as e:
            print(f"[APP_OUT]❌ Error generating comment: {str(e)}")
            self.debug_log(f"Unexpected error generating comment: {str(e)}", "ERROR")
        
        # Fallback to simple comment if API call fails, with Calendly link if available
        fallback_comment = f"Great post! As someone with experience in {self.user_bio[:50]}..., I found your insights valuable."
        calendly_link = self.config.get('calendly_link', '')
        if calendly_link and calendly_link not in fallback_comment:
            fallback_comment = f"{fallback_comment}\n\nIf you'd like to discuss this further, feel free to book a call with me: {calendly_link}"
        return fallback_comment



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

# === CRITICAL MISSING FUNCTIONS FOR POST EVALUATION ===
def calculate_post_score(post_text, author_name=None, time_filter=None):
    """
    Calculate a score for a post based on various factors to prioritize posts from hiring managers.
    Uses FIXED scoring method without problematic normalization.
    
    Args:
        post_text (str): The text content of the post
        author_name (str, optional): The name of the post author
        time_filter (str, optional): The time filter from URL ('past-24h', 'past-week', 'past-month')
    
    Returns:
        float: A score between 0 and 100, with higher scores indicating higher priority
    """
    if not post_text:
        return 0
    
    # Clean the post text for consistent processing
    cleaned_post_text = ' '.join(post_text.strip().split())
    
    total_score = 0
    post_text_lower = cleaned_post_text.lower()
    
    # Log scoring details for debugging
    score_breakdown = {
        'metadata': {
            'text_length': len(cleaned_post_text),
            'word_count': len(cleaned_post_text.split()),
            'has_author': bool(author_name),
            'time_filter': time_filter
        }
    }
    
    # Calculate scores for each category - FIXED scoring method
    for category, config_data in POST_SCORING_CONFIG.items():
        weight = config_data['weight']
        keywords = config_data.get('keywords', [])
        search_author = config_data.get('search_author', False)
        
        # Skip author-based categories if no author name provided
        if search_author and not author_name:
            score_breakdown[category] = {
                'matches': 0,
                'score': 0,
                'weight': weight,
                'skipped': 'no_author_name'
            }
            continue
            
        # Determine text to search in based on category configuration
        search_text = author_name.lower() if search_author and author_name else post_text_lower
        
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
            'weight': weight,
            'search_target': 'author_name' if search_author else 'post_content'
        }
    
    # Add length bonus (not penalty)
    words = len(cleaned_post_text.split())
    if words >= 50:
        total_score += 5  # Bonus for substantial posts
    
    score_breakdown['length'] = {
        'words': words,
        'score': 5 if words >= 50 else 0
    }
    
    # Apply time-based scoring multiplier
    time_multiplier = 1.0
    if time_filter:
        time_multiplier = get_time_based_score(time_filter)
        total_score *= time_multiplier
        score_breakdown['time_bonus'] = {
            'filter': time_filter,
            'multiplier': time_multiplier,
            'boost_percentage': round((time_multiplier - 1.0) * 100, 1)
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

def should_comment_on_post(post_text, author_name=None, hours_ago=999, min_score=60, time_filter=None):
    """Determine if a post is worth commenting on based on score."""
    score = calculate_post_score(post_text, author_name, time_filter)
    print(f"[APP_OUT]⚖️ Post scored: {score}/100 (min required: {min_score})")
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

def sort_posts_by_priority(driver, posts, time_filter=None):
    """Sort posts by priority based on score."""
    posts_with_data = []
    
    print(f"[APP_OUT]📊 Analyzing {len(posts)} posts for priority scoring...")
    
    for i, post in enumerate(posts):
        try:
            # Extract post data
            hours_ago = extract_time_posted(post)
            author_name = extract_author_name(post)
            
            # Try to get post text for scoring (without expanding yet)
            post_text = post.text[:500] if post.text else ""  # Preview for scoring
            
            # Calculate score with time-based multiplier
            score = calculate_post_score(post_text, author_name, time_filter)
            
            posts_with_data.append({
                'element': post,
                'hours_ago': hours_ago,
                'score': score,
                'author': author_name,
                'preview_text': post_text[:100]
            })
            
            print(f"[APP_OUT]📋 Post {i+1}: Score {score:.1f}, Author: {author_name or 'Unknown'}")
            
        except Exception as e:
            debug_log(f"Error processing post for sorting: {e}", "SORT")
            continue
    
    # Sort by score (descending)
    posts_with_data.sort(key=lambda x: -x['score'])
    
    if posts_with_data:
        print(f"[APP_OUT]✨ Sorted {len(posts_with_data)} posts by priority - Top score: {posts_with_data[0]['score']:.1f}")
    debug_log(f"Sorted {len(posts_with_data)} posts by priority", "SORT")
    return posts_with_data

def main():
    """Main execution function that continuously cycles through URLs while respecting limits."""
    global MAX_DAILY_COMMENTS, MAX_SESSION_COMMENTS, SCROLL_PAUSE_TIME, JOB_SEARCH_KEYWORDS
    global LINKEDIN_EMAIL, LINKEDIN_PASSWORD, DEBUG_MODE, SEARCH_URLS, CALENDLY_LINK, USER_BIO
    # ... rest of the code remains the same ...
    global comment_generator, MAX_SCROLL_CYCLES, MAX_COMMENT_WORDS, MIN_COMMENT_DELAY, SHORT_SLEEP_SECONDS
    
    print("[APP_OUT]🚀 Starting LinkedIn Commenter...")
    print("[APP_OUT]Loading configuration...")
    
    # Initialize global CONFIG by calling get_config() which calls load_config_from_args()
    try:
        get_config() # This populates the global CONFIG variable
        if CONFIG is None:
            err_msg = "[FATAL] Global CONFIG is None after get_config(). Critical configuration error. Exiting."
            print(f"[APP_OUT]❌ {err_msg}")
            print(err_msg)
            try: debug_log(err_msg, "ERROR") # Attempt to log if debug_log is available
            except NameError: pass
            sys.exit(1)
        
        DEBUG_MODE = CONFIG.get('debug_mode', False) # Default to False if not in config
        print("[APP_OUT]✅ Configuration loaded successfully")
        debug_log(f"Starting main function. Loaded CONFIG keys: {list(CONFIG.keys()) if CONFIG else 'None'}", "DEBUG")

    except SystemExit: # Catch sys.exit calls from within get_config/load_config_from_args
        raise # Re-raise to ensure script terminates
    except Exception as config_error:
        err_msg = f"[FATAL] Unhandled error during configuration loading: {config_error}. Exiting."
        print(f"[APP_OUT]❌ {err_msg}")
        print(err_msg)
        try: debug_log(f"{err_msg} Traceback: {traceback.format_exc() if 'traceback' in globals() else ''}", "ERROR")
        except NameError: pass 
        sys.exit(1)

    print("[APP_OUT]🔧 Validating configuration...")
    
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

    # Initialize tech relevance keywords with expansion from job keywords
    initialize_tech_relevance_keywords(JOB_SEARCH_KEYWORDS)

    # Critical: Validate essential configuration
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        error_msg = "LinkedIn email or password not found in the configuration (expected under 'linkedin_credentials'). Script cannot proceed."
        print(f"[APP_OUT]❌ {error_msg}")
        debug_log(f"[FATAL] {error_msg} Please check your configuration. Exiting.", "ERROR")
        print(f"[FATAL] {error_msg} Please check your configuration. Exiting.")
        sys.exit(1)
    
    print(f"[APP_OUT]📧 LinkedIn credentials: {'✅ Valid' if LINKEDIN_EMAIL else '❌ Missing'}")
    print(f"[APP_OUT]👤 User bio: {'✅ Set (' + str(len(USER_BIO)) + ' chars)' if USER_BIO else '⚠️ Not set'}")
    print(f"[APP_OUT]🔍 Job keywords: {len(JOB_SEARCH_KEYWORDS)} configured")
    print(f"[APP_OUT]📅 Calendly link: {'✅ Set' if CALENDLY_LINK else '⚠️ Not set'}")
    
    debug_log(f"LinkedIn Email: {'Set' if LINKEDIN_EMAIL else 'Not Set'}", "DEBUG")
    debug_log(f"User Bio length: {len(USER_BIO) if USER_BIO else 'Not Set'}", "DEBUG")
    debug_log(f"Job Keywords: {JOB_SEARCH_KEYWORDS}", "DEBUG")
    debug_log(f"Calendly Link: {CALENDLY_LINK if CALENDLY_LINK else 'Not Set'}", "DEBUG")
    debug_log(f"Direct Search URLs from config: {SEARCH_URLS}", "DEBUG")

    # If specific search URLs are not provided directly in config, try to generate them from keywords
    if not SEARCH_URLS and JOB_SEARCH_KEYWORDS:
        print("[APP_OUT]🔗 Generating search URLs from job keywords...")
        debug_log(f"No direct 'search_urls' in config. Generating from 'job_keywords': {JOB_SEARCH_KEYWORDS}", "INFO")
        SEARCH_URLS = get_search_urls_for_keywords(JOB_SEARCH_KEYWORDS)
        print(f"[APP_OUT]✅ Generated {len(SEARCH_URLS)} search URLs")
        debug_log(f"Generated SEARCH_URLS: {SEARCH_URLS}", "DEBUG")
    
    # Critical check: If no SEARCH_URLS are available now (neither direct nor generated), script cannot proceed.
    if not SEARCH_URLS:
        error_msg = "No 'search_urls' found in config and no 'job_keywords' provided/effective to generate them. Script cannot proceed."
        print(f"[APP_OUT]❌ {error_msg}")
        debug_log(f"[FATAL] {error_msg} Please check your configuration file. Exiting.", "ERROR")
        print(f"[FATAL] {error_msg} Please check your configuration file. Exiting.")
        sys.exit(1)
    
    print(f"[APP_OUT]🎯 Ready with {len(SEARCH_URLS)} search URLs")
    debug_log(f"Final SEARCH_URLS to be used (before optimization): {SEARCH_URLS}", "INFO")
    
    # Add restart counter to prevent infinite restart loops
    restart_count = 0
    max_restarts = 10
    
    # Define cycle_break to control the sleep duration between cycles
    cycle_break = 1  # Default value, adjust as needed
    
    while restart_count < max_restarts:  # Outer loop for automatic restarts with limit
        restart_count += 1
        print(f"[APP_OUT]🔄 Session {restart_count}/{max_restarts}")
        debug_log(f"Restart attempt {restart_count}/{max_restarts}", "INFO")
        driver = None
        try:
            debug_log("[START] Starting LinkedIn Commenter", "INFO")
            
            # Initialize comment counters
            session_comments = 0
            daily_comments = 0
            
            print("[APP_OUT]⚙️ Initializing components...")
            
            # Initialize search performance tracker
            try:
                search_tracker = SearchPerformanceTracker()
                debug_log("[INIT] Initialized search performance tracker", "INFO")
            except Exception as tracker_error:
                print(f"[APP_OUT]❌ Failed to initialize search tracker: {tracker_error}")
                debug_log(f"[ERROR] Failed to initialize search tracker: {tracker_error}", "ERROR")
                raise
            
            # NEW: Initialize behavioral pattern manager for ultra-stealth behavior
            try:
                print("[APP_OUT]🧠 Initializing behavioral pattern manager...")
                behavioral_manager = BehavioralPatternManager()
                activity_multiplier = behavioral_manager.get_current_activity_multiplier()
                print(f"[APP_OUT]📊 Behavioral profile: {behavioral_manager.session_characteristics['type']} session (activity: {activity_multiplier:.2f}x)")
                debug_log(f"[INIT] Initialized behavioral pattern manager with {behavioral_manager.session_characteristics['type']} session profile", "BEHAVIORAL")
            except Exception as behavioral_error:
                print(f"[APP_OUT]❌ Failed to initialize behavioral manager: {behavioral_error}")
                debug_log(f"[ERROR] Failed to initialize behavioral manager: {behavioral_error}", "ERROR")
                raise
            
            # Initialize comment generator with job keywords
            try:
                print("[APP_OUT]🤖 Initializing AI comment generator...")
                debug_log("[INIT] Initializing comment generator", "DEBUG")
                comment_generator = CommentGenerator(
                    user_bio=USER_BIO,
                    job_keywords=JOB_SEARCH_KEYWORDS
                )
                print("[APP_OUT]✅ Comment generator ready")
                debug_log("[INIT] Comment generator initialized with job keywords", "DEBUG")
            except Exception as gen_error:
                print(f"[APP_OUT]❌ Failed to initialize comment generator: {gen_error}")
                debug_log(f"[ERROR] Failed to initialize comment generator: {gen_error}", "ERROR")
                raise
            
            # Initialize browser driver
            try:
                print("[APP_OUT]🌐 Starting Chrome browser...")
                debug_log("[INIT] Initializing browser driver", "DEBUG")
                driver = setup_chrome_driver()
                print("[APP_OUT]✅ Browser ready")
                debug_log("[INIT] Browser driver initialized successfully", "DEBUG")
            except Exception as driver_error:
                print(f"[APP_OUT]❌ Failed to initialize browser: {driver_error}")
                debug_log(f"[ERROR] Failed to initialize browser driver: {driver_error}", "ERROR")
                debug_log(f"[ERROR] Driver error details: {traceback.format_exc()}", "ERROR")
                raise
            
            # Verify login
            print("[APP_OUT]🔐 Verifying LinkedIn login...")
            debug_log("[LOGIN] Verifying LinkedIn login status...", "INFO")
            print("Verifying LinkedIn login status...")
            
            if not ensure_logged_in(driver):
                print("[APP_OUT]❌ Login failed - unable to establish session")
                debug_log("Could not establish a logged-in session. Exiting cycle.", "FATAL")
                # Break the inner while loop to allow the outer restart loop to take over
                break

            while True:  # Inner loop for normal operation
                try:
                    # Check if browser is still responsive before each cycle
                    _ = driver.current_url
                except Exception:
                    print("[APP_OUT]⚠️ Browser connection lost, reinitializing...")
                    debug_log("Browser connection lost, reinitializing...", "WARN")
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass
                    # Re-initialize driver and re-verify login
                    driver = setup_chrome_driver()
                    if not ensure_logged_in(driver):
                        print("[APP_OUT]❌ Re-login failed after browser crash")
                        debug_log("Re-login failed after browser crash. Breaking inner loop.", "FATAL")
                        break # Exit the inner while loop to trigger a full restart
                    else:
                        print("[APP_OUT]✅ Re-login successful")
                        debug_log("Re-login successful.", "INFO")
                        
                debug_log("Login verified successfully", "LOGIN")
                print("[APP_OUT]✅ Login successful, proceeding to search results...")

                # Get active URLs from the tracker
                current_hour = datetime.now().hour
                active_urls = search_tracker.optimize_search_urls(SEARCH_URLS, current_hour)
                        
                if not active_urls:
                    print("[APP_OUT]⚠️ No active URLs, using default search URLs")
                    debug_log("No active URLs to process, using default search URLs", "WARNING")
                    active_urls = SEARCH_URLS
                            
                debug_log(f"Active URLs to process: {active_urls}", "DEBUG")
                print(f"[APP_OUT]🔍 Processing {len(active_urls)} search URLs...")

                # Process each URL
                for i, url in enumerate(active_urls, 1):
                    print(f"[APP_OUT]📍 Processing URL {i}/{len(active_urls)}")
                    debug_log(f"Navigating to search URL: {url}", "NAVIGATION")
                    print(f"[APP_OUT]🔗 Navigating to: {url}")
                    if session_comments >= MAX_SESSION_COMMENTS:
                        print(f"[APP_OUT]🛑 Session limit reached ({MAX_SESSION_COMMENTS} comments)")
                        debug_log(f"Session comment limit reached ({MAX_SESSION_COMMENTS})", "LIMIT")
                        break

                    if daily_comments >= MAX_DAILY_COMMENTS:
                        print(f"[APP_OUT]🛑 Daily limit reached ({MAX_DAILY_COMMENTS} comments) - waiting until midnight")
                        debug_log(f"Daily comment limit reached ({MAX_DAILY_COMMENTS})", "LIMIT")
                        sleep_until_midnight_edt()
                        daily_comments = 0  # Reset counter at midnight
                        continue

                    # ========== ROBUST ANTI-BOT NAVIGATION ==========
                    try:
                        print("[APP_OUT]🚀 Loading search results...")
                        
                        # 1. Pre-navigation stealth delay
                        pre_nav_delay = random.uniform(5, 12)
                        debug_log(f"STEALTH: Pre-navigation delay: {pre_nav_delay:.1f}s", "STEALTH")
                        time.sleep(pre_nav_delay)
                        
                        # 2. Realistic navigation pattern for first URL
                        if i == 1:  # First URL only - establish human browsing pattern
                            debug_log("STEALTH: Establishing human browsing pattern...", "STEALTH")
                            
                            # Visit LinkedIn homepage first
                            driver.get("https://www.linkedin.com")
                            time.sleep(random.uniform(6, 10))
                            
                            # Simulate human reading behavior
                            try:
                                # Random scrolls to simulate reading homepage
                                for _ in range(random.randint(2, 4)):
                                    scroll_amount = random.randint(200, 600)
                                    driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                                    time.sleep(random.uniform(1.5, 3.5))
                                
                                # Random mouse movement simulation
                                ActionChains(driver).move_by_offset(
                                    random.randint(100, 400), 
                                    random.randint(100, 300)
                                ).perform()
                                time.sleep(random.uniform(0.8, 2.0))
                                
                                # Scroll back to top
                                driver.execute_script("window.scrollTo(0, 0);")
                                time.sleep(random.uniform(2, 4))
                            except:
                                pass  # Mouse/scroll simulation not critical
                        
                        # 3. Navigate to target URL with stealth measures
                        debug_log(f"STEALTH: Navigating to target URL: {url}", "STEALTH")
                        driver.get(url)
                        print(f"[APP_OUT]🌐 Navigated to: {url}")
                        
                        # 4. Extended human-like page load waiting
                        initial_wait = random.uniform(8, 15)
                        debug_log(f"STEALTH: Initial page load wait: {initial_wait:.1f}s", "STEALTH")
                        time.sleep(initial_wait)
                        
                        # 5. Comprehensive bot detection checks
                        current_url_check = driver.current_url.lower()
                        page_source_check = driver.page_source.lower()
                        
                        bot_detection_indicators = [
                            "challenge", "blocked", "captcha", "security", "verify", 
                            "unusual activity", "rate limit", "temporarily unavailable",
                            "access denied", "forbidden", "bot", "automation detected",
                            "suspicious activity", "please try again later"
                        ]
                        
                        is_bot_detected = any(indicator in current_url_check or indicator in page_source_check 
                                            for indicator in bot_detection_indicators)
                        
                        if is_bot_detected:
                            debug_log("STEALTH: Bot detection triggered - implementing countermeasures", "WARNING")
                            print(f"[APP_OUT]🛡️ Bot detection triggered - taking defensive action...")
                            
                            # AGGRESSIVE COUNTERMEASURES
                            # Phase 1: Immediate evasion
                            extended_delay = random.uniform(90, 180)
                            debug_log(f"STEALTH: Phase 1 - Extended evasion delay: {extended_delay:.1f}s", "STEALTH")
                            time.sleep(extended_delay)
                            
                            # Phase 2: Human behavior simulation
                            try:
                                debug_log("STEALTH: Phase 2 - Simulating human browsing patterns", "STEALTH")
                                
                                # Visit multiple innocent pages to appear human
                                innocent_pages = [
                                    "https://www.google.com",
                                    "https://www.linkedin.com",
                                    "https://www.linkedin.com/feed"
                                ]
                                
                                for page in innocent_pages:
                                    driver.get(page)
                                    time.sleep(random.uniform(15, 30))
                                    
                                    # Simulate reading and interaction
                                    try:
                                        # Random scrolling
                                        for _ in range(random.randint(3, 6)):
                                            scroll_amount = random.randint(300, 800)
                                            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                                            time.sleep(random.uniform(2, 5))
                                        
                                        # Random mouse movements
                                        ActionChains(driver).move_by_offset(
                                            random.randint(50, 300), 
                                            random.randint(50, 300)
                                        ).perform()
                                        time.sleep(random.uniform(1, 3))
                                        
                                        driver.execute_script("window.scrollTo(0, 0);")
                                        time.sleep(random.uniform(2, 4))
                                    except:
                                        pass
                                
                                # Phase 3: Re-attempt target URL
                                debug_log("STEALTH: Phase 3 - Re-attempting target URL", "STEALTH")
                                driver.get(url)
                                time.sleep(random.uniform(10, 20))
                                
                            except Exception as countermeasure_error:
                                debug_log(f"STEALTH: Countermeasure error: {countermeasure_error}", "WARNING")
                            
                            # Final check - if still blocked, skip this URL
                            final_check = driver.current_url.lower()
                            final_source = driver.page_source.lower()
                            if any(indicator in final_check or indicator in final_source 
                                 for indicator in bot_detection_indicators):
                                debug_log("STEALTH: Still blocked after countermeasures - skipping URL", "WARNING")
                                print("[APP_OUT]🚫 Unable to bypass bot detection - skipping this URL")
                                search_tracker.record_url_performance(url, success=False, comments_made=0, error=True)
                                continue
                        
                        # 6. Additional human behavior simulation
                        debug_log("STEALTH: Post-navigation human simulation", "STEALTH")
                        try:
                            # Simulate reading the page before interacting
                            reading_time = random.uniform(3, 8)
                            time.sleep(reading_time)
                            
                            # Small random scrolls to simulate reading
                            for _ in range(random.randint(1, 3)):
                                scroll_amount = random.randint(100, 400)
                                driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                                time.sleep(random.uniform(1, 3))
                            
                            # Return to top of page
                            driver.execute_script("window.scrollTo(0, 0);")
                            time.sleep(random.uniform(1, 2))
                        except:
                            pass  # Not critical if this fails
                        
                        # Check what page we actually landed on
                        current_url = driver.current_url
                        page_title = driver.title
                        print(f"[APP_OUT]📄 Current URL: {current_url}")
                        print(f"[APP_OUT]📋 Page title: {page_title}")
                        
                        # Check for common LinkedIn issues
                        page_source_snippet = driver.page_source[:1000].lower()
                        
                        # Check for subscription/premium prompts
                        if any(keyword in page_source_snippet for keyword in ['premium', 'subscription', 'upgrade', 'linkedin premium']):
                            print("[APP_OUT]💰 DETECTED: Premium/subscription prompt on page")
                            debug_log("Premium subscription prompt detected", "WARNING")
                        
                        # Check for login issues
                        if any(keyword in page_source_snippet for keyword in ['sign in', 'log in', 'join linkedin']):
                            print("[APP_OUT]🔐 DETECTED: Login required")
                            debug_log("Login required - authentication issue", "WARNING")
                        
                        # Check for rate limiting/blocking
                        if any(keyword in page_source_snippet for keyword in ['blocked', 'rate limit', 'too many requests', 'captcha']):
                            print("[APP_OUT]🚫 DETECTED: Possible rate limiting or blocking")
                            debug_log("Rate limiting or blocking detected", "WARNING")
                        
                        # Look for the search results container with timeout
                        print("[APP_OUT]⏳ Waiting for search results container...")
                        WebDriverWait(driver, 30).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".reusable-search__entity-result-list"))
                        )
                        print("[APP_OUT]✅ Search results container loaded")
                        
                        # Additional verification - check if we actually have content
                        try:
                            result_list = driver.find_element(By.CSS_SELECTOR, ".reusable-search__entity-result-list")
                            all_results = result_list.find_elements(By.CSS_SELECTOR, "*")
                            print(f"[APP_OUT]📊 Found {len(all_results)} elements in search results container")
                            debug_log(f"Search results container has {len(all_results)} child elements", "NAVIGATION")
                        except Exception as check_e:
                            print(f"[APP_OUT]⚠️ Could not verify search results content: {check_e}")
                        
                        debug_log("Search results page loaded and is visible.", "NAVIGATION")
                    except TimeoutException:
                        print("[APP_OUT]⚠️ TIMEOUT: Search results container not found")
                        debug_log(f"TimeoutException: No search results found or page did not load for URL: {url}", "WARNING")
                        
                        # Comprehensive page analysis when timeout occurs
                        try:
                            current_url_timeout = driver.current_url
                            page_title_timeout = driver.title
                            print(f"[APP_OUT]📄 Timeout - Current URL: {current_url_timeout}")
                            print(f"[APP_OUT]📋 Timeout - Page title: {page_title_timeout}")
                            
                            # Check what's actually on the page
                            page_source = driver.page_source.lower()
                            
                            if "premium" in page_source or "subscription" in page_source:
                                print("[APP_OUT]💰 TIMEOUT CAUSE: Premium subscription required")
                            elif "sign in" in page_source or "log in" in page_source:
                                print("[APP_OUT]🔐 TIMEOUT CAUSE: Not logged in properly")  
                            elif "no results" in page_source:
                                print("[APP_OUT]📭 TIMEOUT CAUSE: No search results found")
                            elif "blocked" in page_source or "rate limit" in page_source:
                                print("[APP_OUT]🚫 TIMEOUT CAUSE: Blocked or rate limited")
                            else:
                                print("[APP_OUT]❓ TIMEOUT CAUSE: Unknown - page loaded but selector not found")
                                # Look for alternative selectors
                                alternative_selectors = [
                                    ".search-results-container",
                                    ".search-results",
                                    ".feed-shared-update-v2",
                                    ".feed-shared-update",
                                    "[data-test-id='search-results']",
                                    ".artdeco-card"
                                ]
                                for selector in alternative_selectors:
                                    try:
                                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                        if elements:
                                            print(f"[APP_OUT]🔍 Found {len(elements)} elements with selector: {selector}")
                                    except:
                                        pass
                            
                        except Exception as timeout_debug_e:
                            print(f"[APP_OUT]❌ Error during timeout analysis: {timeout_debug_e}")
                        
                        search_tracker.record_url_performance(url, success=False, comments_made=0, error=True)
                        continue # Move to the next URL
                    except Exception as nav_e:
                        print(f"[APP_OUT]❌ Error loading page: {nav_e}")
                        debug_log(f"Error navigating to {url} or waiting for results: {nav_e}", "ERROR")
                        search_tracker.record_url_performance(url, success=False, comments_made=0, error=True)
                        continue # Move to the next URL

                    try:
                        print("[APP_OUT]🔍 Starting post analysis and commenting...")
                        print("[APP_OUT]🚀 CALLING process_posts() function...")
                        debug_log("About to call process_posts() function", "DEBUG")
                        # Process posts on the current page
                        posts_processed, hiring_posts_found = process_posts(driver)
                        print(f"[APP_OUT]✅ process_posts() returned: {posts_processed} posts processed, {hiring_posts_found} hiring posts found")
                        debug_log(f"process_posts() completed: {posts_processed} processed, {hiring_posts_found} hiring posts", "DEBUG")
                        if posts_processed > 0:
                            session_comments += posts_processed
                            daily_comments += posts_processed
                        search_tracker.record_url_performance(url, success=True, comments_made=posts_processed)
                        
                        # ENHANCED: Behavioral pattern-based delays and breaks
                        try:
                            # Apply behavioral activity multiplier to delay
                            base_delay = random.uniform(MIN_COMMENT_DELAY, MIN_COMMENT_DELAY * 2)
                            activity_multiplier = behavioral_manager.get_current_activity_multiplier()
                            adjusted_delay = base_delay / max(0.5, activity_multiplier)  # More active = shorter delays
                            
                            debug_log(f"BEHAVIORAL: Inter-URL delay: {adjusted_delay:.1f}s (base: {base_delay:.1f}s, multiplier: {activity_multiplier:.2f})", "BEHAVIORAL")
                            time.sleep(adjusted_delay)
                            
                            # Check for behavioral breaks
                            if behavioral_manager.should_take_break():
                                break_duration = behavioral_manager.get_break_duration()
                                print(f"[APP_OUT]☕ Taking behavioral break: {break_duration:.1f}s")
                                debug_log(f"BEHAVIORAL: Taking break for {break_duration:.1f}s", "BEHAVIORAL")
                                behavioral_manager.log_behavior('break', {'duration': break_duration})
                                time.sleep(break_duration)
                            
                            # Perform human-like distraction based on behavioral patterns
                            if behavioral_manager.should_show_distraction():
                                debug_log("BEHAVIORAL: Performing behavioral distraction", "BEHAVIORAL")
                                human_like_distraction(driver)
                                behavioral_manager.log_behavior('distraction', {'type': 'human_like_distraction'})
                        except Exception as behavioral_error:
                            # Fallback to original behavior if behavioral manager fails
                            debug_log(f"BEHAVIORAL: Error in behavioral patterns, using fallback: {behavioral_error}", "WARNING")
                            time.sleep(random.uniform(MIN_COMMENT_DELAY, MIN_COMMENT_DELAY * 2))
                            if random.random() < 0.25:
                                human_like_distraction(driver)

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
    """
    Generate a list of LinkedIn search URLs for each keyword provided.
    Handles keywords as a list of strings or a single comma-separated string.
    """
    if not keywords:
        return []

    keyword_list = []
    if isinstance(keywords, str):
        # Split a comma-separated string into a list of keywords
        keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()]
    elif isinstance(keywords, list):
        # It's already a list
        keyword_list = keywords
    
    if not keyword_list:
        debug_log("Keyword list is empty after processing.", "WARNING")
        return []

    urls = []
    time_filters = ["past-24h", "past-month"]
    
    # Iterate over each individual keyword
    for keyword in keyword_list:
        debug_log(f"Generating URLs for keyword: '{keyword}'", "DEBUG")
        for time_filter in time_filters:
            # Add hiring-focused URL
            hiring_url = construct_linkedin_search_url(
                f'"{keyword}" hiring', # Use quotes for exact phrase matching
                time_filter
            )
            if hiring_url:
                urls.append(hiring_url)
            
            # Add recruiting-focused URL
            recruiting_url = construct_linkedin_search_url(
                f'"{keyword}" recruiting', # Use quotes for exact phrase matching
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

def find_posts(driver):
    """
    Finds all the post container elements on the current page.
    Uses multiple selectors for robustness against UI changes and different page layouts.
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        list: List of WebElement objects representing posts
    """
    print("[APP_OUT]🔥 FIND_POSTS FUNCTION CALLED - STARTING SEARCH...")
    debug_log("Starting post search on current page...", "SEARCH")
    print("[APP_OUT]🔍 Searching for posts on page...")
    posts = []
    
    # Wait for the page to load and any spinners to disappear
    try:
        WebDriverWait(driver, 10).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".artdeco-loader"))
        )
    except TimeoutException:
        debug_log("Loader spinner still present or not found", "DEBUG")
    
    # List of selectors to try, in order of preference
    selectors = [
        # PRIMARY SELECTOR - This should match what we wait for in main()
        {
            'type': 'css',
            'value': '.reusable-search__entity-result-list .reusable-search__result-container',
            'name': 'search results within entity list'
        },
        {
            'type': 'css',
            'value': '.reusable-search__result-container',
            'name': 'search results container'
        },
        {
            'type': 'css',
            'value': '.reusable-search__entity-result-list',
            'name': 'entity result list (same as main wait)'
        },
        # Updated LinkedIn content search selectors
        {
            'type': 'css',
            'value': '.feed-shared-update-v2',
            'name': 'feed shared updates v2'
        },
        {
            'type': 'css',
            'value': '.scaffold-finite-scroll__content .feed-shared-update-v2',
            'name': 'scrollable feed updates'
        },
        {
            'type': 'css',
            'value': '.search-results-container',
            'name': 'legacy search container'
        },
        {
            'type': 'css',
            'value': '.update-components-actor__container',
            'name': 'post containers'
        },
        # Feed-specific selectors
        {
            'type': 'xpath',
            'value': "//div[contains(@class, 'feed-shared-update-v2')]",
            'name': 'feed shared updates'
        },
        {
            'type': 'xpath',
            'value': "//li[contains(@class, 'occludable-update')]",
            'name': 'occludable updates'
        },
        # Additional fallback selectors
        {
            'type': 'css',
            'value': '[data-urn]',
            'name': 'data-urn elements'
        },
        {
            'type': 'xpath',
            'value': "//div[contains(@class, 'feed-shared-update-v2') or contains(@class, 'update-components-actor')]",
            'name': 'combined feed elements'
        },
        {
            'type': 'css',
            'value': '.ember-view.occludable-update',
            'name': 'ember view updates'
        },
        # Content search specific selectors
        {
            'type': 'css',
            'value': '.search-content__result',
            'name': 'content search results'
        },
        {
            'type': 'css',
            'value': '.content-search-result',
            'name': 'content search result items'
        }
    ]
    
    print(f"[APP_OUT]🧪 Trying {len(selectors)} different post selectors...")
    
    # Try each selector in sequence
    for selector_index, selector in enumerate(selectors, 1):
        try:
            selector_type = selector['type']
            selector_value = selector['value']
            selector_name = selector['name']
            
            print(f"[APP_OUT]🔍 Attempt {selector_index}/{len(selectors)}: {selector_name}")
            debug_log(f"Trying selector: {selector_name} ({selector_value})", "SEARCH")
            
            # Wait briefly for elements to be present
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR if selector_type == 'css' else By.XPATH, selector_value)
                    )
                )
                print(f"[APP_OUT]✅ Selector found elements")
            except TimeoutException:
                print(f"[APP_OUT]⏰ Timeout waiting for {selector_name}")
                debug_log(f"Timeout waiting for {selector_name}", "DEBUG")
                continue
                
            # Find elements using the current selector
            posts = driver.find_elements(
                By.CSS_SELECTOR if selector_type == 'css' else By.XPATH,
                selector_value
            )
            
            if posts:
                print(f"[APP_OUT]📋 Found {len(posts)} elements with {selector_name}")
                debug_log(f"Found {len(posts)} posts using {selector_name}", "SEARCH")
                # Verify posts are actually visible and interactive
                visible_posts = [post for post in posts if is_element_visible(driver, post)]
                if visible_posts:
                    print(f"[APP_OUT]✅ {len(visible_posts)} posts are visible and interactive")
                    debug_log(f"{len(visible_posts)} posts are visible and interactive", "SEARCH")
                    return visible_posts
                else:
                    print(f"[APP_OUT]⚠️ Found posts are not visible/interactive, trying next selector")
                    debug_log("Found posts are not visible/interactive, trying next selector", "DEBUG")
            else:
                print(f"[APP_OUT]❌ No posts found with {selector_name}")
            
        except StaleElementReferenceException:
            print(f"[APP_OUT]🔄 Stale elements with {selector_name}, trying next")
            debug_log(f"Stale elements found with {selector_name}, trying next selector", "WARNING")
            continue
        except Exception as e:
            print(f"[APP_OUT]❌ Error with {selector_name}: {str(e)}")
            debug_log(f"Error with {selector_name}: {str(e)}", "WARNING")
            continue
    
    # If no posts found, try scrolling and searching again
    if not posts:
        print("[APP_OUT]📜 No posts found with any selector, trying scroll and retry...")
        debug_log("No posts found, attempting scroll and retry", "SEARCH")
        try:
            # Scroll down a bit
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Wait for potential lazy-loaded content
            
            # Try the first few selectors again after scrolling
            for selector in selectors[:5]:  # Only try top 5 after scroll
                try:
                    selector_type = selector['type']
                    selector_value = selector['value']
                    posts = driver.find_elements(
                        By.CSS_SELECTOR if selector_type == 'css' else By.XPATH,
                        selector_value
                    )
                    if posts:
                        visible_posts = [post for post in posts if is_element_visible(driver, post)]
                        if visible_posts:
                            print(f"[APP_OUT]✅ Found {len(visible_posts)} posts after scrolling")
                            debug_log(f"Found {len(visible_posts)} posts after scrolling", "SEARCH")
                            return visible_posts
                except Exception:
                    continue
        except Exception as e:
            print(f"[APP_OUT]❌ Error during scroll retry: {str(e)}")
            debug_log(f"Error during scroll retry: {str(e)}", "ERROR")
    
    # If still no posts, try taking a screenshot and check page source
    if not posts:
        print("[APP_OUT]📷 No posts found with any method, taking diagnostic screenshot...")
        debug_log("No posts found with any method", "WARNING")
        # Take a screenshot for debugging
        try:
            take_screenshot(driver, "no_posts_found")
            # Log some page info for debugging
            current_url = driver.current_url
            page_title = driver.title
            print(f"[APP_OUT]🔍 Current URL: {current_url}")
            print(f"[APP_OUT]📄 Page title: {page_title}")
            debug_log(f"Diagnostic - URL: {current_url}, Title: {page_title}", "DEBUG")
            
            # Check if there's any content at all
            all_divs = driver.find_elements(By.TAG_NAME, "div")
            print(f"[APP_OUT]📊 Total divs on page: {len(all_divs)}")
            
        except Exception as e:
            print(f"[APP_OUT]❌ Error during diagnostics: {e}")
    
    print(f"[APP_OUT]📝 Returning {len(posts)} posts")
    return posts

def is_element_visible(driver, element):
    """
    Check if an element is visible and interactive.
    
    Args:
        driver: Selenium WebDriver instance
        element: WebElement to check
        
    Returns:
        bool: True if element is visible and interactive
    """
    try:
        return (element.is_displayed() and 
                element.is_enabled() and
                element.location['y'] >= 0 and
                element.size['height'] > 0 and
                element.size['width'] > 0)
    except:
        return False

def process_posts(driver):
    """Process visible posts on the current page with continuous scrolling."""
    print("[APP_OUT]🔥 PROCESS_POSTS FUNCTION CALLED - STARTING...")
    debug_log("Starting post processing with continuous scrolling", "PROCESS")
    print("[APP_OUT]🔍 Processing LinkedIn posts...")
    posts_processed = 0
    hiring_posts_found = 0
    posts_commented = 0
    
    try:
        debug_log("[COMMENT] Beginning comment posting loop", "COMMENT")
        debug_log("Loading processed post IDs", "DATA")
        print("[APP_OUT]📊 Loading post history...")
        processed_log = load_log()
        comment_history = load_comment_history()
        print(f"[APP_OUT]📝 Loaded {len(processed_log)} processed posts and {len(comment_history)} comment records")
        debug_log(f"Loaded {len(processed_log)} processed posts and {len(comment_history)} comments", "DATA")
        
        # Get current URL and extract time filter
        current_url = driver.current_url
        time_filter = None
        if 'datePosted=' in current_url:
            try:
                time_filter = current_url.split('datePosted=')[1].split('&')[0].strip("\"'")
                debug_log(f"Extracted time filter from URL: {time_filter}", "DEBUG")
            except Exception as e:
                debug_log(f"Error extracting time filter from URL: {e}", "WARNING")
        
        print("[APP_OUT]🔄 Starting continuous scroll and post discovery...")
        
        # Continuous scrolling and post processing with better logic
        processed_posts_this_session = set()
        scroll_attempts = 0
        max_scroll_attempts = 50  # Increased from 10 to allow more scrolling
        posts_found_last_cycle = 0
        
        while scroll_attempts < max_scroll_attempts:
            print(f"[APP_OUT]🔄 SCROLL LOOP ITERATION {scroll_attempts + 1}/{max_scroll_attempts}")
            debug_log(f"Scroll attempt {scroll_attempts + 1}/{max_scroll_attempts}", "SCROLL")
            
            # Find posts with retry logic
            print(f"[APP_OUT]🔍 Calling find_posts() in scroll loop...")
            posts = find_posts(driver)
            print(f"[APP_OUT]📊 find_posts() returned {len(posts)} posts")
            current_post_count = len(posts)
            
            print(f"[APP_OUT]📋 Found {current_post_count} posts on current page (scroll {scroll_attempts + 1}/{max_scroll_attempts})")
            debug_log(f"Found {current_post_count} posts on page", "SEARCH")
            
            # If no posts found at all, try scrolling and searching again
            if current_post_count == 0:
                print("[APP_OUT]⚠️ No posts found, attempting scroll to load content...")
                debug_log("No posts found, attempting scroll to load content", "SEARCH")
                scroll_success = scroll_page(driver)
                print(f"[APP_OUT]📜 Scroll {'successful' if scroll_success else 'failed'}")
                time.sleep(3)
                posts = find_posts(driver)
                current_post_count = len(posts)
                print(f"[APP_OUT]📋 After scroll: found {current_post_count} posts")
                if current_post_count == 0:
                    print("[APP_OUT]⚠️ Still no posts found after scroll, may be end of content")
                    debug_log("Still no posts found after scroll, may be end of content", "SEARCH")
                    scroll_attempts += 1
                    continue
            
            # CRITICAL: Sort posts by priority using our scoring system
            if current_post_count > 0:
                print(f"[APP_OUT]📊 Sorting {current_post_count} posts by priority...")
                sorted_posts_data = sort_posts_by_priority(driver, posts, time_filter)
                print(f"[APP_OUT]✅ Posts sorted - processing in priority order")
            else:
                sorted_posts_data = []
            
            # Process each post in priority order (highest scores first)
            new_posts_processed = 0
            for post_index, post_data in enumerate(sorted_posts_data, 1):
                try:
                    post = post_data['element']
                    post_score = post_data['score']
                    author_name = post_data['author']
                    hours_ago = post_data['hours_ago']
                    
                    post_id, _ = compute_post_id(post)
                    
                    # Skip if already processed in this session or historically
                    if (post_id in processed_posts_this_session or 
                        post_id in processed_log or 
                        post_id in comment_history):
                        print(f"[APP_OUT]⏭️ Skipping already processed post {post_index}/{len(sorted_posts_data)}")
                        continue
                    
                    print(f"[APP_OUT]📝 Processing post {post_index}/{len(sorted_posts_data)} (Score: {post_score:.1f})...")
                    
                    # Add to processed set for this session
                    processed_posts_this_session.add(post_id)
                    
                    # Scroll post into view
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post)
                        time.sleep(1)
                    except Exception as e:
                        debug_log(f"Error scrolling post into view: {e}", "WARNING")
                        continue
                    
                    # Expand post content to get full text
                    expand_post(driver, post)
                    
                    # Extract full post data after expansion
                    post_text = get_post_text(driver, post)
                    
                    if not post_text or len(post_text.strip()) < 10:
                        debug_log(f"Post text too short or empty, skipping post {post_id}", "SKIP")
                        continue
                    
                    # Use the standalone should_comment_on_post function
                    should_comment, final_score = should_comment_on_post(post_text, author_name, hours_ago, min_score=50, time_filter=time_filter)
                    
                    if not should_comment:
                        print(f"[APP_OUT]⏭️ Skipping post - score {final_score:.1f} below threshold")
                        debug_log(f"Skipping post (score: {final_score} < 50)", "SKIP")
                        continue
                    
                    print(f"[APP_OUT]✨ High-priority post selected for commenting! (Score: {final_score:.1f})")
                    debug_log(f"Processing high-scoring post (score: {final_score})", "PROCESS")
                    posts_processed += 1
                    new_posts_processed += 1
                    processed_log.append(post_id)
                    
                    # Check if we already commented
                    if has_already_commented(driver, post):
                        print("[APP_OUT]⚠️ Already commented on this post, skipping...")
                        debug_log("Already commented on this post, skipping", "SKIP")
                        continue
                    
                    # Generate comment with retries
                    print("[APP_OUT]🤖 Generating personalized comment...")
                    debug_log("Generating comment", "GENERATE")
                    custom_message = None
                    for retry in range(3):
                        try:
                            custom_message = comment_generator.generate_comment(post_text, author_name)
                            if custom_message:
                                break
                            debug_log(f"Comment generation attempt {retry + 1} failed", "RETRY")
                            time.sleep(2)
                        except Exception as e:
                            debug_log(f"Comment generation error: {e}", "ERROR")
                            time.sleep(2)
                    
                    if not custom_message:
                        print("[APP_OUT]❌ Failed to generate comment after retries")
                        debug_log("Failed to generate comment after retries, skipping", "SKIP")
                        continue
                    
                    print(f"[APP_OUT]✍️ Comment generated: {custom_message[:50]}...")
                    debug_log(f"Generated comment: {custom_message[:100]}...", "DATA")
                    
                    # ========== STEALTH COMMENT POSTING ==========
                    print("[APP_OUT]📤 Posting comment with STEALTH measures...")
                    debug_log("STEALTH: Initiating advanced comment posting sequence", "COMMENT")
                    try:
                        # 1. Pre-comment human behavior simulation
                        pre_comment_delay = random.uniform(8, 18)
                        debug_log(f"STEALTH: Pre-comment preparation delay: {pre_comment_delay:.1f}s", "COMMENT")
                        print(f"[APP_OUT]🧠 Simulating human thought process...")
                        time.sleep(pre_comment_delay)
                        
                        # 2. Simulate reading the post again before commenting
                        try:
                            debug_log("STEALTH: Simulating re-reading post before commenting", "COMMENT")
                            # Scroll to post and simulate reading
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post)
                            time.sleep(random.uniform(3, 7))
                            
                            # Random small mouse movements (like focusing)
                            ActionChains(driver).move_by_offset(
                                random.randint(-30, 30), 
                                random.randint(-20, 20)
                            ).perform()
                            time.sleep(random.uniform(1, 3))
                        except:
                            pass  # Not critical
                        
                        # 3. Attempt comment posting with retry logic
                        success = post_comment(driver, post, custom_message)
                        
                        if success:
                            print("[APP_OUT]✅ Comment posted successfully!")
                            debug_log("STEALTH: Comment posted successfully", "SUCCESS")
                            posts_commented += 1
                            
                            # Save to comment history
                            comment_history[post_id] = {
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "message": custom_message,
                                "score": final_score
                            }
                            save_comment_history(comment_history)
                            
                            # 4. Extended post-comment human behavior
                            print(f"[APP_OUT]🎭 Simulating post-comment human behavior...")
                            debug_log("STEALTH: Post-comment human behavior simulation", "COMMENT")
                            
                            # Simulate checking the posted comment
                            verification_delay = random.uniform(5, 12)
                            debug_log(f"STEALTH: Comment verification delay: {verification_delay:.1f}s", "COMMENT")
                            time.sleep(verification_delay)
                            
                            # Random scroll to see the comment in context
                            try:
                                scroll_adjustment = random.randint(-200, 200)
                                driver.execute_script(f"window.scrollBy(0, {scroll_adjustment});")
                                time.sleep(random.uniform(2, 5))
                                
                                # Scroll back to original position
                                driver.execute_script(f"window.scrollBy(0, {-scroll_adjustment});")
                                time.sleep(random.uniform(1, 3))
                            except:
                                pass
                            
                            # 5. Extended inter-comment delay with human patterns
                            base_delay = random.uniform(45, 90)  # Much longer base delay
                            additional_delay = random.uniform(30, 60)  # Additional randomization
                            total_delay = base_delay + additional_delay
                            
                            print(f"[APP_OUT]⏱️ Taking extended human-like break: {total_delay:.1f}s")
                            debug_log(f"STEALTH: Extended inter-comment delay: {total_delay:.1f}s", "COMMENT")
                            
                            # Break the delay into chunks to simulate human activity
                            delay_chunks = 3
                            chunk_size = total_delay / delay_chunks
                            
                            for chunk in range(delay_chunks):
                                time.sleep(chunk_size)
                                
                                # Simulate occasional human activity during breaks
                                if random.random() < 0.4:  # 40% chance
                                    try:
                                        # Small mouse movement or scroll
                                        if random.random() < 0.5:
                                            ActionChains(driver).move_by_offset(
                                                random.randint(-50, 50), 
                                                random.randint(-30, 30)
                                            ).perform()
                                        else:
                                            mini_scroll = random.randint(-100, 100)
                                            driver.execute_script(f"window.scrollBy(0, {mini_scroll});")
                                        time.sleep(random.uniform(0.5, 2))
                                    except:
                                        pass
                        else:
                            print("[APP_OUT]❌ Failed to post comment")
                            debug_log("Failed to post comment", "ERROR")
                    except Exception as e:
                        print(f"[APP_OUT]❌ Exception during comment posting: {e}")
                        debug_log(f"Exception during comment posting: {e}", "ERROR")
                    
                    # Check comment limits
                    if posts_commented >= MAX_COMMENTS:
                        print(f"[APP_OUT]🛑 Reached maximum comments limit ({MAX_COMMENTS})")
                        debug_log(f"Reached max comments limit ({MAX_COMMENTS})", "LIMIT")
                        save_log(processed_log)
                        return posts_commented, hiring_posts_found
                    
                except Exception as e:
                    print(f"[APP_OUT]❌ Error processing post: {str(e)}")
                    debug_log(f"Error processing individual post: {str(e)}", "ERROR")
                    debug_log(traceback.format_exc(), "ERROR")
                    continue
            
            # Check if we processed new posts this cycle
            if new_posts_processed > 0:
                print(f"[APP_OUT]✅ Processed {new_posts_processed} new posts this cycle")
                debug_log(f"Processed {new_posts_processed} new posts this cycle", "PROGRESS")
                posts_found_last_cycle = current_post_count
            else:
                # No new posts processed, check if we found new posts at all
                if current_post_count <= posts_found_last_cycle:
                    debug_log("No new posts found, may have reached end of content", "SCROLL")
                    # Try a few more scrolls before giving up
                    if scroll_attempts > max_scroll_attempts - 5:
                        print("[APP_OUT]📄 Reached end of content, finishing...")
                        debug_log("Reached end of content, stopping", "COMPLETE")
                        break
                posts_found_last_cycle = current_post_count
            
            # Scroll down to load more posts with human-like behavior
            print("[APP_OUT]📜 Scrolling to load more posts...")
            debug_log("Scrolling to load more posts", "SCROLL")
            scroll_success = scroll_page(driver)
            if not scroll_success:
                debug_log("Scroll did not advance page position", "SCROLL")
            
            # Random delay between scroll cycles
            time.sleep(random.uniform(2, 5))
            scroll_attempts += 1
        
        print("[APP_OUT]💾 Saving progress logs...")
        debug_log("Saving final logs", "DATA")
        save_log(processed_log)
        save_comment_history(comment_history)
        print(f"[APP_OUT]📊 Session complete: {posts_processed} posts analyzed, {posts_commented} comments posted")
        debug_log(f"Processed {posts_processed} posts, commented on {posts_commented}", "SUMMARY")
        return posts_commented, hiring_posts_found
        
    except Exception as e:
        print(f"[APP_OUT]❌ Error in post processing: {str(e)}")
        debug_log(f"Error in process_posts: {str(e)}", "ERROR")
        debug_log(traceback.format_exc(), "ERROR")
        # Save what we have so far
        try:
            save_log(processed_log)
            save_comment_history(comment_history)
        except:
            pass
        return posts_commented, hiring_posts_found

def scroll_page(driver):
    """Scroll down the page incrementally to load more content with EXTREMELY human-like behavior."""
    debug_log("STEALTH: Performing advanced human-like scroll", "SCROLL")
    print("[APP_OUT]📜 Executing STEALTH scroll command...")
    try:
        # Get current position and viewport info
        old_position = driver.execute_script("return window.pageYOffset;")
        viewport_height = driver.execute_script("return window.innerHeight;")
        page_height = driver.execute_script("return document.body.scrollHeight;")
        
        print(f"[APP_OUT]📍 Current scroll position: {old_position}px")
        debug_log(f"STEALTH: Viewport={viewport_height}px, Page={page_height}px, Current={old_position}px", "SCROLL")
        
        # 1. Pre-scroll human behavior simulation
        pre_scroll_delay = random.uniform(2, 5)
        debug_log(f"STEALTH: Pre-scroll reading delay: {pre_scroll_delay:.1f}s", "SCROLL")
        time.sleep(pre_scroll_delay)
        
        # 2. Simulate mouse movement before scrolling (like hovering)
        try:
            ActionChains(driver).move_by_offset(
                random.randint(-50, 50), 
                random.randint(-30, 30)
            ).perform()
            time.sleep(random.uniform(0.3, 0.8))
        except:
            pass  # Mouse simulation not critical
        
        # 3. Multi-step scrolling pattern (humans don't scroll in one big jump)
        total_scroll_target = random.randint(600, 1200)
        scroll_steps = random.randint(2, 4)
        step_size = total_scroll_target // scroll_steps
        
        debug_log(f"STEALTH: Multi-step scroll - {scroll_steps} steps of ~{step_size}px each", "SCROLL")
        
        actual_scrolled = 0
        for step in range(scroll_steps):
            # Randomize each step slightly
            step_scroll = step_size + random.randint(-100, 100)
            
            # Ensure we don't scroll negative amounts
            if step_scroll < 100:
                step_scroll = 100
            
            # 4. Use realistic scroll methods with variation
            scroll_methods = [
                f"window.scrollBy(0, {step_scroll});",
                f"window.scrollTo(0, {old_position + actual_scrolled + step_scroll});",
                f"window.scrollBy({{top: {step_scroll}, behavior: 'smooth'}});",
            ]
            
            scroll_command = random.choice(scroll_methods)
            debug_log(f"STEALTH: Step {step+1}/{scroll_steps}: {scroll_command}", "SCROLL")
            
            try:
                driver.execute_script(scroll_command)
                actual_scrolled += step_scroll
                
                # 5. Human reading pause between scroll steps
                reading_pause = random.uniform(1.5, 4.0)
                debug_log(f"STEALTH: Reading pause: {reading_pause:.1f}s", "SCROLL")
                time.sleep(reading_pause)
                
                # 6. Occasional micro-scrolls (humans adjust their view)
                if random.random() < 0.3:  # 30% chance
                    micro_scroll = random.randint(-50, 50)
                    driver.execute_script(f"window.scrollBy(0, {micro_scroll});")
                    time.sleep(random.uniform(0.5, 1.0))
                    debug_log(f"STEALTH: Micro-scroll adjustment: {micro_scroll}px", "SCROLL")
            
            except Exception as step_error:
                debug_log(f"STEALTH: Step scroll error: {step_error}", "WARNING")
                continue
        
        # 7. Final position check and human behavior
        time.sleep(random.uniform(1, 2))
        new_position = driver.execute_script("return window.pageYOffset;")
        scroll_delta = new_position - old_position
        
        # 8. Simulate brief reading at new position
        if scroll_delta > 0:
            reading_time = random.uniform(2, 6)
            debug_log(f"STEALTH: Post-scroll reading time: {reading_time:.1f}s", "SCROLL")
            time.sleep(reading_time)
        
        print(f"[APP_OUT]📊 STEALTH Scroll result: {old_position}px → {new_position}px (Δ{scroll_delta}px)")
        debug_log(f"STEALTH: Multi-step scroll completed: {old_position} → {new_position} (+{scroll_delta}px)", "SCROLL")
        
        # 9. Return success status
        success = new_position > old_position
        print(f"[APP_OUT]{'✅' if success else '❌'} STEALTH Scroll {'successful' if success else 'failed'}")
        
        # 10. Check if we're near the bottom of the page
        if new_position + viewport_height >= page_height - 100:
            debug_log("STEALTH: Near bottom of page detected", "SCROLL")
            print("[APP_OUT]📄 Near bottom of page")
        
        return success
        
    except Exception as e:
        print(f"[APP_OUT]❌ Error during STEALTH scroll: {e}")
        debug_log(f"STEALTH: Error during advanced scroll: {e}", "ERROR")
        return False

def ensure_logged_in(driver, max_attempts=2):
    """
    Ensures the user is logged into LinkedIn using persistent cookies for stealth.
    - Tries to load cookies to restore a session.
    - If session restore fails, performs a full login.
    - Saves cookies after a successful login for future runs.
    """
    print("[APP_OUT]🔐 Verifying LinkedIn session...")
    debug_log("STEALTH: Verifying login status with cookie persistence.", "LOGIN")

    # 1. Try to load cookies and verify session
    if load_cookies(driver):
        debug_log("STEALTH: Cookies loaded. Refreshing to verify session.", "LOGIN")
        driver.get("https://www.linkedin.com/feed/")
        time.sleep(random.uniform(4, 7))
        
        try:
            # Check for a reliable element that confirms login
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "global-nav-typeahead"))
            )
            print("[APP_OUT]✅ Session restored successfully via cookies!")
            debug_log("STEALTH: Session restored successfully from cookies.", "LOGIN")
            return True
        except TimeoutException:
            print("[APP_OUT]⚠️ Cookie session invalid or expired. Proceeding with full login.")
            debug_log("STEALTH: Cookie session invalid. Proceeding with full login.", "LOGIN")

    # 2. If cookie login fails, proceed with normal login
    for attempt in range(1, max_attempts + 1):
        print(f"[APP_OUT]🔑 Login attempt {attempt}/{max_attempts}...")
        debug_log(f"Login attempt {attempt}/{max_attempts}", "LOGIN")
        try:
            # Explicitly go to login page to be safe
            if "login" not in driver.current_url:
                driver.get("https://www.linkedin.com/login")
                time.sleep(random.uniform(2, 4))

            # Wait for the username field to be present and enter email
            print("[APP_OUT]📧 Entering email...")
            user_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            user_field.send_keys(LINKEDIN_EMAIL)
            time.sleep(random.uniform(0.8, 1.5))

            # Find password field, enter password, and submit
            print("[APP_OUT]🔒 Entering password...")
            password_field = driver.find_element(By.ID, "password")
            password_field.send_keys(LINKEDIN_PASSWORD)
            time.sleep(random.uniform(0.8, 1.5))
            
            print("[APP_OUT]📝 Submitting login form...")
            password_field.send_keys(Keys.RETURN)
            
            debug_log("Submitted login credentials.", "LOGIN")

            # After submitting, verify success and SAVE cookies
            print("[APP_OUT]⏳ Verifying login success...")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "global-nav-typeahead"))
            )
            print("[APP_OUT]✅ Login successful!")
            debug_log("Login successful, saving session cookies.", "LOGIN")
            
            # 3. Save cookies for next time
            save_cookies(driver)
            
            return True

        except Exception as e:
            print(f"[APP_OUT]❌ Login attempt {attempt} failed: {e}")
            debug_log(f"Error during login attempt {attempt}: {e}", "ERROR")
            take_screenshot(driver, f"login_attempt_{attempt}_failed")
            if attempt >= max_attempts:
                print("[APP_OUT]🚫 All login attempts failed!")
                debug_log("All login attempts have failed.", "FATAL")
                return False
    
    return False

def has_already_commented(driver, post):
    """Check if the user has already commented on a post."""
    try:
        # Look for comment sections within the post
        comment_selectors = [
            ".//div[contains(@class, 'comments-comment-item')]",
            ".//article[contains(@class, 'comments-comment-item')]",
            ".//div[contains(@class, 'comment-item')]",
            ".//div[contains(@class, 'social-comments-comment')]"
        ]
        
        # Get current user info to identify our own comments
        try:
            # Try to get current user name from page
            user_name = None
            name_selectors = [
                "//span[contains(@class, 'global-nav__me-name')]",
                "//div[contains(@class, 'identity-headline')]//h1",
                "//button[contains(@class, 'global-nav__primary-link-me')]//span"
            ]
            
            for selector in name_selectors:
                try:
                    name_element = driver.find_element(By.XPATH, selector)
                    if name_element and name_element.text.strip():
                        user_name = name_element.text.strip()
                        break
                except:
                    continue
            
            # Look for existing comments in the post
            for comment_selector in comment_selectors:
                try:
                    comments = post.find_elements(By.XPATH, comment_selector)
                    for comment in comments:
                        if not comment.is_displayed():
                            continue
                            
                        # Check comment author
                        author_selectors = [
                            ".//span[contains(@class, 'comments-comment-item__commenter-name')]",
                            ".//a[contains(@class, 'comment-author')]",
                            ".//div[contains(@class, 'comment-author-name')]"
                        ]
                        
                        for author_selector in author_selectors:
                            try:
                                author_element = comment.find_element(By.XPATH, author_selector)
                                if author_element and author_element.text.strip():
                                    comment_author = author_element.text.strip()
                                    
                                    # Check if this is our comment
                                    if user_name and comment_author.lower() == user_name.lower():
                                        debug_log(f"Found existing comment by {comment_author}", "COMMENT_CHECK")
                                        return True
                            except:
                                continue
                except:
                    continue
            
            debug_log("No existing comments found by current user", "COMMENT_CHECK")
            return False
            
        except Exception as e:
            debug_log(f"Error checking for existing comments: {e}", "COMMENT_CHECK")
            return False
            
    except Exception as e:
        debug_log(f"Error in has_already_commented: {e}", "ERROR")
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
            # Clean the text before returning
            cleaned_text = ' '.join(text.strip().split())
            debug_log(f"Cleaned post text: {len(cleaned_text)} chars", "TEXT")
            return cleaned_text
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
                        # Clean the text before returning
                        cleaned_content = ' '.join(content.strip().split())
                        debug_log(f"Cleaned post text: {len(cleaned_content)} chars", "TEXT")
                        return cleaned_content
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
            # Clean the text before returning
            cleaned_js_text = ' '.join(js_text.strip().split())
            debug_log(f"Cleaned post text: {len(cleaned_js_text)} chars", "TEXT")
            return cleaned_js_text
        debug_log("Could not extract meaningful text from post", "TEXT")
        return ""
    except Exception as e:
        debug_log(f"Error getting post text: {e}", "TEXT")
        return ""

def human_type_text(element, text):
    """Simulate realistic human typing with variable speeds, pauses, and occasional corrections."""
    
    # Get behavioral typing speed multiplier
    try:
        speed_multiplier = behavioral_manager.get_typing_speed_multiplier()
        behavioral_manager.log_behavior('typing_start', {'text_length': len(text), 'speed_multiplier': speed_multiplier})
    except:
        speed_multiplier = 1.0  # Fallback if behavioral manager not available
    
    # Human typing characteristics (adjusted by behavioral patterns)
    base_typing_speed = random.uniform(0.08, 0.15) * speed_multiplier
    typing_rhythm_variation = 0.5  # How much typing speed varies
    word_pause_chance = 0.15  # Chance of pausing between words
    sentence_pause_chance = 0.8  # Chance of pausing at sentence end
    typo_chance = 0.02  # 2% chance of making a typo
    correction_delay = random.uniform(0.3, 0.8) * speed_multiplier  # Delay before correcting typos
    
    debug_log(f"ULTRA-STEALTH: Starting human typing simulation for {len(text)} characters", "TYPING")
    
    words = text.split(' ')
    
    for word_idx, word in enumerate(words):
        # Add space before word (except first word)
        if word_idx > 0:
            element.send_keys(' ')
            time.sleep(random.uniform(0.05, 0.12))
            
            # Random pause between words
            if random.random() < word_pause_chance:
                pause_duration = random.uniform(0.2, 0.6)
                debug_log(f"TYPING: Word pause ({pause_duration:.2f}s)", "TYPING")
                time.sleep(pause_duration)
        
        # Type each character in the word
        for char_idx, char in enumerate(word):
            # Simulate typos occasionally
            if random.random() < typo_chance and char.isalpha():
                # Make a typo
                typo_chars = 'qwertyuiopasdfghjklzxcvbnm'
                typo_char = random.choice(typo_chars)
                element.send_keys(typo_char)
                
                # Typing speed for typo
                typing_delay = base_typing_speed * random.uniform(0.8, 1.2)
                time.sleep(typing_delay)
                
                # Realize mistake and correct it
                time.sleep(correction_delay)
                element.send_keys(Keys.BACKSPACE)
                time.sleep(random.uniform(0.1, 0.3))
                
                debug_log(f"TYPING: Simulated typo '{typo_char}' -> corrected to '{char}'", "TYPING")
            
            # Type the correct character
            element.send_keys(char)
            
            # Variable typing speed (humans don't type at constant speed)
            speed_variation = random.uniform(1 - typing_rhythm_variation, 1 + typing_rhythm_variation)
            typing_delay = base_typing_speed * speed_variation
            
            # Longer pauses for certain characters
            if char in '.,!?;:':
                typing_delay *= random.uniform(1.5, 2.5)
            elif char in '"\'()[]{}':
                typing_delay *= random.uniform(1.2, 2.0)
            elif char.isupper():
                typing_delay *= random.uniform(1.1, 1.6)
            
            time.sleep(typing_delay)
        
        # Pause at end of sentences
        if word.endswith(('.', '!', '?')) and random.random() < sentence_pause_chance:
            sentence_pause = random.uniform(0.5, 1.2)
            debug_log(f"TYPING: Sentence pause ({sentence_pause:.2f}s)", "TYPING")
            time.sleep(sentence_pause)
    
    debug_log("ULTRA-STEALTH: Human typing simulation completed", "TYPING")

def post_comment(driver, post, message):
    """Post a comment on a post with extremely granular debug logging and robust error handling."""
    debug_log("[post_comment] Starting ULTRA-STEALTH comment posting process...", "COMMENT")
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
            # ENHANCED: Human-like button interaction
            try:
                # Simulate hovering before clicking
                ActionChains(driver).move_to_element(comment_button).perform()
                time.sleep(random.uniform(0.3, 0.8))
                
                # Random slight mouse movement (human hesitation)
                ActionChains(driver).move_by_offset(
                    random.randint(-2, 2), random.randint(-2, 2)
                ).perform()
                time.sleep(random.uniform(0.1, 0.3))
                
                comment_button.click()
                time.sleep(random.uniform(1.5, 3.0))  # Extended wait after click
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
        
        # Step 3: ULTRA-ENHANCED Human-like text entry with realistic typing patterns
        debug_log(f"[post_comment] Entering comment text with ULTRA-STEALTH typing: {message[:50]}... (length: {len(message)})", "COMMENT")
        try:
            # ENHANCED: Human-like focus behavior
            # Simulate looking for the input field
            ActionChains(driver).move_to_element(comment_input).perform()
            time.sleep(random.uniform(0.5, 1.2))
            
            # Click to ensure focus with human-like precision
            comment_input.click()
            time.sleep(random.uniform(0.3, 0.8))
            
            # Clear any existing text
            try:
                comment_input.clear()
            except Exception:
                pass
            
            # ULTRA-ENHANCED: Realistic human typing simulation with behavioral patterns
            human_type_text(comment_input, message)
            
            # ENHANCED: Verify text entry with multiple methods
            time.sleep(random.uniform(0.5, 1.0))
            actual_text = None
            
            # Try multiple ways to get the actual text
            for verification_method in ['value', 'text', 'textContent', 'innerText']:
                try:
                    if verification_method == 'value':
                        actual_text = comment_input.get_attribute("value")
                    elif verification_method == 'text':
                        actual_text = comment_input.text
                    else:
                        actual_text = driver.execute_script(f"return arguments[0].{verification_method};", comment_input)
                    
                    if actual_text and len(actual_text.strip()) > 10:
                        debug_log(f"[post_comment] Text verification successful via {verification_method}: {actual_text[:50]}... (length: {len(actual_text)})", "COMMENT")
                        break
                except:
                    continue
            
            # If verification failed, try alternative input method
            if not actual_text or len(actual_text.strip()) < 10:
                debug_log("[post_comment] Text verification failed, trying alternative input method", "COMMENT")
                
                # Clear and try again with more aggressive method
                try:
                    # Focus and select all first
                    comment_input.click()
                    time.sleep(0.2)
                    comment_input.send_keys(Keys.CONTROL + "a")
                    time.sleep(0.2)
                    comment_input.send_keys(Keys.DELETE)
                    time.sleep(0.3)
                    
                    # Type in chunks to avoid input buffer issues
                    chunk_size = 25
                    for i in range(0, len(message), chunk_size):
                        chunk = message[i:i+chunk_size]
                        comment_input.send_keys(chunk)
                        time.sleep(random.uniform(0.1, 0.3))
                    
                except Exception as alt_error:
                    debug_log(f"[post_comment] Alternative input method failed: {alt_error}", "ERROR")
                    take_screenshot(driver, "comment_text_error")
                    return False
                
        except Exception as e:
            debug_log(f"[post_comment] Error entering comment text: {e}", "COMMENT")
            take_screenshot(driver, "comment_text_error")
            return False
        
        take_screenshot(driver, "after_entering_comment")
        
        # Step 4: ENHANCED Submit button detection and interaction
        debug_log("[post_comment] Looking for submit button with enhanced detection", "COMMENT")
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
                    if btn.is_displayed() and btn.is_enabled():
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
        
        # ENHANCED: Human-like submission behavior
        try:
            # Simulate reviewing the comment before submitting
            review_time = random.uniform(1.5, 4.0)
            debug_log(f"ULTRA-STEALTH: Simulating comment review ({review_time:.1f}s)", "COMMENT")
            time.sleep(review_time)
            
            # Hover over submit button
            ActionChains(driver).move_to_element(submit_button).perform()
            time.sleep(random.uniform(0.4, 0.9))
            
            # Small hesitation (human uncertainty)
            if random.random() < 0.3:  # 30% chance of hesitation
                hesitation_time = random.uniform(0.5, 1.5)
                debug_log(f"ULTRA-STEALTH: Human hesitation simulation ({hesitation_time:.1f}s)", "COMMENT")
                time.sleep(hesitation_time)
            
            # Click with slight mouse movement variation
            ActionChains(driver).move_by_offset(
                random.randint(-1, 1), random.randint(-1, 1)
            ).click().perform()
            
            debug_log("[post_comment] Clicked submit button with human-like behavior", "COMMENT")
            time.sleep(random.uniform(1.5, 3.0))
            
        except Exception as e:
            debug_log(f"[post_comment] Failed to click submit button: {e}", "COMMENT")
            take_screenshot(driver, "submit_button_click_failed")
            return False
        
        take_screenshot(driver, "after_submit_attempt")
        
        # Step 5: ENHANCED Verification with multiple checks
        verification_delay = random.uniform(2.0, 4.0)
        debug_log(f"ULTRA-STEALTH: Comment verification delay ({verification_delay:.1f}s)", "COMMENT")
        time.sleep(verification_delay)
        
        # Check if input field is cleared/gone (indication of successful submission)
        try:
            if comment_input.is_displayed():
                current_value = comment_input.get_attribute("value") or comment_input.text
                if current_value and message[:50] in current_value:
                    debug_log("[post_comment] Comment still in input field - submission may have failed", "COMMENT")
                    take_screenshot(driver, "comment_still_in_input")
                    
                    # Try alternative verification
                    time.sleep(2)
                    if has_already_commented(driver, post):
                        debug_log("✅ COMMENT VERIFIED in post despite input field retention", "COMMENT")
                        return True
                    else:
                        return False
        except Exception as e:
            debug_log(f"[post_comment] Error during input field verification: {e}", "COMMENT")
        
        # Final verification - search for our comment in the post
        time.sleep(random.uniform(1.0, 2.5))
        if has_already_commented(driver, post):
            # SUCCESS! Log this prominently for the desktop app
            debug_log("✅ ULTRA-STEALTH COMMENT POSTED SUCCESSFULLY! Comment has been verified in the post.", "COMMENT")
            debug_log(f"📝 Comment content (first 100 chars): {message[:100]}{'...' if len(message) > 100 else ''}", "COMMENT")
            return True
        
        debug_log("✅ ULTRA-STEALTH COMMENT POSTED! Could not verify but submission appears successful.", "COMMENT")
        debug_log(f"📝 Comment content (first 100 chars): {message[:100]}{'...' if len(message) > 100 else ''}", "COMMENT")
        return True
        
    except Exception as e:
        debug_log(f"[post_comment] Error during ULTRA-STEALTH comment posting: {e}", "COMMENT")
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
        # For PyInstaller bundled apps, use a simple approach
        if hasattr(sys, '_MEIPASS'):
            # Running as PyInstaller bundle - use current directory
            return os.path.join(os.getcwd(), "linkedin_commenter.log")
        
        # Try to use the user's home directory
        home_dir = os.path.expanduser("~")
        if home_dir and home_dir != "~":  # Make sure expansion worked
            log_dir = os.path.join(home_dir, "Documents", "JuniorAI", "logs")
            os.makedirs(log_dir, exist_ok=True)
            return os.path.join(log_dir, "linkedin_commenter.log")
        else:
            # Home directory expansion failed, use current directory
            return os.path.join(os.getcwd(), "linkedin_commenter.log")
            
    except Exception as e:
        # Absolute fallback to current directory
        print(f"Warning: Could not create log directory, using current directory: {e}")
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
    try:
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
            
        # Clean message to prevent invalid characters
        cleaned_message = str(message).encode('utf-8', errors='replace').decode('utf-8')
        timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')
        log_message = f"{timestamp} [{level}] {cleaned_message}"
        
        # Send to Electron GUI if level is INFO or higher, as the app will parse this output.
        if level_map.get(level, 0) >= level_map.get('INFO', 1):
            print(f"[APP_OUT]{log_message}", flush=True)
        
        # Always print critical errors to console
        if level in ['WARNING', 'ERROR', 'FATAL']:
            print(log_message)
            
        # Try to write to log file (with robust error handling)
        try:
            # Get log file path from config or use default
            log_file = CONFIG.get('log_file_path') if CONFIG else None
            if not log_file:
                log_file = get_default_log_path()
            
            # Ensure log directory exists
            log_dir = os.path.dirname(log_file)
            if log_dir and log_dir != '':
                os.makedirs(log_dir, exist_ok=True)
                
            # Write to log file with safe error handling
            with open(log_file, "a", encoding="utf-8", errors='replace') as f:
                f.write(log_message + "\n")
                f.flush()  # Force write
                
        except (OSError, IOError, PermissionError) as file_error:
            # File logging failed, but don't crash - just use console
            print(f"Log file write failed: {file_error}")
            if DEBUG_MODE:
                print(log_message)
            
    except Exception as fallback_error:
        # If everything fails, use basic print as absolute fallback
        try:
            print(f"[FALLBACK LOG] {datetime.now()} [{level}] {message}")
            print(f"[FALLBACK LOG] Debug_log error: {fallback_error}")
        except:
            # Even the fallback failed, use the most basic output possible
            print("CRITICAL: Logging system completely failed")

def setup_chrome_driver(max_retries=3, retry_delay=5):
    """
    Set up and return a Chrome WebDriver instance with EXTREMELY robust anti-bot detection.
    
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
            debug_log(f"Setting up ULTRA-STEALTH Chrome WebDriver (Attempt {attempt}/{max_retries})")
            
            # Initialize Chrome options with STEALTH configuration
            chrome_options = Options()
            config = get_config()
            debug_mode = config.get('debug_mode', False)

            # ========== CRITICAL ANTI-BOT DETECTION MEASURES ==========
            
            # 1. ENHANCED Random realistic viewport sizes with device-specific ratios
            viewports = [
                # Desktop viewports with realistic proportions
                (1920, 1080), (1366, 768), (1536, 864), (1440, 900), 
                (1280, 720), (1600, 900), (1024, 768), (1280, 800),
                (1680, 1050), (1280, 1024), (1152, 864), (1024, 600),
                # Laptop viewports
                (1366, 768), (1360, 768), (1280, 800), (1440, 900),
                # High-DPI viewports
                (2560, 1440), (3840, 2160), (2048, 1152), (1920, 1200)
            ]
            width, height = random.choice(viewports)
            
            # 2. ENHANCED Pool of realistic user agents with browser version consistency
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ]
            selected_ua = random.choice(user_agents)
            
            # Configure headless mode with stealth - ALWAYS HEADLESS FOR PRODUCTION
            # Force headless mode regardless of debug_mode to prevent manual intervention
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            debug_log("Running Chrome in ULTRA-STEALTH headless mode (production mode)")
            
            # CRITICAL: Essential stealth arguments (tested and working)
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--disable-javascript")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-renderer-backgrounding")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            
            # CRITICAL: Google sign-in and sync prevention (streamlined)
            chrome_options.add_argument('--disable-signin-promo')
            chrome_options.add_argument('--disable-first-run-ui')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--disable-default-browser-check')
            chrome_options.add_argument('--disable-sync')
            chrome_options.add_argument('--disable-default-apps')
            chrome_options.add_argument('--disable-translate')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--disable-notifications')
            chrome_options.add_argument('--disable-popup-blocking')
            
            # Privacy and tracking prevention (essential only)
            chrome_options.add_argument('--disable-background-networking')
            chrome_options.add_argument('--disable-client-side-phishing-detection')
            chrome_options.add_argument('--disable-component-update')
            chrome_options.add_argument('--disable-domain-reliability')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--disable-ipc-flooding-protection')
            
            # Memory and performance optimization
            chrome_options.add_argument("--memory-pressure-off")
            chrome_options.add_argument("--max_old_space_size=4096")
            
            # Window and user agent configuration
            chrome_options.add_argument(f"--window-size={width},{height}")
            chrome_options.add_argument(f"--user-agent={selected_ua}")
            
            # ENHANCED Language and locale randomization
            locales = [
                "en-US,en;q=0.9", "en-GB,en;q=0.9", "en-CA,en;q=0.9",
                "en-AU,en;q=0.9", "en-NZ,en;q=0.9"
            ]
            selected_locale = random.choice(locales)
            chrome_options.add_argument(f"--lang={selected_locale.split(',')[0]}")
            chrome_options.add_argument(f"--accept-lang={selected_locale}")
            
            # Essential experimental options (streamlined)
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Essential preferences (streamlined to prevent conflicts)
            chrome_options.add_experimental_option("prefs", {
                # Basic privacy settings
                "profile.default_content_setting_values.notifications": 2,
                "profile.password_manager_enabled": False,
                "credentials_enable_service": False,
                
                # Google account prevention (essential only)
                "signin.allowed": False,
                "sync.disabled": True,
                "sync_promo.user_skipped": True,
                "profile.first_run_tabs": [],
                
                # Basic privacy
                "safebrowsing.enabled": False,
                "dns_prefetching.enabled": False,
                "search.suggest_enabled": False
            })
            
            debug_log(f"SIMPLIFIED STEALTH CONFIG: Viewport={width}x{height}, UA={selected_ua[:50]}...")

            # Determine which Chrome and ChromeDriver to use
            service = None
            
            # 1. Prioritize system-installed Chrome
            system_chrome_paths = [
                r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                "/usr/bin/google-chrome",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            ]
            found_system_chrome = next((p for p in system_chrome_paths if p and os.path.exists(p)), None)

            if found_system_chrome:
                debug_log(f"Found system Chrome at: {found_system_chrome}. Using webdriver-manager.")
                chrome_options.binary_location = found_system_chrome
                service = Service(ChromeDriverManager().install())
            else:
                # 2. Fallback to bundled Chromium
                debug_log("System Chrome not found. Attempting to use bundled Chromium.", "INFO")
                # Path relative to the script's location when packaged
                bundled_chrome_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'dist', 'win-unpacked', 'resources', 'chrome-win'))
                bundled_chrome_exe = os.path.join(bundled_chrome_dir, 'chrome.exe')
                bundled_driver_exe = os.path.join(bundled_chrome_dir, 'chromedriver.exe')

                if os.path.exists(bundled_chrome_exe) and os.path.exists(bundled_driver_exe):
                    debug_log(f"Found bundled Chromium: {bundled_chrome_exe}")
                    debug_log(f"Using bundled ChromeDriver: {bundled_driver_exe}")
                    chrome_options.binary_location = bundled_chrome_exe
                    service = Service(executable_path=bundled_driver_exe)
                else:
                    # 3. If neither is found, fail
                    error_msg = "Could not find system Chrome or a fully bundled Chromium with its driver. Please install Google Chrome or ensure the application is correctly packaged."
                    debug_log(error_msg, "FATAL")
                    raise Exception(error_msg)

            # Initialize WebDriver
            debug_log("Initializing Chrome WebDriver...")
            
            try:
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                # ========== POST-INITIALIZATION ULTRA-STEALTH MEASURES ==========
                
                # 7. ULTRA-ENHANCED stealth JavaScript to hide webdriver traces
                ultra_stealth_js = """
                    // Hide webdriver property (existing)
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });
                    
                    // Hide automation indicators (existing)
                    delete navigator.__proto__.webdriver;
                    
                    // ENHANCED: Hide additional automation traces
                    Object.defineProperty(navigator, 'automation', {
                        get: () => undefined,
                    });
                    
                    Object.defineProperty(navigator, 'driver', {
                        get: () => undefined,
                    });
                    
                    // ENHANCED: Fake more comprehensive plugins array
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [
                            {
                                0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format", filename: "internal-pdf-viewer"},
                                description: "Portable Document Format",
                                filename: "internal-pdf-viewer",
                                length: 1,
                                name: "Chrome PDF Plugin"
                            },
                            {
                                0: {type: "application/pdf", suffixes: "pdf", description: "", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai"},
                                description: "",
                                filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", 
                                length: 1,
                                name: "Chrome PDF Viewer"
                            },
                            {
                                description: "Shockwave Flash",
                                filename: "pepflashplayer.dll",
                                length: 1,
                                name: "Shockwave Flash"
                            },
                            {
                                description: "Native Client",
                                filename: "internal-nacl-plugin",
                                length: 2,
                                name: "Native Client"
                            }
                        ],
                    });
                    
                    // ENHANCED: Fake languages with regional variations
                    const languages = [
                        ['en-US', 'en'], ['en-GB', 'en'], ['en-CA', 'en'],
                        ['en-AU', 'en'], ['en-NZ', 'en']
                    ];
                    const selectedLanguages = languages[Math.floor(Math.random() * languages.length)];
                    Object.defineProperty(navigator, 'languages', {
                        get: () => selectedLanguages,
                    });
                    
                    Object.defineProperty(navigator, 'language', {
                        get: () => selectedLanguages[0],
                    });
                    
                    // ENHANCED: Fake permissions with more comprehensive coverage
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => {
                        const deniedPermissions = ['geolocation', 'camera', 'microphone', 'background-sync'];
                        const grantedPermissions = ['notifications'];
                        
                        if (deniedPermissions.includes(parameters.name)) {
                            return Promise.resolve({ state: 'denied' });
                        } else if (grantedPermissions.includes(parameters.name)) {
                            return Promise.resolve({ state: 'granted' });
                        } else if (parameters.name === 'notifications') {
                            return Promise.resolve({ state: Notification.permission });
                        }
                        return originalQuery(parameters);
                    };
                    
                    // ENHANCED: Hide chrome runtime traces more thoroughly
                    if (window.chrome) {
                        if (window.chrome.runtime) {
                            delete window.chrome.runtime.onConnect;
                            delete window.chrome.runtime.onMessage;
                            delete window.chrome.runtime.connect;
                            delete window.chrome.runtime.sendMessage;
                        }
                        // Hide additional chrome APIs
                        delete window.chrome.csi;
                        delete window.chrome.loadTimes;
                        delete window.chrome.app;
                    }
                    
                    // ENHANCED: Randomize screen properties with realistic variations
                    const screenVarX = Math.floor(Math.random() * 50) - 25;
                    const screenVarY = Math.floor(Math.random() * 50) - 25;
                    
                    Object.defineProperty(screen, 'availHeight', {
                        get: () => screen.height - 40 + screenVarY,
                    });
                    
                    Object.defineProperty(screen, 'availWidth', {
                        get: () => screen.width + screenVarX,
                    });
                    
                    Object.defineProperty(screen, 'colorDepth', {
                        get: () => 24,
                    });
                    
                    Object.defineProperty(screen, 'pixelDepth', {
                        get: () => 24,
                    });
                    
                    // ENHANCED: Override image loading with more sophisticated patterns
                    const originalCreateElement = document.createElement;
                    document.createElement = function(tagName) {
                        const element = originalCreateElement.call(document, tagName);
                        if (tagName.toLowerCase() === 'img') {
                            setTimeout(() => {
                                if (Math.random() > 0.05) {  // 95% success rate
                                    element.src = element.src;
                                }
                            }, Math.random() * 200 + 50);  // 50-250ms delay
                        }
                        return element;
                    };
                    
                    // NEW: Hide WebGL fingerprinting
                    const getContext = HTMLCanvasElement.prototype.getContext;
                    HTMLCanvasElement.prototype.getContext = function(contextType, ...args) {
                        if (contextType === 'webgl' || contextType === 'webgl2') {
                            return null;  // Disable WebGL to prevent fingerprinting
                        }
                        if (contextType === '2d') {
                            const context = getContext.call(this, contextType, ...args);
                            if (context) {
                                // Introduce slight randomization to canvas fingerprinting
                                const originalFillText = context.fillText;
                                context.fillText = function(text, x, y, ...rest) {
                                    const noiseX = (Math.random() - 0.5) * 0.01;
                                    const noiseY = (Math.random() - 0.5) * 0.01;
                                    return originalFillText.call(this, text, x + noiseX, y + noiseY, ...rest);
                                };
                            }
                            return context;
                        }
                        return getContext.call(this, contextType, ...args);
                    };
                    
                    // NEW: Fake hardware concurrency
                    Object.defineProperty(navigator, 'hardwareConcurrency', {
                        get: () => Math.floor(Math.random() * 8) + 4,  // 4-12 cores
                    });
                    
                    // NEW: Fake device memory
                    Object.defineProperty(navigator, 'deviceMemory', {
                        get: () => [4, 8, 16][Math.floor(Math.random() * 3)],  // 4GB, 8GB, or 16GB
                    });
                    
                    // NEW: Fake connection type
                    if (navigator.connection) {
                        Object.defineProperty(navigator.connection, 'effectiveType', {
                            get: () => ['4g', '3g', 'wifi'][Math.floor(Math.random() * 3)],
                        });
                    }
                    
                    // NEW: Override timing APIs to prevent timing-based fingerprinting
                    const originalNow = performance.now;
                    performance.now = function() {
                        return originalNow.call(this) + (Math.random() - 0.5) * 2;  // Add ±1ms noise
                    };
                    
                    // NEW: Hide automation-specific errors
                    const originalError = window.Error;
                    window.Error = function(...args) {
                        const error = new originalError(...args);
                        if (error.stack && error.stack.includes('webdriver')) {
                            error.stack = error.stack.replace(/webdriver/g, 'browser');
                        }
                        return error;
                    };
                    
                    // NEW: Randomize User-Agent Client Hints
                    if (navigator.userAgentData) {
                        Object.defineProperty(navigator.userAgentData, 'brands', {
                            get: () => [
                                { brand: 'Google Chrome', version: '121' },
                                { brand: 'Not A(Brand', version: '99' },
                                { brand: 'Chromium', version: '121' }
                            ],
                        });
                        
                        Object.defineProperty(navigator.userAgentData, 'mobile', {
                            get: () => false,
                        });
                        
                        Object.defineProperty(navigator.userAgentData, 'platform', {
                            get: () => ['Windows', 'macOS', 'Linux'][Math.floor(Math.random() * 3)],
                        });
                    }
                """
                
                # Execute ultra-stealth script
                driver.execute_script(ultra_stealth_js)
                debug_log("ULTRA-STEALTH: JavaScript anti-detection measures applied")
                
                # 8. ENHANCED page load timeout and test responsiveness
                driver.set_page_load_timeout(60)  # More generous timeout
                driver.implicitly_wait(12)  # Slightly longer implicit wait
                
                # 9. ENHANCED neutral page navigation with behavioral patterns
                debug_log("ULTRA-STEALTH: Enhanced initial navigation sequence...")
                
                # Start with a search engine (most natural)
                search_engines = [
                    "https://www.google.com",
                    "https://www.bing.com", 
                    "https://duckduckgo.com"
                ]
                initial_page = random.choice(search_engines)
                driver.get(initial_page)
                time.sleep(random.uniform(3, 6))
                
                # Simulate brief search behavior
                try:
                    # Try to find search box and simulate typing (without actual search)
                    search_selectors = ['input[name="q"]', 'input[type="search"]', '#search']
                    for selector in search_selectors:
                        try:
                            search_box = driver.find_element(By.CSS_SELECTOR, selector)
                            if search_box.is_displayed():
                                # Simulate typing a generic query
                                search_box.click()
                                time.sleep(random.uniform(0.5, 1.5))
                                
                                # Type slowly like a human
                                query_parts = ["linkedin", " professional", " network"]
                                for part in query_parts:
                                    for char in part:
                                        search_box.send_keys(char)
                                        time.sleep(random.uniform(0.1, 0.3))
                                
                                time.sleep(random.uniform(1, 3))
                                search_box.clear()  # Clear without searching
                                break
                        except:
                            continue
                except:
                    pass  # Search simulation not critical
                
                # 10. ENHANCED realistic mouse movement simulation with curves
                try:
                    # Create curved mouse movement patterns
                    start_x, start_y = random.randint(100, 300), random.randint(100, 300)
                    
                    # Generate Bezier curve points for natural mouse movement
                    for i in range(5):  # 5 movement points
                        control_x = start_x + random.randint(-100, 200)
                        control_y = start_y + random.randint(-50, 150)
                        
                        end_x = control_x + random.randint(-50, 100)
                        end_y = control_y + random.randint(-30, 80)
                        
                        # Move in small increments to create smooth curve
                        steps = random.randint(3, 7)
                        for step in range(steps):
                            progress = (step + 1) / steps
                            # Quadratic Bezier curve calculation
                            current_x = int((1 - progress)**2 * start_x + 
                                          2 * (1 - progress) * progress * control_x + 
                                          progress**2 * end_x)
                            current_y = int((1 - progress)**2 * start_y + 
                                          2 * (1 - progress) * progress * control_y + 
                                          progress**2 * end_y)
                            
                            try:
                                ActionChains(driver).move_by_offset(
                                    current_x - start_x, current_y - start_y
                                ).perform()
                                time.sleep(random.uniform(0.1, 0.4))
                                start_x, start_y = current_x, current_y
                            except:
                                break
                        
                        time.sleep(random.uniform(0.5, 1.5))
                except:
                    pass  # Mouse simulation not critical
                
                debug_log("ULTRA-STEALTH Chrome WebDriver initialized successfully with advanced anti-bot measures")
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

def extract_author_name(post):
    """Extract the author name from a post."""
    try:
        # Try different selectors for author name
        selectors = [
            ".//span[contains(@class, 'feed-shared-actor__name')]",
            ".//span[contains(@class, 'update-components-actor__name')]",
            ".//a[contains(@class, 'feed-shared-actor__container-link')]//span",
            ".//a[contains(@class, 'update-components-actor__container-link')]//span"
        ]
        
        for selector in selectors:
            try:
                element = post.find_element(By.XPATH, selector)
                if element:
                    name = element.text.strip()
                    if name:
                        debug_log(f"Found author name: {name}", "DATA")
                        return name
            except Exception:
                continue
                
        debug_log("Could not find author name", "WARNING")
        return ""
    except Exception as e:
        debug_log(f"Error extracting author name: {e}", "ERROR")
        return ""

def compute_post_id(post):
    """
    Compute a unique identifier for a post using multiple methods.
    Returns tuple of (id_string, method_used)
    """
    try:
        # Method 1: Try to get data-urn attribute
        try:
            urn = post.get_attribute('data-urn')
            if urn:
                return hashlib.md5(urn.encode()).hexdigest(), 'urn'
        except:
            pass
            
        # Method 2: Try to get permalink
        try:
            permalink = post.find_element(By.XPATH, ".//a[contains(@class, 'post-permalink') or contains(@class, 'feed-shared-permalink')]")
            if permalink:
                href = permalink.get_attribute('href')
                if href:
                    return hashlib.md5(href.encode()).hexdigest(), 'permalink'
        except:
            pass
            
        # Method 3: Use post content + timestamp if available
        try:
            content = post.text[:200]  # First 200 chars should be enough for uniqueness
            timestamp_element = post.find_element(By.XPATH, ".//time")
            if timestamp_element:
                timestamp = timestamp_element.get_attribute('datetime')
                content = f"{content}{timestamp}"
            return hashlib.md5(content.encode()).hexdigest(), 'content'
        except:
            pass
            
        # Method 4: Last resort - use entire HTML content
        html_content = post.get_attribute('outerHTML')
        return hashlib.md5(html_content.encode()).hexdigest(), 'html'
        
    except Exception as e:
        debug_log(f"Error computing post ID: {e}", "ERROR")
        # Fallback to random ID if all methods fail
        return hashlib.md5(str(random.random()).encode()).hexdigest(), 'random'

def save_log(processed_posts):
    """Save the list of processed post IDs to a file."""
    try:
        log_path = get_default_log_path()
        with open(log_path, 'w') as f:
            json.dump(processed_posts, f)
        debug_log(f"Saved {len(processed_posts)} processed posts to log", "DATA")
    except Exception as e:
        debug_log(f"Error saving processed posts log: {e}", "ERROR")

def load_comment_history():
    """Load the comment history from file."""
    try:
        history_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'comment_history.json')
        if os.path.exists(history_path):
            with open(history_path, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        debug_log(f"Error loading comment history: {e}", "ERROR")
        return {}

def save_comment_history(history):
    """Save the comment history to file."""
    try:
        history_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'comment_history.json')
        with open(history_path, 'w') as f:
            json.dump(history, f)
        debug_log(f"Saved {len(history)} comments to history", "DATA")
    except Exception as e:
        debug_log(f"Error saving comment history: {e}", "ERROR")

def save_cookies(driver, path="linkedin_cookies.json"):
    """Save browser cookies to a file."""
    try:
        cookies = driver.get_cookies()
        with open(path, 'w') as f:
            json.dump(cookies, f)
        debug_log(f"STEALTH: Saved {len(cookies)} cookies to {path}", "STEALTH")
        print(f"[APP_OUT]🍪 Saved session cookies to {path}")
    except Exception as e:
        debug_log(f"STEALTH: Error saving cookies: {e}", "STEALTH")

def load_cookies(driver, path="linkedin_cookies.json"):
    """Load browser cookies from a file and add them to the session."""
    try:
        if not os.path.exists(path):
            debug_log("STEALTH: Cookie file not found, skipping load.", "STEALTH")
            return False
        
        with open(path, 'r') as f:
            cookies = json.load(f)
        
        if not cookies:
            debug_log("STEALTH: Cookie file is empty.", "STEALTH")
            return False

        # Navigate to the domain before adding cookies
        driver.get("https://www.linkedin.com")
        time.sleep(2)
        
        for cookie in cookies:
            # Ensure cookie has a domain that is valid for the current page
            if 'domain' in cookie and "linkedin.com" in cookie['domain']:
                driver.add_cookie(cookie)
        
        debug_log(f"STEALTH: Loaded {len(cookies)} cookies from {path}", "STEALTH")
        print(f"[APP_OUT]🍪 Loaded {len(cookies)} session cookies")
        return True
    except Exception as e:
        debug_log(f"STEALTH: Error loading cookies: {e}", "STEALTH")
        return False

def human_like_distraction(driver):
    """Perform a random, human-like distraction activity to break patterns."""
    activities = [
        "check_notifications",
        "view_profile",
        "scroll_feed",
        "view_network"
    ]
    
    chosen_activity = random.choice(activities)
    debug_log(f"STEALTH: Performing distraction activity: {chosen_activity}", "STEALTH")
    print(f"[APP_OUT]🎭 Performing human-like distraction: {chosen_activity}...")
    
    try:
        if chosen_activity == "check_notifications":
            driver.get("https://www.linkedin.com/notifications/")
            time.sleep(random.uniform(8, 15))
            # Simulate scrolling through notifications
            for _ in range(random.randint(1, 4)):
                driver.execute_script(f"window.scrollBy(0, {random.randint(200, 500)});")
                time.sleep(random.uniform(2, 5))
        
        elif chosen_activity == "view_profile":
            driver.get("https://www.linkedin.com/in/me/")
            time.sleep(random.uniform(10, 20))
            driver.execute_script(f"window.scrollBy(0, {random.randint(100, 300)});")
            time.sleep(random.uniform(3, 6))

        elif chosen_activity == "scroll_feed":
            driver.get("https://www.linkedin.com/feed/")
            time.sleep(random.uniform(5, 10))
            for _ in range(random.randint(2, 5)):
                driver.execute_script(f"window.scrollBy(0, {random.randint(400, 800)});")
                time.sleep(random.uniform(3, 7))

        elif chosen_activity == "view_network":
            driver.get("https://www.linkedin.com/mynetwork/")
            time.sleep(random.uniform(8, 15))
            
        # End distraction with a return to the feed
        driver.get("https://www.linkedin.com/feed/")
        time.sleep(random.uniform(4, 8))
        debug_log(f"STEALTH: Completed distraction activity: {chosen_activity}", "STEALTH")
        return True
    except Exception as e:
        debug_log(f"STEALTH: Error during distraction activity '{chosen_activity}': {e}", "STEALTH")
        return False

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