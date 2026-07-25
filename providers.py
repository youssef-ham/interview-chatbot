import os
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()


async def generate(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """
    بتاخد تعليمات (system_prompt) وسؤال (user_prompt)، وبترجع نص رد الموديل.
    """
    client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content