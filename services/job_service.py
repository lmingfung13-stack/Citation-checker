import hashlib
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass

from services.convert_service import convert_docx_bytes_to_pdf_bytes
from utils.errors import AppError
from utils.logging_utils import get_logger, log_exception

JOB_STATUS_QUEUED = "QUEUED"
JOB_STATUS_RUNNING = "RUNNING"
JOB_STATUS_DONE = "DONE"
JOB_STATUS_FAILED = "FAILED"
JOB_STATUS_CANCELED = "CANCELED"

_JOB_CAP = 5
_LOGGER = get_logger("job_service")


@dataclass
class Job:
    job_id: str
    status: str
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    result_bytes: bytes | None = None
    cancel_requested: bool = False
    _docx_bytes: bytes | None = None
    _content_hash: str | None = None


_jobs: dict[str, Job] = {}
_queue = deque()
_done_by_hash: dict[str, str] = {}
_latest_by_hash: dict[str, str] = {}
_worker_thread: threading.Thread | None = None
_lock = threading.Lock()
_cv = threading.Condition(_lock)


def _clone_job(job: Job) -> Job:
    return Job(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        result_bytes=job.result_bytes,
        cancel_requested=job.cancel_requested,
    )


def _refresh_latest_for_hash_locked(content_hash: str):
    candidates = [j for j in _jobs.values() if j._content_hash == content_hash]
    if not candidates:
        _latest_by_hash.pop(content_hash, None)
        _done_by_hash.pop(content_hash, None)
        return
    latest = max(candidates, key=lambda j: j.created_at)
    _latest_by_hash[content_hash] = latest.job_id
    if latest.status == JOB_STATUS_DONE:
        _done_by_hash[content_hash] = latest.job_id
    elif _done_by_hash.get(content_hash) == latest.job_id:
        _done_by_hash.pop(content_hash, None)


def _drop_job_locked(job_id: str):
    job = _jobs.pop(job_id, None)
    if job is None:
        return
    while job_id in _queue:
        _queue.remove(job_id)
    job.result_bytes = None
    job._docx_bytes = None
    if job._content_hash:
        _refresh_latest_for_hash_locked(job._content_hash)


def _prune_jobs_locked():
    while len(_jobs) > _JOB_CAP:
        candidates = [j for j in _jobs.values() if j.status != JOB_STATUS_RUNNING]
        if not candidates:
            return
        oldest = min(candidates, key=lambda j: j.created_at)
        _LOGGER.info(
            "job_prune job_id=%s status=%s created_at=%.3f",
            oldest.job_id,
            oldest.status,
            oldest.created_at,
        )
        _drop_job_locked(oldest.job_id)


def _ensure_worker_started_locked():
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="docx-pdf-job-worker")
    _worker_thread.start()
    _LOGGER.info("worker_started thread=%s", _worker_thread.name)


def submit_docx_to_pdf_job(docx_bytes: bytes) -> str:
    content_hash = hashlib.sha256(docx_bytes).hexdigest()
    now = time.time()
    with _cv:
        existing_done_id = _done_by_hash.get(content_hash)
        if existing_done_id:
            existing_done = _jobs.get(existing_done_id)
            if existing_done and existing_done.status == JOB_STATUS_DONE:
                _LOGGER.info("job_reuse_done job_id=%s hash=%s", existing_done_id, content_hash)
                return existing_done_id
            _done_by_hash.pop(content_hash, None)

        job_id = uuid.uuid4().hex
        job = Job(
            job_id=job_id,
            status=JOB_STATUS_QUEUED,
            created_at=now,
            _docx_bytes=docx_bytes,
            _content_hash=content_hash,
        )
        _jobs[job_id] = job
        _latest_by_hash[content_hash] = job_id
        _queue.append(job_id)
        _ensure_worker_started_locked()
        _prune_jobs_locked()
        _cv.notify()
        _LOGGER.info("job_submitted job_id=%s status=%s hash=%s", job_id, JOB_STATUS_QUEUED, content_hash)
        return job_id


def get_job(job_id: str) -> Job | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return _clone_job(job)


def list_jobs(limit: int = 10) -> list[Job]:
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [_clone_job(j) for j in jobs[: max(1, limit)]]


def get_latest_job_for_hash(file_hash: str) -> Job | None:
    with _lock:
        job_id = _latest_by_hash.get(file_hash)
        if not job_id:
            return None
        job = _jobs.get(job_id)
        if job is None:
            _latest_by_hash.pop(file_hash, None)
            return None
        return _clone_job(job)


