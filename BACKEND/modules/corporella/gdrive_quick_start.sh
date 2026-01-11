#!/bin/bash

# Google Drive Quick Start Script
# This script helps you quickly set up and use Google Drive from terminal

echo "====================================="
echo "Google Drive Terminal Access Setup"
echo "====================================="
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install rclone
install_rclone() {
    echo "Installing rclone..."

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command_exists brew; then
            brew install rclone
        else
            echo "Homebrew not found. Installing via curl..."
            curl https://rclone.org/install.sh | sudo bash
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        curl https://rclone.org/install.sh | sudo bash
    else
        echo "Unsupported OS. Please install rclone manually."
        exit 1
    fi
}

# Function to configure rclone for Google Drive
configure_gdrive() {
    echo "Configuring Google Drive with rclone..."
    echo ""
    echo "Follow these steps:"
    echo "1. Choose 'n' for new remote"
    echo "2. Name it 'gdrive'"
    echo "3. Choose 'drive' for Google Drive"
    echo "4. Leave client_id and client_secret blank for default"
    echo "5. Choose '1' for full access"
    echo "6. Follow OAuth instructions"
    echo ""
    read -p "Press Enter to continue..."

    rclone config
}

# Function to show common commands
show_commands() {
    cat << 'EOF'

===================================
Common Google Drive Commands
===================================

LISTING FILES:
  rclone ls gdrive:                    # List all files
  rclone lsd gdrive:                   # List directories only
  rclone tree gdrive:                  # Show as tree structure

UPLOADING:
  rclone copy file.txt gdrive:        # Upload single file
  rclone copy /folder gdrive:backup/  # Upload folder
  rclone sync /local gdrive:sync/     # Sync folder (careful: deletes extra files in destination)

DOWNLOADING:
  rclone copy gdrive:file.txt .       # Download single file
  rclone copy gdrive:folder/ /local/  # Download folder

MOUNTING AS FILESYSTEM:
  rclone mount gdrive: ~/GoogleDrive/ # Mount (run in background with &)
  fusermount -u ~/GoogleDrive/        # Unmount (Linux)
  umount ~/GoogleDrive/               # Unmount (macOS)

OTHER OPERATIONS:
  rclone delete gdrive:file.txt       # Delete file
  rclone mkdir gdrive:newfolder/      # Create folder
  rclone move file.txt gdrive:        # Move (upload and delete local)
  rclone size gdrive:                 # Show total size
  rclone check /local gdrive:backup/  # Compare local and remote

ADVANCED:
  rclone bisync /local gdrive:sync/   # Two-way sync (experimental)
  rclone serve webdav gdrive:         # Serve as WebDAV
  rclone ncdu gdrive:                 # Interactive disk usage

EOF
}

# Function to create useful aliases
create_aliases() {
    echo ""
    echo "Creating useful aliases..."

    ALIAS_FILE="$HOME/.gdrive_aliases"

    cat > "$ALIAS_FILE" << 'EOF'
# Google Drive aliases
alias gdls='rclone ls gdrive:'
alias gdlsd='rclone lsd gdrive:'
alias gdtree='rclone tree gdrive:'
alias gdsize='rclone size gdrive:'
alias gdmount='rclone mount gdrive: ~/GoogleDrive/ --daemon'
alias gdumount='fusermount -u ~/GoogleDrive/ 2>/dev/null || umount ~/GoogleDrive/'

# Functions for easier uploads/downloads
gdup() {
    # Upload file or folder to Google Drive
    if [ -z "$1" ]; then
        echo "Usage: gdup <file_or_folder> [destination]"
        return 1
    fi
    local dest="${2:-}"
    rclone copy "$1" "gdrive:$dest" --progress
}

gddown() {
    # Download file or folder from Google Drive
    if [ -z "$1" ]; then
        echo "Usage: gddown <remote_path> [local_destination]"
        return 1
    fi
    local dest="${2:-.}"
    rclone copy "gdrive:$1" "$dest" --progress
}

gdsync() {
    # Sync local folder with Google Drive
    if [ -z "$1" ] || [ -z "$2" ]; then
        echo "Usage: gdsync <local_folder> <remote_folder>"
        return 1
    fi
    rclone sync "$1" "gdrive:$2" --progress
}

gdbackup() {
    # Backup folder to Google Drive with date
    if [ -z "$1" ]; then
        echo "Usage: gdbackup <folder>"
        return 1
    fi
    local date=$(date +%Y%m%d_%H%M%S)
    local folder_name=$(basename "$1")
    rclone copy "$1" "gdrive:backups/${folder_name}_${date}/" --progress
}
EOF

    echo ""
    echo "Aliases created in: $ALIAS_FILE"
    echo ""
    echo "To use these aliases, add this line to your ~/.bashrc or ~/.zshrc:"
    echo "  source $ALIAS_FILE"
    echo ""
    echo "Available aliases:"
    echo "  gdls     - List files"
    echo "  gdlsd    - List directories"
    echo "  gdtree   - Show tree structure"
    echo "  gdsize   - Show total size"
    echo "  gdmount  - Mount Google Drive"
    echo "  gdumount - Unmount Google Drive"
    echo ""
    echo "Available functions:"
    echo "  gdup <file> [dest]     - Upload file/folder"
    echo "  gddown <path> [dest]   - Download file/folder"
    echo "  gdsync <local> <remote> - Sync folders"
    echo "  gdbackup <folder>      - Backup with timestamp"
}

# Main menu
main_menu() {
    while true; do
        echo ""
        echo "What would you like to do?"
        echo "1. Install rclone"
        echo "2. Configure Google Drive"
        echo "3. Show common commands"
        echo "4. Create useful aliases"
        echo "5. Test connection (list files)"
        echo "6. Quick upload test"
        echo "7. Mount Google Drive as filesystem"
        echo "8. Exit"
        echo ""
        read -p "Enter your choice (1-8): " choice

        case $choice in
            1)
                install_rclone
                ;;
            2)
                configure_gdrive
                ;;
            3)
                show_commands
                ;;
            4)
                create_aliases
                ;;
            5)
                echo "Testing connection..."
                rclone lsd gdrive: --max-depth 1
                ;;
            6)
                echo "Creating test file..."
                echo "Test upload from terminal at $(date)" > gdrive_test.txt
                rclone copy gdrive_test.txt gdrive: --progress
                echo "Checking if upload succeeded..."
                rclone ls gdrive: | grep gdrive_test.txt
                rm gdrive_test.txt
                ;;
            7)
                mkdir -p ~/GoogleDrive
                echo "Mounting Google Drive to ~/GoogleDrive..."
                echo "Press Ctrl+C to unmount"
                rclone mount gdrive: ~/GoogleDrive/ --vfs-cache-mode writes
                ;;
            8)
                echo "Goodbye!"
                exit 0
                ;;
            *)
                echo "Invalid choice. Please try again."
                ;;
        esac
    done
}

# Check if rclone is installed
if command_exists rclone; then
    echo "✓ rclone is already installed (version: $(rclone version | head -n1))"
else
    echo "✗ rclone is not installed"
    read -p "Would you like to install it now? (y/n): " install_choice
    if [[ $install_choice == "y" || $install_choice == "Y" ]]; then
        install_rclone
    fi
fi

# Start main menu
main_menu