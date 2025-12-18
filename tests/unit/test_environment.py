"""Tests for environment management modules."""

import pytest
from unittest.mock import patch, MagicMock

from aws_sage.core.environment import (
    EnvironmentType,
    EnvironmentConfig,
    LOCALSTACK_COMMUNITY_SERVICES,
    LOCALSTACK_PRO_SERVICES,
    DEFAULT_PRODUCTION_CONFIG,
    DEFAULT_LOCALSTACK_CONFIG,
)
from aws_sage.core.environment_manager import (
    EnvironmentManager,
    EnvironmentSwitchResult,
    get_environment_manager,
    reset_environment_manager,
)
from aws_sage.differentiators.compare import (
    ResourceDifference,
    ResourceComparison,
    ComparisonResult,
    EnvironmentComparer,
    get_environment_comparer,
    reset_environment_comparer,
)


class TestEnvironmentType:
    """Tests for EnvironmentType enum."""

    def test_production_value(self):
        """Test production environment type value."""
        assert EnvironmentType.PRODUCTION.value == "production"

    def test_localstack_value(self):
        """Test localstack environment type value."""
        assert EnvironmentType.LOCALSTACK.value == "localstack"


class TestEnvironmentConfig:
    """Tests for EnvironmentConfig dataclass."""

    def test_production_config(self):
        """Test production environment configuration."""
        config = EnvironmentConfig(
            name="prod",
            type=EnvironmentType.PRODUCTION,
            region="us-west-2",
        )

        assert config.name == "prod"
        assert config.type == EnvironmentType.PRODUCTION
        assert config.region == "us-west-2"
        assert config.endpoint_url is None

    def test_localstack_config_auto_services(self):
        """Test LocalStack config automatically sets available services."""
        config = EnvironmentConfig(
            name="local",
            type=EnvironmentType.LOCALSTACK,
            endpoint_url="http://localhost:4566",
        )

        assert config.available_services == LOCALSTACK_COMMUNITY_SERVICES
        assert "s3" in config.available_services
        assert "dynamodb" in config.available_services

    def test_to_dict(self):
        """Test EnvironmentConfig.to_dict() conversion."""
        config = EnvironmentConfig(
            name="test",
            type=EnvironmentType.LOCALSTACK,
            endpoint_url="http://localhost:4566",
            region="us-east-1",
            is_active=True,
            description="Test environment",
        )

        result = config.to_dict()

        assert result["name"] == "test"
        assert result["type"] == "localstack"
        assert result["endpoint_url"] == "http://localhost:4566"
        assert result["is_active"] is True

    def test_is_service_available_production(self):
        """Test all services available in production."""
        config = EnvironmentConfig(
            name="prod",
            type=EnvironmentType.PRODUCTION,
        )

        assert config.is_service_available("s3") is True
        assert config.is_service_available("rds") is True
        assert config.is_service_available("ce") is True  # Cost Explorer

    def test_is_service_available_localstack_community(self):
        """Test community services available in LocalStack."""
        config = EnvironmentConfig(
            name="local",
            type=EnvironmentType.LOCALSTACK,
        )

        assert config.is_service_available("s3") is True
        assert config.is_service_available("dynamodb") is True
        assert config.is_service_available("lambda") is True

    def test_is_service_not_available_localstack_pro(self):
        """Test pro services not available in LocalStack community."""
        config = EnvironmentConfig(
            name="local",
            type=EnvironmentType.LOCALSTACK,
        )

        assert config.is_service_available("rds") is False
        assert config.is_service_available("ce") is False

    def test_get_client_kwargs_production(self):
        """Test client kwargs for production environment."""
        config = EnvironmentConfig(
            name="prod",
            type=EnvironmentType.PRODUCTION,
            region="eu-west-1",
        )

        kwargs = config.get_client_kwargs("s3")

        assert kwargs["region_name"] == "eu-west-1"
        assert "endpoint_url" not in kwargs

    def test_get_client_kwargs_localstack(self):
        """Test client kwargs for LocalStack environment."""
        config = EnvironmentConfig(
            name="local",
            type=EnvironmentType.LOCALSTACK,
            endpoint_url="http://localhost:4566",
            region="us-east-1",
            access_key_id="test",
            secret_access_key="test",
        )

        kwargs = config.get_client_kwargs("s3")

        assert kwargs["endpoint_url"] == "http://localhost:4566"
        assert kwargs["region_name"] == "us-east-1"
        assert kwargs["aws_access_key_id"] == "test"


