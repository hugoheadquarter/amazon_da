import asyncio
from playwright.async_api import async_playwright, TimeoutError
import random
import time
from urllib.parse import urljoin
from fake_useragent import UserAgent
import os
import aiosqlite
from datetime import date

# Database path
DB_PATH = '/Users/dylankim/Desktop/resume/amazon/db/amazon_products.db'

# Initialize UserAgent
ua = UserAgent(platforms='pc')

def get_random_user_agent():
    return ua.random

async def delay_request(attempt=1):
    await asyncio.sleep(random.uniform(2, 5) * (2 ** attempt))

def construct_url(search_term, page=1):
    base_url = "https://www.amazon.com/s"
    params = {
        "k": search_term,
        "page": str(page),
        "page-size": "60"  # Request 60 items per page
    }
    return f"{base_url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

async def extract_product_info(product):
    try:
        title = await product.query_selector('span.a-text-normal')
        title_text = await title.inner_text() if title else 'N/A'

        url_element = await product.query_selector('a.a-link-normal.s-no-outline')
        url = await url_element.get_attribute('href') if url_element else 'N/A'
        url = urljoin('https://www.amazon.com', url)

        price_element = await product.query_selector('span.a-offscreen')
        price = await price_element.inner_text() if price_element else 'N/A'

        rating_element = await product.query_selector('span.a-icon-alt')
        rating = (await rating_element.inner_text()).split()[0] if rating_element else 'N/A'

        reviews_element = await product.query_selector('span.a-size-base.s-underline-text')
        reviews = await reviews_element.inner_text() if reviews_element else '0'

        if price in ['N/A', '$0.00', '$0', '0', '0.00', '0.0', 'None', 'none', 'Click to see price']:
            #print(f"Skipping product due to invalid price: {title_text}")
            return None
        
        if reviews in ['N/A', '$0.00', '$0', '0', '0.00', '0.0', 'None', 'none', 'Click to see price']:
            #print(f"Skipping product due to invalid price: {title_text}")
            return None
        
        if rating in ['N/A', '$0.00', '$0', '0', '0.00', '0.0', 'None', 'none', 'Click to see price']:
            #print(f"Skipping product due to invalid price: {title_text}")
            return None

        return {
            'title': title_text,
            'url': url,
            'price': price.replace('$', ''),
            'rating': rating,
            'reviews': reviews.replace(',', '')
        }
    except Exception as e:
        print(f"Error extracting product info: {e}")
        return None

async def scrape_amazon_search(search_term, category_id, conn, max_retries=5):
    page_num = 1

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-infobars',
            '--window-position=0,0',
            '--ignore-certifcate-errors',
            '--ignore-certifcate-errors-spki-list',
            '--user-agent=' + get_random_user_agent()
        ])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=get_random_user_agent(),
            java_script_enabled=True,
            ignore_https_errors=True,
            extra_http_headers={'Accept-Language': 'en-US,en;q=0.9'}
        )
        page = await context.new_page()
        
        try:
            while True:
                url = construct_url(search_term, page_num)
                for attempt in range(max_retries):
                    try:
                        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                        await page.wait_for_selector('div[data-component-type="s-search-result"]', timeout=30000)
                        
                        await asyncio.sleep(random.choice([3, 4, 5]))
                        products = await page.query_selector_all('div[data-component-type="s-search-result"]')
                        
                        for product in products:
                            product_info = await extract_product_info(product)
                            if product_info:
                                await insert_product_info(conn, product_info, category_id, search_term)
                            await asyncio.sleep(0.1)
                        
                        print(f"Scraped page {page_num}, found {len(products)} products")
                        
                        next_button = await page.query_selector('a.s-pagination-next:not(.s-pagination-disabled)')
                        if not next_button:
                            print("No more pages to scrape")
                            return
                        
                        page_num += 1
                        await delay_request()
                        break
                    
                    except TimeoutError as e:
                        print(f"Timeout error on page {page_num}, attempt {attempt + 1}: {e}")
                        if attempt == max_retries - 1:
                            print(f"Max retries reached for page {page_num}. Stopping scraping.")
                            return
                        await delay_request(attempt)
                    
                    except Exception as e:
                        print(f"An error occurred while scraping page {page_num}: {e}")
                        return

        finally:
            await browser.close()

