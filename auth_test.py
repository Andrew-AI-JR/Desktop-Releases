#!/usr/bin/env python3
"""
Simple script to test JWT authentication with the backend API.
"""

import requests
import json
import sys

def test_authentication():
    """Test JWT authentication with the backend API."""
    
    # Configuration from test_config.json
    backend_url = "https://junior-api-915940312680.us-west1.run.app"
    linkedin_email = "amalinow1973@gmail.com"
    linkedin_password = "test"
    
    print("🔧 Testing JWT Authentication with Backend API")
    print("=" * 50)
    print(f"Backend URL: {backend_url}")
    print(f"Email: {linkedin_email}")
    print(f"Password: {'*' * len(linkedin_password)}")
    print()
    
    # Test 1: Authentication
    print("📡 Step 1: Testing login authentication...")
    login_url = f"{backend_url}/api/users/token"
    
    try:
        login_payload = {
            "email": linkedin_email,
            "password": linkedin_password
        }
        
        print(f"POST {login_url}")
        print(f"Payload: {json.dumps(login_payload, indent=2)}")
        
        response = requests.post(
            login_url,
            json=login_payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            auth_data = response.json()
            print("✅ Authentication successful!")
            print(f"Response: {json.dumps(auth_data, indent=2)}")
            
            access_token = auth_data.get('access_token')
            refresh_token = auth_data.get('refresh_token')
            
            if access_token:
                print(f"🔑 Access Token: {access_token[:30]}...")
                print(f"🔄 Refresh Token: {refresh_token[:30] if refresh_token else 'None'}...")
                
                # Test 2: Token verification
                print("\n📡 Step 2: Testing token verification...")
                me_url = f"{backend_url}/api/users/me"
                
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
                
                print(f"GET {me_url}")
                print(f"Headers: {headers}")
                
                me_response = requests.get(me_url, headers=headers, timeout=10)
                print(f"Response Status: {me_response.status_code}")
                
                if me_response.status_code == 200:
                    user_data = me_response.json()
                    print("✅ Token verification successful!")
                    print(f"User Data: {json.dumps(user_data, indent=2)}")
                else:
                    print(f"❌ Token verification failed: {me_response.status_code}")
                    print(f"Response: {me_response.text}")
                
                # Test 3: Comment generation
                print("\n📡 Step 3: Testing comment generation...")
                comments_url = f"{backend_url}/api/comments/generate"
                
                test_post = "We're hiring a Data Scientist for our AI team! Looking for someone with Python and machine learning experience. Great opportunity to work on cutting-edge projects."
                
                comment_payload = {
                    'post_text': test_post,
                    'source_linkedin_url': 'https://linkedin.com/posts/test',
                    'comment_date': '2024-12-10T15:30:00.000Z',
                    'calendly_link': 'https://calendly.com/yourlink'
                }
                
                print(f"POST {comments_url}")
                print(f"Payload: {json.dumps(comment_payload, indent=2)}")
                
                comment_response = requests.post(
                    comments_url,
                    json=comment_payload,
                    headers=headers,
                    timeout=30
                )
                
                print(f"Response Status: {comment_response.status_code}")
                
                if comment_response.status_code == 200:
                    try:
                        comment_data = comment_response.json()
                        print("✅ Comment generation successful!")
                        print(f"Generated Comment: {json.dumps(comment_data, indent=2)}")
                    except:
                        print("✅ Comment generation successful!")
                        print(f"Generated Comment: {comment_response.text}")
                else:
                    print(f"❌ Comment generation failed: {comment_response.status_code}")
                    print(f"Response: {comment_response.text}")
                
            else:
                print("❌ No access token received in response")
        else:
            print(f"❌ Authentication failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"🌐 Network error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False
    
    print("\n" + "=" * 50)
    print("🏁 JWT Authentication test completed!")
    return True

if __name__ == "__main__":
    success = test_authentication()
    sys.exit(0 if success else 1) 