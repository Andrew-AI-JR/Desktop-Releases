#!/usr/bin/env python3
"""
Test script for the enhanced comment generation system.
"""

import sys
import os
import json

# Add the scripts directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'resources', 'scripts'))

# Import the CommentGenerator
from linkedin_commenter import CommentGenerator

def test_comment_generation():
    """Test the enhanced comment generation system."""
    
    print("🧪 Testing Enhanced Comment Generation System")
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
    
    # Initialize comment generator
    generator = CommentGenerator(
        user_bio=user_bio,
        config=config,
        job_keywords=job_keywords
    )
    
    # Test cases
    test_posts = [
        {
            'type': 'hiring',
            'text': "We're hiring a Senior Data Scientist for our AI team! Looking for someone with Python, machine learning, and deep learning experience. Great opportunity to work on cutting-edge projects at our fast-growing startup. Remote-friendly position with competitive salary and equity."
        },
        {
            'type': 'tech',
            'text': "Just published a comprehensive analysis on the latest trends in AI and machine learning. The rapid advancement in transformer models and their applications in natural language processing is truly remarkable. What are your thoughts on the future of AI?"
        },
        {
            'type': 'general',
            'text': "Reflecting on the importance of continuous learning in today's fast-paced tech industry. The key to staying relevant is adapting to new technologies and methodologies. Professional development should be a priority for everyone in tech."
        },
        {
            'type': 'leadership',
            'text': "As a Director of Engineering, I've learned that building great teams is about more than just technical skills. It's about fostering collaboration, encouraging innovation, and creating an environment where everyone can thrive."
        }
    ]
    
    print(f"User Bio: {user_bio}")
    print(f"Job Keywords: {job_keywords}")
    print(f"Calendly Link: {config['calendly_link']}")
    print()
    
    # Test each post type
    for i, test_case in enumerate(test_posts, 1):
        print(f"🔬 Test Case {i}: {test_case['type'].upper()} POST")
        print("-" * 40)
        print(f"Post Text: {test_case['text'][:100]}...")
        print()
        
        try:
            # Generate comment
            comment = generator.generate_comment(test_case['text'])
            
            if comment:
                print("✅ Comment Generation Successful!")
                print(f"Generated Comment:")
                print(f"'{comment}'")
                print()
                
                # Analyze comment quality
                has_calendly = config['calendly_link'] in comment
                word_count = len(comment.split())
                is_personalized = any(keyword.lower() in comment.lower() 
                                    for keyword in ['data science', 'machine learning', 'python', 'ai'])
                
                print(f"📊 Quality Analysis:")
                print(f"   • Word Count: {word_count}")
                print(f"   • Contains Calendly Link: {'✅' if has_calendly else '❌'}")
                print(f"   • Personalized Content: {'✅' if is_personalized else '❌'}")
                print(f"   • Appropriate Length: {'✅' if 20 <= word_count <= 150 else '❌'}")
                
            else:
                print("❌ Comment Generation Failed!")
                
        except Exception as e:
            print(f"❌ Error generating comment: {str(e)}")
        
        print("=" * 60)
        print()
    
    print("🏁 Comment Generation Testing Complete!")
    return True

if __name__ == "__main__":
    success = test_comment_generation()
    sys.exit(0 if success else 1) 