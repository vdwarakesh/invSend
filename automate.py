TEMPLATE_FILE = "template.docx"

import re
import os
import time
import subprocess
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from find_message import *
from find_file import *

file_sourceMap = get_sourceMap_file(TEMPLATE_FILE)
dir_sourceMap = get_sourceMap_dir(".")

# ========== Fallbacks if and only if exact roleName.docx doesn't exist ==========
message_roleMap = {
    "l2 support - workday": ["l2","workday"],
    "veeva quality / safety / clinical / rim roles": ["veeva"]
}

file_roleMap = {
    "workday": ["l2", "workday"],
    "veeva quality / safety / clinical / rim roles": ["veeva"]
}
# ========== End of fallbacks ==========

DEBUG_PORT = 9222
DEBUG_URL = f"http://127.0.0.1:{DEBUG_PORT}"

def is_chrome_debugger_ready() -> bool:
    try:
        urllib.request.urlopen(f"{DEBUG_URL}/json/version", timeout=1)
        return True
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
        return False

def get_profile_dir() -> str:
    # A Chrome profile kept inside the current project directory, not your
    # real Chrome profile. It persists across runs (so you only log into
    # Gmail here once), but deleting this project folder deletes it too --
    # no Gmail session is left behind anywhere else on the machine.
    path = os.path.join(os.getcwd(), "chrome-profile")
    os.makedirs(path, exist_ok=True)
    return path


def kill_chrome_process(proc: subprocess.Popen):
    # Kill only the specific Chrome instance (and its child processes) that
    # this script launched -- never other Chrome windows on the machine.
    if proc is None:
        return
    print("Closing the Chrome instance this script launched...")
    try:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass
    time.sleep(1)


def launch_chrome():
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]
    
    valid_path = next((p for p in chrome_paths if os.path.exists(p)), None)
    
    if not valid_path:
        raise FileNotFoundError("Could not find Google Chrome at the default Windows paths.")

    user_data_dir = get_profile_dir()

    def _try_launch():
        print("Launching Chrome with remote debugging (project-local profile)...")
        proc = subprocess.Popen([
            valid_path,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={user_data_dir}",
        ])
        for _ in range(10):
            if is_chrome_debugger_ready():
                return proc, True
            time.sleep(0.5)
        return proc, False

    # If a leftover Chrome process from an earlier run is still holding this
    # same profile directory without the debug port open, the launch above
    # can fail to expose it. Recover by closing just that one instance and
    # retrying once.
    proc, ready = _try_launch()
    if ready:
        return

    kill_chrome_process(proc)

    proc, ready = _try_launch()
    if ready:
        return

    raise RuntimeError("Chrome launched, but the remote debugging port failed to open.")

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return re.sub(r"\s+", " ", text).strip()

def format_phone_number(raw_number: str) -> str:
    digits = re.sub(r'\D', '', raw_number)
    if len(digits) == 10:
        return f"91{digits}"
    elif len(digits) > 10 and digits.startswith("91"):
        return digits
    elif len(digits) > 10 and digits.startswith("0"):
        return f"91{digits[1:]}"
    return digits

NOT_SENT_LOG = "not-sent.txt"


def log_not_sent(number: str, sender: str | None, subject: str, reason: str):
    print(f"Skipping send to {number}: {reason}")
    line = f"{number}\tsender={sender or '-'}\tsubject={subject or '-'}\treason={reason}\n"
    with open(NOT_SENT_LOG, "a", encoding="utf-8") as f:
        f.write(line)


def get_active_search_rows(page):
    return page.locator('div[role="main"]:visible tr.zA:visible')

def get_thread_subject(page) -> str | None:
    subject_loc = page.locator('div[role="main"]:visible h2.hP:visible')
    if subject_loc.count() == 0:
        return None
    return normalize_text(subject_loc.first.inner_text())

def get_message_sender(message) -> str:
    sender_loc = message.locator("span.gD").first
    if sender_loc.count() == 0:
        return ""
    email = sender_loc.get_attribute("email")
    if email:
        return email
    return normalize_text(sender_loc.inner_text())


def expand_all_messages(page):
    main_view = page.locator('div[role="main"]:visible')
    
    expand_all_btn = main_view.locator('[aria-label="Expand all"]:visible')
    if expand_all_btn.count() > 0:
        try:
            expand_all_btn.first.click(timeout=3000)
            page.wait_for_timeout(1000)
        except Exception:
            pass

    collapsed_headers = main_view.locator("div.kv:visible, div.kQ:visible")
    for i in range(collapsed_headers.count()):
        try:
            collapsed_headers.nth(i).click(timeout=2000)
            page.wait_for_timeout(300)
        except Exception:
            pass

    trimmed_buttons = main_view.locator('div.ajR[aria-label="Show trimmed content"]:visible')
    for i in range(trimmed_buttons.count()):
        try:
            trimmed_buttons.nth(i).click(timeout=2000)
            page.wait_for_timeout(300)
        except Exception:
            pass
    page.wait_for_timeout(800)

