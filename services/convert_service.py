import os
import sys
import threading

from utils.errors import ConversionError, ConversionTimeoutError
from utils.logging_utils import get_logger, log_exception
from utils.temp_utils import create_temp_work_dir

try:
    from docx2pdf import convert as convert_docx
    DOCX2PDF_AVAILABLE = True
except ImportError:
    DOCX2PDF_AVAILABLE = False

_LOGGER = get_logger("convert_service")


def _cleanup_when_thread_finishes(worker_thread: threading.Thread, temp_work):
    try:
        worker_thread.join()
    finally:
        temp_work.cleanup()


def convert_docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes | None:
    if not DOCX2PDF_AVAILABLE:
        return None

    try:
        import pythoncom
    except ImportError:
        return None

    temp_work = create_temp_work_dir(prefix="convert")
    input_path = temp_work.file_path("input.docx")
    output_path = temp_work.file_path("output.pdf")
    timed_out = False

    try:
        try:
            with open(input_path, "wb") as f:
                f.write(docx_bytes)
        except Exception as e:
            app_err = ConversionError(detail="Failed to write temporary DOCX file.", cause=e)
            log_exception("convert.write_temp_docx", app_err, _LOGGER)
            raise app_err from e

        conversion_result = {"success": False, "error": None}

        def _worker():
            original_stdout = sys.stdout
            original_stderr = sys.stderr
            null_stdout = None
            null_stderr = None
            try:
                null_stdout = open(os.devnull, "w")
                null_stderr = open(os.devnull, "w")
                sys.stdout = null_stdout
                sys.stderr = null_stderr
                pythoncom.CoInitialize()
                convert_docx(input_path, output_path)
                if os.path.exists(output_path):
                    conversion_result["success"] = True
            except Exception as e:
                conversion_result["error"] = str(e)
            finally:
                sys.stdout = original_stdout
                sys.stderr = original_stderr
                if null_stdout is not None:
                    null_stdout.close()
                if null_stderr is not None:
                    null_stderr.close()
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=60)

        if t.is_alive():
            timed_out = True
            cleanup_thread = threading.Thread(
                target=_cleanup_when_thread_finishes,
                args=(t, temp_work),
                daemon=True,
            )
            cleanup_thread.start()
            app_err = ConversionTimeoutError(detail="docx2pdf conversion timed out after 60 seconds.")
            log_exception("convert.timeout", app_err, _LOGGER)
            raise app_err

        result_bytes = None
        if conversion_result["success"]:
            try:
                with open(output_path, "rb") as f:
                    result_bytes = f.read()
            except Exception as e:
                app_err = ConversionError(detail="Failed to read converted PDF bytes.", cause=e)
                log_exception("convert.read_pdf", app_err, _LOGGER)
                raise app_err from e
            return result_bytes
        app_err = ConversionError(detail=conversion_result["error"] or "docx2pdf did not produce output.")
        log_exception("convert.docx2pdf_failed", app_err, _LOGGER)
        raise app_err
    finally:
        if not timed_out:
            temp_work.cleanup()