class TestLocalStackServices:
    """Tests for LocalStack service sets."""

    def test_community_services_exist(self):
        """Test community services set is populated."""
        assert len(LOCALSTACK_COMMUNITY_SERVICES) > 20
        assert "s3" in LOCALSTACK_COMMUNITY_SERVICES
        assert "dynamodb" in LOCALSTACK_COMMUNITY_SERVICES
        assert "lambda" in LOCALSTACK_COMMUNITY_SERVICES

    def test_pro_services_exist(self):
        """Test pro services set is populated."""
        assert len(LOCALSTACK_PRO_SERVICES) > 10
        assert "rds" in LOCALSTACK_PRO_SERVICES
        assert "ce" in LOCALSTACK_PRO_SERVICES
        assert "elasticache" in LOCALSTACK_PRO_SERVICES

    def test_no_overlap_between_community_and_pro(self):
        """Test community and pro services don't overlap."""
        overlap = LOCALSTACK_COMMUNITY_SERVICES & LOCALSTACK_PRO_SERVICES
        assert len(overlap) == 0


class TestDefaultConfigs:
    """Tests for default environment configurations."""

    def test_default_production_config(self):
        """Test default production configuration."""
        assert DEFAULT_PRODUCTION_CONFIG.name == "production"
        assert DEFAULT_PRODUCTION_CONFIG.type == EnvironmentType.PRODUCTION

    def test_default_localstack_config(self):
        """Test default LocalStack configuration."""
        assert DEFAULT_LOCALSTACK_CONFIG.name == "localstack"
        assert DEFAULT_LOCALSTACK_CONFIG.type == EnvironmentType.LOCALSTACK
        assert DEFAULT_LOCALSTACK_CONFIG.endpoint_url == "http://localhost:4566"


class TestEnvironmentManager:
    """Tests for EnvironmentManager class."""

    def setup_method(self):
        """Reset manager before each test."""
        reset_environment_manager()

    def test_list_environments(self):
        """Test listing environments."""
        manager = EnvironmentManager()
        environments = manager.list_environments()

        assert len(environments) == 2
        names = [env.name for env in environments]
        assert "production" in names
        assert "localstack" in names

    def test_get_environment(self):
        """Test getting environment by name."""
        manager = EnvironmentManager()

        prod = manager.get_environment("production")
        assert prod is not None
        assert prod.type == EnvironmentType.PRODUCTION

        local = manager.get_environment("localstack")
        assert local is not None
        assert local.type == EnvironmentType.LOCALSTACK

    def test_get_nonexistent_environment(self):
        """Test getting non-existent environment returns None."""
        manager = EnvironmentManager()
        result = manager.get_environment("nonexistent")
        assert result is None

    def test_get_active_environment_default(self):
        """Test default active environment is production."""
        manager = EnvironmentManager()
        active = manager.get_active_environment()

        assert active.name == "production"
        assert active.is_active is True

    def test_is_localstack_default(self):
        """Test is_localstack() returns False by default."""
        manager = EnvironmentManager()
        assert manager.is_localstack() is False

    def test_is_production_default(self):
        """Test is_production() returns True by default."""
        manager = EnvironmentManager()
        assert manager.is_production() is True

    def test_switch_to_localstack_without_validation(self):
        """Test switching to LocalStack without connectivity validation."""
        manager = EnvironmentManager()

        result = manager.switch_environment("localstack", validate=False)

        assert result.success is True
        assert result.environment.name == "localstack"
        assert manager.is_localstack() is True
        assert manager.is_production() is False

    def test_switch_to_production_warns(self):
        """Test switching to production includes warning."""
        manager = EnvironmentManager()
        manager.switch_environment("localstack", validate=False)

        result = manager.switch_environment("production", validate=False)

        assert result.success is True
        assert len(result.warnings) > 0
        assert "PRODUCTION" in result.warnings[0]

    def test_switch_to_nonexistent_environment(self):
        """Test switching to non-existent environment fails."""
        manager = EnvironmentManager()

        result = manager.switch_environment("nonexistent")

        assert result.success is False
        assert "not found" in result.message

    def test_add_custom_environment(self):
        """Test adding a custom environment."""
        manager = EnvironmentManager()

        custom = EnvironmentConfig(
            name="staging",
            type=EnvironmentType.PRODUCTION,
            region="eu-central-1",
            description="Staging environment",
        )
        manager.add_environment(custom)

        environments = manager.list_environments()
        assert len(environments) == 3
        assert any(env.name == "staging" for env in environments)

    def test_get_client_kwargs(self):
        """Test getting client kwargs for active environment."""
        manager = EnvironmentManager()

        kwargs = manager.get_client_kwargs("s3", "us-west-2")

        assert kwargs["region_name"] == "us-west-2"

    def test_is_service_available_production(self):
        """Test service availability in production."""
        manager = EnvironmentManager()

        available, message = manager.is_service_available("rds")

        assert available is True

    def test_is_service_available_localstack_community(self):
        """Test community service availability in LocalStack."""
        manager = EnvironmentManager()
        manager.switch_environment("localstack", validate=False)

        available, message = manager.is_service_available("s3")

        assert available is True

    def test_is_service_not_available_localstack_pro(self):
        """Test pro service unavailability in LocalStack."""
        manager = EnvironmentManager()
        manager.switch_environment("localstack", validate=False)

        available, message = manager.is_service_available("rds")

        assert available is False
        assert "Pro" in message

    def test_get_environment_info(self):
        """Test getting environment info."""
        manager = EnvironmentManager()

        info = manager.get_environment_info()

        assert info["name"] == "production"
        assert info["type"] == "production"
        assert info["is_production"] is True
        assert info["is_localstack"] is False


