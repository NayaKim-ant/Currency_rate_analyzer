from app.workers.run_jobs import run_requested


def main() -> None:
    run_requested("rates")


if __name__ == "__main__":
    main()
