"""Tests for cost analyzer module."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from aws_sage.differentiators.cost import (
    CostAnalyzer,
    CostAnalysisResult,
    IdleResource,
    IdleReason,
    RightSizeRecommendation,
    RightSizeAction,
    CostBreakdown,
    CostBreakdownItem,
    CostProjection,
    ResourceProjection,
    CostTrend,
    get_cost_analyzer,
    reset_cost_analyzer,
)


class TestIdleResource:
    """Tests for IdleResource dataclass."""

    def test_to_dict(self):
        """Test IdleResource.to_dict() conversion."""
        resource = IdleResource(
            arn="arn:aws:ec2:us-east-1:123456789:instance/i-123",
            service="ec2",
            resource_type="instance",
            name="test-instance",
            region="us-east-1",
            reason=IdleReason.LOW_CPU,
            metrics={"avg_cpu_percent": 2.5},
            estimated_monthly_cost=50.0,
            confidence=0.8,
        )

        result = resource.to_dict()

        assert result["arn"] == "arn:aws:ec2:us-east-1:123456789:instance/i-123"
        assert result["service"] == "ec2"
        assert result["reason"] == "low_cpu_utilization"
        assert result["estimated_monthly_cost"] == 50.0
        assert result["confidence"] == 0.8
        assert result["metrics"]["avg_cpu_percent"] == 2.5

    def test_to_dict_with_idle_since(self):
        """Test IdleResource.to_dict() with idle_since date."""
        now = datetime(2024, 1, 15, 10, 30, 0)
        resource = IdleResource(
            arn="arn:aws:ec2:us-east-1:123456789:instance/i-123",
            service="ec2",
            resource_type="instance",
            name="test",
            region="us-east-1",
            reason=IdleReason.STOPPED,
            idle_since=now,
            estimated_monthly_cost=0,
            confidence=1.0,
        )

        result = resource.to_dict()
        assert result["idle_since"] == "2024-01-15T10:30:00"


class TestRightSizeRecommendation:
    """Tests for RightSizeRecommendation dataclass."""

    def test_to_dict(self):
        """Test RightSizeRecommendation.to_dict() conversion."""
        rec = RightSizeRecommendation(
            arn="arn:aws:ec2:us-east-1:123456789:instance/i-123",
            service="ec2",
            resource_type="instance",
            name="test-instance",
            region="us-east-1",
            current_config={"instance_type": "m5.xlarge"},
            recommended_config={"instance_type": "m5.large"},
            action=RightSizeAction.DOWNSIZE,
            current_monthly_cost=140.0,
            projected_monthly_cost=70.0,
            savings_percentage=50.0,
            utilization_metrics={"avg_cpu": 15.0, "max_cpu": 25.0},
            reasoning="CPU utilization suggests over-provisioning.",
        )

        result = rec.to_dict()

        assert result["action"] == "downsize"
        assert result["savings_percentage"] == 50.0
        assert result["savings_monthly"] == 70.0
        assert result["current_monthly_cost"] == 140.0
        assert result["projected_monthly_cost"] == 70.0


class TestCostBreakdown:
    """Tests for CostBreakdown dataclass."""

    def test_to_dict(self):
        """Test CostBreakdown.to_dict() conversion."""
        breakdown = CostBreakdown(
            total_cost=1500.0,
            period_start=datetime(2024, 1, 1),
            period_end=datetime(2024, 1, 31),
            by_service=[
                CostBreakdownItem(name="EC2", cost=800.0, percentage=53.3),
                CostBreakdownItem(name="S3", cost=400.0, percentage=26.7),
            ],
        )

        result = breakdown.to_dict()

        assert result["total_cost"] == 1500.0
        assert result["currency"] == "USD"
        assert len(result["by_service"]) == 2
        assert result["by_service"][0]["name"] == "EC2"
        assert result["by_service"][0]["cost"] == 800.0


class TestCostProjection:
    """Tests for CostProjection dataclass."""

    def test_to_dict(self):
        """Test CostProjection.to_dict() conversion."""
        projection = CostProjection(
            resources=[
                ResourceProjection(
                    resource_type="EC2 t3.large",
                    config={"type": "ec2", "instance_type": "t3.large"},
                    hourly_cost=0.0832,
                    monthly_cost=60.74,
                    pricing_source="estimate",
                )
            ],
            total_hourly=0.0832,
            total_monthly=60.74,
            total_yearly=728.88,
            assumptions=["On-demand pricing"],
        )

        result = projection.to_dict()

        assert result["total_monthly"] == 60.74
        assert result["total_yearly"] == 728.88
        assert len(result["resources"]) == 1


class TestCostAnalysisResult:
    """Tests for CostAnalysisResult dataclass."""

    def test_to_dict_idle_resources(self):
        """Test CostAnalysisResult.to_dict() with idle resources."""
        result = CostAnalysisResult(
            analysis_type="idle_resources",
            idle_resources=[
                IdleResource(
                    arn="arn:aws:ec2:us-east-1:123:instance/i-1",
                    service="ec2",
                    resource_type="instance",
                    name="test",
                    region="us-east-1",
                    reason=IdleReason.STOPPED,
                    estimated_monthly_cost=50.0,
                    confidence=0.9,
                )
            ],
            total_potential_savings=50.0,
        )

        data = result.to_dict()

        assert data["analysis_type"] == "idle_resources"
        assert data["idle_resources_count"] == 1
        assert data["idle_resources_cost"] == 50.0
        assert data["total_potential_savings"] == 50.0

    def test_to_dict_with_errors(self):
        """Test CostAnalysisResult.to_dict() with errors."""
        result = CostAnalysisResult(
            analysis_type="cost_breakdown",
            errors=["Access denied to Cost Explorer"],
        )

        data = result.to_dict()

        assert "errors" in data
        assert len(data["errors"]) == 1


class TestCostAnalyzer:
    """Tests for CostAnalyzer class."""

    def test_get_smaller_instance_type(self):
        """Test getting smaller instance type."""
        analyzer = CostAnalyzer()

        assert analyzer._get_smaller_instance_type("t3.large") == "t3.medium"
        assert analyzer._get_smaller_instance_type("t3.medium") == "t3.small"
        assert analyzer._get_smaller_instance_type("t3.nano") is None
        assert analyzer._get_smaller_instance_type("invalid") is None

    def test_get_larger_instance_type(self):
        """Test getting larger instance type."""
        analyzer = CostAnalyzer()

        assert analyzer._get_larger_instance_type("t3.medium") == "t3.large"
        assert analyzer._get_larger_instance_type("t3.large") == "t3.xlarge"
        assert analyzer._get_larger_instance_type("t3.24xlarge") is None

    def test_estimate_ebs_cost_gp3(self):
        """Test EBS cost estimation for gp3."""
        analyzer = CostAnalyzer()

        # gp3 at $0.08/GB-month
        cost = analyzer._estimate_ebs_cost(100, "gp3")
        assert cost == 8.0

    def test_estimate_ebs_cost_gp2(self):
        """Test EBS cost estimation for gp2."""
        analyzer = CostAnalyzer()

        # gp2 at $0.10/GB-month
        cost = analyzer._estimate_ebs_cost(500, "gp2")
        assert cost == 50.0

    def test_estimate_ebs_cost_unknown_type(self):
        """Test EBS cost estimation with unknown type defaults to $0.10."""
        analyzer = CostAnalyzer()

        cost = analyzer._estimate_ebs_cost(100, "unknown")
        assert cost == 10.0

    def test_estimate_lambda_cost_within_free_tier(self):
        """Test Lambda cost within free tier."""
        analyzer = CostAnalyzer()

        # 500K invocations, 128MB, 100ms each = within free tier
        cost = analyzer._estimate_lambda_cost(128, 500000, 100)
        assert cost == 0.0

    def test_estimate_lambda_cost_beyond_free_tier(self):
        """Test Lambda cost beyond free tier."""
        analyzer = CostAnalyzer()

        # 10M invocations, 1024MB, 500ms each = beyond free tier
        cost = analyzer._estimate_lambda_cost(1024, 10000000, 500)
        assert cost > 0


class TestCostAnalyzerSingleton:
    """Tests for cost analyzer singleton pattern."""

    def test_get_cost_analyzer_returns_same_instance(self):
        """Test that get_cost_analyzer returns the same instance."""
        reset_cost_analyzer()

        analyzer1 = get_cost_analyzer()
        analyzer2 = get_cost_analyzer()

        assert analyzer1 is analyzer2

    def test_reset_cost_analyzer(self):
        """Test that reset_cost_analyzer creates a new instance."""
        analyzer1 = get_cost_analyzer()
        reset_cost_analyzer()
        analyzer2 = get_cost_analyzer()

        assert analyzer1 is not analyzer2


class TestCostAnalyzerPricing:
    """Tests for cost analyzer pricing methods."""

    @pytest.mark.asyncio
    async def test_get_ec2_price_fallback(self):
        """Test EC2 price uses fallback values."""
        analyzer = CostAnalyzer()

        price = await analyzer._get_ec2_price("t3.medium", "us-east-1")
        assert price == 0.0416  # Fallback price

    @pytest.mark.asyncio
    async def test_get_ec2_price_unknown_type(self):
        """Test EC2 price for unknown type uses default."""
        analyzer = CostAnalyzer()

        price = await analyzer._get_ec2_price("unknown.type", "us-east-1")
        assert price == 0.10  # Default fallback

    @pytest.mark.asyncio
    async def test_get_rds_price_fallback(self):
        """Test RDS price uses fallback values."""
        analyzer = CostAnalyzer()

        price = await analyzer._get_rds_price("db.t3.medium", "us-east-1")
        assert price == 0.068

    @pytest.mark.asyncio
    async def test_estimate_ec2_cost(self):
        """Test EC2 monthly cost estimation."""
        analyzer = CostAnalyzer()

        # t3.medium at $0.0416/hr * 730 hours = ~$30.37/month
        cost = await analyzer._estimate_ec2_cost("t3.medium", "us-east-1")
        assert abs(cost - 30.37) < 0.5  # Allow small variance


class TestProjectCosts:
    """Tests for project_costs method."""

    @pytest.mark.asyncio
    async def test_project_costs_ec2(self):
        """Test cost projection for EC2 instances."""
        analyzer = CostAnalyzer()

        result = await analyzer.project_costs(
            resources=[{"type": "ec2", "instance_type": "t3.medium", "count": 2}],
            region="us-east-1",
        )

        assert result.analysis_type == "projection"
        assert result.projection is not None
        assert result.projection.total_monthly > 0
        assert len(result.projection.resources) == 1
        assert "EC2 t3.medium" in result.projection.resources[0].resource_type

    @pytest.mark.asyncio
    async def test_project_costs_ebs(self):
        """Test cost projection for EBS volumes."""
        analyzer = CostAnalyzer()

        result = await analyzer.project_costs(
            resources=[{"type": "ebs", "size_gb": 100, "volume_type": "gp3"}],
            region="us-east-1",
        )

        assert result.projection is not None
        # 100GB gp3 = $8/month
        assert result.projection.total_monthly == 8.0

    @pytest.mark.asyncio
    async def test_project_costs_unknown_type(self):
        """Test cost projection with unknown resource type."""
        analyzer = CostAnalyzer()

        result = await analyzer.project_costs(
            resources=[{"type": "unknown", "config": "value"}],
            region="us-east-1",
        )

        assert result.projection is not None
        assert "Unknown resource type: unknown" in result.projection.warnings

    @pytest.mark.asyncio
    async def test_project_costs_multiple_resources(self):
        """Test cost projection for multiple resources."""
        analyzer = CostAnalyzer()

        result = await analyzer.project_costs(
            resources=[
                {"type": "ec2", "instance_type": "t3.medium", "count": 2},
                {"type": "ebs", "size_gb": 100, "volume_type": "gp3"},
                {"type": "rds", "instance_class": "db.t3.medium"},
            ],
            region="us-east-1",
        )

        assert result.projection is not None
        assert len(result.projection.resources) == 3
        assert result.projection.total_monthly > 0
        assert result.projection.total_yearly == result.projection.total_monthly * 12