async def initialize_database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS search_terms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                term TEXT UNIQUE NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                price DECIMAL(10, 2),
                rating DECIMAL(2, 1),
                review_count INTEGER,
                date_scraped DATE DEFAULT CURRENT_DATE
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS product_categories (
                product_id INTEGER,
                category_id INTEGER,
                PRIMARY KEY (product_id, category_id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS product_search_terms (
                product_id INTEGER,
                search_term_id INTEGER,
                PRIMARY KEY (product_id, search_term_id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (search_term_id) REFERENCES search_terms(id)
            )
        ''')
        await db.commit()

async def insert_product_info(conn, product_info, category_id, search_term):
    async with conn.cursor() as cursor:
        # Insert or update product
        await cursor.execute('''
            INSERT OR REPLACE INTO products (title, url, price, rating, review_count, date_scraped)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (product_info['title'], product_info['url'], product_info['price'], 
              product_info['rating'], product_info['reviews'], date.today()))
        
        product_id = cursor.lastrowid

        # Insert category relation
        await cursor.execute('''
            INSERT OR IGNORE INTO product_categories (product_id, category_id)
            VALUES (?, ?)
        ''', (product_id, category_id))

        # Insert or get search term
        await cursor.execute('INSERT OR IGNORE INTO search_terms (term) VALUES (?)', (search_term,))
        await cursor.execute('SELECT id FROM search_terms WHERE term = ?', (search_term,))
        search_term_id = (await cursor.fetchone())[0]

        # Insert search term relation
        await cursor.execute('''
            INSERT OR IGNORE INTO product_search_terms (product_id, search_term_id)
            VALUES (?, ?)
        ''', (product_id, search_term_id))

        await conn.commit()

async def get_or_create_category(conn, category_name):
    async with conn.cursor() as cursor:
        await cursor.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (category_name,))
        await cursor.execute('SELECT id FROM categories WHERE name = ?', (category_name,))
        category_id = await cursor.fetchone()
        await conn.commit()
        return category_id[0] if category_id else None

async def scrape_with_retry(search_term, category_id, conn, max_retries=5):
    for attempt in range(max_retries):
        await scrape_amazon_search(search_term, category_id, conn)
        async with conn.execute('''
            SELECT COUNT(*) FROM products p
            JOIN product_search_terms pst ON p.id = pst.product_id
            JOIN search_terms st ON pst.search_term_id = st.id
            WHERE st.term = ?
        ''', (search_term,)) as cursor:
            count = await cursor.fetchone()
            if count and count[0] > 20:  # If we have more than one page worth of products
                return
        print(f"Only scraped one page. Retrying... (Attempt {attempt + 1} of {max_retries})")
        await asyncio.sleep(random.uniform(10, 20))  # Wait before retrying
    
    print(f"Failed to scrape more than one page after {max_retries} attempts.")

async def main():
    await initialize_database()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        category_name = input("Enter the category name: ")
        category_id = await get_or_create_category(conn, category_name)
        
        if category_id is None:
            print("Failed to create or retrieve category. Exiting.")
            return

        search_terms = []
        while True:
            term = input("Enter a product name (or 'q' to start scraping): ")
            if term.lower() == 'q':
                break
            search_terms.append(term)
        
        if not search_terms:
            print("No products entered. Exiting.")
            return

        for search_term in search_terms:
            print(f"\nProcessing: {search_term}")
            await scrape_with_retry(search_term, category_id, conn)
            print(f"Finished processing: {search_term}\n\n\n")

if __name__ == "__main__":
    asyncio.run(main())