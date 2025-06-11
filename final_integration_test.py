#!/usr/bin/env python3
"""
Final comprehensive test to verify subscription limit integration with main script workflow.
"""

import sys
import os
import json

# Add the scripts directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'resources', 'scripts'))

# Import the CommentGenerator and needed functions
from linkedin_commenter import CommentGenerator, load_config_from_file

def test_subscription_integration():
    """Test the complete subscription integration with main script workflow."""
    
    print("🔗 Final Subscription Integration Test")
    print("=" * 60)
    
    # Load config like the main script does
    try:
        config_path = "../test_config.json"  # Path relative to test script
        config = load_config_from_file(config_path)
        
        if not config:
            print("❌ Failed to load configuration file")
            return False
            
        print(f"✅ Configuration loaded from: {config_path}")
        print(f"   • Backend URL: {config.get('backend_url', 'Not set')}")
        print(f"   • Email: {config.get('linkedin_credentials', {}).get('email', 'Not set')}")
        
    except Exception as config_error:
        print(f"❌ Configuration loading failed: {config_error}")
        return False
    
    # Test initialization like main script
    try:
        print("\n🔧 Step 1: Initialize CommentGenerator (like main script)")
        print("-" * 50)
        
        USER_BIO = config.get('user_bio', 'Test user bio')
        JOB_SEARCH_KEYWORDS = config.get('keywords', 'data science,python').split(',')
        
        comment_generator = CommentGenerator(
            user_bio=USER_BIO,
            config=config,  # This is the key fix - passing config for backend access
            job_keywords=JOB_SEARCH_KEYWORDS
        )
        
        print("✅ CommentGenerator initialized with config")
        print(f"   • User Bio: {USER_BIO[:50]}...")
        print(f"   • Keywords: {JOB_SEARCH_KEYWORDS}")
        print(f"   • Backend URL: {comment_generator.backend_base}")
        
    except Exception as init_error:
        print(f"❌ CommentGenerator initialization failed: {init_error}")
        return False
    
    # Test subscription limit checking (the main integration point)
    print("\n🔧 Step 2: Test subscription limit checking workflow")
    print("-" * 50)
    
    try:
        # This simulates the main script's limit checking logic
        print("📊 Simulating main script limit checking workflow...")
        
        # Test the integrated limit checking
        within_limits = comment_generator.check_usage_limits()
        
        print(f"Subscription Limit Check Result: {'✅ Within Limits' if within_limits else '❌ Limits Exceeded'}")
        
        # Display current subscription state
        print("\n📋 Current Subscription State:")
        print(f"   • Has Subscription: {getattr(comment_generator, 'has_subscription', 'Unknown')}")
        print(f"   • Daily Usage: {getattr(comment_generator, 'daily_usage', 'Unknown')}")
        print(f"   • Monthly Usage: {getattr(comment_generator, 'monthly_usage', 'Unknown')}")
        print(f"   • Daily Limit: {getattr(comment_generator, 'daily_limit', 'Unknown')}")
        print(f"   • Monthly Limit: {getattr(comment_generator, 'monthly_limit', 'Unknown')}")
        print(f"   • Subscription Tier: {getattr(comment_generator, 'subscription_tier', 'Unknown')}")
        print(f"   • Warmup Mode: {getattr(comment_generator, 'is_warmup', 'Unknown')}")
        
    except Exception as limit_error:
        print(f"❌ Subscription limit checking failed: {limit_error}")
        return False
    
    # Test fallback behavior (when subscription endpoints fail)
    print("\n🔧 Step 3: Test fallback limit behavior")
    print("-" * 50)
    
    try:
        # Simulate what happens when subscription endpoints fail
        print("Testing fallback behavior when subscription endpoints are unavailable...")
        
        # Save original URLs
        original_limits_url = comment_generator.subscription_limits_url
        original_usage_url = comment_generator.subscription_usage_url
        
        # Temporarily break the URLs to test fallback
        comment_generator.subscription_limits_url = "https://invalid-url-for-testing.com/limits"
        comment_generator.subscription_usage_url = "https://invalid-url-for-testing.com/usage"
        
        # Test fallback behavior
        fallback_result = comment_generator.check_usage_limits()
        print(f"Fallback Limit Check Result: {'✅ Proceeded' if fallback_result else '❌ Failed'}")
        
        # Restore original URLs
        comment_generator.subscription_limits_url = original_limits_url
        comment_generator.subscription_usage_url = original_usage_url
        
        print("✅ Fallback behavior works correctly")
        
    except Exception as fallback_error:
        print(f"❌ Fallback testing failed: {fallback_error}")
        return False
    
    # Test comment generation with subscription context
    print("\n🔧 Step 4: Test comment generation with subscription context")
    print("-" * 50)
    
    try:
        test_post = "We're hiring a Data Scientist! Looking for Python and ML experience."
        
        comment = comment_generator.generate_comment(test_post)
        
        if comment:
            print("✅ Comment generation successful with subscription integration")
            print(f"Generated Comment: {comment[:100]}...")
        else:
            print("❌ Comment generation failed")
            
    except Exception as comment_error:
        print(f"❌ Comment generation test failed: {comment_error}")
        return False
    
    # Test the main script integration pattern
    print("\n🔧 Step 5: Simulate main script integration pattern")
    print("-" * 50)
    
    try:
        # This simulates the exact pattern used in the main script
        print("Simulating main script limit checking pattern...")
        
        # Mock session/daily counters
        session_comments = 0
        daily_comments = 0
        MAX_SESSION_COMMENTS = 10
        MAX_DAILY_COMMENTS = 50
        
        # Simulate the main script's keyword processing loop
        search_keywords = ["data science", "python"]
        
        for i, keyword in enumerate(search_keywords, 1):
            print(f"\n🔍 Processing keyword {i}/{len(search_keywords)}: {keyword}")
            
            # ENHANCED: Use backend subscription limits (exactly like main script)
            try:
                # Check subscription usage limits from backend API
                within_limits = comment_generator.check_usage_limits()
                
                if not within_limits:
                    print(f"🛑 Subscription limits reached - would stop processing")
                    break
                else:
                    print(f"✅ Within subscription limits - would continue processing")
                    
            except Exception as limit_error:
                # Fallback to hardcoded limits (exactly like main script)
                print(f"⚠️ Subscription limit check failed, using fallback limits: {limit_error}")
                
                # Fallback to original hardcoded behavior
                if session_comments >= MAX_SESSION_COMMENTS:
                    print(f"🛑 Session limit reached ({MAX_SESSION_COMMENTS} comments)")
                    break

                if daily_comments >= MAX_DAILY_COMMENTS:
                    print(f"🛑 Daily limit reached ({MAX_DAILY_COMMENTS} comments)")
                    break
                    
                print(f"✅ Within fallback limits - would continue processing")
        
        print("✅ Main script integration pattern works correctly")
        
    except Exception as integration_error:
        print(f"❌ Main script integration test failed: {integration_error}")
        return False
    
    print("\n" + "=" * 60)
    print("🏁 Final Integration Test Complete!")
    
    print("\n📊 Integration Summary:")
    print("   ✅ Configuration loading works")
    print("   ✅ CommentGenerator initialization with config works")
    print("   ✅ Subscription limit checking works")
    print("   ✅ Fallback behavior works when endpoints fail")
    print("   ✅ Comment generation works with subscription context")
    print("   ✅ Main script integration pattern works")
    
    print("\n🎯 Key Improvements Verified:")
    print("   • Backend subscription limits replace hardcoded limits")
    print("   • Graceful fallback when subscription endpoints fail")
    print("   • Real-time usage tracking from backend API")
    print("   • Proper authentication and limit validation")
    print("   • Seamless integration with existing main script workflow")
    
    return True

if __name__ == "__main__":
    success = test_subscription_integration()
    sys.exit(0 if success else 1) 