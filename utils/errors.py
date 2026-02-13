class AppError(Exception):
    default_code = "APP_ERROR"
    default_message = "Application error."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        detail: str | None = None,
        cause: Exception | None = None,
    ):
        self.code = code or self.default_code
        self.message = message or self.default_message
        self.detail = detail
        self.cause = cause
        super().__init__(self.message)


class ConversionError(AppError):
    default_code = "CONVERSION_ERROR"
    default_message = "Word to PDF conversion failed."


class ConversionTimeoutError(AppError):
    default_code = "CONVERSION_TIMEOUT"
    default_message = "Word to PDF conversion timed out."


class ParseError(AppError):
    default_code = "PARSE_ERROR"
    default_message = "Failed to parse the document."


class ReferenceSectionNotFoundError(AppError):
    default_code = "REFERENCE_SECTION_NOT_FOUND"
    default_message = "Reference section heading was not found."


class PreviewError(AppError):
    default_code = "PREVIEW_ERROR"
    default_message = "Failed to render preview."
