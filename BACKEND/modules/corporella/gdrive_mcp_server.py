#!/usr/bin/env python3
"""
Google Drive MCP Server
Provides conversational control over Google Drive using rclone
"""

import asyncio
import subprocess
import json
import os
import re
from typing import Any, Dict, List, Optional
from pathlib import Path
import logging
from datetime import datetime

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleDriveMCP:
    """MCP server for Google Drive operations via rclone"""

    def __init__(self):
        self.server = Server("google-drive-mcp")
        self.remote_name = "gdrive"  # Default rclone remote name
        self.active_transfers = {}
        self.setup_handlers()

    def setup_handlers(self):
        """Set up all MCP tool handlers"""

        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List all available Google Drive tools"""
            return [
                types.Tool(
                    name="gdrive_list",
                    description="List files and folders in Google Drive. Can specify path like 'folder/subfolder'",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path in Google Drive (optional, defaults to root)",
                                "default": ""
                            },
                            "folders_only": {
                                "type": "boolean",
                                "description": "Show only folders",
                                "default": False
                            }
                        }
                    }
                ),
                types.Tool(
                    name="gdrive_upload",
                    description="Upload files or folders to Google Drive",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "Local file or folder path to upload"
                            },
                            "destination": {
                                "type": "string",
                                "description": "Destination path in Google Drive (optional)",
                                "default": ""
                            },
                            "show_progress": {
                                "type": "boolean",
                                "description": "Show transfer progress",
                                "default": True
                            }
                        },
                        "required": ["source"]
                    }
                ),
                types.Tool(
                    name="gdrive_download",
                    description="Download files or folders from Google Drive",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "Path in Google Drive to download"
                            },
                            "destination": {
                                "type": "string",
                                "description": "Local destination path (optional, defaults to current directory)",
                                "default": "."
                            },
                            "show_progress": {
                                "type": "boolean",
                                "description": "Show transfer progress",
                                "default": True
                            }
                        },
                        "required": ["source"]
                    }
                ),
                types.Tool(
                    name="gdrive_sync",
                    description="Sync a local folder with Google Drive (one-way sync)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "local_path": {
                                "type": "string",
                                "description": "Local folder to sync"
                            },
                            "remote_path": {
                                "type": "string",
                                "description": "Google Drive folder to sync to"
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["to_drive", "from_drive"],
                                "description": "Sync direction: 'to_drive' uploads, 'from_drive' downloads",
                                "default": "to_drive"
                            }
                        },
                        "required": ["local_path", "remote_path"]
                    }
                ),
                types.Tool(
                    name="gdrive_delete",
                    description="Delete files or folders from Google Drive",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path in Google Drive to delete"
                            },
                            "confirm": {
                                "type": "boolean",
                                "description": "Confirm deletion (safety check)",
                                "default": False
                            }
                        },
                        "required": ["path"]
                    }
                ),
                types.Tool(
                    name="gdrive_mount",
                    description="Mount Google Drive as a local filesystem",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "mount_point": {
                                "type": "string",
                                "description": "Local directory to mount Google Drive to",
                                "default": "~/GoogleDrive"
                            }
                        }
                    }
                ),
                types.Tool(
                    name="gdrive_unmount",
                    description="Unmount Google Drive filesystem",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "mount_point": {
                                "type": "string",
                                "description": "Mount point to unmount",
                                "default": "~/GoogleDrive"
                            }
                        }
                    }
                ),
                types.Tool(
                    name="gdrive_search",
                    description="Search for files in Google Drive",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (file name or pattern)"
                            },
                            "path": {
                                "type": "string",
                                "description": "Path to search in (optional)",
                                "default": ""
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="gdrive_info",
                    description="Get information about Google Drive usage and quota",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="gdrive_check_status",
                    description="Check if rclone is configured and Google Drive is accessible",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Optional[Dict[str, Any]]
        ) -> list[types.TextContent]:
            """Handle tool calls"""

            try:
                if name == "gdrive_list":
                    result = await self.list_files(
                        arguments.get("path", ""),
                        arguments.get("folders_only", False)
                    )
                elif name == "gdrive_upload":
                    result = await self.upload(
                        arguments["source"],
                        arguments.get("destination", ""),
                        arguments.get("show_progress", True)
                    )
                elif name == "gdrive_download":
                    result = await self.download(
                        arguments["source"],
                        arguments.get("destination", "."),
                        arguments.get("show_progress", True)
                    )
                elif name == "gdrive_sync":
                    result = await self.sync(
                        arguments["local_path"],
                        arguments["remote_path"],
                        arguments.get("direction", "to_drive")
                    )
                elif name == "gdrive_delete":
                    result = await self.delete(
                        arguments["path"],
                        arguments.get("confirm", False)
                    )
                elif name == "gdrive_mount":
                    result = await self.mount(
                        arguments.get("mount_point", "~/GoogleDrive")
                    )
                elif name == "gdrive_unmount":
                    result = await self.unmount(
                        arguments.get("mount_point", "~/GoogleDrive")
                    )
                elif name == "gdrive_search":
                    result = await self.search(
                        arguments["query"],
                        arguments.get("path", "")
                    )
                elif name == "gdrive_info":
                    result = await self.get_info()
                elif name == "gdrive_check_status":
                    result = await self.check_status()
                else:
                    result = f"Unknown tool: {name}"

                return [types.TextContent(type="text", text=str(result))]

            except Exception as e:
                error_msg = f"Error executing {name}: {str(e)}"
                logger.error(error_msg)
                return [types.TextContent(type="text", text=error_msg)]

    async def run_rclone_command(self, cmd: List[str], capture_output: bool = True) -> Dict[str, Any]:
        """Run an rclone command and return the result"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None
            )

            stdout, stderr = await process.communicate()

            return {
                "success": process.returncode == 0,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
                "returncode": process.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1
            }

    async def list_files(self, path: str = "", folders_only: bool = False) -> str:
        """List files and folders in Google Drive"""
        cmd = ["rclone", "lsd" if folders_only else "ls", f"{self.remote_name}:{path}"]
        result = await self.run_rclone_command(cmd)

        if result["success"]:
            output = result["stdout"]
            if folders_only:
                # Parse folder listing
                lines = output.strip().split('\n')
                folders = []
                for line in lines:
                    if line.strip():
                        # Extract folder name from rclone output
                        parts = line.split()
                        if len(parts) >= 5:
                            folder_name = ' '.join(parts[4:])
                            folders.append(folder_name)
                return f"📁 Folders in '{path or '/'}':\n" + '\n'.join(f"  • {f}" for f in folders)
            else:
                return f"📄 Files in '{path or '/'}':\n{output}"
        else:
            return f"❌ Failed to list files: {result['stderr']}"

    async def upload(self, source: str, destination: str = "", show_progress: bool = True) -> str:
        """Upload files or folders to Google Drive"""
        # Expand user home directory
        source = os.path.expanduser(source)

        if not os.path.exists(source):
            return f"❌ Source path does not exist: {source}"

        # Determine destination
        if not destination:
            destination = os.path.basename(source)

        cmd = ["rclone", "copy", source, f"{self.remote_name}:{destination}"]
        if show_progress:
            cmd.append("--progress")

        result = await self.run_rclone_command(cmd)

        if result["success"]:
            size = self.get_path_size(source)
            return f"✅ Successfully uploaded '{source}' to Google Drive:{destination}\n📊 Size: {size}"
        else:
            return f"❌ Upload failed: {result['stderr']}"

    async def download(self, source: str, destination: str = ".", show_progress: bool = True) -> str:
        """Download files or folders from Google Drive"""
        destination = os.path.expanduser(destination)

        cmd = ["rclone", "copy", f"{self.remote_name}:{source}", destination]
        if show_progress:
            cmd.append("--progress")

        result = await self.run_rclone_command(cmd)

        if result["success"]:
            return f"✅ Successfully downloaded '{source}' from Google Drive to {destination}"
        else:
            return f"❌ Download failed: {result['stderr']}"

    async def sync(self, local_path: str, remote_path: str, direction: str = "to_drive") -> str:
        """Sync folders between local and Google Drive"""
        local_path = os.path.expanduser(local_path)

        if direction == "to_drive":
            cmd = ["rclone", "sync", local_path, f"{self.remote_name}:{remote_path}", "--progress"]
            action = "uploaded to"
        else:
            cmd = ["rclone", "sync", f"{self.remote_name}:{remote_path}", local_path, "--progress"]
            action = "downloaded from"

        result = await self.run_rclone_command(cmd)

        if result["success"]:
            return f"✅ Successfully synced '{local_path}' {action} Google Drive:{remote_path}"
        else:
            return f"❌ Sync failed: {result['stderr']}"

    async def delete(self, path: str, confirm: bool = False) -> str:
        """Delete files or folders from Google Drive"""
        if not confirm:
            return "⚠️ Deletion not confirmed. Set confirm=true to delete."

        cmd = ["rclone", "delete", f"{self.remote_name}:{path}"]
        result = await self.run_rclone_command(cmd)

        if result["success"]:
            return f"✅ Successfully deleted '{path}' from Google Drive"
        else:
            return f"❌ Deletion failed: {result['stderr']}"

    async def mount(self, mount_point: str = "~/GoogleDrive") -> str:
        """Mount Google Drive as a filesystem"""
        mount_point = os.path.expanduser(mount_point)

        # Create mount point if it doesn't exist
        os.makedirs(mount_point, exist_ok=True)

        cmd = ["rclone", "mount", f"{self.remote_name}:", mount_point, "--daemon"]
        result = await self.run_rclone_command(cmd)

        if result["success"]:
            return f"✅ Google Drive mounted at {mount_point}\n💡 Access your files at: {mount_point}"
        else:
            return f"❌ Mount failed: {result['stderr']}"

    async def unmount(self, mount_point: str = "~/GoogleDrive") -> str:
        """Unmount Google Drive filesystem"""
        mount_point = os.path.expanduser(mount_point)

        # Try fusermount first (Linux), then umount (macOS)
        cmd = ["fusermount", "-u", mount_point]
        result = await self.run_rclone_command(cmd)

        if not result["success"]:
            cmd = ["umount", mount_point]
            result = await self.run_rclone_command(cmd)

        if result["success"]:
            return f"✅ Google Drive unmounted from {mount_point}"
        else:
            return f"❌ Unmount failed: {result['stderr']}"

    async def search(self, query: str, path: str = "") -> str:
        """Search for files in Google Drive"""
        cmd = ["rclone", "ls", f"{self.remote_name}:{path}"]
        result = await self.run_rclone_command(cmd)

        if result["success"]:
            lines = result["stdout"].strip().split('\n')
            matches = []
            for line in lines:
                if query.lower() in line.lower():
                    matches.append(line.strip())

            if matches:
                return f"🔍 Found {len(matches)} matches for '{query}':\n" + '\n'.join(matches[:20])
            else:
                return f"No files found matching '{query}'"
        else:
            return f"❌ Search failed: {result['stderr']}"

    async def get_info(self) -> str:
        """Get Google Drive usage information"""
        cmd = ["rclone", "about", f"{self.remote_name}:"]
        result = await self.run_rclone_command(cmd)

        if result["success"]:
            output = result["stdout"]
            # Parse the output to make it more readable
            lines = output.strip().split('\n')
            info = []
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    info.append(f"  {key.strip()}: {value.strip()}")

            return "📊 Google Drive Information:\n" + '\n'.join(info)
        else:
            return f"❌ Failed to get info: {result['stderr']}"

    async def check_status(self) -> str:
        """Check if rclone and Google Drive are properly configured"""
        # Check if rclone is installed
        cmd = ["which", "rclone"]
        result = await self.run_rclone_command(cmd)

        if not result["success"]:
            return "❌ rclone is not installed. Install it with: brew install rclone"

        # Check if Google Drive remote is configured
        cmd = ["rclone", "listremotes"]
        result = await self.run_rclone_command(cmd)

        if result["success"]:
            remotes = result["stdout"].strip()
            if f"{self.remote_name}:" in remotes:
                # Try to list root to verify authentication
                cmd = ["rclone", "lsd", f"{self.remote_name}:", "--max-depth", "1"]
                test_result = await self.run_rclone_command(cmd)

                if test_result["success"]:
                    return f"✅ Google Drive is configured and accessible!\n🔗 Remote name: {self.remote_name}"
                else:
                    return f"⚠️ Google Drive remote exists but authentication may be needed:\n{test_result['stderr']}"
            else:
                return f"❌ Google Drive remote '{self.remote_name}' not found. Available remotes:\n{remotes}"
        else:
            return f"❌ Failed to check remotes: {result['stderr']}"

    def get_path_size(self, path: str) -> str:
        """Get human-readable size of a path"""
        try:
            if os.path.isfile(path):
                size = os.path.getsize(path)
            else:
                size = sum(
                    os.path.getsize(os.path.join(dirpath, filename))
                    for dirpath, dirnames, filenames in os.walk(path)
                    for filename in filenames
                )

            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size < 1024.0:
                    return f"{size:.2f} {unit}"
                size /= 1024.0
            return f"{size:.2f} PB"
        except Exception as e:
            return "Unknown size"

    async def run(self):
        """Run the MCP server"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="google-drive-mcp",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

async def main():
    """Main entry point"""
    server = GoogleDriveMCP()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())