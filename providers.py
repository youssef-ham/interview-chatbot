from groq import AsyncGroq

from config import get_setting

CLIENT: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    global CLIENT
    if CLIENT is None:
        api_key = get_setting("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("Missing GROQ_API_KEY environment variable")
        CLIENT = AsyncGroq(api_key=api_key)
    return CLIENT


async def generate(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """
    بتاخد تعليمات (system_prompt) وسؤال (user_prompt)، وبترجع نص رد الموديل.
    """
    client = get_groq_client()

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content
