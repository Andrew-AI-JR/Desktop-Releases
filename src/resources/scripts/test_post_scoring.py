"""
Test script for LinkedIn post scoring.
Run this script to verify scoring changes with example posts.
"""

import json
from linkedin_commenter import calculate_post_score, should_comment_on_post, get_time_based_score

def test_post():
    # Example post that shouldn't have triggered a comment
    test_post = """🚀 We're entering the era of touchless recruiting, where AI-driven automation is transforming how talent acquisition operates. At one of our customer sites, we've begun embedding Generative AI and agentic tools within Oracle Recruiting Cloud (ORC) to eliminate repetitive tasks and streamline the end-to-end hiring journey.

From auto-generating job descriptions and emails to screening candidates, these smart tools are helping recruiters reclaim their time for more strategic, human-centric work.

Generative AI isn't replacing recruiters - it's amplifying them.

Next Up: leveraging AI Agent Studio to develop more tailored and personalized solutions.

If you're working with ORC or leading a TA transformation, now's the time to explore what embedded AI + SaaS-native platforms can do. The tools are ready-and the results are real."""

    author_name = "Manoj Gupta"
    time_filter = "past-week"  # Post is 6 days old
    hours_ago = 6 * 24  # 6 days in hours

    # Calculate raw score
    raw_score = calculate_post_score(test_post, author_name, time_filter)
    
    # Check if we should comment
    should_comment, final_score = should_comment_on_post(
        test_post, 
        author_name=author_name,
        hours_ago=hours_ago,
        min_score=55,
        time_filter=time_filter
    )

    print("\n=== Post Analysis ===")
    print(f"Raw Score: {raw_score:.1f}")
    print(f"Final Score: {final_score:.1f}")
    print(f"Should Comment: {'Yes' if should_comment else 'No'}")
    print("\nScore Breakdown:")
    
    # Check for negative context matches
    negative_matches = []
    for keyword in ['era of', 'transforming', 'automation', 'future']:
        if keyword in test_post.lower():
            negative_matches.append(keyword)
    
    if negative_matches:
        print(f"⚠️ Negative Context Keywords Found: {', '.join(negative_matches)}")
    
    # Check for hiring intent
    hiring_indicators = ['hiring', 'job opening', 'position available', 'join our team']
    hiring_matches = []
    for keyword in hiring_indicators:
        if keyword in test_post.lower():
            hiring_matches.append(keyword)
    
    if not hiring_matches:
        print("❌ No Clear Hiring Intent Found")
    
    # Time-based analysis
    time_multiplier = get_time_based_score(time_filter)
    print(f"\nTime Analysis:")
    print(f"Time Filter: {time_filter}")
    print(f"Hours Ago: {hours_ago}")
    print(f"Time Multiplier: {time_multiplier:.2f}")

if __name__ == "__main__":
    test_post()
