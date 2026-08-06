from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITES_CONFIG = PROJECT_ROOT / "sites.json"
DEFAULT_HISTORY_CACHE = PROJECT_ROOT / "recent_10_cache.json"
DEFAULT_OUTPUT_DIR = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\七类数据统一归纳")
DEFAULT_FAILURE_OUTPUT_DIR = Path(r"C:\Users\Administrator\Desktop\每天工具\爬虫合集\七类数据统一归纳失败")

DEFAULT_HTTP_WORKERS = 8
DEFAULT_BROWSER_WORKERS = 2
DEFAULT_DOCUMENT_WORKERS = 4
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_RETRY_TIMEOUT_SECONDS = 45
HISTORY_LIMIT = 10
REGION_WINDOW = 3
