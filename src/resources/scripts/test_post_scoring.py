"""
Test script for LinkedIn post scoring.
Run this script and paste LinkedIn post text to see its score breakdown.
"""

import json
from linkedin_commenter import CommentGenerator, POST_SCORING_CONFIG

def get_time_filter():
    """Prompt user to select a time filter."""
    print("\nSelect time filter (affects scoring):")
    print("1. Past 24 hours (2.0x multiplier)")
    print("2. Past week (1.5x multiplier)")
    print("3. Past month (1.0x multiplier)")
    print("4. No time filter (1.0x multiplier)")
    
    while True:
        choice = input("Enter your choice (1-4): ").strip()
        if choice == '1':
            return 'past-24h'
        elif choice == '2':
            return 'past-week'
        elif choice in ('3', '4'):
            return 'past-month'
        print("Invalid choice. Please enter 1-4.")

def get_job_keywords():
    """Prompt user for job keywords."""
    print("\nEnter job keywords (comma-separated, or press Enter to skip):")
    keywords_input = input("> ").strip()
    if not keywords_input:
        return []
    return [k.strip().lower() for k in keywords_input.split(',') if k.strip()]

def print_score_breakdown(score_breakdown):
    """Print the score breakdown in a readable format."""
    print("\n" + "="*50)
    print("SCORE BREAKDOWN")
    print("="*50)
    
    # Print category scores
    for category, data in score_breakdown.items():
        if category == 'final_score':
            continue
        if isinstance(data, dict):
            score = data.get('score', 0)
            if score > 0 or 'multiplier' in data:  # Only show categories with positive score or explicit multiplier
                print(f"{category.upper()}: {score:.2f}")
    
    # Print final score breakdown
    if 'final_score' in score_breakdown:
        final = score_breakdown['final_score']
        print("\n" + "-"*50)
        print(f"BASE SCORE: {final.get('base_score', 0):.2f}")
        print(f"TIME MULTIPLIER: {final.get('time_multiplier', 1.0)}x")
        print(f"FINAL SCORE: {final.get('final_score', 0):.2f}")
        print("="*50)

def main():
    print("LinkedIn Post Scoring Test")
    print("="*50)
    
    # Get user input
    job_keywords = get_job_keywords()
    time_filter = get_time_filter()
    
    # Initialize comment generator with job keywords
    comment_generator = CommentGenerator(
        user_bio="Test bio",  # Not used in scoring
        config=POST_SCORING_CONFIG,
        job_keywords=job_keywords
    )
    
    print("\nPaste the LinkedIn post text (press Enter twice when done):")
    post_lines = []
    while True:
        line = input()
        if not line.strip() and post_lines and not post_lines[-1].strip():
            break
        post_lines.append(line)
    
    post_text = '\n'.join(post_lines).strip()
    if not post_text:
        print("No post text provided. Exiting.")
        return
    
    # Calculate score with detailed breakdown
    score_breakdown = {}
    
    def debug_log(message, level=None):
        if level == "SCORE" and message.startswith("Post scoring breakdown:"):
            # Extract the JSON part of the message
            try:
                json_str = message.split("Post scoring breakdown: ", 1)[1]
                score_breakdown.update(json.loads(json_str))
            except (IndexError, json.JSONDecodeError) as e:
                print(f"Error parsing score breakdown: {e}")
    
    # Monkey patch debug_log to capture the score breakdown
    import sys
    original_debug_log = sys.modules[__name__].debug_log if 'debug_log' in sys.modules[__name__].__dict__ else None
    sys.modules[__name__].debug_log = debug_log
    
    # Calculate the score
    score = comment_generator.calculate_post_score(post_text, time_filter=time_filter)
    
    # Restore original debug_log if it existed
    if original_debug_log:
        sys.modules[__name__].debug_log = original_debug_log
    
    # Print results
    print("\n" + "="*50)
    print(f"POST SCORE: {score:.2f}")
    print("="*50)
    
    if score_breakdown:
        print_score_breakdown(score_breakdown)
    
    # Print interpretation
    print("\nSCORE INTERPRETATION:")
    if score >= 55:
        print("✅ Excellent match - This post is highly relevant and worth commenting on")
    elif score >= 40:
        print("👍 Good match - This post is relevant")
    elif score >= 20:
        print("🤔 Moderate match - This post might be relevant")
    else:
        print("⏭️  Low relevance - Consider skipping this post")

if __name__ == "__main__":
    main()
