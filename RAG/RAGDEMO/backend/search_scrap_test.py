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
async def google_search(query: str, num_results: int = 3, date_restrict: str = None):
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_KEY,
        "q": query,
        "num": num_results,
        
    }


    if date_restrict:
        params["dateRestrict"] = date_restrict

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
import re
from playwright.async_api import async_playwright, TimeoutError
from bs4 import BeautifulSoup

async def scrape_webpage_content(url: str) -> dict:
    """
    Fetches content from a URL, handling dynamic content with Playwright,
    and extracts meaningful text using Beautiful Soup.
    It includes a specific, targeted scraper for the Dar Al-Ifta prayer times page.
    """
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            dar_alifta_url = "https://www.dar-alifta.org/ar/prayer"
            if url == dar_alifta_url:
                print(f"DEBUG: Targeted scraping for Dar Al-Ifta prayer times at {url}")
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1000)
                html_content = await page.content()
                soup = BeautifulSoup(html_content, 'lxml')
                
                prayer_times = {}
                title = soup.title.string.strip() if soup.title else "مواقيت الصلاة - دار الإفتاء المصرية"
                
                # --- THIS IS THE CORRECTED SELECTOR ---
                prayer_table = soup.find('div', class_='tbl_prays')
                
                if prayer_table:
                    rows = prayer_table.find_all('tr')
                    for row in rows:
                        cols = row.find_all(['td', 'th'])
                        if len(cols) >= 2:
                            name = cols[0].get_text(strip=True).replace("صلاة ", "")
                            time = cols[1].get_text(strip=True)
                            prayer_times[name] = time
                    
                    if prayer_times:
                        content_text = "مواقيت الصلاة من دار الإفتاء المصرية:\n"
                        for name, time in prayer_times.items():
                            content_text += f"- {name}: {time}\n"
                        
                        return {
                            "success": True,
                            "url": url,
                            "title": title,
                            "content": content_text
                        }
                    else:
                        print(f"DEBUG: Found table but no data extracted from {url}.")
                        return {"success": False, "error": f"Found table but no data could be extracted from {url}."}
                else:
                    print(f"DEBUG: Specific prayer times table NOT found on {url}.")
                    return {"success": False, "error": f"Could not find the prayer times table on {url}. HTML structure might have changed."}
            
            # --- GENERAL SCRAPING LOGIC (Fallback) ---
            else:
                print(f"DEBUG: General scraping for URL: {url}")
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1000)
                html_content = await page.content()
                soup = BeautifulSoup(html_content, 'lxml')

                text_content_parts = []
                title = soup.title.string.strip() if soup.title and soup.title.string else "No Title Found"

                main_content_selectors = ['article', 'main', 'div.main-content', 'div[role="main"]', 'div.content']
                found_main_content = False
                for selector in main_content_selectors:
                    main_element = soup.select_one(selector)
                    if main_element:
                        paragraphs = main_element.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4']) 
                        if paragraphs:
                            text_content_parts.extend([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                            found_main_content = True
                            break
                
                if not found_main_content:
                    print(f"DEBUG: No specific main content found for {url}. Falling back to general extraction.")
                    for elem in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav', 'aside', '.sidebar', '#sidebar', '.ad', '.ads']):
                        elem.decompose()
                    all_text_elements = soup.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    text_content_parts.extend([
                        elem.get_text(strip=True)
                        for elem in all_text_elements
                        if elem.get_text(strip=True) and len(elem.get_text(strip=True)) > 20
                    ])

                text_content = "\n\n".join(text_content_parts)
                text_content = re.sub(r'[\n\s]+', ' ', text_content).strip()
                text_content = re.sub(r'[^\w\s.,?!:;\'"()\[\]`~-]', '', text_content)

                MAX_SCRAPED_CONTENT_LENGTH = 4000
                if len(text_content) > MAX_SCRAPED_CONTENT_LENGTH:
                    text_content = text_content[:MAX_SCRAPED_CONTENT_LENGTH] + "...\n[Content truncated due to length]"

                return {
                    "success": True,
                    "url": url,
                    "title": title,
                    "content": text_content
                }

    except TimeoutError:
        print(f"ERROR: Playwright timed out fetching {url}. Page took too long to load.")
        return {"success": False, "error": f"Page load timed out for {url}."}
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during Playwright scraping {url}: {e}")
        # --- Make sure this line is present and enabled ---
        import traceback
        traceback.print_exc()
        # --- End of important line ---
        return {"success": False, "error": f"An unexpected error occurred during scraping {url}: {e}"}
    finally:
        if browser:
            await browser.close()