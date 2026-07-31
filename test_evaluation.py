import asyncio

from ai_service import evaluate_answer


async def main():
    result = await evaluate_answer(
        question="What is the difference between a list and a tuple?",
        expected_points=["list is mutable", "tuple is immutable", "performance difference"],
        user_answer="list ممكن تتعدل بعد ما تتعمل، لكن tuple لأ",
    )
    print(result)


asyncio.run(main())
