from reranker import rerank_documents


def main():
    query = "Python list comprehension and generators"
    docs = [
        "Explain the difference between a list comprehension and a generator in Python.",
        "Describe the main principles of object-oriented programming.",
        "What is the difference between SQL and NoSQL databases?",
    ]

    scores = rerank_documents(query, docs)
    print(list(zip(docs, scores)))
    print("Best doc:", docs[scores.index(max(scores))])


if __name__ == "__main__":
    main()
