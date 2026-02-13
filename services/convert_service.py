import os
import shutil
import subprocess
import sys

from utils.errors import ConversionError, ConversionTimeoutError
from utils.logging_utils import get_logger, log_exception
from utils.temp_utils import create_temp_work_dir

_LOGGER = get_logger("convert_service")


def get_libreoffice_cmd():
    if sys.platform.startswith("linux"):
        if shutil.which("soffice"):
            return "soffice"
        raise FileNotFoundError("LibreOffice (soffice) is not installed.")

    if os.name == "nt":
        windows_soffice = r"C:\Program Files\LibreOffice\program\soffice.exe"
        if os.path.exists(windows_soffice):
            return windows_soffice
        if shutil.which("soffice"):
            return "soffice"
        raise FileNotFoundError("LibreOffice (soffice.exe) is not installed.")

    if shutil.which("soffice"):
        return "soffice"

    raise FileNotFoundError("LibreOffice (soffice) is not installed.")


def convert_docx_to_pdf(input_path: str, output_dir: str) -> str:
    _LOGGER.info("convert_start input_path=%s", input_path)

    os.makedirs(output_dir, exist_ok=True)

    pdf_filename = f"{os.path.splitext(os.path.basename(input_path))[0]}.pdf"
    output_path = os.path.abspath(os.path.join(output_dir, pdf_filename))

    if os.path.exists(output_path):
        os.remove(output_path)

    try:
        soffice_cmd = get_libreoffice_cmd()
    except FileNotFoundError as e:
        app_err = ConversionError(detail=str(e), cause=e)
        log_exception("convert.libreoffice_not_found", app_err, _LOGGER)
        raise app_err from e

    cmd = [
        soffice_cmd,
        "--headless",
        "--convert-to",
        "pdf:writer_pdf_Export",
        input_path,
        "--outdir",
        output_dir,
    ]
    _LOGGER.info("convert_command cmd=%s", cmd)

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=60)
    except FileNotFoundError as e:
        app_err = ConversionError(detail="LibreOffice executable not found.", cause=e)
        log_exception("convert.libreoffice_not_found", app_err, _LOGGER)
        raise app_err from e
    except subprocess.TimeoutExpired as e:
        app_err = ConversionTimeoutError(detail="LibreOffice conversion timed out after 60 seconds.", cause=e)
        log_exception("convert.timeout", app_err, _LOGGER)
        raise app_err from e
    except subprocess.CalledProcessError as e:
        stderr_text = (e.stderr or b"").decode("utf-8", errors="ignore").strip()
        stdout_text = (e.stdout or b"").decode("utf-8", errors="ignore").strip()
        detail = stderr_text or stdout_text or f"Exit code: {e.returncode}"
        app_err = ConversionError(detail=f"LibreOffice conversion failed. {detail}", cause=e)
        log_exception("convert.libreoffice_failed", app_err, _LOGGER)
        raise app_err from e

    if not os.path.exists(output_path):
        app_err = ConversionError(detail=f"Converted PDF not found: {output_path}")
        log_exception("convert.output_missing", app_err, _LOGGER)
        raise app_err

    _LOGGER.info("convert_success output_path=%s", output_path)
    return output_path


try:
    get_libreoffice_cmd()
    DOCX2PDF_AVAILABLE = True
except Exception:
    DOCX2PDF_AVAILABLE = False


def convert_docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes | None:
    if not DOCX2PDF_AVAILABLE:
        return None

    temp_work = create_temp_work_dir(prefix="convert")
    input_path = temp_work.file_path("input.docx")

    try:
        try:
            with open(input_path, "wb") as f:
                f.write(docx_bytes)
        except Exception as e:
            app_err = ConversionError(detail="Failed to write temporary DOCX file.", cause=e)
            log_exception("convert.write_temp_docx", app_err, _LOGGER)
            raise app_err from e

        output_path = convert_docx_to_pdf(input_path, temp_work.path)

        try:
            with open(output_path, "rb") as f:
                return f.read()
        except Exception as e:
            app_err = ConversionError(detail="Failed to read converted PDF bytes.", cause=e)
            log_exception("convert.read_pdf", app_err, _LOGGER)
            raise app_err from e
    finally:
        temp_work.cleanup()
