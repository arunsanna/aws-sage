"""Composition with official AWS MCP servers."""

from aws_sage.composition.docs_proxy import AWSDocsProxy, DocSearchResult, get_docs_proxy
from aws_sage.composition.knowledge_proxy import (
    AWSKnowledgeProxy,
    KnowledgeCategory,
    KnowledgeItem,
    KnowledgeSource,
    LiveQueryResult,
    get_knowledge_proxy,
)

__all__ = [
    "AWSDocsProxy",
    "DocSearchResult",
    "get_docs_proxy",
    "AWSKnowledgeProxy",
    "KnowledgeCategory",
    "KnowledgeItem",
    "KnowledgeSource",
    "LiveQueryResult",
    "get_knowledge_proxy",
]
