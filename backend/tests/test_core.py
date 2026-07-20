from mcp.types import Tool

from app.services.actions.executor import _extract_corrected_command, _operation_key
from app.services.bedrock.client import (
    bedrock_message_to_chat,
    messages_to_bedrock,
    tools_to_bedrock,
)
from app.services.aws_cli.validator import cli_validator
from app.services.mcp.tools import (
    build_action_summary,
    coerce_read_only_command,
    find_search_doc_tool,
    is_destructive_tool_call,
    is_tool_error_output,
    is_write_tool_call,
    parse_tool_call,
    resolve_tool_name,
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
    kinds = {g.kind for g in result.groups}
    assert "region" in kinds
    assert "global" in kinds


def test_build_scan_result_hierarchical_layout() -> None:
    parsed = {
        "vpc": {
            "Vpcs": [
                {
                    "VpcId": "vpc-aaa",
                    "Tags": [{"Key": "Name", "Value": "main-vpc"}],
                }
            ]
        },
        "subnet": {
            "Subnets": [
                {
                    "SubnetId": "subnet-1",
                    "VpcId": "vpc-aaa",
                    "AvailabilityZone": "us-east-1a",
                    "Tags": [{"Key": "Name", "Value": "public-a"}],
                },
                {
                    "SubnetId": "subnet-2",
                    "VpcId": "vpc-aaa",
                    "AvailabilityZone": "us-east-1b",
                    "Tags": [{"Key": "Name", "Value": "public-b"}],
                },
            ]
        },
        "ec2": {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-111",
                            "InstanceType": "t3.micro",
                            "VpcId": "vpc-aaa",
                            "SubnetId": "subnet-1",
                            "Tags": [{"Key": "Name", "Value": "web-1"}],
                        },
                        {
                            "InstanceId": "i-222",
                            "InstanceType": "t3.small",
                            "VpcId": "vpc-aaa",
                            "SubnetId": "subnet-2",
                            "Tags": [{"Key": "Name", "Value": "web-2"}],
                        },
                    ]
                }
            ]
        },
        "s3": {"Buckets": [{"Name": "my-bucket"}]},
        "lambda": {
            "Functions": [
                {
                    "FunctionName": "orphan-fn",
                    "FunctionArn": "arn:aws:lambda:us-east-1:1:function:orphan-fn",
                    "Runtime": "python3.12",
                }
            ]
        },
    }
    result = build_scan_result("123456789012", "us-east-1", parsed)
    assert result.groups is not None

    by_id = {g.id: g for g in result.groups}
    assert "vpc-aaa" in by_id
    assert by_id["vpc-aaa"].parentId == "region-us-east-1"
    assert "subnet-1" in by_id
    assert by_id["subnet-1"].parentId == "vpc-aaa"
    assert "subnet-2" in by_id
    assert by_id["global"].parentId is None

    nodes_by_id = {n.id: n for n in result.nodes}
    assert nodes_by_id["i-111"].parentId == "subnet-1"
    assert nodes_by_id["i-222"].parentId == "subnet-2"
    assert nodes_by_id["my-bucket"].parentId == "global"
    assert nodes_by_id["i-111"].label == "web-1"

    orphan = next(n for n in result.nodes if n.type == "lambda")
    assert orphan.parentId is not None
    assert orphan.parentId.startswith("ungrouped-")

    # No two nodes in the same parent share the same relative cell.
    from collections import defaultdict

    cells: dict[str, set[tuple[float, float]]] = defaultdict(set)
    for node in result.nodes:
        parent = node.parentId or ""
        cell = (node.x, node.y)
        assert cell not in cells[parent], f"overlap in {parent}: {cell}"
        cells[parent].add(cell)

    # Parent groups enclose child extents (relative coords).
    vpc = by_id["vpc-aaa"]
    for subnet_id in ("subnet-1", "subnet-2"):
        subnet = by_id[subnet_id]
        assert subnet.x + subnet.width <= vpc.width + 1
        assert subnet.y + subnet.height <= vpc.height + 1


def test_build_action_summary_run_instances() -> None:
    label, summary = build_action_summary(
        "aws ec2 run-instances --image-id ami-123 --instance-type t3.micro"
    )
    assert label == "Create EC2 instance"
    assert "EC2" in summary


def test_build_action_summary_create_bucket() -> None:
    label, summary = build_action_summary("aws s3api create-bucket --bucket my-bucket")
    assert label == "Create S3 bucket"
    assert "bucket" in summary.lower()


