from __future__ import annotations

from dataclasses import dataclass
import json
import re

from wuxing.domain.models import Candidate, SourceDocument


@dataclass(frozen=True)
class AuthorityDecision:
    passed: bool
    reason: str
    source_document_id: str | None
    record_id: str | None


def validate_authority_boundary(
    documents: tuple[SourceDocument, ...] | list[SourceDocument],
    candidate: Candidate,
) -> AuthorityDecision:
    matching = [document for document in documents if document.document_id == candidate.source_document_id]
    if len(matching) != 1:
        return AuthorityDecision(
            passed=False,
            reason=f"候选来源文档不在唯一权威文档集合中：{candidate.source_document_id}",
            source_document_id=candidate.source_document_id,
            record_id=candidate.record_id,
        )
    document = matching[0]
    if candidate.source_url and document.url != candidate.source_url:
        return AuthorityDecision(
            passed=False,
            reason=(
                f"候选来源URL与文档不一致：候选={candidate.source_url} 文档={document.url}"
            ),
            source_document_id=document.document_id,
            record_id=document.record_id,
        )
    if (candidate.record_id or document.record_id) and document.record_id != candidate.record_id:
        return AuthorityDecision(
            passed=False,
            reason=(
                f"候选记录ID与来源文档不一致：候选={candidate.record_id} "
                f"文档={document.record_id or '缺失'}"
            ),
            source_document_id=document.document_id,
            record_id=document.record_id,
        )
    metadata = document.metadata_map
    if metadata.get("logical_block") == "explicit":
        try:
            components = json.loads(metadata.get("component_match_texts", "[]"))
        except json.JSONDecodeError:
            components = []
        candidate_text = re.sub(r"\s+", "", candidate.raw)
        component_matches = [
            component for component in components
            if isinstance(component, str) and candidate_text and candidate_text in component
        ]
        if len(component_matches) != 1:
            return AuthorityDecision(
                passed=False,
                reason="候选跨逻辑组件或无法回查到唯一原始文档块",
                source_document_id=document.document_id,
                record_id=document.record_id,
            )
    return AuthorityDecision(
        passed=True,
        reason="候选属于已选权威文档，记录边界一致",
        source_document_id=document.document_id,
        record_id=document.record_id,
    )