def ensure_gmail_loaded(page):
    try:
        page.goto("https://mail.google.com/", wait_until="domcontentloaded")
    except Exception as e:
        # Google's login redirect chain aborts this initial navigation when
        # the profile isn't logged in yet -- that's expected, not a real
        # failure, so ignore it here and check the resulting URL instead.
        if "ERR_ABORTED" not in str(e):
            raise

    page.wait_for_timeout(1500)

    if "accounts.google.com" in page.url or "ServiceLogin" in page.url:
        print("\nGmail isn't logged in yet in this Chrome profile.")
        input("Log into Gmail in the Chrome window that opened, then press Enter here to continue...")
        page.goto("https://mail.google.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)


def run_search(page, query: str):
    search_input = page.locator('input[aria-label="Search mail"], input[name="q"]').first
    search_input.wait_for(state="visible", timeout=60000)
    search_input.click()
    search_input.fill(query)
    search_input.press("Enter")
    
    try:
        page.wait_for_function(
            "() => window.location.hash.startsWith('#search') || window.location.hash.startsWith('#advanced-search') || window.location.hash.startsWith('#inbox')",
            timeout=15000,
        )
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(3000)

def message_sender_ss(sender: str = None, subject: str = None, after_ss=None, max_messages: int = 40):
    query_parts = []
    if subject:
        query_parts.append(f'subject:"{subject}"')
        target_subject_norm = normalize_text(subject).casefold()
    else:
        target_subject_norm = None
        
    if sender:
        query_parts.append(f'from:"{sender}"')
        
    search_query = " ".join(query_parts).strip()
    if not search_query:
        search_query = "in:anywhere"

    if not is_chrome_debugger_ready():
        launch_chrome()

    with sync_playwright() as p:
        print("\nConnecting to Chrome...")
        browser = p.chromium.connect_over_cdp(DEBUG_URL)
        if not browser.contexts:
            raise RuntimeError("No Chrome browser context found.")

        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()

        print("Navigating to Gmail...")
        ensure_gmail_loaded(page)
        
        print(f'Searching with query: "{search_query}"...')
        run_search(page, search_query)

        page_index = 1
        sent_count = 0
        limit_reached = False

        while True:
            rows = get_active_search_rows(page)
            try:
                rows.first.wait_for(state="visible", timeout=12000)
            except PlaywrightTimeoutError:
                print("No matching search results found on this page.")
                break

            row_count = rows.count()
            print(f"\n--- Page {page_index}: Found {row_count} search result row(s) ---")

            for i in range(row_count):
                try:
                    rows = get_active_search_rows(page)
                    if i >= rows.count():
                        break

                    row = rows.nth(i)

                    subject_cell = row.locator("span.bog").first
                    if subject_cell.count() > 0:
                        if target_subject_norm:
                            row_subject = normalize_text(subject_cell.inner_text())
                            if row_subject.casefold() != target_subject_norm:
                                continue
                        subject_cell.click(timeout=10000)
                    else:
                        row.locator("td.xY, td.a4W").first.click(timeout=10000)

                    page.locator('div[role="main"]:visible h2.hP:visible').first.wait_for(state="visible", timeout=15000)
                    actual_subject = get_thread_subject(page) or ""

                    if target_subject_norm and actual_subject.casefold() != target_subject_norm:
                        page.go_back()
                        get_active_search_rows(page).first.wait_for(state="visible", timeout=15000)
                        continue

                    main_view = page.locator('div[role="main"]:visible')
                    main_view.locator("div.adn:visible").first.wait_for(state="visible", timeout=20000)
                    expand_all_messages(page)

                    messages = main_view.locator("div.adn:visible")
                    message_count = messages.count()

                    for j in range(message_count):
                        try:
                            messages = page.locator('div[role="main"]:visible div.adn:visible')
                            message = messages.nth(j)
                            message.scroll_into_view_if_needed()
                            page.wait_for_timeout(500)

                            body = message.locator(".a3s:visible")
                            if body.count() == 0:
                                continue

                            actual_sender = get_message_sender(message) or sender

                            body_text = body.first.inner_text()
                            phone_match = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', body_text)
                            
                            if phone_match:
                                raw_number = phone_match.group(0)
                                number = format_phone_number(raw_number)
                                print(f"Extracted Phone: {number}")
                                
                                message.screenshot(path="temp.png", animations="disabled", timeout=60000)
                                
                                if after_ss:
                                    messageNum = message_to_send(actual_subject, file_sourceMap, message_roleMap)
                                    fileNum = file_to_send(actual_subject, dir_sourceMap, file_roleMap)

                                    message_missing = not messageNum
                                    file_missing = not fileNum

                                    if message_missing or file_missing:
                                        if message_missing and file_missing:
                                            reason = "No matching message template or file found"
                                        elif message_missing:
                                            reason = "No matching message template found"
                                        else:
                                            reason = "No matching file found"
                                        log_not_sent(number, actual_sender, actual_subject, reason)
                                    else:
                                        after_ss(number, messageNum, None)
                                        after_ss(number, None, "temp.png")
                                        after_ss(number, None, fileNum)

                                        sent_count += 1
                                        print(f"Sent {sent_count}/{max_messages}")
                                        if sent_count >= max_messages:
                                            print(f"Reached max_messages limit ({max_messages}). Stopping.")
                                            limit_reached = True
                            else:
                                print(f"No phone number found in message {j + 1}.")

                        except Exception as msg_err:
                            print(f"Message {j + 1} processing failed: {msg_err}")

                        if limit_reached:
                            break

                    if limit_reached:
                        break

                    page.go_back()
                    get_active_search_rows(page).first.wait_for(state="visible", timeout=15000)
                    page.wait_for_timeout(1000)

                except Exception as thread_err:
                    print(f"Error processing thread: {thread_err}")
                    try:
                        run_search(page, search_query)
                    except Exception:
                        break

            if limit_reached:
                break

            older_btn = page.locator('div[role="main"]:visible [aria-label="Older"]:visible').first
            if older_btn.count() == 0:
                older_btn = page.locator('[aria-label="Older"]:visible').last
            if older_btn.count() == 0 or older_btn.get_attribute("aria-disabled") == "true":
                break

            older_btn.click()
            page.wait_for_timeout(3000)
            page_index += 1

        print("\nAutomation complete.")