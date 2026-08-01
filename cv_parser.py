"""
Extract raw text from uploaded resume files.
Supports TXT, PDF, and DOCX resumes when the required parser libraries are installed.
"""

import io


def _extract_pdf(raw_bytes: bytes) -> str:
    """Try best-effort PDF extraction.

    Preferred: use pypdf.PdfReader when available for reliable text extraction.
    Fallback: if pypdf is not installed, scan raw bytes for long printable runs
    and return them as a last-resort plain-text extraction so the app still works
    on environments where installing pypdf is not possible.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        # Best-effort fallback: grab long runs of printable characters from the
        # PDF bytes. This is imperfect but allows the app to continue on hosts
        # where pypdf isn't installed (e.g., a restrictive Streamlit Cloud build
        # cache). Prefer installing pypdf for robust extraction.
        import re

        # Find sequences of printable characters. Minimum length tuned to 30 to
        # avoid noise from PDF internals.
        printable_runs = re.findall(rb"[\x20-\x7E\x0A\x0D]{30,}", raw_bytes)
        # Decode runs with best-effort UTF-8, fallback to latin-1 to avoid
        # raising on binary contents.
        decoded = []
        for r in printable_runs:
            try:
                decoded.append(r.decode("utf-8", errors="ignore"))
            except Exception:
                try:
                    decoded.append(r.decode("latin-1", errors="ignore"))
                except Exception:
                    pass
        # Join runs with two newlines to approximate paragraph breaks.
        text = "\n\n".join(line.strip() for line in decoded if line.strip())
        if text:
            return text
        # If fallback found nothing, raise ImportError to trigger user-facing guidance.
        raise ImportError(
            "Cannot read PDF because the 'pypdf' library is not installed and a fallback extraction found no readable text. "
            "Install 'pypdf' or upload a TXT/DOCX resume instead."
        )

    # If pypdf is available, use it (more reliable)
    reader = PdfReader(io.BytesIO(raw_bytes))
    texts = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            # continue on per-page errors
            continue
    return "\n".join(texts).strip()


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


def _detect_format(filename: str, raw_bytes: bytes) -> str:
    filename = (filename or "").lower()
    if filename.endswith(".txt"):
        return "txt"
    if filename.endswith(".pdf"):
        return "pdf"
    if filename.endswith(".docx"):
        return "docx"

    if raw_bytes.startswith(b"%PDF"):
        return "pdf"
    if raw_bytes.startswith(b"PK\x03\x04"):
        return "docx"

    try:
        raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    return "txt"


def extract_text_from_bytes(filename: str, raw_bytes: bytes) -> str:
    file_format = _detect_format(filename, raw_bytes)
    if file_format == "txt":
        return raw_bytes.decode("utf-8", errors="ignore")
    if file_format == "pdf":
        return _extract_pdf(raw_bytes)
    if file_format == "docx":
        return _extract_docx(raw_bytes)

    raise ValueError(
        "Unsupported resume format. Please upload a valid TXT, PDF, or DOCX resume file."
    )


def extract_text_from_file(uploaded_file) -> str:
    """For Streamlit file uploader objects with .name, .type, and .read()."""
    raw_bytes = uploaded_file.read()
    content_type = (getattr(uploaded_file, "type", "") or "").lower()

    if "pdf" in content_type:
        return _extract_pdf(raw_bytes)
    if "docx" in content_type or "officedocument" in content_type or "msword" in content_type:
        return _extract_docx(raw_bytes)
    if "text/plain" in content_type:
        return raw_bytes.decode("utf-8", errors="ignore")

    return extract_text_from_bytes(uploaded_file.name, raw_bytes)
