import argparse
import time

from app.db.session import SessionLocal
from app.services.job_runner import drain_jobs
from app.services.jobs import JOB_TYPES, enqueue_job


def run_requested(job_type: str) -> int:
    with SessionLocal() as session:
        job_id = enqueue_job(session, job_type, source="cli").id
    drain_jobs()
    print(f"Job {job_id}: inspect /api/v1/jobs/{job_id} for state and results")
    return job_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the persistent market pipeline worker")
    parser.add_argument("--once", action="store_true", help="Process currently ready jobs and exit")
    parser.add_argument("--job", choices=JOB_TYPES, help="Queue one job before processing")
    args = parser.parse_args()
    if args.job:
        with SessionLocal() as session:
            print(f"Queued job {enqueue_job(session, args.job, source='cli').id}")
    while True:
        drain_jobs()
        if args.once:
            return
        time.sleep(5)


if __name__ == "__main__":
    main()
