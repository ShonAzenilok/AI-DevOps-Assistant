from app.services.mcp.tools import (
    coerce_read_only_command,
    is_destructive_tool_call,
    is_write_tool_call,
    parse_tool_call,
)
from app.services.resources.scanner import build_scan_result


def test_parse_tool_call_dict_arguments() -> None:
    name, args = parse_tool_call(
        {
            "function": {
                "name": "aws___call_aws",
                "arguments": {"cli_command": "aws s3api list-buckets"},
            }
        }
    )
    assert name == "aws___call_aws"
    assert args["cli_command"] == "aws s3api list-buckets"


def test_coerce_read_query_from_write_command() -> None:
    cmd = coerce_read_only_command(
        "list my ec2 instances",
        "us-east-1",
        "aws ec2 run-instances --image-id ami-123 --tags Key=Name,Value=test",
    )
    assert "describe-instances" in cmd
    assert "run-instances" not in cmd


def test_write_command_staged() -> None:
    assert is_write_tool_call(
        "call_aws",
        {"cli_command": "aws ec2 run-instances --image-id ami-123"},
    )


def test_destructive_cli_detection() -> None:
    assert is_destructive_tool_call(
        "call_aws",
        {"cli_command": "aws ec2 terminate-instances --instance-ids i-123"},
    )
    assert not is_destructive_tool_call(
        "call_aws",
        {"cli_command": "aws ec2 describe-instances --region us-east-1"},
    )


def test_build_scan_result_empty() -> None:
    result = build_scan_result("123456789012", "us-east-1", {})
    assert result.accountId == "123456789012"
    assert result.region == "us-east-1"
    assert result.edges == []
    assert result.groups is not None
    assert len(result.groups) >= 2
