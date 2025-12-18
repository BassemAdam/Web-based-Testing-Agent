import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page

def test_TC_NAVIGATE_VIDEO_TUTORIALS_01(page):
    # Step 1: Navigate to the start URL
    home_page = Page_0Page(page)
    home_page.navigate()

    # Step 2: Click on the 'Video Tutorials' link
    home_page.click_video_tutorials()

    # Step 3: Verify that the user is redirected to the video tutorials page on YouTube
    expect(page).to_have_url("https://www.youtube.com/c/AutomationExercise")