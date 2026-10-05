import pytest

from app.loaders import UnreadableFileError, UnsupportedFileError, load
from tests.conftest import make_docx, make_pdf


def test_text_is_decoded_and_whitespace_cleaned():
    segments = load("notes.txt", "Café   menu\r\n\r\n\r\n\r\nOpen\tdaily".encode("utf-8-sig"))
    assert [s.text for s in segments] == ["Café menu\n\nOpen daily"]
    assert segments[0].page is None


def test_non_utf8_text_falls_back_to_cp1252():
    assert load("old.md", "naïve résumé".encode("cp1252"))[0].text == "naïve résumé"


def test_csv_rows_become_self_describing_lines():
    data = b"name,role,office\nAda,Engineer,London\nGrace,Admiral,\n"
    (segment,) = load("team.csv", data)
    assert segment.text.splitlines() == [
        "name: Ada; role: Engineer; office: London",
        "name: Grace; role: Admiral",
    ]


def test_docx_reads_paragraphs_and_tables():
    data = make_docx(["Quarterly report", "Revenue grew."], table=[["Region", "Sales"], ["EU", "42"]])
    (segment,) = load("report.docx", data)
    assert "Quarterly report" in segment.text
    assert "Region | Sales" in segment.text
    assert "EU | 42" in segment.text


def test_pdf_pages_keep_their_numbers():
    segments = load("guide.pdf", make_pdf(["First page about setup.", "Second page about billing."]))
    assert [(s.page, s.text) for s in segments] == [
        (1, "First page about setup."),
        (2, "Second page about billing."),
    ]


def test_unsupported_extension_is_rejected():
    with pytest.raises(UnsupportedFileError):
        load("tool.exe", b"MZ")


def test_corrupt_pdf_is_reported_as_unreadable():
    with pytest.raises(UnreadableFileError):
        load("broken.pdf", b"%PDF-1.4 this is not really a pdf")
