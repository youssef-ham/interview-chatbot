"""
Extract raw text from uploaded resume files.
The app currently supports only TXT resumes reliably. PDF and DOCX uploads are rejected unless
supporting libraries are installed, but the deployable default flow uses TXT only.
"""

import io


def extract_text_from_bytes(filename: str, raw_bytes: bytes) -> str:
    filename = filename.lower()
    if filename.endswith(".txt"):
        return raw_bytes.decode("utf-8", errors="ignore")

    raise ValueError(
        "Unsupported resume format. Please upload a TXT resume file."
    )


def extract_text_from_file(uploaded_file) -> str:
    """For Streamlit file uploader objects with .name and .read()."""
    return extract_text_from_bytes(uploaded_file.name, uploaded_file.read())


def extract_text_from_file(uploaded_file) -> str:
    """للاستخدام من Streamlit - uploaded_file كائن فيه .name و .read()"""
    return extract_text_from_bytes(uploaded_file.name, uploaded_file.read())
