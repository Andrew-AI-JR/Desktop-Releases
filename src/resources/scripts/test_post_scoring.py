"""
Test script for LinkedIn post scoring.
Run this script to verify scoring changes with example posts.
"""

import json
from linkedin_commenter import calculate_post_score, should_comment_on_post, get_time_based_score

def test_post():
    # New sample post from Emilio Arias (3 weeks old)
    test_post = """I'm eager to share that I'm starting a new position as Senior Technical Recruiter at Rad AI!

Over the past few years, I've realized how deeply motivated I am by mission-driven work—especially at the intersection of health, technology, and social impact.
My time at Rula reaffirmed that conviction. Helping expand access to mental health care showed me just how powerful it can be to build teams around meaningful, purpose-led work.

Continuing in that spirit, I'm excited to share that I've joined Rad AI as a Senior Recruiter!

Rad AI is using generative AI to help radiologists work more efficiently, reduce burnout, and ultimately deliver better patient care. It's thoughtful, high-impact work—and I'm honored to be part of the team helping to scale it.
We're growing fast, and I'm hiring for:
🧠 Senior ML Research Scientists
💻 Software Engineering Interns (Summer 2025)
If you're excited about building at the intersection of healthcare and AI, let's connect."""

    author_name = "Emilio Arias"
    time_filter = "past-month"  # Post is 3 weeks old
    hours_ago = 21 * 24  # 3 weeks in hours

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
