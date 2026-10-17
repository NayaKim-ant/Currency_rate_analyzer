from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.jobs import AnalysisJob, JobTransition
from app.schemas.jobs import JobCreate, JobDetail, JobRead
from app.services.jobs import JobConflict, enqueue_job, retry_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/collection", response_model=JobRead, status_code=202)
def request_job(payload: JobCreate, db: Session = Depends(get_db)) -> AnalysisJob:
    return enqueue_job(db, payload.job_type)


@router.get("", response_model=list[JobRead])
def list_jobs(limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)) -> list[AnalysisJob]:
    return list(db.scalars(select(AnalysisJob).order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc()).limit(limit)))


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobDetail:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    history = list(db.scalars(select(JobTransition).where(JobTransition.job_id == job_id).order_by(JobTransition.id)))
    return JobDetail(**JobRead.model_validate(job).model_dump(), history=history)


@router.post("/{job_id}/retry", response_model=JobRead, status_code=202)
def request_retry(job_id: int, db: Session = Depends(get_db)) -> AnalysisJob:
    try:
        return retry_job(db, job_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except JobConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
