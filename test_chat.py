# -*- coding: utf-8 -*-
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Setup Chrome options
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
chrome_options.add_argument("--disable-extensions")

# Initialize driver
driver = webdriver.Chrome(options=chrome_options)

try:
    # Step 1: Navigate to login page
    print("=== Step 1: Navigating to http://127.0.0.1:5000/login ===")
    driver.get("http://127.0.0.1:5000/login")
    time.sleep(3)
    
    # Check if we're on login page
    print(f"Current URL: {driver.current_url}")
    print(f"Page title: {driver.title}")
    
    # Step 2: Login with credentials
    print("\n=== Step 2: Logging in ===")
    print("Phone/Username: 0865054042")
    print("Password: Duc@12345")
    
    # Look for username input (not phone)
    try:
        # Look for username input
        username_input = driver.find_element(By.NAME, "username")
        password_input = driver.find_element(By.NAME, "password")
        
        username_input.send_keys("0865054042")
        password_input.send_keys("Duc@12345")
        
        # Find and click login button
        login_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_btn.click()
        
        time.sleep(5)
        print(f"After login URL: {driver.current_url}")
        print(f"After login title: {driver.title}")
    except Exception as e:
        print(f"Error during login: {e}")
    
    # Step 3: Check for chat widget after login
    print("\n=== Step 3: Checking for chat widget ===")
    time.sleep(3)
    
    # Look for chat widget button (red circular button)
    try:
        chat_button = driver.find_element(By.ID, "chat-widget-btn")
        print(f"Found chat button: {chat_button.get_attribute('class')}")
        print(f"Chat button visible: {chat_button.is_displayed()}")
    except:
        print("Chat button NOT found by ID 'chat-widget-btn'")
        # Try other selectors
        try:
            chat_button = driver.find_element(By.CLASS_NAME, "chat-widget-toggle")
            print(f"Found chat widget class: {chat_button.get_attribute('class')}")
        except:
            print("Chat widget NOT found by class 'chat-widget-toggle'")
    
    # Try to find any element with 'chat' in id or class
    try:
        chat_elements = driver.find_elements(By.XPATH, "//*[contains(@id, 'chat') or contains(@class, 'chat')]")
        print(f"Found {len(chat_elements)} elements with 'chat' in id or class:")
        for el in chat_elements:
            print(f"  - id={el.get_attribute('id')}, class={el.get_attribute('class')}")
    except Exception as e:
        print(f"Error finding chat elements: {e}")
    
    # Take a screenshot to see the page
    driver.save_screenshot("screenshot1_after_login.png")
    print("Screenshot saved: screenshot1_after_login.png")
    
    # Step 4: Click on chat widget if found
    print("\n=== Step 4: Opening chat widget ===")
    try:
        chat_button = driver.find_element(By.ID, "chat-widget-btn")
        chat_button.click()
        time.sleep(2)
        print("Clicked chat button!")
    except Exception as e:
        print(f"Could not click chat button by ID: {e}")
        # Try other selector
        try:
            chat_button = driver.find_element(By.CLASS_NAME, "chat-widget-toggle")
            chat_button.click()
            time.sleep(2)
            print("Clicked chat button by class!")
        except Exception as e2:
            print(f"Could not click chat button by class: {e2}")
    
    # Step 5: Send a message
    print("\n=== Step 5: Sending message 'Xin chao' ===")
    try:
        message_input = driver.find_element(By.ID, "chat-message-input")
        message_input.send_keys("Xin chao")
        
        send_button = driver.find_element(By.ID, "chat-send-btn")
        send_button.click()
        
        time.sleep(5)
        print("Message sent!")
    except Exception as e:
        print(f"Could not send message: {e}")
    
    # Take another screenshot
    driver.save_screenshot("screenshot2_after_send.png")
    print("Screenshot saved: screenshot2_after_send.png")
    
    # Step 6: Check for AI response
    print("\n=== Step 6: Checking for AI response ===")
    time.sleep(3)
    try:
        messages = driver.find_elements(By.CLASS_NAME, "chat-message")
        print(f"Found {len(messages)} messages")
        for msg in messages:
            print(f"  Message: {msg.text}")
    except Exception as e:
        print(f"Error checking messages: {e}")
    
    # Step 7: Close and reopen chat to check history
    print("\n=== Step 7: Closing chat ===")
    try:
        close_btn = driver.find_element(By.CLASS_NAME, "chat-close")
        close_btn.click()
        time.sleep(2)
        print("Chat closed!")
    except Exception as e:
        print(f"Could not close chat: {e}")
        # Try clicking the toggle again to close
        try:
            chat_button = driver.find_element(By.ID, "chat-widget-btn")
            chat_button.click()
            time.sleep(2)
            print("Chat closed by toggling!")
        except Exception as e2:
            print(f"Could not close chat: {e2}")
    
    print("\n=== Step 8: Reopening chat ===")
    try:
        chat_button = driver.find_element(By.ID, "chat-widget-btn")
        chat_button.click()
        time.sleep(2)
        print("Chat reopened!")
    except Exception as e:
        print(f"Could not reopen chat: {e}")
    
    # Take another screenshot
    driver.save_screenshot("screenshot3_reopen.png")
    print("Screenshot saved: screenshot3_reopen.png")
    
    # Step 9: Check if old messages are still there
    print("\n=== Step 9: Checking message history ===")
    try:
        messages = driver.find_elements(By.CLASS_NAME, "chat-message")
        print(f"Found {len(messages)} messages after reopen")
        for msg in messages:
            print(f"  Message: {msg.text}")
    except Exception as e:
        print(f"Error checking messages: {e}")
    
    # Take a final screenshot
    print("\n=== Final state ===")
    print(f"Current URL: {driver.current_url}")
    
    driver.save_screenshot("screenshot_final.png")
    print("Screenshot saved: screenshot_final.png")
    
    input("Press Enter to close the browser...")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    
finally:
    driver.quit()
