# DeHashed Web Visualization

An interactive graph visualization for exploring DeHashed breach data. Features an old-school terminal aesthetic with green-on-black styling.

## Features

- **Interactive Graph**: Click nodes to see details, double-click to expand and find connections
- **Search Functionality**: Search by email, username, password, IP address, phone, domain, etc.
- **Auto-detection**: Automatically detects the type of search query
- **Visual Connections**: See relationships between breaches, emails, usernames, and other data
- **Old-School Terminal Look**: Classic hacker aesthetic with monospace fonts and green text

## Requirements

- Python 3.x
- Flask (`pip install flask flask-cors`)
- Internet connection for DeHashed API access

## Usage

1. Start the server:

   ```bash
   cd /Users/brain/Downloads/EYE-D/web
   python server.py
   ```

2. Open your browser and navigate to:

   ```
   http://localhost:5000
   ```

3. Enter a search query (email, username, etc.) and click Search

4. Interact with the graph:
   - **Single Click**: View node details in the info panel
   - **Double Click**: Expand node to find related data
   - **Drag**: Move nodes around (physics enabled)

## Graph Node Types

- **Yellow**: Search queries
- **Green**: Email addresses
- **Cyan**: Usernames
- **Magenta**: Passwords/Hashes
- **Orange**: IP addresses
- **Blue**: Phone numbers
- **Red**: Breach/Database records

## API Key

The server uses the DeHashed API key configured in `server.py`. Make sure it's valid and has sufficient balance.

## Security Note

This tool is for security research and defensive purposes only. Handle breach data responsibly.
