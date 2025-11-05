from pathlib import Path


def test_extract_text_txt(make_txt):
    from document_processor.extractors.text_extractor import extract_text
    p = make_txt('a.txt', 'привет мир')
    out = extract_text(str(p))
    assert 'привет' in out and 'мир' in out


def test_extract_text_missing():
    from document_processor.extractors.text_extractor import extract_text
    out = extract_text('/non/existent/file.txt')
    assert out == ''
