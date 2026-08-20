from __future__ import annotations

from conftest import BrowserTestServer
from playwright.sync_api import Page, expect


def test_customer_can_open_chat_and_view_a_recommendation(
    page: Page,
    browser_test_server: BrowserTestServer,
) -> None:
    page.goto(f"{browser_test_server.base_url}/preview")

    launcher = page.get_by_role("button", name="Chat with us")
    expect(launcher).to_be_visible()
    launcher.click()
    expect(page.get_by_text("E2E Flooring Guide")).to_be_visible()
    greeting = page.get_by_text("Tell me about the room and the flooring look you prefer.")
    expect(greeting).to_be_visible()

    message = "I need waterproof luxury vinyl for my kitchen"
    page.get_by_role("textbox", name="Message").fill(message)
    page.get_by_role("button", name="Send").click()

    expect(page.locator(".fc-user")).to_have_text(message)
    expect(page.get_by_text("I ranked 1 matching product.")).to_be_visible()
    expect(page.locator(".fc-card-title")).to_have_text("Coastal Oak")
    expect(page.locator(".fc-meta")).to_contain_text("SKU: ABC123 · $4.75")
    expect(page.locator(".fc-reason")).to_contain_text("waterproof luxury vinyl")
    product_link = page.get_by_role("link", name="View product")
    expect(product_link).to_have_attribute(
        "href", f"{browser_test_server.base_url}/?s=ABC123"
    )
    with page.expect_popup() as popup_info:
        product_link.click()
    popup_info.value.close()

    page.get_by_role("button", name="Yes").click()
    expect(page.get_by_text("Thanks for your feedback.")).to_be_visible()

    assert browser_test_server.agent.calls[-1][1:] == (message, browser_test_server.base_url)


def test_floating_and_inline_widgets_can_be_closed_and_reopened(
    page: Page,
    browser_test_server: BrowserTestServer,
) -> None:
    page.goto(f"{browser_test_server.base_url}/preview")
    page.get_by_role("button", name="Chat with us").click()
    page.get_by_role("button", name="Close chat").click()
    expect(page.locator(".fc-panel")).to_be_hidden()
    expect(page.get_by_role("button", name="Chat with us")).to_be_focused()

    page.goto(f"{browser_test_server.base_url}/preview-inline")
    page.get_by_role("button", name="Close chat").click()
    reopen = page.get_by_role("button", name="Open chat")
    expect(reopen).to_be_visible()
    reopen.click()
    expect(page.get_by_role("textbox", name="Message")).to_be_focused()


def test_widget_displays_service_errors_and_recovers_input(
    page: Page,
    browser_test_server: BrowserTestServer,
) -> None:
    page.goto(f"{browser_test_server.base_url}/preview-inline")
    textbox = page.get_by_role("textbox", name="Message")
    textbox.fill("trigger service error")
    page.get_by_role("button", name="Send").click()

    expect(page.locator(".fc-error")).to_have_text(
        "The recommendation service is temporarily unavailable"
    )
    expect(textbox).to_be_enabled()
    expect(textbox).to_be_focused()


def test_floating_panel_fits_a_mobile_viewport(
    page: Page,
    browser_test_server: BrowserTestServer,
) -> None:
    page.set_viewport_size({"width": 360, "height": 640})
    page.goto(f"{browser_test_server.base_url}/preview")
    page.get_by_role("button", name="Chat with us").click()

    panel = page.locator(".fc-panel")
    expect(panel).to_be_visible()
    bounds = panel.bounding_box()
    assert bounds is not None
    assert bounds["x"] >= 0
    assert bounds["y"] >= 0
    assert bounds["x"] + bounds["width"] <= 360
    assert bounds["y"] + bounds["height"] <= 640
    expect(page.get_by_role("button", name="Close chat")).to_be_visible()
