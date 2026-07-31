import asyncio

from ai_service import generate_question


async def main():
    question = await generate_question(topic="Python", difficulty="mid")
    print(question)


asyncio.run(main())
