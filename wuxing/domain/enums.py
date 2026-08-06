from enum import Enum


class Region(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"

    @classmethod
    def from_value(cls, value: object) -> "Region":
        normalized = str(value).strip().lower()
        aliases = {
            "top": cls.TOP,
            "顶部": cls.TOP,
            "上": cls.TOP,
            "bottom": cls.BOTTOM,
            "尾部": cls.BOTTOM,
            "底部": cls.BOTTOM,
            "下": cls.BOTTOM,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise ValueError(f"方向必须是 top 或 bottom：{value}") from exc

    @property
    def label(self) -> str:
        return "顶部" if self is Region.TOP else "底部"


class SourceKind(str, Enum):
    PAGE = "page"
    SCRIPT = "script"
    IFRAME = "iframe"
    API = "api"
    SPA = "spa"
    BROWSER = "browser"
    OCR = "ocr"


class ResultStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class RunMode(str, Enum):
    SINGLE = "single"
    MULTI = "multi"
    DUPLICATE = "duplicate"
    VALIDATION = "validation"


class WritePolicy(str, Enum):
    READ_ONLY = "read_only"
    UPDATE_CACHE = "update_cache"


class FetchStrategy(str, Enum):
    HTTP = "http"
    HTTP_THEN_BROWSER = "http_then_browser"
    BROWSER_FIRST = "browser_first"
    ARTICLE_API = "article_api"
    SPA_API = "spa_api"
    CLICK_THROUGH = "click_through"


class FailureCode(str, Enum):
    CONFIG_ERROR = "CONFIG_ERROR"
    FETCH_TIMEOUT = "FETCH_TIMEOUT"
    TLS_ERROR = "TLS_ERROR"
    HTTP_ERROR = "HTTP_ERROR"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    ENTRY_NOT_FOUND = "ENTRY_NOT_FOUND"
    RECORD_ID_MISMATCH = "RECORD_ID_MISMATCH"
    AUTHORITY_NOT_UNIQUE = "AUTHORITY_NOT_UNIQUE"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    POSITION_WINDOW = "POSITION_WINDOW"
    KEYWORD_MISMATCH = "KEYWORD_MISMATCH"
    NON_STANDARD_WUXING = "NON_STANDARD_WUXING"
    TARGET_CONFLICT = "TARGET_CONFLICT"
    DUPLICATE_WUXING = "DUPLICATE_WUXING"
    OCR_UNVERIFIED = "OCR_UNVERIFIED"
    INVALID_RECORD_ID = "INVALID_RECORD_ID"
    API_RECORD_INVALID = "API_RECORD_INVALID"
    CACHE_ERROR = "CACHE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
