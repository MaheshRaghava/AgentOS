"""
HTTP fetch tool — async GET request, returns page text content.
Used by browser agent as lightweight fallback when Playwright isn't available.
"""
import httpx


async def http_fetch(url: str, timeout: int = 10) -> str:
    """
    Fetch a URL and return the text content.
    Strips excessive whitespace. Returns empty string on failure.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        async with httpx.AsyncClient(
            timeout=timeout, 
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            # Basic HTML tag stripping — good enough for LLM input
            import re
            text = response.text
            
            # Remove script and style tags first
            text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
            
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()

            print(f"[HttpFetch] Fetched {url} — {len(text)} chars")
            return text[:10000]

    except httpx.TimeoutException:
        print(f"[HttpFetch] Timeout fetching {url}")
        return ""
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            print(f"[HttpFetch] 403 Forbidden for {url} — site blocked automated request")
        elif e.response.status_code == 404:
            print(f"[HttpFetch] 404 Not Found for {url}")
        else:
            print(f"[HttpFetch] HTTP {e.response.status_code} for {url}")
        return ""
    except Exception as e:
        print(f"[HttpFetch] Failed to fetch {url}: {e}")
        return ""