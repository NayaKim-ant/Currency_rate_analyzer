from app.workers.run_jobs import run_requested


def main() -> None:
    run_requested("news_history")
    run_requested("news_recent")


if __name__ == "__main__":
    main()
