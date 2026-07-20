from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.models.schemas import ScanGroup, ScanNode, ScanResult, StoredAwsCredentials
from app.services.mcp.manager import McpClientManager

logger = logging.getLogger(__name__)

NODE_W = 180
NODE_H = 72
GAP_X = 24
GAP_Y = 24
GROUP_PAD = 40


def _parse_json_output(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def _extract_list(payload: Any, *keys: str) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for value in payload.values():
            if isinstance(value, list):
                return value
    return []


class ResourceScanner:
    def __init__(self, mcp: McpClientManager) -> None:
        self.mcp = mcp

    async def scan(self, credentials: StoredAwsCredentials) -> ScanResult:
        region = credentials.region
        account_id = credentials.account_id

        commands = {
            "vpc": f"aws ec2 describe-vpcs --region {region}",
            "ec2": f"aws ec2 describe-instances --region {region}",
            "s3": "aws s3api list-buckets",
            "rds": f"aws rds describe-db-instances --region {region}",
            "lambda": f"aws lambda list-functions --region {region}",
            "elb": f"aws elbv2 describe-load-balancers --region {region}",
            "ebs": f"aws ec2 describe-volumes --region {region}",
            "dynamodb": f"aws dynamodb list-tables --region {region}",
            "ecr": f"aws ecr describe-repositories --region {region}",
            "apigateway": f"aws apigateway get-rest-apis --region {region}",
            "amplify": f"aws amplify list-apps --region {region}",
            "route53": "aws route53 list-hosted-zones",
            "cloudwatch": f"aws cloudwatch describe-alarms --region {region}",
        }

        async def run_scan(resource_type: str, cli_command: str) -> tuple[str, Any]:
            try:
                output = await self.mcp.call_aws_cli(cli_command, max_results=50)
                return resource_type, _parse_json_output(output)
            except Exception as exc:
                logger.warning("Scan failed for %s: %s", resource_type, exc)
                return resource_type, None

        results = await asyncio.gather(*(run_scan(rt, cmd) for rt, cmd in commands.items()))
        parsed = dict(results)

        return build_scan_result(account_id, region, parsed)


def build_scan_result(account_id: str, region: str, parsed: dict[str, Any]) -> ScanResult:
    groups: list[ScanGroup] = []
    nodes: list[ScanNode] = []

    region_group = ScanGroup(
        id=f"region-{region}",
        label=region,
        x=40,
        y=40,
        width=900,
        height=700,
        color="#00A4A6",
        kind="region",
    )
    groups.append(region_group)

    vpcs = _extract_list(parsed.get("vpc"), "Vpcs")
    vpc_groups: dict[str, ScanGroup] = {}
    for index, vpc in enumerate(vpcs):
        vpc_id = vpc.get("VpcId", f"vpc-{index}")
        group = ScanGroup(
            id=vpc_id,
            label=vpc_id,
            x=80 + (index % 2) * 420,
            y=80 + (index // 2) * 320,
            width=380,
            height=260,
            color="#8C4FFF",
            kind="vpc",
        )
        vpc_groups[vpc_id] = group
        groups.append(group)

    global_group = ScanGroup(
        id="global",
        label="Global",
        x=980,
        y=40,
        width=320,
        height=420,
        color="#E9EBED",
        kind="global",
    )
    groups.append(global_group)

    def add_nodes(
        resource_type: str,
        items: list[dict[str, Any]],
        *,
        global_scope: bool = False,
        label_key: str = "Name",
        sublabel_fn: Any = None,
        id_fn: Any = None,
    ) -> None:
        parent = global_group if global_scope else region_group
        base_x = parent.x + GROUP_PAD
        base_y = parent.y + GROUP_PAD
        for index, item in enumerate(items):
            node_id = id_fn(item) if id_fn else item.get("id") or f"{resource_type}-{index}"
            label = item.get(label_key) or node_id
            sublabel = sublabel_fn(item) if sublabel_fn else resource_type.upper()
            col = index % 3
            row = index // 3
            nodes.append(
                ScanNode(
                    id=str(node_id),
                    label=str(label)[:40],
                    sublabel=str(sublabel)[:40],
                    type=resource_type,  # type: ignore[arg-type]
                    x=base_x + col * (NODE_W + GAP_X),
                    y=base_y + row * (NODE_H + GAP_Y),
                )
            )

    instances = []
    for reservation in _extract_list(parsed.get("ec2"), "Reservations"):
        instances.extend(_extract_list(reservation, "Instances"))

    add_nodes(
        "ec2",
        instances,
        label_key="InstanceId",
        sublabel_fn=lambda i: i.get("InstanceType", "EC2"),
        id_fn=lambda i: i.get("InstanceId"),
    )

    buckets = _extract_list(parsed.get("s3"), "Buckets")
    add_nodes(
        "s3",
        buckets,
        global_scope=True,
        label_key="Name",
        sublabel_fn=lambda b: "S3 bucket",
        id_fn=lambda b: b.get("Name"),
    )

    add_nodes(
        "rds",
        _extract_list(parsed.get("rds"), "DBInstances"),
        label_key="DBInstanceIdentifier",
        sublabel_fn=lambda d: d.get("Engine", "RDS"),
        id_fn=lambda d: d.get("DBInstanceIdentifier"),
    )

    add_nodes(
        "lambda",
        _extract_list(parsed.get("lambda"), "Functions"),
        label_key="FunctionName",
        sublabel_fn=lambda f: f.get("Runtime", "Lambda"),
        id_fn=lambda f: f.get("FunctionArn") or f.get("FunctionName"),
    )

    add_nodes(
        "elb",
        _extract_list(parsed.get("elb"), "LoadBalancers"),
        label_key="LoadBalancerName",
        sublabel_fn=lambda lb: lb.get("Type", "ELB"),
        id_fn=lambda lb: lb.get("LoadBalancerArn") or lb.get("LoadBalancerName"),
    )

    add_nodes(
        "ebs",
        _extract_list(parsed.get("ebs"), "Volumes"),
        label_key="VolumeId",
        sublabel_fn=lambda v: v.get("State", "EBS"),
        id_fn=lambda v: v.get("VolumeId"),
    )

    add_nodes(
        "dynamodb",
        [{"Name": name} for name in _extract_list(parsed.get("dynamodb"), "TableNames")],
        label_key="Name",
        sublabel_fn=lambda _: "DynamoDB",
        id_fn=lambda t: t.get("Name"),
    )

    add_nodes(
        "ecr",
        _extract_list(parsed.get("ecr"), "repositories"),
        label_key="repositoryName",
        sublabel_fn=lambda r: "ECR",
        id_fn=lambda r: r.get("repositoryArn") or r.get("repositoryName"),
    )

    add_nodes(
        "apigateway",
        _extract_list(parsed.get("apigateway"), "items"),
        label_key="name",
        sublabel_fn=lambda a: "API Gateway",
        id_fn=lambda a: a.get("id") or a.get("name"),
    )

    add_nodes(
        "amplify",
        _extract_list(parsed.get("amplify"), "apps"),
        label_key="name",
        sublabel_fn=lambda a: a.get("platform", "Amplify"),
        id_fn=lambda a: a.get("appId") or a.get("name"),
    )

    add_nodes(
        "route53",
        _extract_list(parsed.get("route53"), "HostedZones"),
        global_scope=True,
        label_key="Name",
        sublabel_fn=lambda z: f"{z.get('ResourceRecordSetCount', 0)} records",
        id_fn=lambda z: z.get("Id"),
    )

    add_nodes(
        "cloudwatch",
        _extract_list(parsed.get("cloudwatch"), "MetricAlarms"),
        label_key="AlarmName",
        sublabel_fn=lambda a: a.get("StateValue", "Alarm"),
        id_fn=lambda a: a.get("AlarmArn") or a.get("AlarmName"),
    )

    return ScanResult(accountId=account_id, region=region, nodes=nodes, edges=[], groups=groups)
