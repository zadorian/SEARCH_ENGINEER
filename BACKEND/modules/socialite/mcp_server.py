"""SOCIALITE MCP Server - Social Media Search and Analysis."""
import asyncio
import json
import logging
from typing import Optional, List, Dict, Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from modules.socialite.platforms import twitter, instagram, facebook, threads
from modules.socialite.engines.socialsearcher import SocialSearcher
from modules.socialite.analysis import network_mapper, influence_analyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = Server("socialite")

@mcp.list_tools()
async def list_tools() -> List[Tool]:
    """List available social media tools."""
    return [
        Tool(
            name="search_twitter",
            description="Search Twitter/X. Returns direct search URLs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "username": {"type": "string", "description": "Search tweets from user"},
                    "since": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "until": {"type": "string", "description": "End date (YYYY-MM-DD)"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_instagram",
            description="Get Instagram profile URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Instagram username"}
                },
                "required": ["username"]
            }
        ),
        Tool(
            name="search_facebook",
            description="Search Facebook or get profile URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "username": {"type": "string", "description": "Specific username"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_reddit",
            description="Search Reddit using SocialSearcher API.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "subreddit": {"type": "string", "description": "Specific subreddit"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_multi_platform",
            description="Search across multiple social media platforms.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "platforms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Platforms (twitter, instagram, facebook, reddit, youtube)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_person",
            description="Search for a person across all supported platforms.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Person's name or handle"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="map_social_network",
            description="Map social network for a username across platforms.",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username to investigate"},
                    "depth": {"type": "integer", "default": 1, "description": "Connection depth"}
                },
                "required": ["username"]
            }
        ),
        Tool(
            name="analyze_influence",
            description="Analyze influence metrics for a user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username to analyze"},
                    "platform": {"type": "string", "default": "twitter", "description": "Platform"}
                },
                "required": ["username"]
            }
        )
    ]

@mcp.call_tool()
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    """Execute social media tools."""
    try:
        if name == "search_twitter":
            if arguments.get("username"):
                if arguments.get("since") and arguments.get("until"):
                    url = twitter.twitter_from_user_date_range(
                        arguments["username"],
                        arguments["since"],
                        arguments["until"],
                        arguments.get("query", "")
                    )
                else:
                    url = twitter.twitter_from_user(arguments["username"], arguments.get("query", ""))
            elif arguments.get("since") and arguments.get("until"):
                search_query = f"{arguments['query']} since:{arguments['since']} until:{arguments['until']}"
                url = f"https://x.com/search?q={twitter._twitter_quote(search_query)}&f=live"
            else:
                url = twitter.twitter_search(arguments["query"])
            return [TextContent(type="text", text=url)]

        elif name == "search_instagram":
            url = instagram.instagram_profile(arguments["username"])
            return [TextContent(type="text", text=url)]

        elif name == "search_facebook":
            if arguments.get("username"):
                url = facebook.facebook_profile(arguments["username"])
            else:
                url = facebook.facebook_search(arguments["query"])
            return [TextContent(type="text", text=url)]

        elif name == "search_reddit":
            searcher = SocialSearcher()
            results = searcher.search(arguments["query"], content_type="reddit")
            return [TextContent(type="text", text=json.dumps({
                "query": arguments["query"],
                "platform": "reddit",
                "result_count": len(results),
                "results": results
            }, indent=2))]

        elif name == "search_multi_platform":
            platforms = arguments.get("platforms", ["twitter", "instagram", "facebook"])
            query = arguments["query"]

            results = {
                "query": query,
                "platforms_searched": platforms,
                "results": {}
            }

            if "twitter" in platforms:
                results["results"]["twitter"] = twitter.twitter_search(query)
            if "instagram" in platforms:
                results["results"]["instagram"] = instagram.instagram_search(query)
            if "facebook" in platforms:
                results["results"]["facebook"] = facebook.facebook_search(query)

            if "reddit" in platforms or "youtube" in platforms:
                searcher = SocialSearcher()
                for platform in ["reddit", "youtube"]:
                    if platform in platforms:
                        api_results = searcher.search(query, content_type=platform)
                        results["results"][platform] = {
                            "result_count": len(api_results),
                            "posts": api_results
                        }

            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "search_person":
            # Reuse logic from search_multi_platform
            return await call_tool("search_multi_platform", {"query": arguments["name"]})

        elif name == "map_social_network":
            result = await network_mapper.map_social_network(
                arguments["username"],
                arguments.get("depth", 1)
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "analyze_influence":
            result = await influence_analyzer.analyze_influence(
                arguments["username"],
                arguments.get("platform", "twitter")
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]

async def main():
    """
    Run MCP server.
    """
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