class TestEnvironmentManagerSingleton:
    """Tests for environment manager singleton pattern."""

    def setup_method(self):
        """Reset manager before each test."""
        reset_environment_manager()

    def test_get_environment_manager_returns_same_instance(self):
        """Test singleton returns same instance."""
        manager1 = get_environment_manager()
        manager2 = get_environment_manager()

        assert manager1 is manager2

    def test_reset_environment_manager_creates_new_instance(self):
        """Test reset creates new instance."""
        manager1 = get_environment_manager()
        reset_environment_manager()
        manager2 = get_environment_manager()

        assert manager1 is not manager2


class TestResourceComparison:
    """Tests for ResourceComparison dataclass."""

    def test_to_dict(self):
        """Test ResourceComparison.to_dict() conversion."""
        comparison = ResourceComparison(
            resource_type="bucket",
            identifier="my-bucket",
            difference=ResourceDifference.ONLY_IN_SOURCE,
            source_value={"name": "my-bucket"},
        )

        result = comparison.to_dict()

        assert result["resource_type"] == "bucket"
        assert result["identifier"] == "my-bucket"
        assert result["difference"] == "only_in_source"
        assert result["source_value"]["name"] == "my-bucket"


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_to_dict(self):
        """Test ComparisonResult.to_dict() conversion."""
        result = ComparisonResult(
            service="s3",
            source_environment="localstack",
            target_environment="production",
            resource_type="bucket",
            only_in_source=[
                ResourceComparison(
                    resource_type="bucket",
                    identifier="test-bucket",
                    difference=ResourceDifference.ONLY_IN_SOURCE,
                )
            ],
            identical=[
                ResourceComparison(
                    resource_type="bucket",
                    identifier="shared-bucket",
                    difference=ResourceDifference.IDENTICAL,
                )
            ],
        )

        data = result.to_dict()

        assert data["service"] == "s3"
        assert data["source_environment"] == "localstack"
        assert data["summary"]["only_in_source"] == 1
        assert data["summary"]["identical"] == 1


class TestEnvironmentComparer:
    """Tests for EnvironmentComparer class."""

    def setup_method(self):
        """Reset comparer before each test."""
        reset_environment_comparer()

    def test_supported_services(self):
        """Test list of supported services."""
        comparer = EnvironmentComparer()

        supported = comparer.supported_services

        assert "s3" in supported
        assert "dynamodb" in supported
        assert "lambda" in supported
        assert "sqs" in supported
        assert "sns" in supported

    @pytest.mark.asyncio
    async def test_compare_unsupported_service(self):
        """Test comparing unsupported service returns error."""
        comparer = EnvironmentComparer()
        source_env = DEFAULT_LOCALSTACK_CONFIG
        target_env = DEFAULT_PRODUCTION_CONFIG

        result = await comparer.compare_environments("unsupported", source_env, target_env)

        assert len(result.errors) > 0
        assert "not supported" in result.errors[0]


class TestEnvironmentComparerSingleton:
    """Tests for environment comparer singleton pattern."""

    def setup_method(self):
        """Reset comparer before each test."""
        reset_environment_comparer()

    def test_get_environment_comparer_returns_same_instance(self):
        """Test singleton returns same instance."""
        comparer1 = get_environment_comparer()
        comparer2 = get_environment_comparer()

        assert comparer1 is comparer2

    def test_reset_environment_comparer_creates_new_instance(self):
        """Test reset creates new instance."""
        comparer1 = get_environment_comparer()
        reset_environment_comparer()
        comparer2 = get_environment_comparer()

        assert comparer1 is not comparer2
