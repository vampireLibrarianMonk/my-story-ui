"""Paths: rendered markdown read view with edit toggle, and the reference-image thumbnail + lightbox."""

from __future__ import annotations

import struct
import zlib

from playwright.sync_api import expect


def _png() -> bytes:
    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x30\x60\x40" * 4 for _ in range(4))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


MD = "# Title\n\n> A caution note.\n\n## Section\n\nA paragraph with **bold** and *italic* and `code`.\n\n- one\n- two\n"


def make_markdown_doc(api, pid):
    return api.post(
        "/api/documents",
        json={"project_id": pid, "type": "character", "title": "Rendered", "body": MD},
    ).json()


def test_existing_document_opens_rendered_not_raw(nx, api, pid):
    make_markdown_doc(api, pid)
    nx.reload()
    nx.run("/doc open Rendered")
    expect(nx.doc_dialog).to_be_visible()
    view = nx.page.locator("#docPreview")
    expect(view).to_be_visible()
    expect(nx.doc_body).to_be_hidden()
    expect(view.locator("h1")).to_have_text("Title")
    expect(view.locator("h2")).to_have_text("Section")
    expect(view.locator("blockquote")).to_contain_text("A caution note.")
    expect(view.locator("li")).to_have_count(2)
    expect(view.locator("strong")).to_have_text("bold")
    assert "##" not in view.inner_text()


def test_edit_toggle_reveals_the_raw_textarea(nx, api, pid):
    make_markdown_doc(api, pid)
    nx.reload()
    nx.run("/doc open Rendered")
    nx.doc_dialog.get_by_role("button", name="Edit").click()
    expect(nx.doc_body).to_be_visible()
    expect(nx.doc_body).to_have_value(MD)
    nx.doc_dialog.get_by_role("button", name="Preview").click()
    expect(nx.page.locator("#docPreview")).to_be_visible()


def test_new_document_opens_in_edit_mode_without_a_toggle(nx):
    nx.run("/doc new note Fresh")
    expect(nx.doc_body).to_be_visible()
    expect(nx.doc_dialog.get_by_role("button", name="Edit")).to_have_count(0)


def test_reply_text_is_not_rendered_as_markdown(nx):
    # Chat transcript stays literal; only saved documents get the rendered view.
    nx.ask("# not a heading and **not bold**")
    expect(nx.user_messages.first).to_contain_text("# not a heading and **not bold**")
    assert nx.user_messages.first.locator("strong").count() == 0


def test_image_thumbnail_and_lightbox(nx, api, pid):
    doc = make_markdown_doc(api, pid)
    api.put(
        f"/api/documents/{doc['id']}/image",
        content=_png(),
        headers={"content-type": "image/png"},
    )
    nx.reload()
    nx.run("/doc open Rendered")
    thumb = nx.page.locator("#docImageThumb")
    expect(thumb).to_be_visible()
    expect(nx.page.locator("#docImageRow")).to_contain_text(
        "Visual exploration, not canon"
    )
    thumb.click()
    lightbox = nx.page.get_by_role("dialog", name="Reference image")
    expect(lightbox).to_be_visible()
    nx.page.wait_for_function("document.getElementById('imageFull')?.naturalWidth > 0")
    assert nx.page.evaluate("document.getElementById('imageFull').naturalWidth") == 4
    nx.page.keyboard.press("Escape")
    expect(lightbox).to_be_hidden()


def test_document_without_image_shows_add_not_thumbnail(nx, api, pid):
    make_markdown_doc(api, pid)
    nx.reload()
    nx.run("/doc open Rendered")
    expect(nx.page.locator("#docImageThumb")).to_be_hidden()
    expect(nx.page.get_by_role("button", name="Add image")).to_be_visible()
    expect(nx.page.get_by_role("button", name="Remove")).to_be_hidden()


def test_upload_via_button_shows_the_thumbnail(nx, api, pid, tmp_path):
    make_markdown_doc(api, pid)
    nx.reload()
    nx.run("/doc open Rendered")
    expect(nx.page.locator("#docImageThumb")).to_be_hidden()
    png = tmp_path / "ref.png"
    png.write_bytes(_png())
    nx.page.set_input_files("#docImageFile", str(png))
    expect(nx.page.locator("#docImageThumb")).to_be_visible()
    expect(nx.page.get_by_role("button", name="Remove")).to_be_visible()
    nx.page.wait_for_function(
        "(()=>{const i=document.querySelector('#docImageThumb img'); return i && i.complete && i.naturalWidth>0})()"
    )
    # Reopening shows the thumbnail from the cached overview (metadata now travels with the doc list).
    nx.page.keyboard.press("Escape")
    nx.run("/doc open Rendered")
    expect(nx.page.locator("#docImageThumb")).to_be_visible()


def test_header_lines_render_on_separate_lines(nx, api, pid):
    api.post(
        "/api/documents",
        json={
            "project_id": pid,
            "type": "note",
            "title": "Header",
            "body": "**Role:** snapshot\n**Status:** mixed\n**Version:** 0.1\n",
        },
    )
    nx.reload()
    nx.run("/doc open Header")
    para = nx.page.locator("#docPreview .markdown p").first
    expect(para.locator("br")).to_have_count(2)


def test_relationships_render_grouped_by_scale(nx, api, pid):
    # Two characters linked at two scales, one directed.
    a = api.post(
        "/api/documents",
        json={"project_id": pid, "type": "character", "title": "Alpha", "body": "x"},
    ).json()["id"]
    b = api.post(
        "/api/documents",
        json={"project_id": pid, "type": "character", "title": "Beta", "body": "x"},
    ).json()["id"]
    api.post(
        "/api/relationships",
        json={
            "project_id": pid,
            "from_doc": a,
            "to_doc": b,
            "scale": "personal",
            "nature": "ally",
        },
    )
    api.post(
        "/api/relationships",
        json={
            "project_id": pid,
            "from_doc": a,
            "to_doc": b,
            "scale": "organizational",
            "nature": "authority",
            "direction": "from_to",
            "status": "decided",
        },
    )
    nx.reload()
    nx.run("/doc open Alpha")
    section = nx.page.locator("#docRelationships")
    expect(section).to_be_visible()
    expect(nx.page.locator("#relCount")).to_have_text("2")
    expect(nx.page.locator(".rel-scale")).to_have_count(2)
    rows = nx.page.locator(".rel-row")
    expect(rows).to_have_count(2)
    expect(rows.filter(has_text="Beta").first).to_be_visible()


def test_document_without_relationships_hides_the_section(nx, api, pid):
    api.post(
        "/api/documents",
        json={"project_id": pid, "type": "note", "title": "Lonely", "body": "x"},
    )
    nx.reload()
    nx.run("/doc open Lonely")
    expect(nx.doc_dialog).to_be_visible()
    expect(nx.page.locator("#docRelationships")).to_be_hidden()
