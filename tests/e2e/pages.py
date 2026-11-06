"""Page object: accessible locators and UI verbs only. Business assertions live in the specs."""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class NexusPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

    # ---- lifecycle
    def open(self) -> None:
        self.page.goto(self.base_url)
        self.page.locator("body[data-ready=true]").wait_for(state="attached")
        self.prompt.wait_for()

    reload = open

    # ---- prompt and menu
    @property
    def prompt(self) -> Locator:
        return self.page.get_by_role("combobox", name="Write a prompt")

    @property
    def suggestions(self) -> Locator:
        return self.page.get_by_role("listbox", name="Command suggestions")

    @property
    def options(self) -> Locator:
        return self.suggestions.get_by_role("option")

    @property
    def send_button(self) -> Locator:
        return self.page.locator("#sendBtn")

    @property
    def mode_status(self) -> Locator:
        return self.page.locator("#modeStatusText")

    def pill(self, name: str) -> Locator:
        return self.page.locator("#modePills").get_by_role("button", name=name)

    def pill_for(self, mode_id: str) -> Locator:
        return self.page.locator(f'#modePills [data-mode="{mode_id}"]')

    def set_prompt(self, text: str) -> None:
        self.prompt.fill(text)

    def send(self) -> None:
        self.prompt.press("Control+Enter")

    def run(self, text: str) -> None:
        """Send and wait until the app is no longer busy, so commands never race each other."""
        self.set_prompt(text)
        self.send()
        expect(self.send_button).not_to_have_attribute("aria-busy", "true")

    def ask(self, text: str) -> None:
        """Send a prompt and wait for one more assistant reply to be rendered."""
        before = self.replies.count()
        self.run(text)
        expect(self.replies).to_have_count(before + 1)

    def send_and_capture(self) -> dict:
        with self.page.expect_request(
            lambda r: r.url.endswith("/api/chat") and r.method == "POST"
        ) as info:
            self.send()
        return info.value.post_data_json

    # ---- status strip
    @property
    def project_chip(self) -> Locator:
        return self.page.locator("#projectName")

    @property
    def model_chip(self) -> Locator:
        return self.page.locator("#modelName")

    @property
    def docs_chip(self) -> Locator:
        return self.page.locator("#chipDocs")

    @property
    def chats_chip(self) -> Locator:
        return self.page.locator("#chipChats")

    # ---- context pane
    @property
    def pane(self) -> Locator:
        return self.page.get_by_role("complementary", name="Contextual tools")

    @property
    def pane_title(self) -> Locator:
        return self.page.locator("#contextTitle")

    def widget(self, label: str) -> Locator:
        return self.pane.get_by_label(label, exact=True)

    @property
    def related_cards(self) -> Locator:
        return self.page.locator("#relatedItems .related-card")

    # ---- feedback
    @property
    def toast(self) -> Locator:
        return self.page.get_by_role("status")

    # ---- conversation
    @property
    def conversation(self) -> Locator:
        return self.page.locator("#conversation")

    @property
    def user_messages(self) -> Locator:
        return self.page.locator(".message-user")

    @property
    def replies(self) -> Locator:
        return self.page.locator(".message-ai")

    @property
    def last_reply(self) -> Locator:
        return self.replies.last

    def reply_action(self, name: str) -> Locator:
        return self.last_reply.get_by_role("button", name=name)

    # ---- document dialog (ids: the labels wrap the controls and include their values in the name)
    @property
    def doc_dialog(self) -> Locator:
        return self.page.locator("#documentModal").get_by_role("dialog")

    @property
    def doc_type(self) -> Locator:
        return self.page.locator("#docType")

    @property
    def doc_title(self) -> Locator:
        return self.page.locator("#docTitle")

    @property
    def doc_body(self) -> Locator:
        return self.page.locator("#docBody")

    @property
    def doc_status(self) -> Locator:
        return self.page.locator("#docSaveStatus")

    def save_document(self) -> None:
        self.doc_dialog.get_by_role("button", name="Save document").click()

    # ---- search dialog
    @property
    def search_dialog(self) -> Locator:
        return self.page.get_by_role("dialog", name="Search archive")

    @property
    def search_input(self) -> Locator:
        return self.search_dialog.get_by_role("searchbox")