def test_build_action_summary_terminate() -> None:
    label, summary = build_action_summary(
        "aws ec2 terminate-instances --instance-ids i-123"
    )
    assert label == "Terminate EC2 instance"
    assert "terminate" in summary.lower()


def test_build_action_summary_create_tags() -> None:
    label, summary = build_action_summary(
        "aws ec2 create-tags --resources i-0d3fda6b90f32b57a "
        "--tags Key=Name,Value=test-ai --region us-east-1"
    )
    assert label == "Tag resource"
    assert "Create EC2 resource" not in label
    assert "tag" in summary.lower()
    assert "create a new" not in summary.lower()


def _tool(name: str) -> Tool:
    return Tool(name=name, inputSchema={"type": "object", "properties": {}})


def test_resolve_tool_name_exact_and_prefixed() -> None:
    tools = [_tool("aws___call_aws"), _tool("aws___search_documentation")]
    assert resolve_tool_name("aws___call_aws", tools) == "aws___call_aws"
    assert resolve_tool_name("call_aws", tools) == "aws___call_aws"
    assert resolve_tool_name("search_documentation", tools) == "aws___search_documentation"
    assert (
        resolve_tool_name("knowledge___search_documentation", tools)
        == "aws___search_documentation"
    )
    assert resolve_tool_name("made_up_tool", tools) is None


def test_find_search_doc_tool() -> None:
    tools = [_tool("aws___call_aws"), _tool("aws___search_documentation")]
    found = find_search_doc_tool(tools)
    assert found is not None
    assert found.name == "aws___search_documentation"
    assert find_search_doc_tool([_tool("aws___call_aws")]) is None


def test_action_registry_summary_not_delete_specific() -> None:
    from app.models.schemas import StagedMcpCall
    from app.services.actions.registry import ActionRegistry

    registry = ActionRegistry()
    pending = registry.stage(
        StagedMcpCall(
            tool_name="aws___call_aws",
            arguments={"cli_command": "aws ec2 run-instances --image-id ami-1"},
            label="Create EC2 instance",
            detail="This will launch a new EC2 instance with the specified configuration.",
            resource={
                "Summary": "This will launch a new EC2 instance with the specified configuration.",
                "Command": "aws ec2 run-instances --image-id ami-1",
            },
        )
    )
    assert pending.label == "Create EC2 instance"
    assert "Summary" in pending.resource
    cancelled = registry.cancel(pending.id)
    assert cancelled.status == "cancelled"
    assert cancelled.summary is not None
    assert "Deleted" not in cancelled.summary
    assert "Cancelled — Create EC2 instance" == cancelled.summary


def test_cli_validator_valid_read_command() -> None:
    result = cli_validator.validate("aws ec2 describe-instances --region us-east-1")
    assert result.ok
    assert result.error is None


def test_cli_validator_invalid_parameter() -> None:
    result = cli_validator.validate("aws ec2 run-instances --minimize-tags x --image-id ami-1")
    assert not result.ok
    assert result.error is not None
    assert "--minimize-tags" in result.error
    assert "--tag-specifications" in result.valid_params


def test_cli_validator_original_tags_mistake() -> None:
    result = cli_validator.validate("aws ec2 run-instances --image-id ami-1 --tags Key=Name,Value=x")
    assert not result.ok
    assert result.error is not None
    assert "--tags" in result.error
    assert "--tag-specifications" in result.valid_params


def test_cli_validator_unknown_operation() -> None:
    result = cli_validator.validate("aws ec2 not-an-op")
    assert not result.ok
    assert result.error is not None
    assert "not-an-op" in result.error


def test_cli_validator_unknown_service() -> None:
    result = cli_validator.validate("aws notaservice list-things")
    assert not result.ok
    assert result.error is not None
    assert "notaservice" in result.error


def test_cli_validator_not_aws() -> None:
    result = cli_validator.validate("not-aws foo")
    assert not result.ok


def test_cli_validator_global_options_allowed() -> None:
    result = cli_validator.validate(
        "aws s3api list-buckets --region us-east-1 --output json --max-items 10"
    )
    assert result.ok


def test_cli_validator_custom_s3_commands_pass() -> None:
    assert cli_validator.validate("aws s3 ls").ok


def test_cli_validator_cli_input_json_bypass() -> None:
    result = cli_validator.validate("aws ec2 run-instances --cli-input-json file://in.json")
    assert result.ok


