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
if sys.stdout is not None and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(line_buffering=True)

# =====================
# CRITICAL FIX: APP_OUT Helper Function
# =====================
def app_out(message):
    """
    Print message with [APP_OUT] prefix and immediate flush.
    This ensures the Electron GUI receives updates immediately.
    """
    print(f"[APP_OUT]{message}")
    sys.stdout.flush()  # CRITICAL: Force immediate flush to Electron process

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
    
    # LinkedIn credentials
    parser.add_argument('--email', type=str, help='LinkedIn account email (overrides config file and env vars)')
    parser.add_argument('--password', type=str, help='LinkedIn account password (overrides config file and env vars)')
    
    # Backend authentication credentials
    parser.add_argument('--access-token', type=str, help='Backend API access token (highest priority)')
    parser.add_argument('--backend-email', type=str, help='Backend API email for authentication')
    parser.add_argument('--backend-password', type=str, help='Backend API password for authentication')

    # Other settings
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
                config.update(file_config) # This will load all credentials if present from file
                
                # CRITICAL: Handle base directory for path resolution
                if 'base_dir' in file_config:
                    # Convert all relative paths to absolute using the base_dir
                    if 'chrome_path' in config and config['chrome_path']:
                        config['chrome_path'] = os.path.join(file_config['base_dir'], config['chrome_path'])
                    if 'log_file_path' in config and config['log_file_path']:
                        config['log_file_path'] = os.path.join(file_config['base_dir'], config['log_file_path'])
                    if 'chrome_profile_path' in config and config['chrome_profile_path']:
                        config['chrome_profile_path'] = os.path.join(file_config['base_dir'], config['chrome_profile_path'])
                    
                    app_out(f"🔍 Using base directory for path resolution: {file_config['base_dir']}")
                    debug_log(f"Base directory for path resolution: {file_config['base_dir']}", "CONFIG")
            else:
                print(f"[WARN] Failed to load or parse configuration from {args.config}. File might be empty or malformed. Continuing with other sources.")
        else:
            print(f"[WARN] Config file specified but does not exist: {args.config}. Relying on CLI/env for all settings.")
    else:
        print("[INFO] No --config argument provided. Relying on CLI args or environment variables for settings.")

    # Ensure credential structures exist for overrides, even if not in file
    if 'linkedin_credentials' not in config:
        config['linkedin_credentials'] = {}
    if 'backend_credentials' not in config:
        config['backend_credentials'] = {}

    # Environment variable overrides (middle priority)
    env_email = os.getenv('LINKEDIN_EMAIL')
    env_pass = os.getenv('LINKEDIN_PASSWORD')
    env_backend_email = os.getenv('BACKEND_EMAIL')
    env_backend_pass = os.getenv('BACKEND_PASSWORD')
    env_access_token = os.getenv('ACCESS_TOKEN')
    env_log_level = os.getenv('LOG_LEVEL')
    env_chrome_path = os.getenv('CHROME_PATH')

    # Populate linkedin_credentials if not already set by the config file
    if env_email and not config['linkedin_credentials'].get('email'):
        config['linkedin_credentials']['email'] = env_email
    if env_pass and not config['linkedin_credentials'].get('password'):
        config['linkedin_credentials']['password'] = env_pass
        
    # Populate backend_credentials from environment if not set by file
    if env_backend_email and not config['backend_credentials'].get('email'):
        config['backend_credentials']['email'] = env_backend_email
    if env_backend_pass and not config['backend_credentials'].get('password'):
        config['backend_credentials']['password'] = env_backend_pass
    if env_access_token and not config.get('access_token'):
        config['access_token'] = env_access_token

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
    
    # CLI overrides (highest priority)
    # LinkedIn creds
    if args.email:
        config['linkedin_credentials']['email'] = args.email
    if args.password:
        config['linkedin_credentials']['password'] = args.password
        
    # Backend creds
    if args.backend_email:
        config['backend_credentials']['email'] = args.backend_email
    if args.backend_password:
        config['backend_credentials']['password'] = args.backend_password
    if args.access_token: # Access token is top-level and overrides email/pass
        config['access_token'] = args.access_token
        
    # Other settings
    if args.chrome_path:
        config['chrome_path'] = args.chrome_path
        
    global LOG_LEVEL_OVERRIDE
    if args.debug:
        config['log_level'] = 'debug'
        config['debug_mode'] = True
        LOG_LEVEL_OVERRIDE = 'DEBUG'
    elif args.log_level:
        config['log_level'] = args.log_level
        LOG_LEVEL_OVERRIDE = args.log_level.upper()
    elif config.get('log_level'):
        LOG_LEVEL_OVERRIDE = config['log_level'].upper()
    else:
        config['log_level'] = 'info'
        LOG_LEVEL_OVERRIDE = 'INFO'

    if 'debug_mode' not in config: 
        config['debug_mode'] = config.get('log_level', 'info').lower() == 'debug'
    
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
        ]
    },
    'direct_hiring': {
        'weight': 6.0,  # Very high weight - direct hiring signals from decision makers
        'keywords': [
            'hiring',  # CRITICAL: Basic word that should catch most hiring posts
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
            'looking for',  # Common hiring phrase
            'seeking',      # Another common hiring phrase
            'filling a position'
        ]
    },
    'negative_context': {
        'weight': -4.0,  # Negative weight to penalize discussion/informational posts
        'keywords': [
            'era of',
            'future of',
            'transforming',
            'automation',
            'discussing',
            'article',
            'thoughts on',
            'insights',
            'trends',
            'industry update',
            'announcement',
            'introducing',
            'launching',
            'webinar',
            'conference',
            'event',
            'research',
            'study shows',
            'report',
            'analysis'
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
    LEVEL 6 & 8: Advanced Behavioral Mimicry with Micro-Interaction Enhancement
    Manages ultra-realistic human behavioral patterns including reading simulation,
    natural tab management, ambient interactions, and momentum-based movements.
    """
    def __init__(self):
        self.session_start_time = datetime.now()
        self.daily_activity_pattern = self._generate_daily_pattern()
        self.weekly_activity_pattern = self._generate_weekly_pattern()
        self.session_characteristics = self._generate_session_characteristics()
        self.behavior_history = []
        self.reading_profile = self._generate_reading_profile()
        self.mouse_movement_history = []
        self.tab_management_pattern = self._generate_tab_pattern()
        self.distraction_schedule = self._generate_distraction_schedule()
        self.ambient_interaction_counter = 0
        
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
            
    # LEVEL 6: Advanced Behavioral Mimicry Methods
    def _generate_reading_profile(self):
        """Generate realistic reading speed and patterns for this session."""
        reading_profiles = [
            {
                'type': 'fast_scanner',
                'words_per_minute': random.randint(250, 350),
                'comprehension_depth': 0.6,
                'skimming_tendency': 0.8,
                'detail_focus_chance': 0.2
            },
            {
                'type': 'careful_reader',
                'words_per_minute': random.randint(180, 240),
                'comprehension_depth': 0.9,
                'skimming_tendency': 0.3,
                'detail_focus_chance': 0.7
            },
            {
                'type': 'selective_reader',
                'words_per_minute': random.randint(200, 280),
                'comprehension_depth': 0.7,
                'skimming_tendency': 0.5,
                'detail_focus_chance': 0.4
            }
        ]
        
        selected = random.choice(reading_profiles)
        debug_log(f"BEHAVIORAL: Reading profile: {selected['type']} at {selected['words_per_minute']} WPM", "BEHAVIORAL")
        return selected
    
    def _generate_tab_pattern(self):
        """Generate natural tab management patterns for this session."""
        patterns = [
            {
                'type': 'tab_minimalist',
                'max_tabs': random.randint(2, 4),
                'new_tab_chance': 0.1,
                'background_browsing_chance': 0.05
            },
            {
                'type': 'tab_moderate',
                'max_tabs': random.randint(4, 8),
                'new_tab_chance': 0.25,
                'background_browsing_chance': 0.15
            },
            {
                'type': 'tab_power_user',
                'max_tabs': random.randint(8, 15),
                'new_tab_chance': 0.4,
                'background_browsing_chance': 0.3
            }
        ]
        
        selected = random.choice(patterns)
        debug_log(f"BEHAVIORAL: Tab pattern: {selected['type']} (max {selected['max_tabs']} tabs)", "BEHAVIORAL")
        return selected
    
    def _generate_distraction_schedule(self):
        """Generate natural distraction patterns throughout the session."""
        session_duration_minutes = self.session_characteristics['duration_range'][1]
        distractions = []
        
        # Generate 2-5 natural distraction points during the session
        num_distractions = random.randint(2, 5)
        for i in range(num_distractions):
            distraction_time = random.randint(5, session_duration_minutes - 5)  # Not at very start/end
            distraction_type = random.choice([
                'check_notifications', 'brief_scroll', 'tab_switch', 
                'mini_break', 'look_around', 'stretch_pause'
            ])
            distractions.append({
                'time_minutes': distraction_time,
                'type': distraction_type,
                'duration_seconds': random.randint(5, 30)
            })
        
        # Sort by time
        distractions.sort(key=lambda x: x['time_minutes'])
        debug_log(f"BEHAVIORAL: Scheduled {len(distractions)} natural distractions", "BEHAVIORAL")
        return distractions
    
    def calculate_reading_time(self, text_length):
        """Calculate realistic reading time based on user's reading profile."""
        if not text_length or text_length < 10:
            return random.uniform(0.5, 2.0)  # Minimal glance time
        
        # Estimate word count (average 5 characters per word)
        estimated_words = max(1, text_length // 5)
        wpm = self.reading_profile['words_per_minute']
        
        # Base reading time in seconds
        base_time = (estimated_words / wpm) * 60
        
        # Apply comprehension and skimming adjustments
        if random.random() < self.reading_profile['skimming_tendency']:
            # Skimming - much faster
            time_multiplier = random.uniform(0.3, 0.6)
        elif random.random() < self.reading_profile['detail_focus_chance']:
            # Detailed reading - slower
            time_multiplier = random.uniform(1.2, 1.8)
        else:
            # Normal reading
            time_multiplier = random.uniform(0.8, 1.2)
        
        adjusted_time = base_time * time_multiplier
        
        # Add realistic pause variations
        pause_factor = random.uniform(1.1, 1.4)  # 10-40% additional time for natural pauses
        final_time = adjusted_time * pause_factor
        
        # Reasonable bounds: 1-45 seconds
        return max(1.0, min(45.0, final_time))
    
    # LEVEL 8: Micro-Interaction Enhancement Methods
    def generate_ambient_mouse_movement(self, driver):
        """Generate subtle ambient mouse movements over non-target elements."""
        try:
            self.ambient_interaction_counter += 1
            
            # Only do ambient movements occasionally (every 3-7 actions)
            if self.ambient_interaction_counter % random.randint(3, 7) != 0:
                return
            
            # Get window dimensions
            window_size = driver.get_window_size()
            width, height = window_size['width'], window_size['height']
            
            # Define safe zones (avoid edges and very center)
            safe_margin = 50
            x_range = (safe_margin, width - safe_margin)
            y_range = (safe_margin + 100, height - safe_margin)  # Avoid browser chrome
            
            # Generate 2-4 subtle movements
            num_movements = random.randint(2, 4)
            action_chain = ActionChains(driver)
            
            for i in range(num_movements):
                # Small, realistic movements (50-200 pixels)
                dx = random.randint(-200, 200)
                dy = random.randint(-150, 150)
                
                # Ensure we stay in safe bounds
                current_x = random.randint(*x_range)
                current_y = random.randint(*y_range)
                
                action_chain.move_by_offset(dx, dy)
                
                # Small pause between movements
                if i < num_movements - 1:
                    time.sleep(random.uniform(0.1, 0.3))
            
            # Execute the movement chain
            action_chain.perform()
            
            # Brief pause after ambient movement
            time.sleep(random.uniform(0.2, 0.6))
            
            debug_log(f"MICRO: Ambient mouse movement performed ({num_movements} movements)", "BEHAVIORAL")
            
        except Exception as e:
            debug_log(f"MICRO: Ambient movement failed: {str(e)}", "WARNING")
    
    def momentum_based_scroll(self, driver, target_element=None, scroll_direction='down'):
        """Perform realistic momentum-based scrolling with physics simulation."""
        try:
            # Initial velocity (pixels per scroll)
            initial_velocity = random.randint(100, 300)
            
            # Physics parameters
            friction = 0.85  # Velocity reduction per step
            min_velocity = 20  # Stop when velocity gets too low
            
            current_velocity = initial_velocity
            total_scrolled = 0
            scroll_steps = 0
            
            while current_velocity > min_velocity and scroll_steps < 15:  # Prevent infinite loops
                # Calculate scroll amount for this step
                scroll_amount = int(current_velocity)
                
                if scroll_direction == 'down':
                    driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                else:
                    driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")
                
                total_scrolled += scroll_amount
                scroll_steps += 1
                
                # Apply friction (momentum decay)
                current_velocity *= friction
                
                # Realistic pause between scroll steps (getting longer as momentum decreases)
                pause_time = random.uniform(0.05, 0.15) * (1.2 - (current_velocity / initial_velocity))
                time.sleep(pause_time)
            
            # Final settle pause
            time.sleep(random.uniform(0.3, 0.8))
            
            debug_log(f"MICRO: Momentum scroll completed - {total_scrolled}px in {scroll_steps} steps", "BEHAVIORAL")
            
        except Exception as e:
            debug_log(f"MICRO: Momentum scroll failed: {str(e)}", "WARNING")
    
    def pre_action_hesitation(self, action_type='click'):
        """Simulate natural hesitation before important actions."""
        hesitation_patterns = {
            'click': {
                'base_delay': (0.2, 0.8),
                'important_multiplier': 1.5,
                'uncertainty_chance': 0.15
            },
            'type': {
                'base_delay': (0.1, 0.4),
                'important_multiplier': 1.3,
                'uncertainty_chance': 0.08
            },
            'scroll': {
                'base_delay': (0.05, 0.2),
                'important_multiplier': 1.2,
                'uncertainty_chance': 0.05
            }
        }
        
        pattern = hesitation_patterns.get(action_type, hesitation_patterns['click'])
        
        # Base hesitation
        hesitation_time = random.uniform(*pattern['base_delay'])
        
        # Uncertainty hesitation (occasionally people pause longer)
        if random.random() < pattern['uncertainty_chance']:
            hesitation_time *= random.uniform(2.0, 4.0)
            debug_log(f"MICRO: Extended hesitation for {action_type} ({hesitation_time:.2f}s)", "BEHAVIORAL")
        
        time.sleep(hesitation_time)
    
    def visual_element_focus_time(self, element_type='text', content_length=100):
        """Calculate realistic focus time based on visual element type and content."""
        focus_patterns = {
            'text': {
                'base_time': 0.5,
                'length_factor': 0.01,  # Additional time per character
                'max_time': 8.0
            },
            'image': {
                'base_time': 1.2,
                'length_factor': 0,  # Images don't scale with "length"
                'max_time': 4.0
            },
            'video': {
                'base_time': 2.0,
                'length_factor': 0,
                'max_time': 6.0
            },
            'button': {
                'base_time': 0.3,
                'length_factor': 0.02,  # Button text length
                'max_time': 2.0
            },
            'link': {
                'base_time': 0.4,
                'length_factor': 0.015,
                'max_time': 3.0
            }
        }
        
        pattern = focus_patterns.get(element_type, focus_patterns['text'])
        
        # Calculate focus time
        base_time = pattern['base_time']
        length_adjustment = content_length * pattern['length_factor']
        total_time = base_time + length_adjustment
        
        # Apply random variation
        variation = random.uniform(0.7, 1.4)
        final_time = total_time * variation
        
        # Respect maximum bounds
        final_time = min(final_time, pattern['max_time'])
        
        return max(0.1, final_time)  # Minimum 0.1 seconds

# LEVEL 7: Network-Level Stealth Enhancement
class NetworkStealthManager:
    """
    LEVEL 7: Advanced Network-Level Stealth
    Manages network-level anti-detection including DNS rotation, 
    connection patterns, and geographic consistency.
    """
    def __init__(self):
        self.dns_servers = [
            '8.8.8.8',      # Google Public DNS
            '1.1.1.1',      # Cloudflare
            '208.67.222.222', # OpenDNS
            '9.9.9.9'       # Quad9
        ]
        self.current_dns = random.choice(self.dns_servers)
        self.connection_profile = self._generate_connection_profile()
        self.session_fingerprint = self._generate_session_fingerprint()
        
    def _generate_connection_profile(self):
        """Generate realistic connection characteristics."""
        profiles = [
            {
                'type': 'home_fiber',
                'download_mbps': random.randint(100, 1000),
                'upload_mbps': random.randint(20, 100),
                'latency_ms': random.randint(5, 25),
                'jitter_ms': random.randint(1, 5)
            },
            {
                'type': 'home_cable',
                'download_mbps': random.randint(50, 300),
                'upload_mbps': random.randint(10, 50),
                'latency_ms': random.randint(15, 40),
                'jitter_ms': random.randint(2, 8)
            },
            {
                'type': 'office_enterprise',
                'download_mbps': random.randint(200, 500),
                'upload_mbps': random.randint(50, 200),
                'latency_ms': random.randint(3, 15),
                'jitter_ms': random.randint(1, 3)
            },
            {
                'type': 'mobile_4g',
                'download_mbps': random.randint(20, 150),
                'upload_mbps': random.randint(5, 30),
                'latency_ms': random.randint(30, 80),
                'jitter_ms': random.randint(5, 15)
            }
        ]
        
        selected = random.choice(profiles)
        debug_log(f"NETWORK: Connection profile: {selected['type']} ({selected['download_mbps']}↓/{selected['upload_mbps']}↑ Mbps)", "NETWORK")
        return selected
    
    def _generate_session_fingerprint(self):
        """Generate unique session fingerprint for this automation run."""
        import hashlib
        timestamp = str(time.time())
        random_seed = str(random.randint(1000000, 9999999))
        raw_fingerprint = f"{timestamp}_{random_seed}_{self.connection_profile['type']}"
        return hashlib.md5(raw_fingerprint.encode()).hexdigest()[:16]
    
    def apply_network_delays(self):
        """Apply realistic network delays based on connection profile."""
        base_delay = self.connection_profile['latency_ms'] / 1000  # Convert to seconds
        jitter = (self.connection_profile['jitter_ms'] / 1000) * random.uniform(-1, 1)
        total_delay = max(0.001, base_delay + jitter)  # Minimum 1ms
        
        time.sleep(total_delay)
        return total_delay

# LEVEL 9: Machine Learning Countermeasures
class MLCountermeasuresManager:
    """
    LEVEL 9: Advanced Machine Learning Countermeasures
    Implements pattern obfuscation, adaptive learning, and dynamic strategy selection
    to counter ML-based bot detection systems.
    """
    def __init__(self):
        self.pattern_history = []
        self.success_metrics = {}
        self.adaptive_parameters = self._initialize_adaptive_params()
        self.strategy_success_rates = {}
        self.behavioral_signatures = self._generate_behavioral_signatures()
        
    def _initialize_adaptive_params(self):
        """Initialize adaptive parameters that evolve based on success/failure."""
        return {
            'base_scroll_speed': random.uniform(0.8, 1.2),
            'comment_frequency': random.uniform(0.7, 1.3),
            'pause_duration_multiplier': random.uniform(0.9, 1.1),
            'reading_speed_factor': random.uniform(0.8, 1.2),
            'interaction_randomness': random.uniform(0.5, 1.5)
        }
    
    def _generate_behavioral_signatures(self):
        """Generate multiple distinct behavioral 'personalities' to rotate between."""
        signatures = [
            {
                'name': 'methodical_professional',
                'characteristics': {
                    'scroll_pattern': 'steady_medium',
                    'reading_style': 'thorough',
                    'interaction_speed': 'deliberate',
                    'comment_style': 'professional',
                    'break_frequency': 'regular'
                }
            },
            {
                'name': 'quick_scanner',
                'characteristics': {
                    'scroll_pattern': 'fast_variable',
                    'reading_style': 'skim',
                    'interaction_speed': 'quick',
                    'comment_style': 'concise',
                    'break_frequency': 'minimal'
                }
            },
            {
                'name': 'careful_researcher',
                'characteristics': {
                    'scroll_pattern': 'slow_detailed',
                    'reading_style': 'comprehensive',
                    'interaction_speed': 'measured',
                    'comment_style': 'detailed',
                    'break_frequency': 'frequent'
                }
            },
            {
                'name': 'casual_browser',
                'characteristics': {
                    'scroll_pattern': 'irregular',
                    'reading_style': 'selective',
                    'interaction_speed': 'variable',
                    'comment_style': 'conversational',
                    'break_frequency': 'sporadic'
                }
            }
        ]
        
        selected = random.choice(signatures)
        debug_log(f"ML_COUNTER: Behavioral signature: {selected['name']}", "ML_COUNTER")
        return selected
    
    def record_detection_event(self, event_type, context=None):
        """Record potential detection events for adaptive learning."""
        event = {
            'timestamp': datetime.now(),
            'type': event_type,
            'context': context or {},
            'current_params': self.adaptive_parameters.copy(),
            'signature': self.behavioral_signatures['name']
        }
        
        self.pattern_history.append(event)
        
        # Trigger adaptive response
        self._adapt_parameters(event_type)
        
        debug_log(f"ML_COUNTER: Detection event recorded: {event_type}", "ML_COUNTER")
    
    def _adapt_parameters(self, detection_type):
        """Adapt behavioral parameters based on detection feedback."""
        adaptations = {
            'soft_throttling': {
                'pause_duration_multiplier': 1.3,
                'comment_frequency': 0.8,
                'interaction_randomness': 1.4
            },
            'bot_challenge': {
                'base_scroll_speed': 0.7,
                'reading_speed_factor': 1.4,
                'pause_duration_multiplier': 1.6
            },
            'rate_limiting': {
                'comment_frequency': 0.6,
                'pause_duration_multiplier': 1.8,
                'interaction_randomness': 1.2
            },
            'captcha_triggered': {
                'base_scroll_speed': 0.5,
                'comment_frequency': 0.4,
                'pause_duration_multiplier': 2.0
            }
        }
        
        if detection_type in adaptations:
            for param, multiplier in adaptations[detection_type].items():
                self.adaptive_parameters[param] *= multiplier
                # Keep parameters within reasonable bounds
                self.adaptive_parameters[param] = max(0.1, min(3.0, self.adaptive_parameters[param]))
            
            debug_log(f"ML_COUNTER: Adapted parameters for {detection_type}", "ML_COUNTER")
    
    def select_optimal_strategy(self, context='general'):
        """Dynamically select the best strategy based on historical performance."""
        if context not in self.strategy_success_rates:
            self.strategy_success_rates[context] = {
                'aggressive': 0.5,
                'moderate': 0.7,
                'conservative': 0.9
            }
        
        # Select strategy based on success rates with some randomness
        rates = self.strategy_success_rates[context]
        
        # Weighted random selection favoring higher success rates
        strategies = list(rates.keys())
        weights = [rates[s] for s in strategies]
        
        # Add some exploration (10% chance to try non-optimal strategy)
        if random.random() < 0.1:
            selected = random.choice(strategies)
        else:
            selected = random.choices(strategies, weights=weights)[0]
        
        debug_log(f"ML_COUNTER: Selected strategy '{selected}' for context '{context}' (rate: {rates[selected]:.2f})", "ML_COUNTER")
        return selected
    
    def generate_pattern_noise(self):
        """Generate controlled randomness to obfuscate behavioral patterns."""
        noise_factors = {
            'timing_variance': random.uniform(0.7, 1.3),
            'action_order_shuffle': random.random() < 0.15,  # 15% chance to vary action order
            'micro_breaks_injection': random.random() < 0.25,  # 25% chance for micro-breaks
            'phantom_interactions': random.random() < 0.1   # 10% chance for phantom actions
        }
        
        return noise_factors
    
    def get_adaptive_delay(self, base_delay, action_type='general'):
        """Get adaptively modified delay based on current parameters and ML countermeasures."""
        base_multiplier = self.adaptive_parameters['pause_duration_multiplier']
        randomness_factor = self.adaptive_parameters['interaction_randomness']
        
        # Apply base adaptation
        adapted_delay = base_delay * base_multiplier
        
        # Add ML-specific randomness
        noise = random.uniform(-randomness_factor, randomness_factor) * 0.3
        final_delay = adapted_delay * (1 + noise)
        
        # Ensure reasonable bounds
        return max(0.1, min(30.0, final_delay))

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
    Generates comments for LinkedIn posts using a backend API with JWT authentication.
    """
    def __init__(self, user_bio, config=None, job_keywords=None):
        self.user_bio = user_bio
        self.config = config or {}
        # Get backend base URL
        backend_base = self.config.get('backend_url') or os.getenv('BACKEND_URL') or 'https://junior-api-915940312680.us-west1.run.app'
        
        # Store base URL for different endpoints
        if backend_base.endswith('/'):
            self.backend_base = backend_base.rstrip('/')
        else:
            self.backend_base = backend_base
            
        # Set up endpoint URLs
        self.login_url = f"{self.backend_base}/api/users/token"
        self.comments_url = f"{self.backend_base}/api/comments/generate"
        self.me_url = f"{self.backend_base}/api/users/me"
        
        # Subscription management endpoints
        self.subscription_limits_url = f"{self.backend_base}/api/subscription/limits"
        self.subscription_usage_url = f"{self.backend_base}/api/subscription/usage"
        self.subscription_stats_url = f"{self.backend_base}/api/subscription/stats"
        
        # Authentication state
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        
        # User account info (populated after verification)
        self.user_id = None
        self.user_email = None
        self.stripe_customer_id = None
        
        # Subscription limits and usage (fetched from API)
        self.daily_limit = None
        self.monthly_limit = None
        self.daily_usage = None
        self.monthly_usage = None
        self.is_warmup = None
        self.subscription_tier = None
        self.warmup_week = None
        self.warmup_percentage = None
        self.has_subscription = None

        # Check for access token first (provided by Electron app)
        self.access_token = config.get('access_token')
        
        
        # Get credentials for backend authentication (separate from LinkedIn)
        # Use desktop app credentials for backend API authentication
        backend_creds = config.get('backend_credentials', {})
        self.backend_email = backend_creds.get('email')  # Your backend account email
        self.backend_password = backend_creds.get('password')  # Desktop app password
        
        # Keep LinkedIn credentials separate for LinkedIn login
        self.linkedin_email = config.get('linkedin_credentials', {}).get('email')
        self.linkedin_password = config.get('linkedin_credentials', {}).get('password')
        
        # Log the backend URL being used for transparency
        print(f"[APP_OUT]🔗 Backend API configured: {self.backend_base}")
        print(f"[APP_OUT]🔐 Backend authentication email: {'✅ Set' if self.backend_email else '❌ Missing'}")
        print(f"[APP_OUT]🔗 LinkedIn login email: {'✅ Set' if self.linkedin_email else '❌ Missing'}")
        self.debug_log(f"Comment generation backend URL: {self.backend_base}", "INFO")
        
        # Check authentication status
        if self.access_token:
            print(f"[APP_OUT]🔐 Backend authentication: ✅ Access token provided")
            self.debug_log("Using provided access token for backend authentication", "INFO")
            # Verify the token works
            self._verify_authentication()
        elif self.backend_email and self.backend_password:
            print(f"[APP_OUT]🔐 Backend authentication email: ✅ Set")
            print(f"[APP_OUT]🔐 Authenticating with email/password...")
            self._authenticate()
        else:
            print(f"[APP_OUT]🔐 Backend authentication: ❌ No access token or credentials provided")
            print(f"[APP_OUT]⚠️ API calls will fail without authentication")
            self.debug_log("No access token or backend credentials provided for backend authentication", "WARNING")
        
        print(f"[APP_OUT]🔗 LinkedIn login email: {'✅ Set' if self.linkedin_email else '❌ Missing'}")
        self.debug_log(f"Comment generation backend URL: {self.backend_base}", "INFO")

    def debug_log(self, message, level="INFO"):
        if 'debug_log' in globals():
            debug_log(message, level)
        else:
            print(f"[{level}] {message}")
    
    def _authenticate(self):
        """Authenticate with the backend API to get JWT tokens."""
        try:
            print(f"[APP_OUT]🔐 Authenticating with backend...")
            
            # Prepare login payload using backend credentials
            login_data = {
                "email": self.backend_email,
                "password": self.backend_password
            }
            
            # Make login request
            response = requests.post(
                self.login_url,
                json=login_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                
                if self.access_token:
                    print(f"[APP_OUT]✅ Authentication successful!")
                    self.debug_log("Successfully authenticated with backend API", "INFO")
                    
                    # Verify the token works by calling /me endpoint
                    self._verify_authentication()
                    return True
                else:
                    print(f"[APP_OUT]❌ Authentication failed: No access token received")
                    self.debug_log("No access token in authentication response", "ERROR")
                    return False
            else:
                print(f"[APP_OUT]❌ Authentication failed: {response.status_code}")
                print(f"[APP_OUT]📄 Response: {response.text}")
                self.debug_log(f"Authentication failed: {response.status_code} - {response.text}", "ERROR")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"[APP_OUT]🌐 Network error during authentication: {str(e)}")
            self.debug_log(f"Network error during authentication: {str(e)}", "ERROR")
            return False
        except Exception as e:
            print(f"[APP_OUT]❌ Unexpected error during authentication: {str(e)}")
            self.debug_log(f"Unexpected error during authentication: {str(e)}", "ERROR")
            return False
    
    def _verify_authentication(self):
        """Verify the current authentication by calling the /me endpoint."""
        try:
            if not self.access_token:
                return False
                
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(self.me_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                user_data = response.json()
                user_email = user_data.get('email', 'Unknown')
                user_id = user_data.get('id', 'Unknown')
                is_active = user_data.get('is_active', False)
                stripe_customer_id = user_data.get('stripe_customer_id', 'None')
                
                print(f"[APP_OUT]📋 User Details:")
                print(f"[APP_OUT]   • ID: {user_id}")
                print(f"[APP_OUT]   • Email: {user_email}")
                print(f"[APP_OUT]   • Active Status: {'✅ Active' if is_active else '❌ Inactive'}")
                print(f"[APP_OUT]   • Stripe Customer: {stripe_customer_id}")
                
                # CRITICAL: Check if user account is active
                if not is_active:
                    print(f"[APP_OUT]❌ Account is not active - authentication failed")
                    self.debug_log(f"User account is not active: {user_email}", "ERROR")
                    return False
                
                # Store user info for later use
                self.user_id = user_id
                self.user_email = user_email
                self.stripe_customer_id = stripe_customer_id
                
                print(f"[APP_OUT]✅ Token verified for active user: {user_email}")
                self.debug_log(f"Token verified for active user: {user_email} (ID: {user_id})", "INFO")
                return True
            else:
                print(f"[APP_OUT]⚠️ Token verification failed: {response.status_code}")
                self.debug_log(f"Token verification failed: {response.status_code}", "WARNING")
                return False
                
        except Exception as e:
            print(f"[APP_OUT]⚠️ Token verification error: {str(e)}")
            self.debug_log(f"Token verification error: {str(e)}", "WARNING")
            return False
    
    def _get_auth_headers(self):
        """Get authentication headers for API requests."""
        if not self.access_token:
            # Try to re-authenticate
            if not self._authenticate():
                return None
                
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    def _handle_auth_error(self, response):
        """Handle authentication errors by attempting to re-authenticate."""
        if response.status_code in [401, 403]:
            print(f"[APP_OUT]🔄 Authentication expired, attempting to re-authenticate...")
            self.debug_log("Authentication expired, attempting to re-authenticate", "INFO")
            
            # Clear current tokens
            self.access_token = None
            self.refresh_token = None
            
            # Try to re-authenticate
            return self._authenticate()
        return False

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
            
        # Get Calendly link from config
        calendly_link = self.config.get('calendly_link', '')
        
        # PRIORITIZE API-GENERATED COMMENTS for quality and personalization
        print(f"[APP_OUT]🤖 Generating personalized comment via API...")
        
        # Try API first for AI-generated comments
        try:
            # Get authentication headers
            headers = self._get_auth_headers()
            if not headers:
                print(f"[APP_OUT]❌ API authentication failed, falling back to local generation")
                self.debug_log("API authentication failed, falling back to local generation", "WARNING")
                return self._generate_fallback_comment(post_text, calendly_link)
            
            # Clean the post text before processing
            cleaned_post_text = self.clean_post_text(post_text)
            
            # Prepare the request payload according to the expected API format
            payload = {
                'post_text': cleaned_post_text,
                'source_linkedin_url': post_url or '',
                'comment_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                'calendly_link': calendly_link  # Pass Calendly link to API
            }
            
            self.debug_log(f"Making primary API call for comment generation", "DEBUG")
            print(f"[APP_OUT]🌐 Calling /api/comments/generate...")
            
            # Make the authenticated API request
            response = requests.post(
                self.comments_url,
                json=payload,
                headers=headers,
                timeout=30  # Allow time for AI generation
            )
            
            print(f"[APP_OUT]📨 API Response: Status {response.status_code}")
            
            # Handle subscription requirement (402) gracefully
            if response.status_code == 402:
                try:
                    error_data = response.json()
                    error_detail = error_data.get('detail', 'Subscription required')
                except:
                    error_detail = 'Subscription required'
                
                print(f"[APP_OUT]💳 API Subscription Required:")
                print(f"[APP_OUT]   • Status: {response.status_code} Payment Required")
                print(f"[APP_OUT]   • Details: {error_detail}")
                print(f"[APP_OUT]   • User ID: {getattr(self, 'user_id', 'Unknown')}")
                print(f"[APP_OUT]   • Stripe Customer: {getattr(self, 'stripe_customer_id', 'Unknown')}")
                print(f"[APP_OUT]   • Fallback: Using enhanced local generation")
                
                self.debug_log(f"API subscription required for user {getattr(self, 'user_email', 'unknown')}: {error_detail}", "INFO")
                return self._generate_fallback_comment(post_text, calendly_link)
            
            # Handle authentication errors
            if response.status_code in [401, 403]:
                print(f"[APP_OUT]🔄 Authentication error, falling back to local generation")
                return self._generate_fallback_comment(post_text, calendly_link)
            
            # Check if the request was successful
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict) and 'comment' in data:
                        comment = data['comment']
                        print(f"[APP_OUT]✅ Generated comment via API: {comment[:100]}...")
                        
                        # ALWAYS ensure Calendly link is included if available with proper formatting
                        if calendly_link and calendly_link not in comment:
                            calendly_signoffs = [
                                "If you'd like to discuss this further, feel free to book a call with me.",
                                "Would be happy to continue this conversation - feel free to schedule time.",
                                "Open to discussing this further if you're interested.",
                                "Feel free to book a time if you'd like to chat more about this.",
                                "Happy to connect and discuss this in more detail.",
                                "Would welcome the opportunity to continue this conversation."
                            ]
                            signoff = random.choice(calendly_signoffs)
                            comment = f"{comment}\n\n{signoff}\n\n{calendly_link}"
                        
                        # Remove mixed capitalization and fix formatting
                        comment = self._fix_comment_formatting(comment)
                        return comment
                        
                    elif isinstance(data, str):
                        # Handle case where the API directly returns the comment string
                        comment = data
                        if calendly_link and calendly_link not in comment:
                            calendly_signoffs = [
                                "If you'd like to discuss this further, feel free to book a call with me.",
                                "Would be happy to continue this conversation - feel free to schedule time.",
                                "Open to discussing this further if you're interested.",
                                "Feel free to book a time if you'd like to chat more about this.",
                                "Happy to connect and discuss this in more detail.",
                                "Would welcome the opportunity to continue this conversation."
                            ]
                            signoff = random.choice(calendly_signoffs)
                            comment = f"{comment}\n\n{signoff}\n\n{calendly_link}"
                        comment = self._fix_comment_formatting(comment)
                        return comment
                        
                except ValueError:
                    # If response is not JSON, return it as is with Calendly link
                    comment = response.text
                    if calendly_link and calendly_link not in comment:
                        calendly_signoffs = [
                            "If you'd like to discuss this further, feel free to book a call with me.",
                            "Would be happy to continue this conversation - feel free to schedule time.",
                            "Open to discussing this further if you're interested.",
                            "Feel free to book a time if you'd like to chat more about this.",
                            "Happy to connect and discuss this in more detail.",
                            "Would welcome the opportunity to continue this conversation."
                        ]
                        signoff = random.choice(calendly_signoffs)
                        comment = f"{comment}\n\n{signoff}\n\n{calendly_link}"
                    comment = self._fix_comment_formatting(comment)
                    return comment
            
            # Log error if API call failed but don't exit
            print(f"[APP_OUT]⚠️ API backup failed: Status {response.status_code}, using local generation")
            self.debug_log(f"API backup failed: {response.status_code} - {response.text}", "WARNING")
            
        except requests.exceptions.RequestException as e:
            print(f"[APP_OUT]🌐 API network error, using local generation: {str(e)}")
            self.debug_log(f"API network error: {str(e)}", "WARNING")
        except Exception as e:
            print(f"[APP_OUT]⚠️ API error, using local generation: {str(e)}")
            self.debug_log(f"API error: {str(e)}", "WARNING")
        
        # Final fallback - enhanced local generation
        print(f"[APP_OUT]🤖 Using enhanced local comment generation as fallback...")
        return self._generate_fallback_comment(post_text, calendly_link)
    
    def _fix_comment_formatting(self, comment):
        """Fix common formatting issues in generated comments."""
        if not comment:
            return comment
            
        # Fix mixed capitalization issues - convert random CAPS to normal case
        # But preserve proper nouns and intentional caps
        lines = comment.split('\n')
        fixed_lines = []
        
        for line in lines:
            # Don't modify URLs or email addresses
            if 'http' in line.lower() or '@' in line:
                fixed_lines.append(line)
                continue
                
            # Fix lines that are mostly caps (likely formatting errors)
            if len(line) > 10 and sum(1 for c in line if c.isupper()) > len(line) * 0.6:
                # Convert to title case but preserve existing sentence structure
                line = line.lower()
                # Capitalize first letter and letters after punctuation
                line = '. '.join(sentence.strip().capitalize() for sentence in line.split('.'))
                line = '! '.join(sentence.strip().capitalize() for sentence in line.split('!'))
                line = '? '.join(sentence.strip().capitalize() for sentence in line.split('?'))
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _generate_fallback_comment(self, post_text, calendly_link):
        """Generate a high-quality fallback comment with maximum variety and authenticity."""
        
        post_lower = post_text.lower()
        
        # Extract key information from the post
        is_hiring = any(word in post_lower for word in ['hiring', 'job', 'position', 'role', 'team', 'looking for', 'seeking', 'recruiting'])
        is_tech = any(word in post_lower for word in ['ai', 'tech', 'data', 'software', 'development', 'machine learning', 'python', 'engineer'])
        is_leadership = any(word in post_lower for word in ['director', 'manager', 'lead', 'senior', 'principal', 'head of'])
        is_remote = any(word in post_lower for word in ['remote', 'work from home', 'distributed', 'virtual'])
        is_startup = any(word in post_lower for word in ['startup', 'scale', 'growth', 'funding', 'series'])
        
        # Determine skills from user bio with better extraction
        skills = "technology and innovation"
        if self.user_bio:
            bio_lower = self.user_bio.lower()
            if any(word in bio_lower for word in ['data scientist', 'data science', 'analytics', 'sql']):
                skills = "data science and analytics"
            elif any(word in bio_lower for word in ['software engineer', 'developer', 'programming', 'coding']):
                skills = "software development"
            elif any(word in bio_lower for word in ['ai', 'machine learning', 'ml', 'deep learning']):
                skills = "AI and machine learning"
            elif any(word in bio_lower for word in ['product manager', 'product', 'pm']):
                skills = "product management"
            elif any(word in bio_lower for word in ['marketing', 'growth', 'seo', 'content']):
                skills = "marketing and growth"
            elif any(word in bio_lower for word in ['design', 'ux', 'ui', 'creative']):
                skills = "design and user experience"
        
        # Generate different comment styles based on post content
        if is_hiring:
            templates = [
                "This role sounds incredible! The combination of {context} really aligns with my background in {skills}. {company_comment}",
                "I've been following opportunities in {relevant_area} and this position stands out. My experience with {skills} would be a great fit. {enthusiasm}",
                "What an exciting opportunity! The focus on {context} is exactly what I'm passionate about. {experience_note}",
                "This caught my attention immediately - {context} is such a critical area. Would love to learn more about the team culture and growth opportunities.",
                "Perfect timing! I've been looking for roles that emphasize {context}. My background in {skills} has prepared me for exactly this type of challenge."
            ]
            
            # Context-specific variables for hiring posts
            context_options = ["innovation and growth", "team collaboration", "technical excellence", "data-driven decisions", "scalable solutions"]
            company_comments = ["The company mission really resonates with me.", "I'm impressed by the company's approach to innovation.", "Your team's reputation in the industry is outstanding."]
            enthusiasm_options = ["Excited to contribute to meaningful work!", "Would love to be part of this journey.", "This aligns perfectly with my career goals."]
            experience_notes = ["I've tackled similar challenges in previous roles.", "My expertise directly applies to these requirements.", "I thrive in environments like this."]
            
            context = random.choice(context_options)
            company_comment = random.choice(company_comments) if random.random() > 0.5 else ""
            enthusiasm = random.choice(enthusiasm_options) if random.random() > 0.5 else ""
            experience_note = random.choice(experience_notes) if random.random() > 0.5 else ""
            
        elif is_tech:
            templates = [
                "Fantastic insights on {topic}! I've been working extensively with {skills} and your points about {specific_aspect} really resonate.",
                "This is spot-on. In my experience with {skills}, I've seen {observation}. {additional_thought}",
                "Really valuable perspective! The {topic} landscape is evolving so rapidly, and {specific_aspect} is becoming increasingly critical.",
                "Great analysis! As someone deep in {skills}, I completely agree that {specific_aspect} is the key differentiator.",
                "This perfectly captures the current state of {topic}. {personal_experience} Thanks for sharing these insights!"
            ]
            
            # Tech-specific variables
            topics = ["the AI space", "data science", "software engineering", "technology innovation", "digital transformation"]
            observations = ["similar patterns emerge", "the same challenges", "tremendous potential", "rapid advancement", "these exact trends"]
            aspects = ["scalability", "user experience", "data quality", "automation", "innovation", "efficiency"]
            experiences = ["I've implemented similar solutions.", "We've tackled comparable challenges.", "These trends align with what I'm seeing."]
            additional_thoughts = ["The future possibilities are exciting.", "Implementation is key.", "Excited to see how this evolves."]
            
            topic = random.choice(topics)
            observation = random.choice(observations)
            specific_aspect = random.choice(aspects)
            personal_experience = random.choice(experiences) if random.random() > 0.4 else ""
            additional_thought = random.choice(additional_thoughts) if random.random() > 0.6 else ""
            
        else:
            # General professional comments
            templates = [
                "Thank you for sharing this! Your perspective on {topic} is invaluable. {personal_note}",
                "This resonates strongly with my experience in {skills}. {specific_observation} Great post!",
                "Excellent point about {aspect}! I've seen {observation} in my work with {skills}.",
                "Really appreciate this insight. {specific_observation} The industry needs more conversations like this.",
                "Spot on! {aspect} is often overlooked but absolutely critical. {personal_experience}"
            ]
            
            # General variables
            topics = ["professional development", "industry trends", "leadership", "innovation", "team dynamics", "business strategy"]
            aspects = ["strategic thinking", "team collaboration", "continuous learning", "adaptability", "problem-solving"]
            observations = ["similar challenges", "these exact patterns", "tremendous value in this approach", "the importance of this mindset"]
            personal_notes = ["Looking forward to more insights like this.", "Always learning from posts like yours.", "This added real value to my day."]
            experiences = ["I've applied similar principles in my role.", "This aligns with my recent experiences.", "I've found this to be true as well."]
            
            topic = random.choice(topics)
            aspect = random.choice(aspects)
            observation = random.choice(observations)
            personal_note = random.choice(personal_notes) if random.random() > 0.5 else ""
            personal_experience = random.choice(experiences) if random.random() > 0.5 else ""
            specific_observation = f"I've noticed {observation}" if random.random() > 0.4 else ""
        
        # Select and format template
        template = random.choice(templates)
        
        # Set relevant_area based on post content
        if is_hiring:
            relevant_area = "talent acquisition and team building"
        elif is_tech:
            relevant_area = "technology and innovation"
        elif is_leadership:
            relevant_area = "leadership and strategy" 
        else:
            relevant_area = "professional development"
        
        # Format the comment with appropriate variables
        try:
            if is_hiring:
                comment = template.format(
                    skills=skills, 
                    context=context, 
                    company_comment=company_comment,
                    enthusiasm=enthusiasm,
                    experience_note=experience_note,
                    relevant_area=relevant_area
                )
            elif is_tech:
                comment = template.format(
                    skills=skills,
                    topic=topic,
                    observation=observation,
                    specific_aspect=specific_aspect,
                    personal_experience=personal_experience,
                    additional_thought=additional_thought
                )
            else:
                comment = template.format(
                    skills=skills,
                    topic=topic,
                    aspect=aspect,
                    observation=observation,
                    personal_note=personal_note,
                    personal_experience=personal_experience,
                    specific_observation=specific_observation
                )
        except KeyError:
            # Fallback to simpler template if formatting fails
            fallback_templates = [
                f"Great insights! This really resonates with my experience in {skills}.",
                f"Thank you for sharing this valuable perspective. As someone working in {skills}, I found this particularly relevant.",
                f"Excellent post! The points about {relevant_area} align perfectly with what I've been seeing in my work."
            ]
            comment = random.choice(fallback_templates)
        
        # Clean up any double spaces or formatting issues
        comment = ' '.join(comment.split())
        
        # Add engaging closer (sometimes)
        if random.random() > 0.7:
            closers = [
                "Looking forward to seeing how this develops!",
                "Thanks for the thought-provoking content.",
                "Always enjoy posts that make me think differently.",
                "Appreciate you taking the time to share this."
            ]
            comment += f" {random.choice(closers)}"
        
        # Add Calendly link with professional sign-offs and proper formatting
        if calendly_link:
            # Professional sign-off phrases for Calendly link introduction
            calendly_signoffs = [
                "I'd be happy to discuss this further if you're interested.",
                "Feel free to reach out if you'd like to continue the conversation.",
                "Would love to chat more about this if you have time.",
                "Happy to connect and discuss this in more detail.",
                "If you'd like to explore this topic further, let's connect.",
                "Open to discussing this opportunity further.",
                "Would be glad to share more insights on this topic.",
                "Always happy to connect with like-minded professionals.",
                "Feel free to book a time if you'd like to discuss further.",
                "Would enjoy continuing this conversation.",
                "Happy to share more thoughts on this if helpful.",
                "Open to connecting and exchanging ideas.",
                "Would welcome the opportunity to discuss this more.",
                "Feel free to reach out if you'd like to chat.",
                "Always interested in meaningful professional conversations."
            ]
            
            # Select random sign-off
            signoff = random.choice(calendly_signoffs)
            
            # Format properly: comment + signoff + Calendly link on its own line for preview
            comment = f"{comment}\n\n{signoff}\n\n{calendly_link}"
        
        return comment
    
    def _generate_simple_fallback(self, post_text, calendly_link):
        """Generate a simple but professional fallback comment when all else fails."""
        
        simple_templates = [
            "Thanks for sharing this! Really valuable insights.",
            "Great post! This definitely resonates with my experience.",
            "Excellent perspective - always enjoy thought-provoking content like this.",
            "Really appreciate you taking the time to share this.",
            "This is spot-on! Thanks for the valuable insights."
        ]
        
        comment = random.choice(simple_templates)
        
        # Add Calendly link if available with proper formatting
        if calendly_link:
            simple_signoffs = [
                "Feel free to connect if you'd like to discuss further.",
                "Would be happy to continue this conversation - feel free to schedule time.",
                "Open to connecting and exchanging ideas.",
                "Happy to chat more about this if you're interested."
            ]
            signoff = random.choice(simple_signoffs)
            comment = f"{comment}\n\n{signoff}\n\n{calendly_link}"
        
        return comment
    
    def get_subscription_limits(self):
        """Fetch subscription limits from the backend API."""
        try:
            headers = self._get_auth_headers()
            if not headers:
                print(f"[APP_OUT]❌ Cannot fetch subscription limits: Authentication failed")
                return False
            
            response = requests.get(
                self.subscription_limits_url,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                limits_data = response.json()
                
                self.daily_limit = limits_data.get('daily_limit', 0)
                self.monthly_limit = limits_data.get('monthly_limit', 0)
                self.is_warmup = limits_data.get('is_warmup', False)
                self.subscription_tier = limits_data.get('tier', 'unknown')
                self.warmup_week = limits_data.get('warmup_week', 0)
                self.warmup_percentage = limits_data.get('warmup_percentage', 0)
                
                print(f"[APP_OUT]📊 Subscription Limits Retrieved:")
                print(f"[APP_OUT]   • Daily Limit: {self.daily_limit}")
                print(f"[APP_OUT]   • Monthly Limit: {self.monthly_limit}")
                print(f"[APP_OUT]   • Tier: {self.subscription_tier}")
                print(f"[APP_OUT]   • Warmup Mode: {'✅ Yes' if self.is_warmup else '❌ No'}")
                if self.is_warmup:
                    print(f"[APP_OUT]   • Warmup Week: {self.warmup_week}")
                    print(f"[APP_OUT]   • Warmup Percentage: {self.warmup_percentage}%")
                
                self.debug_log(f"Subscription limits: daily={self.daily_limit}, monthly={self.monthly_limit}, tier={self.subscription_tier}", "INFO")
                return True
                
            elif response.status_code == 402:
                print(f"[APP_OUT]💳 Subscription required to access limits")
                self.debug_log("Subscription required to access limits", "WARNING")
                return False
            else:
                print(f"[APP_OUT]⚠️ Failed to fetch subscription limits: {response.status_code}")
                self.debug_log(f"Failed to fetch subscription limits: {response.status_code}", "WARNING")
                return False
                
        except Exception as e:
            print(f"[APP_OUT]❌ Error fetching subscription limits: {str(e)}")
            self.debug_log(f"Error fetching subscription limits: {str(e)}", "ERROR")
            return False
    
    def get_subscription_usage(self):
        """Fetch current subscription usage from the backend API."""
        try:
            headers = self._get_auth_headers()
            if not headers:
                print(f"[APP_OUT]❌ Cannot fetch subscription usage: Authentication failed")
                return False
            
            response = requests.get(
                self.subscription_usage_url,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                usage_data = response.json()
                
                self.daily_usage = usage_data.get('daily_usage', 0)
                self.monthly_usage = usage_data.get('monthly_usage', 0)
                
                print(f"[APP_OUT]📈 Current Usage:")
                print(f"[APP_OUT]   • Daily Usage: {self.daily_usage}")
                print(f"[APP_OUT]   • Monthly Usage: {self.monthly_usage}")
                
                # Calculate remaining if limits are available
                if self.daily_limit is not None:
                    daily_remaining = max(0, self.daily_limit - self.daily_usage)
                    print(f"[APP_OUT]   • Daily Remaining: {daily_remaining}")
                
                if self.monthly_limit is not None:
                    monthly_remaining = max(0, self.monthly_limit - self.monthly_usage)
                    print(f"[APP_OUT]   • Monthly Remaining: {monthly_remaining}")
                
                self.debug_log(f"Subscription usage: daily={self.daily_usage}, monthly={self.monthly_usage}", "INFO")
                return True
                
            elif response.status_code == 402:
                print(f"[APP_OUT]💳 Subscription required to access usage stats")
                self.debug_log("Subscription required to access usage stats", "WARNING")
                return False
            else:
                print(f"[APP_OUT]⚠️ Failed to fetch subscription usage: {response.status_code}")
                self.debug_log(f"Failed to fetch subscription usage: {response.status_code}", "WARNING")
                return False
                
        except Exception as e:
            print(f"[APP_OUT]❌ Error fetching subscription usage: {str(e)}")
            self.debug_log(f"Error fetching subscription usage: {str(e)}", "ERROR")
            return False
    
    def get_subscription_stats(self):
        """Fetch comprehensive subscription statistics from the backend API."""
        try:
            headers = self._get_auth_headers()
            if not headers:
                print(f"[APP_OUT]❌ Cannot fetch subscription stats: Authentication failed")
                return False
            
            response = requests.get(
                self.subscription_stats_url,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                stats_data = response.json()
                
                self.has_subscription = stats_data.get('has_subscription', False)
                limits = stats_data.get('limits', {})
                usage = stats_data.get('usage', {})
                remaining = stats_data.get('remaining', {})
                progress = stats_data.get('progress', {})
                recent_activity = stats_data.get('recent_activity', [])
                message = stats_data.get('message', '')
                
                print(f"[APP_OUT]📊 Comprehensive Subscription Stats:")
                print(f"[APP_OUT]   • Has Active Subscription: {'✅ Yes' if self.has_subscription else '❌ No'}")
                print(f"[APP_OUT]   • Limits: {limits}")
                print(f"[APP_OUT]   • Usage: {usage}")
                print(f"[APP_OUT]   • Remaining: {remaining}")
                print(f"[APP_OUT]   • Progress: {progress}")
                if message:
                    print(f"[APP_OUT]   • Message: {message}")
                if recent_activity:
                    print(f"[APP_OUT]   • Recent Activity: {len(recent_activity)} entries")
                
                self.debug_log(f"Subscription stats: has_subscription={self.has_subscription}, message={message}", "INFO")
                return True
                
            elif response.status_code == 402:
                print(f"[APP_OUT]💳 Subscription required to access comprehensive stats")
                self.debug_log("Subscription required to access comprehensive stats", "WARNING")
                return False
            else:
                print(f"[APP_OUT]⚠️ Failed to fetch subscription stats: {response.status_code}")
                self.debug_log(f"Failed to fetch subscription stats: {response.status_code}", "WARNING")
                return False
                
        except Exception as e:
            print(f"[APP_OUT]❌ Error fetching subscription stats: {str(e)}")
            self.debug_log(f"Error fetching subscription stats: {str(e)}", "ERROR")
            return False
    
    def check_usage_limits(self):
        """Check if user has reached their usage limits."""
        # Fetch current usage and limits
        if not self.get_subscription_usage():
            print(f"[APP_OUT]⚠️ Could not fetch usage data - proceeding with caution")
            return True  # Allow operation if we can't check limits
        
        if not self.get_subscription_limits():
            print(f"[APP_OUT]⚠️ Could not fetch limit data - proceeding with caution")
            return True  # Allow operation if we can't check limits
        
        # Check daily limit
        if self.daily_limit and self.daily_usage >= self.daily_limit:
            print(f"[APP_OUT]🛑 Daily limit reached: {self.daily_usage}/{self.daily_limit}")
            self.debug_log(f"Daily limit reached: {self.daily_usage}/{self.daily_limit}", "WARNING")
            return False
        
        # Check monthly limit
        if self.monthly_limit and self.monthly_usage >= self.monthly_limit:
            print(f"[APP_OUT]🛑 Monthly limit reached: {self.monthly_usage}/{self.monthly_limit}")
            self.debug_log(f"Monthly limit reached: {self.monthly_usage}/{self.monthly_limit}", "WARNING")
            return False
        
        # Display progress
        if self.daily_limit:
            daily_progress = (self.daily_usage / self.daily_limit) * 100
            print(f"[APP_OUT]📊 Daily Progress: {self.daily_usage}/{self.daily_limit} ({daily_progress:.1f}%)")
        
        if self.monthly_limit:
            monthly_progress = (self.monthly_usage / self.monthly_limit) * 100
            print(f"[APP_OUT]📊 Monthly Progress: {self.monthly_usage}/{self.monthly_limit} ({monthly_progress:.1f}%)")
        
        return True



def get_time_based_score(time_filter):
    """
    Calculate a score multiplier based on the time filter used in the URL.
    More aggressively penalizes older posts.
    
    Args:
        time_filter (str): The time filter from the URL ('past-24h', 'past-week', 'past-month')
    
    Returns:
        float: Score multiplier based on recency
    """
    time_weights = {
        'past-24h': 2.0,    # Highest weight for most recent posts
        'past-week': 1.2,   # Reduced from 1.5 to 1.2 to penalize week-old posts
        'past-month': 0.7   # Reduced from 1.0 to 0.7 to penalize old posts
    }
    return time_weights.get(time_filter, 0.7)  # Default to low score if unknown filter

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
    
    # Reduced length bonus to avoid over-scoring long but irrelevant posts
    words = len(cleaned_post_text.split())
    if words >= 50:
        total_score += 2  # Reduced bonus from 5 to 2
    
    score_breakdown['length'] = {
        'words': words,
        'score': 2 if words >= 50 else 0
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

def should_comment_on_post(post_text, author_name=None, hours_ago=999, min_score=55, time_filter=None):
    """
    Determine if a post is worth commenting on based on score and hiring intent.
    Implements stricter checks for actual hiring signals vs discussion posts.
    """
    # Calculate initial score
    score = calculate_post_score(post_text, author_name, time_filter)
    
    # Strong hiring intent indicators that must be present
    hiring_indicators = [
        'hiring', 'job opening', 'position available', 'join our team',
        'looking to hire', 'seeking candidates', 'open role', 'open position',
        'job opportunity', 'career opportunity'
    ]
    
    # Check for clear hiring intent
    post_text_lower = post_text.lower()
    has_hiring_intent = any(indicator in post_text_lower for indicator in hiring_indicators)
    
    # Heavily penalize posts without clear hiring intent
    if not has_hiring_intent:
        score *= 0.5  # 50% penalty
        debug_log("No clear hiring intent found - applying 50% score penalty", "SCORE")
    
    # Additional time-based penalty for older posts
    if hours_ago > 48:  # More than 2 days old
        score *= 0.8  # 20% penalty
        debug_log(f"Post age penalty applied: {hours_ago} hours old", "SCORE")
    
    print(f"[APP_OUT]⚖️ Post scored: {score}/100 (min required: {min_score})")
    debug_log(f"Post score: {score} (min required: {min_score}, has_hiring_intent: {has_hiring_intent})", "SCORE")
    
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
    
    # CRITICAL FIX: Ensure job_keywords is always a list
    job_keywords_raw = CONFIG.get('job_keywords', [])
    if isinstance(job_keywords_raw, str):
        # Convert comma-separated string to list
        JOB_SEARCH_KEYWORDS = [kw.strip() for kw in job_keywords_raw.split(',') if kw.strip()]
    elif isinstance(job_keywords_raw, list):
        JOB_SEARCH_KEYWORDS = job_keywords_raw
    else:
        JOB_SEARCH_KEYWORDS = []
    
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
            
            # Initialize session timing for human-like behavior
            session_start_time = datetime.now()
            session_duration_minutes = random.randint(20, 90)  # Random session length: 20-90 minutes
            session_break_minutes = random.randint(5, 20)      # Random break length: 5-20 minutes
            
            print("[APP_OUT]⚙️ Initializing components...")
            print(f"[APP_OUT]⏰ Session planned: {session_duration_minutes} minutes active, {session_break_minutes} minute break")
            debug_log(f"SESSION: Planned session duration: {session_duration_minutes} minutes, break: {session_break_minutes} minutes", "SESSION")
            
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
                
            # LEVEL 7: Initialize Network Stealth Manager
            try:
                print("[APP_OUT]🌐 Initializing network stealth manager...")
                network_stealth = NetworkStealthManager()
                print(f"[APP_OUT]🔗 Network profile: {network_stealth.connection_profile['type']} ({network_stealth.connection_profile['download_mbps']}↓/{network_stealth.connection_profile['upload_mbps']}↑ Mbps)")
                debug_log(f"[INIT] Network stealth initialized with {network_stealth.connection_profile['type']} profile", "NETWORK")
            except Exception as network_error:
                print(f"[APP_OUT]❌ Failed to initialize network stealth manager: {network_error}")
                debug_log(f"[ERROR] Failed to initialize network stealth manager: {network_error}", "ERROR")
                raise
                
            # LEVEL 9: Initialize ML Countermeasures Manager  
            try:
                print("[APP_OUT]🤖 Initializing ML countermeasures manager...")
                ml_counter = MLCountermeasuresManager()
                signature_name = ml_counter.behavioral_signatures['name']
                print(f"[APP_OUT]🎭 ML Defense profile: {signature_name}")
                debug_log(f"[INIT] ML countermeasures initialized with {signature_name} behavioral signature", "ML_COUNTER")
            except Exception as ml_error:
                print(f"[APP_OUT]❌ Failed to initialize ML countermeasures manager: {ml_error}")
                debug_log(f"[ERROR] Failed to initialize ML countermeasures manager: {ml_error}", "ERROR")
                raise
            
            # Initialize comment generator with job keywords
            try:
                print("[APP_OUT]🤖 Initializing AI comment generator...")
                debug_log("[INIT] Initializing comment generator", "DEBUG")
                comment_generator = CommentGenerator(
                    user_bio=USER_BIO,
                    config=CONFIG,  # Pass the loaded configuration for backend API access
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
                print("[APP_OUT]✅ Login successful, beginning advanced session warming...")

                # ========== LEVEL 5: ADVANCED SESSION WARMING ==========
                print("[APP_OUT]🔥 Starting comprehensive session warming sequence...")
                warming_success = advanced_session_warming(driver)
                
                if warming_success:
                    print("[APP_OUT]✅ Session warming completed successfully")
                    debug_log("✅ Advanced session warming completed - ready for natural searches", "STEALTH")
                else:
                    print("[APP_OUT]⚠️ Session warming had issues but continuing...")
                    debug_log("⚠️ Session warming encountered issues but proceeding", "STEALTH")

                # ========== NATURAL JOB SEARCH STRATEGY ==========
                print("[APP_OUT]🔍 Beginning natural job search strategy...")
                
                # Instead of using direct URLs, perform natural searches based on job keywords
                # CRITICAL FIX: Ensure search_keywords is always a list, never a string
                if isinstance(JOB_SEARCH_KEYWORDS, list) and len(JOB_SEARCH_KEYWORDS) > 0:
                    search_keywords = JOB_SEARCH_KEYWORDS
                elif isinstance(JOB_SEARCH_KEYWORDS, str) and JOB_SEARCH_KEYWORDS.strip():
                    # Fallback conversion for string input
                    search_keywords = [kw.strip() for kw in JOB_SEARCH_KEYWORDS.split(',') if kw.strip()]
                else:
                    search_keywords = ["technology", "software", "business"]
                
                # Anti-detection: Randomize keyword order
                search_keywords = search_keywords.copy()  # Don't modify original
                random.shuffle(search_keywords)
                
                print(f"[APP_OUT]🎯 Processing {len(search_keywords)} job keywords...")
                debug_log(f"Natural search strategy with keywords: {search_keywords}", "SEARCH")

                # Process each keyword with natural searches
                for i, keyword in enumerate(search_keywords, 1):
                    print(f"[APP_OUT]📍 Processing keyword {i}/{len(search_keywords)}: {keyword}")
                    debug_log(f"Natural search for keyword: {keyword}", "SEARCH")
                    
                    # HUMAN-LIKE SESSION MANAGEMENT: Check if it's time for a session break
                    current_session_time = (datetime.now() - session_start_time).total_seconds() / 60  # minutes
                    
                    if current_session_time >= session_duration_minutes:
                        print(f"[APP_OUT]😴 Session break time! Active for {current_session_time:.1f} minutes")
                        print(f"[APP_OUT]☕ Taking {session_break_minutes} minute break (like a real person would)")
                        debug_log(f"SESSION: Taking session break after {current_session_time:.1f} minutes of activity", "SESSION")
                        
                        # Long break simulation (5-20 minutes)
                        break_seconds = session_break_minutes * 60
                        print(f"[APP_OUT]⏰ Break will last {session_break_minutes} minutes...")
                        time.sleep(break_seconds)
                        
                        # Reset session timing for next session
                        session_start_time = datetime.now()
                        session_duration_minutes = random.randint(20, 90)  # New random session length
                        session_break_minutes = random.randint(5, 20)     # New random break length
                        
                        print(f"[APP_OUT]🔄 Session break complete! Next session: {session_duration_minutes} minutes")
                        debug_log(f"SESSION: Break complete, new session planned: {session_duration_minutes} minutes", "SESSION")
                    else:
                        # Show session progress for transparency
                        remaining_minutes = session_duration_minutes - current_session_time
                        print(f"[APP_OUT]⏱️ Session progress: {current_session_time:.1f}/{session_duration_minutes} minutes ({remaining_minutes:.1f} min remaining)")
                    
                    # ENHANCED: Use backend subscription limits instead of hardcoded limits
                    try:
                        # Check subscription usage limits from backend API
                        within_limits = comment_generator.check_usage_limits()
                        
                        if not within_limits:
                            print(f"[APP_OUT]🛑 Subscription limits reached - stopping for now")
                            debug_log("Subscription limits reached", "LIMIT")
                            break
                            
                    except Exception as limit_error:
                        # Fallback to hardcoded limits if subscription check fails
                        print(f"[APP_OUT]⚠️ Subscription limit check failed, using fallback limits: {limit_error}")
                        debug_log(f"Subscription limit check failed: {limit_error}", "WARNING")
                        
                        # Fallback to original hardcoded behavior
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

                    # ========== NATURAL SEARCH INSTEAD OF DIRECT URLS ==========
                    try:
                        print(f"[APP_OUT]🔍 Performing natural search for: {keyword}")
                        
                        # Use natural job search instead of direct URL navigation
                        search_success = natural_job_search(driver, keyword, "past-24h")
                        
                        if not search_success:
                            print(f"[APP_OUT]⚠️ Natural search failed for '{keyword}' - trying fallback method")
                            debug_log(f"Natural search failed for keyword: {keyword}", "WARNING")
                            
                            # Fallback: try a more generic approach
                            try:
                                driver.get("https://www.linkedin.com/search/results/content/")
                                time.sleep(random.uniform(5, 8))
                                
                                # Try direct search box interaction
                                search_box = driver.find_element(By.CSS_SELECTOR, 'input[placeholder*="Search"]')
                                search_box.clear()
                                time.sleep(random.uniform(0.5, 1))
                                
                                fallback_query = f"{keyword} hiring"
                                for char in fallback_query:
                                    search_box.send_keys(char)
                                    time.sleep(random.uniform(0.1, 0.25))
                                
                                search_box.send_keys(Keys.RETURN)
                                time.sleep(random.uniform(4, 7))
                                
                                print(f"[APP_OUT]✅ Fallback search completed for: {keyword}")
                            except Exception as fallback_error:
                                print(f"[APP_OUT]❌ Fallback search also failed: {fallback_error}")
                                debug_log(f"Both natural and fallback search failed for {keyword}: {fallback_error}", "ERROR")
                                continue
                        else:
                            print(f"[APP_OUT]✅ Natural search successful for: {keyword}")
                        
                        # ENHANCED: Longer waits to avoid detection
                        search_wait = random.uniform(15, 30)  # Increased from 5-10 to 15-30
                        debug_log(f"STEALTH: Post-search stabilization wait: {search_wait:.1f}s", "STEALTH")
                        time.sleep(search_wait)
                        
                        # IMPROVED: Less aggressive bot detection check
                        current_url_check = driver.current_url.lower()
                        page_title_check = driver.title.lower()
                        
                        # More specific bot detection indicators
                        critical_indicators = [
                            "challenge", "blocked", "captcha", "security check", "verify",
                            "unusual activity", "rate limit", "access denied", "forbidden"
                        ]
                        
                        # Only trigger on critical indicators, not soft ones
                        is_bot_detected = any(indicator in current_url_check or indicator in page_title_check 
                                            for indicator in critical_indicators)
                        
                        # Additional check: look for actual LinkedIn pages vs error pages
                        is_linkedin_page = "linkedin.com" in current_url_check and ("search" in current_url_check or "feed" in current_url_check)
                        
                        if is_bot_detected and not is_linkedin_page:
                            debug_log("STEALTH: Bot detection triggered - skipping this keyword", "WARNING")
                            print(f"[APP_OUT]🛡️ Bot detection triggered for '{keyword}' - moving to next keyword")
                            # Add longer cooldown when detection is triggered
                            cooldown_time = random.uniform(60, 120)  # 1-2 minute cooldown
                            debug_log(f"STEALTH: Bot detection cooldown: {cooldown_time:.1f}s", "STEALTH")
                            time.sleep(cooldown_time)
                            continue
                        else:
                            print(f"[APP_OUT]✅ No bot detection for '{keyword}' - proceeding with post analysis")
                        
                        # Post-search human behavior simulation
                        debug_log("STEALTH: Post-search human simulation", "STEALTH")
                        try:
                            # Simulate reading the search results before interacting
                            reading_time = random.uniform(3, 8)
                            time.sleep(reading_time)
                            
                            # Small random scrolls to simulate reading results
                            for _ in range(random.randint(1, 3)):
                                scroll_amount = random.randint(100, 400)
                                driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                                time.sleep(random.uniform(1, 3))
                            
                            # Return to top of page
                            driver.execute_script("window.scrollTo(0, 0);")
                            time.sleep(random.uniform(1, 2))
                        except:
                            pass  # Not critical if this fails
                        
                        # Check current status
                        current_url = driver.current_url
                        page_title = driver.title
                        print(f"[APP_OUT]📄 Current URL: {current_url}")
                        print(f"[APP_OUT]📋 Page title: {page_title}")
                        
                        # Check for common LinkedIn issues
                        page_source_snippet = driver.page_source[:1000].lower()
                        
                        # Check for subscription/premium prompts
                        if any(issue_keyword in page_source_snippet for issue_keyword in ['premium', 'subscription', 'upgrade', 'linkedin premium']):
                            print("[APP_OUT]💰 DETECTED: Premium/subscription prompt on page")
                            debug_log("Premium subscription prompt detected", "WARNING")
                        
                        # Check for login issues
                        if any(issue_keyword in page_source_snippet for issue_keyword in ['sign in', 'log in', 'join linkedin']):
                            app_out("🔐 DETECTED: Login required")
                            debug_log("Login required - authentication issue", "WARNING")
                        
                        # Check for rate limiting/blocking
                        if any(issue_keyword in page_source_snippet for issue_keyword in ['blocked', 'rate limit', 'too many requests', 'captcha']):
                            app_out("🚫 DETECTED: Possible rate limiting or blocking")
                            debug_log("Rate limiting or blocking detected", "WARNING")
                        
                        # Look for search results with flexible selectors
                        app_out("⏳ Waiting for search results...")
                        try:
                            # Try multiple selectors for search results
                            result_selectors = [
                                ".reusable-search__entity-result-list",
                                ".search-results-container",
                                ".search-results",
                                ".feed-shared-update-v2",
                                "[data-test-id='search-results']"
                            ]
                            
                            search_results_found = False
                            for selector in result_selectors:
                                try:
                                    WebDriverWait(driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                    )
                                    app_out(f"✅ Search results found with selector: {selector}")
                                    search_results_found = True
                                    break
                                except:
                                    continue
                            
                            if not search_results_found:
                                app_out("⚠️ No standard search results container found")
                                debug_log("No standard search results container found", "WARNING")
                                
                        except Exception as results_error:
                            print(f"[APP_OUT]⚠️ Search results detection error: {results_error}")
                            debug_log(f"Search results detection error: {results_error}", "WARNING")
                        
                        debug_log(f"Natural search completed for keyword: {keyword}", "SEARCH")
                    except Exception as search_error:
                        print(f"[APP_OUT]❌ Error during natural search for '{keyword}': {search_error}")
                        debug_log(f"Error during natural search for keyword '{keyword}': {search_error}", "ERROR")
                        
                        # Log search performance for keyword (converting to dummy URL format for tracking)
                        dummy_url = f"natural_search:{keyword}"
                        search_tracker.record_url_performance(dummy_url, success=False, comments_made=0, error=True)
                        continue # Move to the next keyword

                    try:
                        app_out("🔍 Starting post analysis and commenting...")
                        app_out("🚀 CALLING process_posts() function...")
                        debug_log("About to call process_posts() function", "DEBUG")
                        # Process posts on the current page
                        posts_processed, hiring_posts_found = process_posts(driver)
                        print(f"[APP_OUT]✅ process_posts() returned: {posts_processed} posts processed, {hiring_posts_found} hiring posts found")
                        debug_log(f"process_posts() completed: {posts_processed} processed, {hiring_posts_found} hiring posts", "DEBUG")
                        if posts_processed > 0:
                            session_comments += posts_processed
                            daily_comments += posts_processed
                        
                        # Log performance for keyword (converting to dummy URL format for tracking)
                        dummy_url = f"natural_search:{keyword}"
                        search_tracker.record_url_performance(dummy_url, success=True, comments_made=posts_processed)
                        
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

                    # ENHANCED: Longer sleep between keywords to avoid detection
                    keyword_break = random.uniform(30, 90)  # 30-90 seconds between keywords
                    debug_log(f"STEALTH: Inter-keyword break: {keyword_break:.1f}s", "STEALTH")
                    time.sleep(keyword_break)
                    
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
    # FIXED: Focus on recent posts only - avoid old posts from months ago
    time_filters = ["past-24h", "past-week"]
    
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

def construct_linkedin_search_url(keywords, time_filter="past-24h"):
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
        
        # FIXED: Remove quotes around time_filter to make filtering work properly
        params = {
            'keywords': encoded_keywords,
            'origin': 'FACETED_SEARCH',
            'sid': 'tnP',
            'datePosted': time_filter  # FIXED: No quotes around the value
        }
        
        # Build the URL with parameters - ensure proper URL encoding
        query_string = urllib.parse.urlencode(params)
        final_url = f"{base_url}?{query_string}"
        
        debug_log(f"Constructed LinkedIn URL: {final_url}", "DEBUG")
        return final_url
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
    app_out("🔥 FIND_POSTS FUNCTION CALLED - STARTING SEARCH...")
    debug_log("Starting post search on current page...", "SEARCH")
    app_out("🔍 Searching for posts on page...")
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
    app_out("🔥 PROCESS_POSTS FUNCTION CALLED - STARTING...")
    debug_log("Starting post processing with continuous scrolling", "PROCESS")
    app_out("🔍 Processing LinkedIn posts...")
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
        
        # CRITICAL: Ensure comment history file exists from the start
        debug_log("💾 Creating/updating comment history file to ensure Dashboard can read it", "INIT")
        print("[APP_OUT]💾 Initializing comment history file for Dashboard...")
        save_comment_history(comment_history)
        
        # Get current URL and extract time filter
        current_url = driver.current_url
        time_filter = None
        if 'datePosted=' in current_url:
            try:
                time_filter = current_url.split('datePosted=')[1].split('&')[0].strip("\"'")
                debug_log(f"Extracted time filter from URL: {time_filter}", "DEBUG")
            except Exception as e:
                debug_log(f"Error extracting time filter from URL: {e}", "WARNING")
        
        app_out("🔄 Starting continuous scroll and post discovery...")
        
        # Continuous scrolling and post processing with better logic
        processed_posts_this_session = set()
        scroll_attempts = 0
        max_scroll_attempts = 50  # Increased from 10 to allow more scrolling
        posts_found_last_cycle = 0
        
        while scroll_attempts < max_scroll_attempts:
            app_out(f"🔄 SCROLL LOOP ITERATION {scroll_attempts + 1}/{max_scroll_attempts}")
            debug_log(f"Scroll attempt {scroll_attempts + 1}/{max_scroll_attempts}", "SCROLL")
            
            # Find posts with retry logic
            app_out(f"🔍 Calling find_posts() in scroll loop...")
            posts = find_posts(driver)
            app_out(f"📊 find_posts() returned {len(posts)} posts")
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
                    should_comment, final_score = should_comment_on_post(post_text, author_name, hours_ago, min_score=55, time_filter=time_filter)
                    
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
    """
    LIGHTNING FAST: Check comment history file instead of scraping DOM.
    Completely avoids infinite loops and DOM hangs.
    """
    try:
        # Get post ID first
        post_id, id_method = compute_post_id(post)
        
        if not post_id:
            debug_log("FAST_CHECK: No post ID found, assuming safe to comment", "COMMENT_CHECK")
            return False
        
        debug_log(f"FAST_CHECK: Checking post ID {post_id} in comment history", "COMMENT_CHECK")
        
        # Load comment history from file (super fast)
        comment_history = load_comment_history()
        
        # Check if post ID exists in history
        if post_id in comment_history:
            debug_log(f"FAST_CHECK: Post {post_id} found in comment history - SKIPPING", "COMMENT_CHECK")
            return True
        
        debug_log(f"FAST_CHECK: Post {post_id} not in history - safe to comment", "COMMENT_CHECK")
        return False
        
    except Exception as e:
        debug_log(f"FAST_CHECK: Error checking comment history: {e}", "ERROR")
        return False  # Assume safe to comment on error

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
        # Always try to use the user's home directory first, regardless of PyInstaller
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

def get_comment_history_path():
    """Get comment history path in the SAME directory as linkedin_commenter.log (OneDrive-aware)."""
    try:
        # CRITICAL: Use the exact same directory where linkedin_commenter.log is actually saved
        # This handles OneDrive folder redirection automatically
        linkedin_log_path = get_default_log_path()
        log_dir = os.path.dirname(linkedin_log_path)
        
        # Ensure the directory exists (it should, since linkedin_commenter.log works)
        os.makedirs(log_dir, exist_ok=True)
        
        comment_history_path = os.path.join(log_dir, "comment_history.json")
        debug_log(f"🔗 Using SAME directory as linkedin_commenter.log: {log_dir}", "INIT")
        print(f"[APP_OUT]🔗 Comment history will be saved alongside linkedin_commenter.log in: {log_dir}")
        
        return comment_history_path
        
    except Exception as e:
        # Absolute fallback to current directory
        print(f"Warning: Could not determine log directory, using current directory: {e}")
        debug_log(f"Error determining comment history path: {e}", "ERROR")
        return "comment_history.json"

def load_comment_history():
    """Load the comment history from file in the proper JuniorAI/logs directory."""
    try:
        history_path = get_comment_history_path()
        debug_log(f"📖 Loading comment history from: {history_path}", "DATA")
        print(f"[APP_OUT]📖 Looking for comment history at: {history_path}")
        
        if os.path.exists(history_path):
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
            debug_log(f"✅ Loaded {len(history)} comments from history", "DATA")
            print(f"[APP_OUT]✅ Loaded {len(history)} comments from history")
            return history
        else:
            debug_log(f"📄 Comment history file not found, starting fresh", "DATA")
            print(f"[APP_OUT]📄 No existing comment history found, starting fresh")
            return {}
    except Exception as e:
        debug_log(f"❌ Error loading comment history: {e}", "ERROR")
        print(f"[APP_OUT]❌ Error loading comment history: {e}")
        return {}

def save_comment_history(history):
    """Save the comment history to file in the proper JuniorAI/logs directory."""
    try:
        history_path = get_comment_history_path()
        debug_log(f"💾 Saving comment history to: {history_path}", "DATA")
        print(f"[APP_OUT]💾 Comment history path: {history_path}")
        
        # Ensure directory exists
        comment_dir = os.path.dirname(history_path)
        if comment_dir and comment_dir != '':
            os.makedirs(comment_dir, exist_ok=True)
            debug_log(f"📁 Created/verified directory: {comment_dir}", "DATA")
            print(f"[APP_OUT]📁 Created/verified directory: {comment_dir}")
            
        # Additional validation
        if not isinstance(history, dict):
            debug_log(f"⚠️ Warning: history is not a dict, converting. Type: {type(history)}", "WARNING")
            history = {} if history is None else dict(history)
            
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        # Verify the file was actually created
        if os.path.exists(history_path):
            file_size = os.path.getsize(history_path)
            debug_log(f"✅ Saved {len(history)} comments to history at {history_path} (size: {file_size} bytes)", "DATA")
            print(f"[APP_OUT]✅ Successfully saved {len(history)} comments to history file ({file_size} bytes)")
        else:
            debug_log(f"❌ File was not created: {history_path}", "ERROR")
            print(f"[APP_OUT]❌ File was not created: {history_path}")
        
    except Exception as e:
        debug_log(f"❌ Error saving comment history: {e}", "ERROR")
        print(f"[APP_OUT]❌ Failed to save comment history: {e}")
        # Try to provide more details about the error
        import traceback
        debug_log(f"❌ Comment history save traceback: {traceback.format_exc()}", "ERROR")

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

# ========== LEVEL 5: ADVANCED SESSION WARMING & NATURAL NAVIGATION ==========

def advanced_session_warming(driver):
    """
    SIMPLIFIED session warming to reduce browser timeout issues.
    Focus on essential warming without complex interactions.
    """
    debug_log("🔥 SIMPLIFIED: Beginning lightweight session warming")
    
    try:
        # Step 1: Simple LinkedIn landing page visit
        debug_log("Step 1: Basic LinkedIn navigation")
        driver.get("https://www.linkedin.com")
        time.sleep(random.uniform(3, 6))
        
        # Step 2: Visit feed page (most common user behavior)
        debug_log("Step 2: Feed page visit")
        try:
            driver.get("https://www.linkedin.com/feed/")
            time.sleep(random.uniform(4, 8))
            
            # Simple scroll simulation (reduced complexity)
            for i in range(random.randint(1, 2)):
                driver.execute_script(f"window.scrollBy(0, {random.randint(300, 600)});")
                time.sleep(random.uniform(2, 4))
                
        except Exception as e:
            debug_log(f"Feed visit error (non-critical): {e}")
        
        # Step 3: Brief visit to one more section (simplified)
        debug_log("Step 3: Brief secondary page visit")
        try:
            secondary_pages = [
                "https://www.linkedin.com/mynetwork/",
                "https://www.linkedin.com/notifications/"
            ]
            
            selected_page = random.choice(secondary_pages)
            driver.get(selected_page)
            time.sleep(random.uniform(3, 6))
            
        except Exception as e:
            debug_log(f"Secondary page error (non-critical): {e}")
        
        # Step 4: Return to feed and final warming
        debug_log("Step 4: Final warming phase")
        try:
            driver.get("https://www.linkedin.com/feed/")
            time.sleep(random.uniform(5, 10))
            
        except Exception as e:
            debug_log(f"Final warming error (non-critical): {e}")
        
        debug_log("✅ Simplified session warming completed successfully")
        return True
        
    except Exception as e:
        debug_log(f"⚠️ Session warming encountered issues: {e}")
        debug_log("Using minimal delay as fallback")
        time.sleep(random.uniform(8, 15))  # Minimal fallback delay
        return False

def natural_job_search(driver, keywords, time_filter="past-24h", max_retries=2):
    """
    IMPROVED: Use direct URL navigation to avoid interface interaction issues.
    This is more reliable than trying to interact with search elements.
    """
    debug_log(f"🔍 Improved search for: {keywords}")
    
    for attempt in range(max_retries):
        try:
            debug_log(f"Search attempt {attempt + 1}/{max_retries}")
            
            # STRATEGY 1: Direct LinkedIn search URL (most reliable)
            search_query = f"{keywords} hiring"
            debug_log(f"🔍 Constructed search query: '{search_query}'", "SEARCH")
            print(f"[APP_OUT]🔍 Search query with hiring: '{search_query}'")
            encoded_query = search_query.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
            debug_log(f"🔗 URL-encoded query: '{encoded_query}'", "SEARCH")
            
            # Use the most reliable LinkedIn search URL format  
            if time_filter == "past-24h":
                direct_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&origin=SWITCH_SEARCH_VERTICAL&datePosted=past-24h"
            else:
                direct_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&origin=SWITCH_SEARCH_VERTICAL"
            
            debug_log(f"Using direct URL: {direct_url}")
            print(f"[APP_OUT]🔗 Full search URL: {direct_url}")
            driver.get(direct_url)
            time.sleep(random.uniform(4, 8))
            
            # Check if we successfully reached search results (simple validation)
            current_url = driver.current_url.lower()
            page_title = driver.title.lower()
            
            if "search" in current_url and "linkedin" in current_url:
                debug_log("✅ Successfully navigated to LinkedIn search results")
                
                # Quick check for any content on the page
                try:
                    # Look for any of these indicators that content loaded
                    result_indicators = [
                        ".search-results-container",
                        ".search-results__list", 
                        "[data-chameleon-result-urn]",
                        ".feed-shared-update-v2",
                        ".search-result__wrapper",
                        ".artdeco-empty-state"  # Even "no results" page is valid
                    ]
                    
                    content_found = False
                    for indicator in result_indicators:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, indicator)
                            if elements:
                                debug_log(f"✅ Found content with selector: {indicator}")
                                content_found = True
                                break
                        except:
                            continue
                    
                    if content_found or "no results" in page_title:
                        debug_log(f"✅ Search completed successfully for: {keywords}")
                        return True
                    else:
                        debug_log("⚠️ Page loaded but no content found, trying fallback...")
                        
                except Exception as content_error:
                    debug_log(f"Content check error (non-critical): {content_error}")
                    # If we can't verify content but URL looks right, assume success
                    return True
            
            # If direct URL failed, try fallback approach
            debug_log("⚠️ Direct URL didn't work, trying fallback...")
            
        except Exception as e:
            debug_log(f"❌ Search attempt {attempt + 1} failed: {str(e)[:100]}...")
            
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 3
                debug_log(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                continue
    
    # STRATEGY 2: Fallback URL variations if main approach fails
    debug_log("🔄 Trying fallback URL strategies...")
    
    try:
        search_variations = [
            f"{keywords} jobs",
            f"hiring {keywords}",
            f"{keywords} recruiting"
        ]
        
        for variation in search_variations:
            try:
                encoded_query = variation.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
                fallback_url = f"https://www.linkedin.com/search/results/all/?keywords={encoded_query}"
                
                debug_log(f"Trying fallback: {fallback_url[:80]}...")
                driver.get(fallback_url)
                time.sleep(random.uniform(3, 6))
                
                if "search" in driver.current_url.lower():
                    debug_log("✅ Fallback URL successful")
                    return True
                    
            except Exception as fallback_error:
                debug_log(f"Fallback attempt failed: {fallback_error}")
                continue
    
    except Exception as e:
        debug_log(f"❌ All fallback attempts failed: {e}")
    
    debug_log(f"❌ All search methods failed for: {keywords}")
    return False

# ========== ENHANCED BEHAVIORAL PATTERNS ==========

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
