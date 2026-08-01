import os

from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st
except Exception:  # pragma: no cover - streamlit is optional in non-UI contexts
    st = None


def get_setting(key: str, default=None):
    """Read settings from Streamlit secrets first, then environment variables."""
    if st is not None:
        try:
            secrets = getattr(st, "secrets", None)
            if secrets is not None:
                if hasattr(secrets, "get"):
                    value = secrets.get(key)
                    if value not in (None, ""):
                        return value
                elif isinstance(secrets, dict):
                    value = secrets.get(key)
                    if value not in (None, ""):
                        return value
                else:
                    try:
                        value = secrets[key]
                        if value not in (None, ""):
                            return value
                    except Exception:
                        pass
        except Exception:
            pass

    value = os.getenv(key)
    if value not in (None, ""):
        return value
    return default
