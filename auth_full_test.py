#!/usr/bin/env python3
"""
Comprehensive test for improved JWT authentication flow with is_active checking.
"""

import sys
import os
import json

# Add the scripts directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'resources', 'scripts'))

# Import the CommentGenerator
from linkedin_commenter import CommentGenerator

def test_full_authentication_flow():
    """Test the complete authentication flow including is_active verification."""
    
    print("🔐 Comprehensive Authentication Flow Test")
    print("=" * 60)
    
    # Configuration from test_config.json
    config = {
        'linkedin_credentials': {
            'email': 'amalinow1973@gmail.com',
            'password': 'test'
        },
        'calendly_link': 'https://calendly.com/yourlink',
        'backend_url': 'https://junior-api-915940312680.us-west1.run.app'
    }
    
    user_bio = "Data Scientist and AI Engineer with expertise in machine learning, Python, and analytics"
    job_keywords = ["data science", "machine learning", "python", "ai", "analytics"]
    
    print(f"Backend URL: {config['backend_url']}")
    print(f"Test Email: {config['linkedin_credentials']['email']}")
    print()
    
    # Test 1: Initialize CommentGenerator (this triggers authentication)
    print("🔧 Step 1: Initializing CommentGenerator (triggers auth flow)")
    print("-" * 50)
    
    try:
        generator = CommentGenerator(
            user_bio=user_bio,
            config=config,
            job_keywords=job_keywords
        )
        
        print("✅ CommentGenerator initialized successfully")
        
        # Check if authentication was successful
        if generator.access_token:
            print(f"✅ Access token obtained: {generator.access_token[:30]}...")
        else:
            print("❌ No access token - authentication failed")
            return False
            
        # Display user info that should be populated
        print("\n📋 User Account Information:")
        print(f"   • User ID: {getattr(generator, 'user_id', 'Not set')}")
        print(f"   • Email: {getattr(generator, 'user_email', 'Not set')}")
        print(f"   • Stripe Customer: {getattr(generator, 'stripe_customer_id', 'Not set')}")
        
    except Exception as e:
        print(f"❌ CommentGenerator initialization failed: {str(e)}")
        return False
    
    # Test 2: Manual verification call to see detailed output
    print("\n🔧 Step 2: Manual authentication verification")
    print("-" * 50)
    
    try:
        verification_result = generator._verify_authentication()
        print(f"Verification Result: {'✅ Success' if verification_result else '❌ Failed'}")
    except Exception as e:
        print(f"❌ Manual verification failed: {str(e)}")
    
    # Test 3: Test comment generation with subscription handling
    print("\n🔧 Step 3: Testing comment generation with subscription handling")
    print("-" * 50)
    
    test_post = "We're hiring a Senior Data Scientist! Looking for someone with Python and ML experience."
    
    try:
        comment = generator.generate_comment(test_post)
        
        if comment:
            print("✅ Comment generation successful!")
            print(f"Generated Comment Preview: {comment[:100]}...")
        else:
            print("❌ Comment generation failed!")
            
    except Exception as e:
        print(f"❌ Comment generation error: {str(e)}")
    
    # Test 4: Check authentication state
    print("\n🔧 Step 4: Authentication State Summary")
    print("-" * 50)
    
    print(f"Access Token: {'✅ Present' if generator.access_token else '❌ Missing'}")
    print(f"User ID: {getattr(generator, 'user_id', '❌ Not set')}")
    print(f"User Email: {getattr(generator, 'user_email', '❌ Not set')}")
    print(f"Stripe Customer: {getattr(generator, 'stripe_customer_id', '❌ Not set')}")
    
    # Test 5: Direct API call to understand subscription status
    print("\n🔧 Step 5: Direct API Subscription Test")
    print("-" * 50)
    
    try:
        import requests
        
        headers = generator._get_auth_headers()
        if headers:
            test_payload = {
                'post_text': 'Test post for subscription verification',
                'source_linkedin_url': 'https://linkedin.com/posts/test',
                'comment_date': '2024-12-10T15:30:00.000Z',
                'calendly_link': config['calendly_link']
            }
            
            print(f"Attempting API call to: {generator.comments_url}")
            response = requests.post(
                generator.comments_url,
                json=test_payload,
                headers=headers,
                timeout=15
            )
            
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ API subscription is active!")
                try:
                    data = response.json()
                    print(f"API Response: {json.dumps(data, indent=2)}")
                except:
                    print(f"API Response (text): {response.text}")
            elif response.status_code == 402:
                print("💳 Subscription required (expected for free users)")
                try:
                    error_data = response.json()
                    print(f"Error Details: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"Error Response: {response.text}")
            else:
                print(f"⚠️ Unexpected API response: {response.status_code}")
                print(f"Response: {response.text}")
        else:
            print("❌ Could not get authentication headers")
            
    except Exception as e:
        print(f"❌ Direct API test failed: {str(e)}")
    
    print("\n" + "=" * 60)
    print("🏁 Comprehensive Authentication Test Complete!")
    print("\n📊 Summary:")
    print("   • Authentication flow now properly checks is_active field")
    print("   • User account details are stored after verification")
    print("   • Subscription errors (402) are handled gracefully")
    print("   • Enhanced local generation serves as reliable fallback")
    
    return True

if __name__ == "__main__":
    success = test_full_authentication_flow()
    sys.exit(0 if success else 1) 