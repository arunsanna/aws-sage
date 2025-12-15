"""Composition with official AWS MCP servers."""

from aws_mcp.composition.docs_proxy import AWSDocsProxy, DocSearchResult, get_docs_proxy
from aws_mcp.composition.knowledge_proxy import (
    AWSKnowledgeProxy,
    KnowledgeCategory,
    KnowledgeItem,
    get_knowledge_proxy,
)

__all__ = [
    "AWSDocsProxy",
    "DocSearchResult",
    "get_docs_proxy",
    "AWSKnowledgeProxy",
    "KnowledgeCategory",
    "KnowledgeItem",
    "get_knowledge_proxy",
]