def cancel_job(job_id: str) -> bool:
    with _cv:
        job = _jobs.get(job_id)
        if job is None:
            return False

        if job.status == JOB_STATUS_QUEUED:
            while job_id in _queue:
                _queue.remove(job_id)
            job.status = JOB_STATUS_CANCELED
            job.error = "Canceled by user."
            job.finished_at = time.time()
            job._docx_bytes = None
            job.result_bytes = None
            if job._content_hash:
                _refresh_latest_for_hash_locked(job._content_hash)
            _prune_jobs_locked()
            _LOGGER.info("job_canceled job_id=%s from=QUEUED", job_id)
            return True

        if job.status == JOB_STATUS_RUNNING:
            job.cancel_requested = True
            _LOGGER.info("job_cancel_requested job_id=%s status=RUNNING", job_id)
            return True

        return False


def _worker_loop():
    while True:
        with _cv:
            while not _queue:
                _cv.wait()
            job_id = _queue.popleft()
            job = _jobs.get(job_id)
            if job is None or job.status != JOB_STATUS_QUEUED:
                continue
            job.status = JOB_STATUS_RUNNING
            job.started_at = time.time()
            payload = job._docx_bytes
            _LOGGER.info("job_started job_id=%s", job_id)

        try:
            pdf_bytes = convert_docx_bytes_to_pdf_bytes(payload or b"")
            with _cv:
                job = _jobs.get(job_id)
                if job is None:
                    continue
                now = time.time()
                elapsed = (now - job.started_at) if job.started_at else 0.0
                if job.cancel_requested:
                    job.status = JOB_STATUS_CANCELED
                    job.error = "Canceled by user."
                    job.result_bytes = None
                    job.finished_at = now
                    job._docx_bytes = None
                    if job._content_hash:
                        _refresh_latest_for_hash_locked(job._content_hash)
                    _LOGGER.info("job_canceled job_id=%s from=RUNNING elapsed=%.3fs", job_id, elapsed)
                elif pdf_bytes:
                    job.status = JOB_STATUS_DONE
                    job.error = None
                    job.result_bytes = pdf_bytes
                    job.finished_at = now
                    job._docx_bytes = None
                    if job._content_hash:
                        _done_by_hash[job._content_hash] = job_id
                        _latest_by_hash[job._content_hash] = job_id
                    _LOGGER.info("job_done job_id=%s elapsed=%.3fs bytes=%s", job_id, elapsed, len(pdf_bytes))
                else:
                    job.status = JOB_STATUS_FAILED
                    job.error = "Conversion failed."
                    job.result_bytes = None
                    job.finished_at = now
                    job._docx_bytes = None
                    if job._content_hash:
                        _refresh_latest_for_hash_locked(job._content_hash)
                    _LOGGER.info("job_failed job_id=%s elapsed=%.3fs error=%s", job_id, elapsed, job.error)
                _prune_jobs_locked()
        except AppError as e:
            log_exception("job.convert.app_error", e, _LOGGER)
            with _cv:
                job = _jobs.get(job_id)
                if job is None:
                    continue
                now = time.time()
                elapsed = (now - job.started_at) if job.started_at else 0.0
                if job.cancel_requested:
                    job.status = JOB_STATUS_CANCELED
                    job.error = "Canceled by user."
                else:
                    job.status = JOB_STATUS_FAILED
                    job.error = e.message
                job.finished_at = now
                job.result_bytes = None
                job._docx_bytes = None
                if job._content_hash:
                    _refresh_latest_for_hash_locked(job._content_hash)
                _LOGGER.info("job_failed job_id=%s elapsed=%.3fs error=%s", job_id, elapsed, job.error)
                _prune_jobs_locked()
        except Exception as e:
            log_exception("job.convert.unexpected_error", e, _LOGGER)
            with _cv:
                job = _jobs.get(job_id)
                if job is None:
                    continue
                now = time.time()
                elapsed = (now - job.started_at) if job.started_at else 0.0
                if job.cancel_requested:
                    job.status = JOB_STATUS_CANCELED
                    job.error = "Canceled by user."
                else:
                    job.status = JOB_STATUS_FAILED
                    job.error = str(e)
                job.finished_at = now
                job.result_bytes = None
                job._docx_bytes = None
                if job._content_hash:
                    _refresh_latest_for_hash_locked(job._content_hash)
                _LOGGER.info("job_failed job_id=%s elapsed=%.3fs error=%s", job_id, elapsed, job.error)
                _prune_jobs_locked()
