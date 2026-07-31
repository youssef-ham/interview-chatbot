from retrieval import build_profile_text, build_query_text


def main():
    profile = {
        "skills": ["Python", "Data Structures"],
        "technologies": ["FastAPI", "SQLAlchemy"],
        "programming_languages": ["Python", "JavaScript"],
        "frameworks": ["FastAPI", "Streamlit"],
        "work_experience_years": 3,
        "projects": [
            {"name": "Interview Analyzer", "description": "A system to evaluate candidate answers."}
        ],
    }

    text = build_profile_text(profile)
    query = build_query_text("Python", profile, ["generator", "list comprehension"])

    print("Profile summary:\n", text)
    print("\nSearch query:\n", query)


if __name__ == "__main__":
    main()
