import csv
from pathlib import Path

LOG_FILE = Path("./data/rerank_feedback.csv")


def main():
    if not LOG_FILE.exists():
        print("No rerank feedback log found.")
        return

    with LOG_FILE.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            print(row)


if __name__ == "__main__":
    main()
