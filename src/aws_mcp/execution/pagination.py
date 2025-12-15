"""Pagination handling for AWS API calls."""

from __future__ import annotations

from typing import Any, AsyncIterator

import structlog

from aws_mcp.config import get_config

logger = structlog.get_logger()


class PaginationHandler:
    """Handles AWS API pagination automatically."""

    def __init__(
        self,
        max_pages: int | None = None,
        max_items: int | None = None,
    ) -> None:
        """Initialize the pagination handler."""
        config = get_config()
        self.max_pages = max_pages or config.pagination_max_pages
        self.max_items = max_items or config.pagination_max_items

    def execute_paginated(
        self,
        client: Any,
        operation: str,
        parameters: dict[str, Any] | None = None,
        result_key: str | None = None,
    ) -> tuple[list[Any], bool]:
        """
        Execute an operation with automatic pagination.

        Args:
            client: boto3 client
            operation: Operation name
            parameters: Operation parameters
            result_key: Key in response containing results (auto-detected if not provided)

        Returns:
            Tuple of (results list, was_truncated)
        """
        parameters = parameters or {}

        # Check if operation supports pagination
        if self._supports_pagination(client, operation):
            return self._paginate(client, operation, parameters, result_key)
        else:
            return self._single_call(client, operation, parameters, result_key)

    def _supports_pagination(self, client: Any, operation: str) -> bool:
        """Check if an operation supports pagination."""
        try:
            client.get_paginator(operation)
            return True
        except Exception:
            return False

    def _paginate(
        self,
        client: Any,
        operation: str,
        parameters: dict[str, Any],
        result_key: str | None,
    ) -> tuple[list[Any], bool]:
        """Execute with pagination."""
        results: list[Any] = []
        truncated = False
        item_count = 0

        try:
            paginator = client.get_paginator(operation)

            for page_num, page in enumerate(paginator.paginate(**parameters)):
                if page_num >= self.max_pages:
                    truncated = True
                    logger.info(
                        "pagination_truncated",
                        reason="max_pages",
                        operation=operation,
                        pages=page_num,
                    )
                    break

                # Extract results from page
                page_results = self._extract_results(page, result_key)
                results.extend(page_results)
                item_count += len(page_results)

                if item_count >= self.max_items:
                    truncated = True
                    results = results[: self.max_items]
                    logger.info(
                        "pagination_truncated",
                        reason="max_items",
                        operation=operation,
                        items=item_count,
                    )
                    break

            logger.debug(
                "pagination_complete",
                operation=operation,
                total_items=len(results),
                truncated=truncated,
            )

            return results, truncated

        except Exception as e:
            logger.warning(
                "pagination_failed",
                operation=operation,
                error=str(e),
            )
            # Fall back to single call
            return self._single_call(client, operation, parameters, result_key)

    def _single_call(
        self,
        client: Any,
        operation: str,
        parameters: dict[str, Any],
        result_key: str | None,
    ) -> tuple[list[Any], bool]:
        """Execute a single API call without pagination."""
        method = getattr(client, operation)
        response = method(**parameters)
        results = self._extract_results(response, result_key)
        return results, False

    def _extract_results(
        self,
        response: dict[str, Any],
        result_key: str | None,
    ) -> list[Any]:
        """Extract the results list from an API response."""
        # Remove metadata
        if "ResponseMetadata" in response:
            response = {k: v for k, v in response.items() if k != "ResponseMetadata"}

        # If result_key specified, use it
        if result_key and result_key in response:
            value = response[result_key]
            return value if isinstance(value, list) else [value]

        # Auto-detect: find the first list in the response
        for key, value in response.items():
            if isinstance(value, list):
                return value

        # If no list found, return the whole response as a single item
        return [response] if response else []


class AsyncPaginationHandler:
    """Async version of pagination handler."""

    def __init__(
        self,
        max_pages: int | None = None,
        max_items: int | None = None,
    ) -> None:
        """Initialize the async pagination handler."""
        config = get_config()
        self.max_pages = max_pages or config.pagination_max_pages
        self.max_items = max_items or config.pagination_max_items

    async def execute_paginated(
        self,
        client: Any,
        operation: str,
        parameters: dict[str, Any] | None = None,
        result_key: str | None = None,
    ) -> tuple[list[Any], bool]:
        """
        Execute an operation with automatic pagination (async).

        This wraps the sync pagination in an async context.
        For true async, use aioboto3.
        """
        import asyncio

        handler = PaginationHandler(self.max_pages, self.max_items)
        return await asyncio.to_thread(
            handler.execute_paginated,
            client,
            operation,
            parameters,
            result_key,
        )

    async def stream_paginated(
        self,
        client: Any,
        operation: str,
        parameters: dict[str, Any] | None = None,
        result_key: str | None = None,
    ) -> AsyncIterator[Any]:
        """
        Stream results from a paginated operation.

        Yields items one at a time, useful for processing large result sets.
        """
        parameters = parameters or {}
        item_count = 0

        try:
            paginator = client.get_paginator(operation)

            for page_num, page in enumerate(paginator.paginate(**parameters)):
                if page_num >= self.max_pages:
                    break

                results = self._extract_results(page, result_key)
                for item in results:
                    if item_count >= self.max_items:
                        return
                    yield item
                    item_count += 1

        except Exception:
            # Fall back to single call
            method = getattr(client, operation)
            response = method(**parameters)
            results = self._extract_results(response, result_key)
            for item in results:
                if item_count >= self.max_items:
                    return
                yield item
                item_count += 1

    def _extract_results(
        self,
        response: dict[str, Any],
        result_key: str | None,
    ) -> list[Any]:
        """Extract results from response."""
        if "ResponseMetadata" in response:
            response = {k: v for k, v in response.items() if k != "ResponseMetadata"}

        if result_key and result_key in response:
            value = response[result_key]
            return value if isinstance(value, list) else [value]

        for key, value in response.items():
            if isinstance(value, list):
                return value

        return [response] if response else []


# Convenience function
def paginate(
    client: Any,
    operation: str,
    parameters: dict[str, Any] | None = None,
    result_key: str | None = None,
    max_pages: int | None = None,
    max_items: int | None = None,
) -> tuple[list[Any], bool]:
    """
    Convenience function for paginated execution.

    Args:
        client: boto3 client
        operation: Operation name
        parameters: Operation parameters
        result_key: Key in response containing results
        max_pages: Maximum pages to fetch
        max_items: Maximum items to return

    Returns:
        Tuple of (results, was_truncated)
    """
    handler = PaginationHandler(max_pages, max_items)
    return handler.execute_paginated(client, operation, parameters, result_key)
