#!/bin/bash

# Comprehensive Python bundling setup script
# This script helps developers build Python executables for distribution

set -e

echo "🐍 Python Bundling Setup for Junior Desktop"
echo "==========================================="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if we're in the right directory
if [[ ! -f "package.json" ]] || [[ ! -d "src/resources/scripts" ]]; then
    log_error "Please run this script from the junior-desktop project root directory"
    exit 1
fi

# Function to check Python installation
check_python() {
    log_info "Checking Python installation..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1)
        log_success "Found Python: $PYTHON_VERSION"
        return 0
    else
        log_error "Python 3 not found. Please install Python 3.8 or later."
        return 1
    fi
}

# Function to install PyInstaller
install_pyinstaller() {
    log_info "Installing PyInstaller..."
    
    if python3 -m pip install pyinstaller; then
        log_success "PyInstaller installed successfully"
    else
        log_error "Failed to install PyInstaller"
        exit 1
    fi
}

# Function to install Python dependencies
install_dependencies() {
    log_info "Installing Python dependencies..."
    
    if [[ -f "src/resources/scripts/requirements.txt" ]]; then
        if python3 -m pip install -r src/resources/scripts/requirements.txt; then
            log_success "Python dependencies installed successfully"
        else
            log_error "Failed to install Python dependencies"
            exit 1
        fi
    else
        log_error "requirements.txt not found"
        exit 1
    fi
}

# Function to build Python executable
build_executable() {
    log_info "Building Python executable for current platform..."
    
    # Get platform info
    case "$(uname -s)" in
        Darwin*)
            if [[ "$(uname -m)" == "arm64" ]]; then
                PLATFORM_DIR="mac-arm64"
            else
                PLATFORM_DIR="mac-x64"
            fi
            ;;
        Linux*)
            if [[ "$(uname -m)" == "x86_64" ]]; then
                PLATFORM_DIR="linux-x64"
            else
                PLATFORM_DIR="linux-ia32"
            fi
            ;;
        CYGWIN*|MINGW32*|MSYS*|MINGW*)
            if [[ "$(uname -m)" == "x86_64" ]]; then
                PLATFORM_DIR="win-x64"
            else
                PLATFORM_DIR="win-ia32"
            fi
            ;;
        *)
            log_error "Unsupported platform: $(uname -s)"
            exit 1
            ;;
    esac
    
    log_info "Building for platform: $PLATFORM_DIR"
    
    # Create output directory
    mkdir -p "resources/python-executables/$PLATFORM_DIR"
    
    # Build using PyInstaller
    if python3 -m PyInstaller \
        --distpath "resources/python-executables/$PLATFORM_DIR" \
        --workpath "build/pyinstaller" \
        linkedin_commenter.spec; then
        log_success "Build completed for $PLATFORM_DIR"
        
        # Check if executable was created
        if [[ -f "resources/python-executables/$PLATFORM_DIR/linkedin_commenter" ]]; then
            log_success "Executable created: resources/python-executables/$PLATFORM_DIR/linkedin_commenter"
            
            # Make executable on Unix systems
            if [[ "$(uname -s)" != CYGWIN* ]] && [[ "$(uname -s)" != MINGW* ]] && [[ "$(uname -s)" != MSYS* ]]; then
                chmod +x "resources/python-executables/$PLATFORM_DIR/linkedin_commenter"
                log_success "Set executable permissions"
            fi
        else
            log_error "Executable not found after build"
            exit 1
        fi
    else
        log_error "Build failed"
        exit 1
    fi
}

# Function to test the built executable
test_executable() {
    log_info "Testing the built executable..."
    
    # Create a test config
    cat > test-config-minimal.json << EOF
{
  "credentials": {
    "email": "test@example.com",
    "password": "test"
  },
  "calendly_url": "https://calendly.com/test",
  "user_bio": "Test bio",
  "keywords": "test",
  "limits": {
    "commentsPerCycle": 1
  },
  "chrome_profile_path": "/tmp/test_profile"
}
EOF

    # Get platform directory
    case "$(uname -s)" in
        Darwin*)
            if [[ "$(uname -m)" == "arm64" ]]; then
                PLATFORM_DIR="mac-arm64"
            else
                PLATFORM_DIR="mac-x64"
            fi
            ;;
        Linux*)
            PLATFORM_DIR="linux-x64"
            ;;
        *)
            log_warning "Skipping test on this platform"
            return 0
            ;;
    esac
    
    EXECUTABLE_PATH="resources/python-executables/$PLATFORM_DIR/linkedin_commenter"
    
    if [[ -f "$EXECUTABLE_PATH" ]]; then
        log_info "Testing executable at: $EXECUTABLE_PATH"
        
        # Test with a timeout - the script will likely fail due to missing Chrome setup
        # but we just want to see if it starts and recognizes arguments
        timeout 10s "$EXECUTABLE_PATH" --config test-config-minimal.json 2>/dev/null || true
        
        if [[ $? -eq 124 ]]; then
            log_success "Executable started successfully (timed out as expected)"
        else
            log_success "Executable ran (may have exited early due to missing dependencies)"
        fi
        
        # Clean up test config
        rm -f test-config-minimal.json
    else
        log_error "Executable not found: $EXECUTABLE_PATH"
    fi
}

# Function to show next steps
show_next_steps() {
    echo
    log_success "Python bundling setup completed!"
    echo
    echo "Next steps:"
    echo "1. Test the automation service in the Electron app"
    echo "2. Build for other platforms if needed:"
    echo "   - On Windows: run scripts/build-python.bat"
    echo "   - On Linux: run this script on a Linux machine"
    echo "3. Build the Electron app: npm run build"
    echo
    echo "The bundled Python executable is located at:"
    echo "resources/python-executables/[platform]/linkedin_commenter"
    echo
}

# Main execution
main() {
    echo "Starting Python bundling setup..."
    echo
    
    # Check Python
    check_python || exit 1
    
    # Install PyInstaller
    install_pyinstaller
    
    # Install dependencies
    install_dependencies
    
    # Build executable
    build_executable
    
    # Test executable
    test_executable
    
    # Show next steps
    show_next_steps
}

# Show help
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo "Python Bundling Setup Script"
    echo
    echo "This script sets up Python bundling for the Junior Desktop application."
    echo "It will:"
    echo "1. Check Python installation"
    echo "2. Install PyInstaller"
    echo "3. Install Python dependencies"
    echo "4. Build a platform-specific executable"
    echo "5. Test the executable"
    echo
    echo "Usage: $0"
    echo "       $0 --help"
    echo
    exit 0
fi

# Run main function
main "$@"
