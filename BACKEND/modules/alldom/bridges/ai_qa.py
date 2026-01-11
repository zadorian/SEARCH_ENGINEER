"""
ALLDOM Bridge: AI Question Answering

Ask AI questions about domain content or search for exact phrases.
Operators: "exact phrase"?:?domain, question?:?domain, "exact phrase"?:url?, question?:url?
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def ask_question(
    question: str,
    target: str,
    target_type: str = "domain",
    is_exact_phrase: bool = False,
    max_pages: int = 20,
    **kwargs
) -> Dict[str, Any]:
    """
    Ask AI question about domain/URL content or search for exact phrase.
    
    Args:
        question: Question to ask or phrase to search (if quoted)
        target: Domain or URL to query
        target_type: 'domain' or 'url'
        is_exact_phrase: True if question is quoted (exact search), False for AI Q&A
        max_pages: Max pages to analyze (domain mode only)
        **kwargs: Additional parameters (model, temperature, etc.)
    
    Returns:
        Dict with answer, sources, snippets
    """
    try:
        from modules.JESTER import Jester
        from modules.JESTER.MAPPER.mapper import JesterMapper
        from modules.brain import Brain
        
        # If exact phrase mode, use keyword search
        if is_exact_phrase:
            from modules.ALLDOM.bridges.keyword import search_keyword
            matches = await search_keyword(question, target, target_type, max_pages)
            return {
                "mode": "exact_phrase",
                "phrase": question,
                "matches": matches,
                "total_matches": sum(m.get("match_count", 0) for m in matches)
            }
        
        # AI Q&A mode
        # Step 1: Discover and scrape content
        urls = []
        if target_type == "url":
            urls = [target]
        else:
            mapper = JesterMapper()
            async for discovered in mapper.discover_stream(target, mode="fast"):
                urls.append(discovered.url)
                if len(urls) >= max_pages:
                    break
            
            if not urls:
                urls = [f"https://{target}"]
        
        # Step 2: Scrape pages
        jester = Jester()
        scraped_content = []
        
        for url in urls[:max_pages]:
            result = await jester.scrape(url)
            if result and result.content:
                scraped_content.append({
                    "url": url,
                    "title": getattr(result, "title", None) or url,
                    "content": result.content[:10000]  # Limit content length
                })
        
        await jester.close()
        
        if not scraped_content:
            return {
                "mode": "ai_qa",
                "question": question,
                "answer": "No content could be scraped from target.",
                "sources": []
            }
        
        # Step 3: Construct prompt for AI
        context_parts = []
        for item in scraped_content[:10]:  # Limit to 10 pages for token constraints
            context_parts.append(f"URL: {item['url']}\nTitle: {item['title']}\nContent: {item['content']}\n")
        
        context = "\n---\n".join(context_parts)
        
        prompt = f"""Based on the following content from {target}:

{context}

Question: {question}

Provide a clear, concise answer based ONLY on the information in the content above. Include specific URL references where relevant."""
        
        # Step 4: Call AI
        brain = Brain()
        model = kwargs.get("model", "gpt-5-nano")
        
        response = await brain.generate(
            prompt=prompt,
            model=model,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 1000)
        )
        
        return {
            "mode": "ai_qa",
            "question": question,
            "answer": response.get("text", ""),
            "sources": [item["url"] for item in scraped_content],
            "pages_analyzed": len(scraped_content),
            "model": model,
            "metadata": {
                "target": target,
                "target_type": target_type
            }
        }
        
    except ImportError as e:
        logger.warning(f"AI Q&A dependencies not available: {e}")
        return {
            "error": f"Dependencies missing: {e}",
            "question": question
        }
    except Exception as e:
        logger.error(f"AI Q&A error: {e}")
        return {
            "error": str(e),
            "question": question
        }


async def ask_domain(question: str, domain: str, is_exact_phrase: bool = False, **kwargs) -> Dict[str, Any]:
    """Ask question about domain content."""
    return await ask_question(question, domain, "domain", is_exact_phrase, **kwargs)


async def ask_url(question: str, url: str, is_exact_phrase: bool = False, **kwargs) -> Dict[str, Any]:
    """Ask question about specific URL."""
    return await ask_question(question, url, "url", is_exact_phrase, **kwargs)
