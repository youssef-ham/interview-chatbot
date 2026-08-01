"""
استخراج نص خام من ملف الـ CV (PDF أو DOCX أو TXT).
فيه دالتين: واحدة لـ Streamlit (بتاخد كائن فيه .name و .read())،
وواحدة للـ API (بتاخد اسم الملف والبايتس مباشرة) - الاتنين بيستخدموا نفس منطق الاستخراج.
"""

import io


def _extract_pdf(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError(
            "لا يمكن قراءة ملف PDF لأن مكتبة pypdf غير مثبتة. "
            "ثبت pypdf أو ارفع ملف TXT بدلاً من PDF."
        ) from exc

    reader = PdfReader(io.BytesIO(raw_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_docx(raw_bytes: bytes) -> str:
    try:
        import docx
    except ImportError as exc:
        raise ImportError(
            "لا يمكن قراءة ملف DOCX لأن مكتبة python-docx غير مثبتة. "
            "ثبت python-docx أو ارفع ملف TXT بدلاً من DOCX."
        ) from exc

    doc = docx.Document(io.BytesIO(raw_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()


def extract_text_from_bytes(filename: str, raw_bytes: bytes) -> str:
    filename = filename.lower()
    if filename.endswith(".pdf"):
        return _extract_pdf(raw_bytes)
    elif filename.endswith(".docx"):
        return _extract_docx(raw_bytes)
    elif filename.endswith(".txt"):
        return raw_bytes.decode("utf-8", errors="ignore")
    else:
        raise ValueError(f"صيغة ملف غير مدعومة: {filename}")


def extract_text_from_file(uploaded_file) -> str:
    """للاستخدام من Streamlit - uploaded_file كائن فيه .name و .read()"""
    return extract_text_from_bytes(uploaded_file.name, uploaded_file.read())
