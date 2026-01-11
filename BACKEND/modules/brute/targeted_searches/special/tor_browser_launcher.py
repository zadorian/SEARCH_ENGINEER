#!/usr/bin/env python3
"""
Tor Browser Launcher
--------------------
Launches Chrome with Tor SOCKS5 proxy configuration
Supports macOS, Linux, and Windows
"""

import os
import sys
import platform
import subprocess
import socket
import time
from pathlib import Path
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)

# Tor default ports
TOR_SOCKS_PORTS = [9050, 9150]  # 9050 for Tor service, 9150 for Tor Browser Bundle

# Chrome executable paths by platform
CHROME_PATHS = {
    "Darwin": [  # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chrome.app/Contents/MacOS/Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ],
    "Linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        "/usr/local/bin/chrome",
    ],
    "Windows": [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Users\\%USERNAME%\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe",
    ]
}

def check_tor_running(port: int = 9050) -> bool:
    """Check if Tor is running on the specified port"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"Error checking Tor on port {port}: {e}")
        return False

def find_tor_port() -> Optional[int]:
    """Find which port Tor is running on"""
    for port in TOR_SOCKS_PORTS:
        if check_tor_running(port):
            logger.info(f"Found Tor running on port {port}")
            return port
    return None

def find_chrome_executable() -> Optional[str]:
    """Find Chrome executable path for current platform"""
    system = platform.system()
    paths = CHROME_PATHS.get(system, [])
    
    for path in paths:
        # Expand user home directory
        path = os.path.expanduser(path)
        # Expand environment variables (Windows)
        path = os.path.expandvars(path)
        
        if os.path.exists(path):
            logger.info(f"Found Chrome at: {path}")
            return path
    
    # Try 'which' command on Unix-like systems
    if system in ["Darwin", "Linux"]:
        try:
            result = subprocess.run(
                ["which", "google-chrome", "chromium", "chrome"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                chrome_path = result.stdout.strip().split('\n')[0]
                if chrome_path and os.path.exists(chrome_path):
                    logger.info(f"Found Chrome via which: {chrome_path}")
                    return chrome_path
        except Exception:
            pass
    
    # Try 'where' command on Windows
    if system == "Windows":
        try:
            result = subprocess.run(
                ["where", "chrome.exe"],
                capture_output=True,
                text=True,
                shell=True
            )
            if result.returncode == 0:
                chrome_path = result.stdout.strip().split('\n')[0]
                if chrome_path and os.path.exists(chrome_path):
                    logger.info(f"Found Chrome via where: {chrome_path}")
                    return chrome_path
        except Exception:
            pass
    
    return None

def launch_tor_browser(
    tor_port: Optional[int] = None,
    profile_dir: Optional[str] = None,
    check_url: str = "https://check.torproject.org"
) -> Dict[str, any]:
    """
    Launch Chrome with Tor proxy configuration
    
    Args:
        tor_port: Tor SOCKS port (auto-detect if None)
        profile_dir: Chrome profile directory (creates temp if None)
        check_url: URL to open (Tor check page by default)
    
    Returns:
        Dict with status, message, and process info
    """
    result = {
        "success": False,
        "message": "",
        "tor_port": None,
        "chrome_path": None,
        "process": None
    }
    
    # Check if Tor is running
    if tor_port is None:
        tor_port = find_tor_port()
    
    if tor_port is None:
        result["message"] = "Tor is not running. Please start Tor first."
        logger.error(result["message"])
        return result
    
    result["tor_port"] = tor_port
    
    # Find Chrome executable
    chrome_path = find_chrome_executable()
    if chrome_path is None:
        result["message"] = "Chrome/Chromium not found. Please install Chrome."
        logger.error(result["message"])
        return result
    
    result["chrome_path"] = chrome_path
    
    # Create profile directory if not specified
    if profile_dir is None:
        profile_dir = os.path.join(
            Path.home(), 
            ".chrome-tor-profile"
        )
    
    # Ensure profile directory exists
    os.makedirs(profile_dir, exist_ok=True)
    
    # Build Chrome command with Tor proxy
    chrome_args = [
        chrome_path,
        f"--proxy-server=socks5://127.0.0.1:{tor_port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-domain-reliability",
        "--disable-features=AutofillServerCommunication",
        "--disable-sync",
        "--disable-web-resources",
        "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
        "--incognito",
        check_url
    ]
    
    try:
        # Launch Chrome
        if platform.system() == "Darwin":
            # macOS: Use 'open' command for better integration
            process = subprocess.Popen(
                ["open", "-a", chrome_path, "--args"] + chrome_args[1:],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:
            # Linux/Windows: Direct execution
            process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        
        # Give Chrome a moment to start
        time.sleep(1)
        
        # Check if process is still running
        if process.poll() is None:
            result["success"] = True
            result["message"] = f"Chrome launched with Tor proxy on port {tor_port}"
            result["process"] = process
            logger.info(result["message"])
        else:
            stderr = process.stderr.read().decode('utf-8', errors='ignore')
            result["message"] = f"Chrome failed to start: {stderr[:200]}"
            logger.error(result["message"])
            
    except Exception as e:
        result["message"] = f"Error launching Chrome: {str(e)}"
        logger.error(result["message"])
    
    return result

def get_tor_instructions() -> str:
    """Get platform-specific Tor installation instructions"""
    system = platform.system()
    
    if system == "Darwin":
        return """
To install Tor on macOS:
1. Using Homebrew: brew install tor
2. Or download Tor Browser from: https://www.torproject.org/download/
3. Start Tor: brew services start tor (or open Tor Browser)
"""
    elif system == "Linux":
        return """
To install Tor on Linux:
1. Ubuntu/Debian: sudo apt-get install tor
2. Fedora/RHEL: sudo yum install tor
3. Arch: sudo pacman -S tor
4. Start Tor: sudo systemctl start tor
Or download Tor Browser from: https://www.torproject.org/download/
"""
    else:  # Windows
        return """
To install Tor on Windows:
1. Download Tor Browser from: https://www.torproject.org/download/
2. Install and run Tor Browser
3. Or use Tor Expert Bundle for standalone service
"""

def main():
    """CLI interface for testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Launch Chrome with Tor proxy")
    parser.add_argument("--port", type=int, help="Tor SOCKS port (auto-detect if not specified)")
    parser.add_argument("--profile", help="Chrome profile directory")
    parser.add_argument("--url", default="https://check.torproject.org", help="URL to open")
    parser.add_argument("--check-only", action="store_true", help="Only check if Tor is running")
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.check_only:
        tor_port = find_tor_port()
        if tor_port:
            print(f"✓ Tor is running on port {tor_port}")
            sys.exit(0)
        else:
            print("✗ Tor is not running")
            print(get_tor_instructions())
            sys.exit(1)
    
    # Launch browser
    result = launch_tor_browser(
        tor_port=args.port,
        profile_dir=args.profile,
        check_url=args.url
    )
    
    if result["success"]:
        print(f"✓ {result['message']}")
        print(f"  Chrome: {result['chrome_path']}")
        print(f"  Tor port: {result['tor_port']}")
        print(f"  Opening: {args.url}")
    else:
        print(f"✗ {result['message']}")
        if "Tor is not running" in result["message"]:
            print(get_tor_instructions())
        sys.exit(1)

if __name__ == "__main__":
    main()