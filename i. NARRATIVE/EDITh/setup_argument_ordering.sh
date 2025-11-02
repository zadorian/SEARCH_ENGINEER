#!/bin/bash

# Argument Ordering Setup Script
# Sets up the complete visual drag-and-drop argument ordering system

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_step() {
    echo -e "${BLUE}🔵 $1${NC}"
}

# Main setup function
main() {
    print_header "🎯 ARGUMENT ORDERING SETUP"
    echo -e "${GREEN}Visual drag-and-drop argument reordering with AI text generation${NC}"
    echo
    
    # Check current directory
    if [[ ! -f "app.js" ]] || [[ ! -f "index.html" ]]; then
        print_error "Please run this script from the EDITh project directory"
        exit 1
    fi
    
    print_success "Running from correct directory: $(pwd)"
    echo
    
    # Step 1: Check dependencies
    print_step "Step 1: Checking Dependencies"
    echo "─────────────────────────────────"
    
    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version)
        print_success "Python available: $PYTHON_VERSION"
    else
        print_error "Python 3 not found. Please install Python 3.8 or later."
        exit 1
    fi
    
    # Check pip packages
    check_python_package() {
        if python3 -c "import $1" 2>/dev/null; then
            print_success "$2 installed"
        else
            print_warning "$2 not installed. Installing..."
            pip3 install $1
            print_success "$2 installed successfully"
        fi
    }
    
    check_python_package "flask" "Flask"
    check_python_package "flask_cors" "Flask-CORS"
    check_python_package "anthropic" "Anthropic API library"
    
    echo
    
    # Step 2: Verify files
    print_step "Step 2: Verifying Implementation Files"
    echo "──────────────────────────────────────"
    
    required_files=(
        "assets/js/modules/ArgumentOrderingPanel.js"
        "assets/js/modules/BlueprintManager.js"
        "blueprint_api_server.py"
        "claude_opus_blueprint_processor.py"
        "argument_demo.html"
    )
    
    for file in "${required_files[@]}"; do
        if [[ -f "$file" ]]; then
            print_success "$(basename "$file") exists"
        else
            print_error "Missing file: $file"
            exit 1
        fi
    done
    
    echo
    
    # Step 3: Check API key
    print_step "Step 3: API Key Configuration"
    echo "─────────────────────────────"
    
    if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
        print_success "ANTHROPIC_API_KEY is set"
    else
        print_warning "ANTHROPIC_API_KEY not set"
        echo
        echo "🔑 To use Claude Opus AI features, you need to set your API key:"
        echo "   export ANTHROPIC_API_KEY=your_api_key_here"
        echo
        echo "📖 Get your API key from: https://console.anthropic.com/"
        echo
        read -p "Do you have an API key you'd like to set now? (y/n): " -n 1 -r
        echo
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            read -s -p "Enter your Anthropic API key: " api_key
            echo
            export ANTHROPIC_API_KEY="$api_key"
            
            # Add to shell profile for persistence
            shell_profile=""
            if [[ -f "$HOME/.bashrc" ]]; then
                shell_profile="$HOME/.bashrc"
            elif [[ -f "$HOME/.zshrc" ]]; then
                shell_profile="$HOME/.zshrc"
            elif [[ -f "$HOME/.bash_profile" ]]; then
                shell_profile="$HOME/.bash_profile"
            fi
            
            if [[ -n "$shell_profile" ]]; then
                echo "export ANTHROPIC_API_KEY=\"$api_key\"" >> "$shell_profile"
                print_success "API key added to $shell_profile"
            fi
        else
            print_info "You can set the API key later using the UI or environment variable"
        fi
    fi
    
    echo
    
    # Step 4: Start API server
    print_step "Step 4: Starting API Server"
    echo "───────────────────────────"
    
    # Check if server is already running
    if curl -s http://localhost:5000/api/health &>/dev/null; then
        print_success "API server is already running"
    else
        print_info "Starting Flask API server..."
        
        # Start server in background
        python3 blueprint_api_server.py &
        SERVER_PID=$!
        
        # Wait for server to start
        for i in {1..10}; do
            if curl -s http://localhost:5000/api/health &>/dev/null; then
                print_success "API server started successfully (PID: $SERVER_PID)"
                break
            fi
            sleep 1
        done
        
        if ! curl -s http://localhost:5000/api/health &>/dev/null; then
            print_error "Failed to start API server"
            exit 1
        fi
    fi
    
    echo
    
    # Step 5: Run tests
    print_step "Step 5: Running System Tests"
    echo "────────────────────────────"
    
    # Test health endpoint
    if health_response=$(curl -s http://localhost:5000/api/health); then
        print_success "Health endpoint responding"
    else
        print_error "Health endpoint failed"
        exit 1
    fi
    
    # Test validation endpoint
    if curl -s -X POST http://localhost:5000/api/blueprint/validate \
       -H "Content-Type: application/json" \
       -d '{"arguments":[{"id":"test","claim":"Test","dependencies":[]}]}' &>/dev/null; then
        print_success "Validation endpoint working"
    else
        print_error "Validation endpoint failed"
        exit 1
    fi
    
    echo
    
    # Step 6: Success and instructions
    print_step "🎉 Setup Complete!"
    echo "─────────────────"
    echo
    print_success "All components are installed and running successfully!"
    echo
    echo "📋 NEXT STEPS:"
    echo
    echo "1. 🌐 Open the application:"
    echo "   • Main app: open index.html in your browser"
    echo "   • Demo: open argument_demo.html"
    echo
    echo "2. 🎯 Access argument ordering:"
    echo "   • Click the Blueprint Mode button (📐)"
    echo "   • Click the Arguments button"
    echo "   • Or use the demo page directly"
    echo
    echo "3. 🔑 Configure API key (if not done above):"
    echo "   • Click the menu → API Configuration"
    echo "   • Or set: export ANTHROPIC_API_KEY=your_key"
    echo
    echo "📖 FEATURES AVAILABLE:"
    echo "   ✅ Visual drag-and-drop argument reordering"
    echo "   ✅ Real-time AI text rewriting with Claude Opus"
    echo "   ✅ Constraint validation and dependency checking"
    echo "   ✅ Smart Note knowledge integration"
    echo "   ✅ Live preview of generated content"
    echo
    print_info "API Server running at: http://localhost:5000"
    print_info "Health check: curl http://localhost:5000/api/health"
    echo
    print_success "Ready to use! 🚀"
}

# Handle interruption
trap 'echo -e "\n${RED}Setup interrupted${NC}"; exit 1' INT

# Run main function
main "$@"