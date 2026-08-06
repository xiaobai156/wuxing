class WuxingError(RuntimeError):
    """Base error for expected domain and infrastructure failures."""


class ConfigError(WuxingError):
    pass


class CacheError(WuxingError):
    pass


class CacheConflictError(CacheError):
    pass


class FetchError(WuxingError):
    pass


class ParseError(WuxingError):
    pass


class ValidationError(WuxingError):
    pass