def test_is_tool_error_output() -> None:
    assert is_tool_error_output(
        "Error calling tool 'call_aws': Error while executing the command: "
        'Parameter validation failed:\nMissing required parameter in input: "MaxCount"'
    )
    assert is_tool_error_output("An error occurred (UnauthorizedOperation) when calling ...")
    assert not is_tool_error_output('{"Instances": [{"InstanceId": "i-123"}]}')
    assert not is_tool_error_output("")


def test_executor_operation_key() -> None:
    assert _operation_key("aws ec2 run-instances --image-id ami-1") == ("ec2", "run-instances")
    assert _operation_key("aws s3api create-bucket --bucket b") == ("s3api", "create-bucket")


def test_executor_extract_corrected_command_from_tool_call() -> None:
    response = {
        "message": {
            "tool_calls": [
                {
                    "function": {
                        "name": "aws___call_aws",
                        "arguments": {
                            "cli_command": "aws ec2 run-instances --image-id ami-1 --count 1"
                        },
                    }
                }
            ]
        }
    }
    assert (
        _extract_corrected_command(response)
        == "aws ec2 run-instances --image-id ami-1 --count 1"
    )


def test_bedrock_message_translation_round_trip() -> None:
    messages = [
        {"role": "system", "content": "You are DevBot."},
        {"role": "user", "content": "Create an EC2 instance"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "t1",
                    "function": {
                        "name": "aws___call_aws",
                        "arguments": {"cli_command": "aws ec2 run-instances --image-id ami-1"},
                    },
                }
            ],
        },
        {"role": "tool", "content": '{"Instances": []}', "name": "aws___call_aws"},
    ]
    converted, system = messages_to_bedrock(messages)
    assert system == [{"text": "You are DevBot."}]
    assert converted[0] == {"role": "user", "content": [{"text": "Create an EC2 instance"}]}
    assert converted[1]["role"] == "assistant"
    tool_use = converted[1]["content"][0]["toolUse"]
    assert tool_use["toolUseId"] == "t1"
    assert tool_use["name"] == "aws___call_aws"
    assert tool_use["input"] == {"cli_command": "aws ec2 run-instances --image-id ami-1"}
    # Tool result pairs with the same toolUseId.
    tool_result = converted[2]["content"][0]["toolResult"]
    assert converted[2]["role"] == "user"
    assert tool_result["toolUseId"] == "t1"


def test_bedrock_merges_consecutive_same_role_messages() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "a", "function": {"name": "call_aws", "arguments": {"cli_command": "aws s3 ls"}}},
                {"id": "b", "function": {"name": "call_aws", "arguments": {"cli_command": "aws s3 ls"}}},
            ],
        },
        {"role": "tool", "content": "out1", "name": "call_aws"},
        {"role": "tool", "content": "out2", "name": "call_aws"},
    ]
    converted, _ = messages_to_bedrock(messages)
    assert len(converted) == 2
    assert [b["toolResult"]["toolUseId"] for b in converted[1]["content"]] == ["a", "b"]


def test_bedrock_tools_translation() -> None:
    config = tools_to_bedrock(
        [
            {
                "type": "function",
                "function": {
                    "name": "aws___call_aws",
                    "description": "Run AWS CLI",
                    "parameters": {
                        "type": "object",
                        "properties": {"cli_command": {"type": "string"}},
                    },
                },
            }
        ]
    )
    spec = config["tools"][0]["toolSpec"]
    assert spec["name"] == "aws___call_aws"
    assert spec["inputSchema"]["json"]["properties"]["cli_command"] == {"type": "string"}


def test_bedrock_output_message_to_chat() -> None:
    message = bedrock_message_to_chat(
        {
            "role": "assistant",
            "content": [
                {"text": "Running the command."},
                {
                    "toolUse": {
                        "toolUseId": "xyz",
                        "name": "aws___call_aws",
                        "input": {"cli_command": "aws s3api list-buckets"},
                    }
                },
            ],
        }
    )
    assert message["content"] == "Running the command."
    assert message["tool_calls"][0]["function"]["name"] == "aws___call_aws"
    assert message["tool_calls"][0]["function"]["arguments"] == {
        "cli_command": "aws s3api list-buckets"
    }


def test_executor_extract_corrected_command_from_text() -> None:
    response = {
        "message": {
            "content": "Here is the fixed command:\n`aws ec2 run-instances --image-id ami-1 --count 1`"
        }
    }
    assert (
        _extract_corrected_command(response)
        == "aws ec2 run-instances --image-id ami-1 --count 1"
    )
    assert _extract_corrected_command({"message": {"content": "no command here"}}) is None
