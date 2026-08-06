from __future__ import annotations

from dataclasses import dataclass, field
import hashlib

from .enums import FailureCode, Region, ResultStatus, RunMode, SourceKind, WritePolicy


VALID_WUXING = frozenset({"金行", "木行", "水行", "火行", "土行"})


def sanitize_text(value: str) -> str:
    """Remove unpaired UTF-16 surrogates before hashing, matching, or writing text."""
    return value.encode("utf-8", errors="ignore").decode("utf-8")


@dataclass(frozen=True)
class SiteConfig:
    site_id: str
    name: str
    url: str
    region: Region
    rule_id: str
    parser_id: str = ""
    shared_source_id: str = ""
    api_url: str = ""
    click_first: bool = False
    enabled: bool = True
    config_version: int = 1

    def __post_init__(self) -> None:
        if not self.site_id.strip():
            raise ValueError("site_id 不能为空")
        if not self.name.strip():
            raise ValueError("站点名称不能为空")
        if not self.url.strip():
            raise ValueError("站点 URL 不能为空")
        if not self.rule_id.strip():
            raise ValueError("rule_id 不能为空")
        if not isinstance(self.region, Region):
            object.__setattr__(self, "region", Region.from_value(self.region))

    @property
    def pick(self) -> str:
        return self.region.value


@dataclass(frozen=True)
class ScrapeRequest:
    periods: tuple[int, ...]
    mode: RunMode = RunMode.SINGLE
    timeout_seconds: int = 20
    show_browser: bool = False
    write_policy: WritePolicy = WritePolicy.READ_ONLY

    def __post_init__(self) -> None:
        if not self.periods or any(period <= 0 for period in self.periods):
            raise ValueError("抓取期数必须是正整数")
        if self.timeout_seconds <= 0:
            raise ValueError("超时必须大于0秒")

    @property
    def period(self) -> int:
        if len(self.periods) != 1:
            raise ValueError("当前请求包含多个期数")
        return self.periods[0]


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    url: str
    source_kind: SourceKind
    text: str
    order: int
    parent_document_id: str | None = None
    record_id: str | None = None
    rendered: bool = False
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError("document_id 不能为空")
        if not isinstance(self.source_kind, SourceKind):
            object.__setattr__(self, "source_kind", SourceKind(self.source_kind))
        object.__setattr__(self, "text", sanitize_text(self.text))
        object.__setattr__(
            self,
            "metadata",
            tuple((sanitize_text(str(key)), sanitize_text(str(value))) for key, value in self.metadata),
        )

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def metadata_map(self) -> dict[str, str]:
        return dict(self.metadata)


@dataclass(frozen=True)
class Candidate:
    period: int
    wuxing: str
    source_document_id: str
    order: int
    raw: str
    rule_version: str
    record_id: str | None = None
    anchor: str = ""
    keyword: str = ""
    block_start: int | None = None
    block_end: int | None = None
    source_url: str = ""
    document_order: int = 0

    def __post_init__(self) -> None:
        if self.period <= 0:
            raise ValueError("候选期号必须大于0")
        if self.wuxing not in VALID_WUXING:
            raise ValueError(f"不是标准五行：{self.wuxing}")
        if not self.source_document_id:
            raise ValueError("候选必须绑定来源文档")
        if not self.rule_version:
            raise ValueError("候选必须记录解析规则版本")


@dataclass(frozen=True)
class ValidationEvidence:
    period_pass: bool = False
    position_pass: bool = False
    authority_pass: bool = False
    keyword_pass: bool = False
    wuxing_pass: bool = False
    conflict_pass: bool = False
    details: tuple[str, ...] = ()

    @property
    def all_pass(self) -> bool:
        return all((
            self.period_pass,
            self.position_pass,
            self.authority_pass,
            self.keyword_pass,
            self.wuxing_pass,
            self.conflict_pass,
        ))


@dataclass(frozen=True)
class ScrapeResult:
    site: SiteConfig
    period: int
    status: ResultStatus
    candidate: Candidate | None
    failure_code: FailureCode | None
    reason: str
    evidence: ValidationEvidence = field(default_factory=ValidationEvidence)
    documents: tuple[SourceDocument, ...] = ()
    elapsed_seconds: float = 0.0
    attempts: int = 1

    def __post_init__(self) -> None:
        if self.status is ResultStatus.SUCCESS:
            if self.candidate is None or self.failure_code is not None:
                raise ValueError("成功结果必须且只能携带候选")
            if self.candidate.period != self.period:
                raise ValueError("成功候选期号和请求期号不一致")
            if not self.evidence.all_pass:
                raise ValueError("成功结果必须携带完整校验回执")
        elif self.candidate is not None or self.failure_code is None:
            raise ValueError("失败结果不能携带候选且必须有失败代码")

    @classmethod
    def success(
        cls,
        site: SiteConfig,
        period: int,
        candidate: Candidate,
        elapsed_seconds: float,
        evidence: ValidationEvidence | None = None,
        documents: tuple[SourceDocument, ...] = (),
        attempts: int = 1,
    ) -> "ScrapeResult":
        return cls(
            site=site,
            period=period,
            status=ResultStatus.SUCCESS,
            candidate=candidate,
            failure_code=None,
            reason="",
            evidence=evidence or ValidationEvidence(),
            documents=documents,
            elapsed_seconds=elapsed_seconds,
            attempts=attempts,
        )

    @classmethod
    def failure(
        cls,
        site: SiteConfig,
        period: int,
        code: FailureCode,
        reason: str,
        elapsed_seconds: float,
        evidence: ValidationEvidence | None = None,
        documents: tuple[SourceDocument, ...] = (),
        attempts: int = 1,
    ) -> "ScrapeResult":
        return cls(
            site=site,
            period=period,
            status=ResultStatus.FAILURE,
            candidate=None,
            failure_code=code,
            reason=reason,
            evidence=evidence or ValidationEvidence(),
            documents=documents,
            elapsed_seconds=elapsed_seconds,
            attempts=attempts,
        )


@dataclass(frozen=True)
class BatchResult:
    results: tuple[ScrapeResult, ...]

    @property
    def successes(self) -> tuple[ScrapeResult, ...]:
        return tuple(result for result in self.results if result.status is ResultStatus.SUCCESS)

    @property
    def failures(self) -> tuple[ScrapeResult, ...]:
        return tuple(result for result in self.results if result.status is ResultStatus.FAILURE)
