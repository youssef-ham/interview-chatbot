import asyncio
from ai_service import generate_report

async def main():
    fake_answers = [
        {"question": "What is a list?", "score": 8, "missing_points": []},
        {"question": "What is the GIL?", "score": 4, "missing_points": ["multiprocessing alternative"]},
    ]
    result = await generate_report(fake_answers)
    print(result)

asyncio.run(main())