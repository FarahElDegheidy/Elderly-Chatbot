import os
import httpx
import requests
import re
from bs4 import BeautifulSoup
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

GOOGLE_API_KEY= os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_KEY= os.getenv("GOOGLE_CSE_ID")
search_url= "https://www.googleapis.com/customsearch/v1"

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

def format_link(title, url):
    if "facebook.com" in url:
        label = "📘 Facebook Post"
    elif "instagram.com" in url:
        label = "📷 Instagram Post"
    elif "youtube.com" in url:
        label = "▶️ YouTube Video"
    elif "twitter.com" in url:
        label = "🌞 Twitter Post"
    else:
        label = title.strip()[:70] + "..." if title and len(title.strip()) > 70 else title or url[:50] + "..."
    return f"- [{label}]({url})"

#Defining Google Search Function
async def google_search(query: str, num_results: int = 3):
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_KEY,
        "q": query,
        "num": num_results,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(search_url, params=params)
        response.raise_for_status()
        data = response.json()

    results = []
    for item in data.get("items", []):
        results.append({
            "title": item.get("title", "بدون عنوان"),
            "snippet": item.get("snippet", ""),
            "link": item.get("link", "#"),
        })

    return results

#Defining YouTube Search Function
def search_youtube_videos(query: str, max_results: int = 3) -> list:
    """
    Search YouTube for videos related to a query.

    Returns a list of dictionaries containing video titles and URLs.

    """
    params = {
        "key": YOUTUBE_API_KEY,
        "q": query,
        "type": "video",
        "maxResults": max_results
    }

    response = requests.get(YOUTUBE_SEARCH_URL, params=params)
    data = response.json()

    results = []
    for item in data.get("items", []):
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        url = f"https://www.youtube.com/watch?v={video_id}"
        results.append({"title": title, "url": url})

    return results

#Defining Scraping webpage Function:
async def scrape_webpage_content(url: str) -> dict:
    """
    Fetches content from a URL, handling dynamic content with Playwright,
    and extracts meaningful text using Beautiful Soup.
    """
    browser = None
    try:
        async with async_playwright() as p:
            # Launch a headless Chromium browser
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Set a longer navigation timeout, some dynamic sites take time to load
            await page.goto(url, wait_until="domcontentloaded", timeout=30000) # 30 seconds

            # Wait for specific content or a short delay if unsure
            # For dynamic content, a short delay might be needed for elements to render
            # Or, you could wait for a specific selector if you knew what content to expect
            await page.wait_for_timeout(2000) # Wait for 2 seconds for JS to execute and render content

            # Get the fully rendered HTML content
            html_content = await page.content()

            soup = BeautifulSoup(html_content, 'html.parser')

            text_content_parts = []
            title = soup.title.string.strip() if soup.title and soup.title.string else "No Title Found"

            # Strategy 1: Look for main content sections
            main_content_selectors = [
                'article',
                'main',
                'div[role="main"]',
                'div.content',
                'div.main-content',
                'div.post-content',
                'div#bodyContent',
                'div.entry-content',
                'div[itemprop="articleBody"]',
                # Add more selectors that might contain the main information,
                # e.g., if you observe patterns on common news/info sites.
            ]

            found_main_content = False
            for selector in main_content_selectors:
                main_element = soup.select_one(selector)
                if main_element:
                    # Extract text from common block elements within the main content
                    paragraphs = main_element.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div']) # Added 'div' to catch more
                    if paragraphs:
                        text_content_parts.extend([p.get_text(separator=' ', strip=True) for p in paragraphs if p.get_text(strip=True)])
                        found_main_content = True
                        break

            # Strategy 2: If no specific main content found, try to extract from common text tags within the body
            if not found_main_content:
                print(f"DEBUG: No specific main content found for {url}. Falling back to general text extraction.")
                # Exclude common navigation, footer, header, script, style elements
                for script_or_style in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav', 'aside']):
                    script_or_style.decompose()

                # Get text from all remaining paragraph, list item, heading, and common text-holding div/span tags
                all_text_elements = soup.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'span'])
                text_content_parts.extend([
                    elem.get_text(separator=' ', strip=True)
                    for elem in all_text_elements
                    if elem.get_text(strip=True) and len(elem.get_text(strip=True)) > 10 # Increased minimum length slightly
                ])

            # Clean up and consolidate text
            text_content = "\n".join(text_content_parts)
            text_content = re.sub(r'\n\s*\n+', '\n\n', text_content) # Reduce multiple blank lines
            text_content = re.sub(r'\s{2,}', ' ', text_content)     # Reduce multiple spaces
            text_content = text_content.strip()

            # Limit the content length
            MAX_SCRAPED_CONTENT_LENGTH = 3000 # Keep this reasonable for LLM context
            if len(text_content) > MAX_SCRAPED_CONTENT_LENGTH:
                text_content = text_content[:MAX_SCRAPED_CONTENT_LENGTH] + "...\n[Content truncated due to length]"

            return {
                "success": True,
                "url": url,
                "title": title,
                "content": text_content
            }

    except PlaywrightTimeoutError:
        print(f"ERROR: Playwright timed out fetching {url}. Page took too long to load.")
        return {"success": False, "error": f"Page load timed out for {url}."}
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during Playwright scraping {url}: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        return {"success": False, "error": f"An unexpected error occurred during scraping {url}: {e}"}
    finally:
        if browser:
            await browser.close()
