import os
import json
import re
import time
import hashlib
import html
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

class TAMUSeleniumScraper:
    def __init__(self, email_config):
        self.base_url = "https://jobs.rwfm.tamu.edu/search/?PageSize=50&PageNum=1#results"
        self.email_config = email_config
        self.sent_jobs_file = "sent_jobs.json"
        self.sent_jobs = self.load_sent_jobs()

        self.keywords = [
            "reptile", "amphibian", "herp", "turtle", "toad", "frog",
            "seal", "island", "whale", "cetacean", "tortoise",
            "spatial ecology", "predator", "tropical", "hawaii",
            "bear", "lion", "snake", "lizard", "alligator",
            "crocodile", "M.S."
        ]
        self.keyword_patterns = [re.compile(rf'\b{kw}s?\b', re.I) for kw in self.keywords]

    def load_sent_jobs(self):
        if os.path.exists(self.sent_jobs_file):
            try:
                with open(self.sent_jobs_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_sent_jobs(self):
        with open(self.sent_jobs_file, 'w') as f:
            json.dump(self.sent_jobs, f, indent=2)

    def create_job_id(self, title, description):
        return hashlib.md5((title + description[:200]).lower().encode()).hexdigest()

    def contains_keywords(self, text):
        matches = [kw.pattern.strip(r'\bs?\b') for kw in self.keyword_patterns if kw.search(text)]
        return matches

    def scrape_jobs(self):
        print(f"Launching browser for {self.base_url}...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")

        driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
        driver.get(self.base_url)
        time.sleep(5)  # Wait for JS to load

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()

        job_containers = soup.select("div[class*='job'], div[class*='posting'], li[class*='job']")
        jobs = []

        for container in job_containers:
            text = container.get_text(strip=True)
            if len(text) < 50:
                continue

            title_elem = container.find(['h2', 'h3', 'a'])
            title = title_elem.get_text(strip=True) if title_elem else text[:80]
            url_elem = container.find('a', href=True)
            job_url = url_elem['href'] if url_elem else self.base_url
            if job_url.startswith('/'):
                job_url = "https://jobs.rwfm.tamu.edu" + job_url

            job_text = html.unescape(text)
            job_id = self.create_job_id(title, job_text)
            match_keywords = self.contains_keywords(job_text.lower())

            if match_keywords:
                jobs.append({
                    "id": job_id,
                    "title": title,
                    "url": job_url,
                    "description": job_text[:1000],
                    "scraped_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "matching_keywords": match_keywords
                })

        print(f"Scraped {len(jobs)} matching jobs.")
        return jobs

    def send_email(self, jobs):
        if not jobs:
            print("No new jobs to send.")
            return

        subject = f"TAMU Job Alert - {len(jobs)} New Job(s) ({datetime.now().strftime('%Y-%m-%d')})"
        html_body = self.create_email_body(jobs)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.email_config["from_email"]
        msg["To"] = self.email_config["to_email"]
        msg.attach(MIMEText(html_body, "html"))

        try:
            print("Connecting to email server...")
            with smtplib.SMTP(self.email_config["smtp_server"], self.email_config["smtp_port"]) as server:
                server.starttls()
                server.login(self.email_config["from_email"], self.email_config["password"])
                server.send_message(msg)
            print("Email sent.")
        except Exception as e:
            print(f"Failed to send email: {e}")

        for job in jobs:
            if job["id"] not in self.sent_jobs:
                self.sent_jobs.append(job["id"])
        self.save_sent_jobs()

    def create_email_body(self, jobs):
        html_content = """
        <html><body><h2>🐢 TAMU Wildlife Job Alert</h2>
        <ul>
        """
        for job in jobs:
            html_content += f"""
            <li>
                <strong>{html.escape(job['title'])}</strong><br/>
                <a href="{job['url']}" target="_blank">View Posting</a><br/>
                <em>Keywords: {', '.join(job['matching_keywords'])}</em><br/>
                <p>{html.escape(job['description'][:300])}...</p>
            </li><br/>
            """
        html_content += "</ul></body></html>"
        return html_content

    def run(self):
        print("Starting scrape...")
        jobs = self.scrape_jobs()
        new_jobs = [job for job in jobs if job["id"] not in self.sent_jobs]
        self.send_email(new_jobs)

def main():
    smtp_port_str = os.environ.get("SMTP_PORT", "587").strip()
    smtp_port = int(smtp_port_str) if smtp_port_str.isdigit() else 587

    email_config = {
        "from_email": os.environ.get("FROM_EMAIL", "").strip(),
        "password": os.environ.get("EMAIL_PASSWORD", "").strip(),
        "to_email": os.environ.get("TO_EMAIL", "").strip(),
        "smtp_server": os.environ.get("SMTP_SERVER", "smtp.gmail.com").strip(),
        "smtp_port": smtp_port
    }

    missing = [k for k in ['from_email', 'password', 'to_email'] if not email_config[k]]
    if missing:
        print(f"Missing required email config: {missing}")
        return

    scraper = TAMUSeleniumScraper(email_config)
    scraper.run()

if __name__ == "__main__":
    main()
