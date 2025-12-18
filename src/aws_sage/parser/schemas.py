"""Pydantic models for parsed AWS commands."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from aws_sage.config import OperationCategory


class ParsedIntent(BaseModel):
    """Result of intent classification."""

    intent_type: str = Field(..., description="Type of intent (list, describe, create, delete, etc.)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    raw_input: str = Field(..., description="Original user input")


class ParsedService(BaseModel):
    """Identified AWS service."""

    service_name: str = Field(..., description="Boto3 service name (e.g., 's3', 'ec2')")
    display_name: str = Field(..., description="Human-readable name")
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_keywords: list[str] = Field(default_factory=list)


class ParsedOperation(BaseModel):
    """Identified AWS operation."""

    operation_name: str = Field(..., description="Boto3 operation name (e.g., 'list_buckets')")
    category: OperationCategory = Field(..., description="Operation category")
    confidence: float = Field(..., ge=0.0, le=1.0)
    suggested_alternatives: list[str] = Field(default_factory=list)


class ParsedParameter(BaseModel):
    """A parsed parameter from user input."""

    name: str = Field(..., description="Parameter name")
    value: Any = Field(..., description="Parameter value")
    source: str = Field(default="inferred", description="How this was determined: 'explicit', 'inferred', 'default'")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class StructuredCommand(BaseModel):
    """Fully parsed and validated AWS command."""

    service: str = Field(..., description="AWS service name")
    operation: str = Field(..., description="Operation name")
    parameters: dict[str, Any] = Field(default_factory=dict)
    category: OperationCategory = Field(default=OperationCategory.READ)
    region: Optional[str] = Field(None, description="Target region")

    # Metadata
    raw_input: str = Field(default="", description="Original user input")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_pagination: bool = Field(default=False)
    supports_dry_run: bool = Field(default=False)

    # Validation results
    is_valid: bool = Field(default=True)
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)

    @field_validator("service", "operation")
    @classmethod
    def lowercase_names(cls, v: str) -> str:
        return v.lower()

    def to_boto3_call(self) -> dict[str, Any]:
        """Convert to boto3-compatible call parameters."""
        return {
            "service": self.service,
            "operation": self.operation,
            "parameters": self.parameters,
        }

    def get_operation_key(self) -> str:
        """Get the operation key for safety checks."""
        return f"{self.service}.{self.operation}"


class ParseResult(BaseModel):
    """Complete result of parsing user input."""

    success: bool = Field(..., description="Whether parsing succeeded")
    command: Optional[StructuredCommand] = Field(None, description="Parsed command if successful")
    error: Optional[str] = Field(None, description="Error message if parsing failed")
    suggestions: list[str] = Field(default_factory=list, description="Suggested corrections")

    # Parsing details
    intent: Optional[ParsedIntent] = None
    service: Optional[ParsedService] = None
    operation: Optional[ParsedOperation] = None
    parameters: list[ParsedParameter] = Field(default_factory=list)

    @classmethod
    def success_result(cls, command: StructuredCommand, **kwargs: Any) -> "ParseResult":
        """Create a successful parse result."""
        return cls(success=True, command=command, **kwargs)

    @classmethod
    def error_result(cls, error: str, suggestions: list[str] | None = None) -> "ParseResult":
        """Create a failed parse result."""
        return cls(success=False, error=error, suggestions=suggestions or [])


class ValidationResult(BaseModel):
    """Result of command validation."""

    valid: bool = Field(..., description="Whether the command is valid")
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Parameter validation
    missing_required: list[str] = Field(default_factory=list)
    unknown_parameters: list[str] = Field(default_factory=list)
    type_mismatches: list[str] = Field(default_factory=list)

    @classmethod
    def valid_result(cls, warnings: list[str] | None = None) -> "ValidationResult":
        """Create a valid result."""
        return cls(valid=True, warnings=warnings or [])

    @classmethod
    def invalid_result(cls, errors: list[str], warnings: list[str] | None = None) -> "ValidationResult":
        """Create an invalid result."""
        return cls(valid=False, errors=errors, warnings=warnings or [])
