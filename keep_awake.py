"""
Keep the ChessMood Tracker Streamlit app awake.

Opens the app in a headless browser and, if it has gone to sleep,
clicks the "Yes, get this app back up!" button. Run on a schedule
(every 6 hours) via GitHub Actions so the app never stays asleep.
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

URL = "https://chessmood-tracker.streamlit.app"

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--window-size=1280,900")

driver = webdriver.Chrome(options=opts)
try:
    driver.get(URL)
    time.sleep(8)  # let the page render

    clicked = False
    # The wake button can take a moment to appear; try a few times.
    for _ in range(4):
        for b in driver.find_elements(By.TAG_NAME, "button"):
            label = (b.text or "").strip().lower()
            if "get this app back up" in label or "yes, get this app" in label:
                b.click()
                clicked = True
                print("Wake button found and clicked.")
                break
        if clicked:
            break
        time.sleep(3)

    if not clicked:
        print("No wake button found - app was already awake.")

    # Stay on the page so the visit registers as real traffic.
    time.sleep(30)
    print("Done. Page title:", driver.title)
finally:
    driver.quit()
