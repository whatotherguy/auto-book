import fitz

from app.services.manuscript import extract_text_from_manuscript_file


def build_sample_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 80), "CHAPTER 57", fontsize=24)
    page.insert_text((72, 130), "LICKING WOUNDS", fontsize=32)
    page.insert_text((72, 220), "T", fontsize=42)
    page.insert_text((102, 224), "ears streamed down Lynette's face.", fontsize=16)

    return document.tobytes()


def test_extract_text_from_pdf_merges_drop_cap():
    text, metadata = extract_text_from_manuscript_file("chapter57.pdf", build_sample_pdf())

    assert metadata["type"] == "pdf"
    assert metadata["pages"] == 1
    assert "CHAPTER 57" in text
    assert "LICKING WOUNDS" in text
    assert "Tears streamed down Lynette's face." in text


def test_extract_text_from_txt():
    text, metadata = extract_text_from_manuscript_file("chapter.txt", b"Hello world")

    assert text == "Hello world"
    assert metadata["type"] == "txt"
