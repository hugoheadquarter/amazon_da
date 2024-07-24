from playwright.sync_api import sync_playwright, TimeoutError
from amazoncaptcha import AmazonCaptcha
from fake_useragent import UserAgent
import sqlite3

EMAIL = "hugoheadquarter@gmail.com"
PASSWORD = "Gr70390909#@!"
DB_PATH = '/Users/dylankim/Desktop/resume/amazon/db/amazon_products.db'

ua = UserAgent(platforms='pc')

def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        rating INTEGER,
        title TEXT,
        date TEXT,
        reviewer TEXT,
        verified TEXT,
        text TEXT,
        helpful TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    ''')
    conn.commit()
    return conn

def insert_review(conn, product_id, review_data):
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO reviews (product_id, rating, title, date, reviewer, verified, text, helpful)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_id,
        review_data['rating'],
        review_data['title'],
        review_data['date'],
        review_data['reviewer'],
        review_data['verified'],
        review_data['text'],
        review_data['helpful']
    ))
    conn.commit()

def solve_captcha(page):
    print("Captcha detected. Attempting to solve...")
    captcha_image = page.query_selector('img[src*="captcha"]')
    if captcha_image:
        captcha_url = captcha_image.get_attribute('src')
        captcha = AmazonCaptcha.fromlink(captcha_url)
        solution = captcha.solve()
        
        if solution:
            print(f"Captcha solved: {solution}")
            input_field = page.query_selector('input[name="field-keywords"]')
            if input_field:
                input_field.fill(solution)
                submit_button = page.query_selector('button[type="submit"]')
                if submit_button:
                    submit_button.click()
                    page.wait_for_load_state('networkidle')
                    return True
    
    print("Failed to solve captcha")
    return False

def login(page):
    page.goto("https://www.amazon.com")
    page.click('a#nav-link-accountList')
    page.fill('#ap_email', EMAIL)
    page.click('#continue')
    page.fill('#ap_password', PASSWORD)
    page.click('#signInSubmit')
    
    if "captcha" in page.url:
        if not solve_captcha(page):
            raise Exception("Captcha solving failed during login")
    
    print("Login successful")

def scrape_star_reviews(page, star_rating, product_id, conn):
    star_filter = page.query_selector(f'a.a-link-normal[class*="{star_rating}star"]')
    if star_filter:
        href = star_filter.get_attribute('href')
        if href:
            full_url = f"https://www.amazon.com{href}" if href.startswith('/') else href
            page.goto(full_url)
            page.wait_for_selector('div[data-hook="review"]')
    else:
        print(f"{star_rating}-star filter not found")
        return []

    reviews = []
    page_num = 1
    while True:
        review_elements = page.query_selector_all('div[data-hook="review"]')
        if not review_elements:
            break
        
        for review in review_elements:
            review_data = {}
            
            rating_element = review.query_selector('i[data-hook="review-star-rating"], i[class*="a-star"]')
            if rating_element:
                rating_text = rating_element.get_attribute('class')
                if f'a-star-{star_rating}' in rating_text:
                    review_data['rating'] = str(star_rating)
                else:
                    continue
            else:
                continue
            
            title_element = review.query_selector('a[data-hook="review-title"]')
            review_data['title'] = title_element.inner_text() if title_element else 'N/A'
            
            date_element = review.query_selector('span[data-hook="review-date"]')
            review_data['date'] = date_element.inner_text() if date_element else 'N/A'
            
            name_element = review.query_selector('span.a-profile-name')
            review_data['reviewer'] = name_element.inner_text() if name_element else 'N/A'
            
            verified_element = review.query_selector('span[data-hook="avp-badge"]')
            review_data['verified'] = 'Verified Purchase' if verified_element else 'Not Verified'
            
            text_element = review.query_selector('span[data-hook="review-body"]')
            review_data['text'] = text_element.inner_text() if text_element else 'N/A'
            
            helpful_element = review.query_selector('span[data-hook="helpful-vote-statement"]')
            review_data['helpful'] = helpful_element.inner_text() if helpful_element else '0 people found this helpful'
            
            reviews.append(review_data)
            insert_review(conn, product_id, review_data)
        
        next_button = page.query_selector('ul.a-pagination li.a-last:not(.a-disabled) a')
        if next_button:
            next_button.click()
            page.wait_for_selector('div[data-hook="review"]')
        else:
            break
        
        page_num += 1
    
    return reviews

def get_product_urls(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, url FROM products")
    return cursor.fetchall()

def scrape_reviews(page, product_url, product_id, conn):
    page.goto(product_url)
    see_all_reviews = page.query_selector('a[data-hook="see-all-reviews-link-foot"], a[data-hook="see-all-reviews-link"]')
    if see_all_reviews:
        see_all_reviews.click()
        page.wait_for_selector('div[data-hook="review"]')

    all_reviews = []
    for star in range(1, 6):
        try:
            if "filterByStar" in page.url:
                page.goto(page.url.split("filterByStar")[0])
            
            star_reviews = scrape_star_reviews(page, star, product_id, conn)
            all_reviews.extend(star_reviews)
            print(f"Scraped {len(star_reviews)} {star}-star reviews")
        except Exception as e:
            print(f"Error scraping {star}-star reviews: {e}")
            print(f"Moving to the next rating...")
            continue

    return all_reviews

def main():
    conn = setup_database()
    
    with sync_playwright() as p:
        user_agent = ua.random
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(user_agent=user_agent)
        page = context.new_page()
        
        print(f"Using User-Agent: {user_agent}")
        
        try:
            login(page)
            
            product_urls = get_product_urls(conn)
            total_products = len(product_urls)
            for index, (product_id, url) in enumerate(product_urls, 1):
                print(f"Processing product {index} of {total_products}: ID {product_id}")
                try:
                    reviews = scrape_reviews(page, url, product_id, conn)
                    print(f"Scraped {len(reviews)} total reviews for ID: {product_id}")
                except Exception as e:
                    print(f"Error processing product ID {product_id}: {e}")
                    print("Moving to next product...")
                    continue
        
        except Exception as e:
            print(f"An error occurred in the main process: {e}")
            page.screenshot(path="error_screenshot.png")
        
        finally:
            browser.close()
            conn.close()

if __name__ == "__main__":
    main()