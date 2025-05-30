#!/usr/bin/env python3
import sys
print("Python test successful")
print(f"Python version: {sys.version}")
print("Testing LinkedIn commenter script...")

try:
    # Change to the script directory
    import os
    os.chdir('/Users/roberthall/projects/junior-desktop/src/resources/scripts')
    
    # Try to import the linkedin_commenter module
    import linkedin_commenter
    print("✅ LinkedIn commenter imports successful")
    
    # Call main function
    linkedin_commenter.main()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
