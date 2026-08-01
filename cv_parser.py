"""
Extract raw text from uploaded resume files.
Supports TXT, PDF, and DOCX resumes when the required parser libraries are installed.
"""

import io


def _extract_pdf(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError(
            "Cannot read PDF because the 'pypdf' library is not installed. "
            "Install 'pypdf' or upload a TXT/DOCX resume instead."
        ) from exc

    reader = PdfReader(io.BytesIO(raw_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_docx(raw_bytes: bytes) -> str:
    try:
        import docx
    except ImportError as exc:
        raise ImportError(
            "Cannot read DOCX because the 'python-docx' library is not installed. "
            "Install 'python-docx' or upload a TXT/PDF resume instead."
        ) from exc

    doc = docx.Document(io.BytesIO(raw_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()


def extract_text_from_bytes(filename: str, raw_bytes: bytes) -> str:
    filename = filename.lower()
    if filename.endswith(".txt"):
        return raw_bytes.decode("utf-8", errors="ignore")
    if filename.endswith(".pdf"):
        return _extract_pdf(raw_bytes)
    if filename.endswith(".docx"):
        return _extract_docx(raw_bytes)

    raise ValueError(
        "Unsupported resume format. Please upload a TXT, PDF, or DOCX resume file."
    )


def extract_text_from_file(uploaded_file) -> str:
    """For Streamlit file uploader objects with .name and .read()."""
    return extract_text_from_bytes(uploaded_file.name, uploaded_file.read())


def extract_text_from_file(uploaded_file) -> str:
    """للاستخدام من Streamlit - uploaded_file كائن فيه .name و .read()"""
    return extract_text_from_bytes(uploaded_file.name, uploaded_file.read())
