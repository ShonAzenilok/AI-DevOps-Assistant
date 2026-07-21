from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.models.schemas import ScanGroup, ScanNode, ScanResult, StoredAwsCredentials
from app.services.mcp.manager import McpClientManager

logger = logging.getLogger(__name__)

NODE_W = 180
NODE_H = 72
GAP_X = 24
GAP_Y = 24
GROUP_PAD = 40
HEADER_H = 36
COLS = 3
MIN_GROUP_W = 220
MIN_GROUP_H = 120


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


def _tag_name(item: dict[str, Any]) -> str | None:
    tags = item.get("Tags") or item.get("TagList") or []
    if not isinstance(tags, list):
        return None
    for tag in tags:
        if isinstance(tag, dict) and tag.get("Key") == "Name" and tag.get("Value"):
            return str(tag["Value"])
    return None


@dataclass
class _PendingNode:
    id: str
    label: str
    sublabel: str
    type: str
    parent_id: str


@dataclass
class _LayoutCursor:
    index: int = 0
    max_col: int = 0
    max_row: int = 0

    def next_cell(self) -> tuple[float, float]:
        col = self.index % COLS
        row = self.index // COLS
        self.index += 1
        self.max_col = max(self.max_col, col)
        self.max_row = max(self.max_row, row)
        x = GROUP_PAD + col * (NODE_W + GAP_X)
        y = GROUP_PAD + HEADER_H + row * (NODE_H + GAP_Y)
        return x, y

    def content_size(self) -> tuple[float, float]:
        if self.index == 0:
            return MIN_GROUP_W, MIN_GROUP_H
        cols = min(COLS, self.index)
        rows = (self.index + COLS - 1) // COLS
        width = GROUP_PAD * 2 + cols * NODE_W + max(0, cols - 1) * GAP_X
        height = GROUP_PAD + HEADER_H + rows * NODE_H + max(0, rows - 1) * GAP_Y + GROUP_PAD
        return max(width, MIN_GROUP_W), max(height, MIN_GROUP_H)


@dataclass
class _GroupBox:
    id: str
    label: str
    kind: str
    color: str
    parent_id: str | None = None
    x: float = 0
    y: float = 0
    width: float = MIN_GROUP_W
    height: float = MIN_GROUP_H
    cursor: _LayoutCursor = field(default_factory=_LayoutCursor)
    child_group_ids: list[str] = field(default_factory=list)


# Simple scanners: (resource_type, payload_key, list_keys, parent_mode, fields_fn)
# parent_mode: "ungrouped" | "global"
# fields_fn(item) -> (id, label, sublabel) | None to skip
_SimpleFields = Callable[[Any], tuple[str, str, str] | None]


def _fields_string_name(item: Any) -> tuple[str, str, str] | None:
    name = str(item)
    return name, name, "DynamoDB"


def _fields_ecr(item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    return (
        str(item.get("repositoryArn") or item.get("repositoryName") or ""),
        str(item.get("repositoryName") or ""),
        "ECR",
    )


def _fields_apigateway(item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    return (
        str(item.get("id") or item.get("name") or ""),
        str(item.get("name") or item.get("id") or ""),
        "API Gateway",
    )


def _fields_amplify(item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    return (
        str(item.get("appId") or item.get("name") or ""),
        str(item.get("name") or ""),
        str(item.get("platform") or "Amplify"),
    )


def _fields_cloudwatch(item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    return (
        str(item.get("AlarmArn") or item.get("AlarmName") or ""),
        str(item.get("AlarmName") or ""),
        str(item.get("StateValue") or "Alarm"),
    )


def _fields_s3(item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get("Name") or "")
    return name, name, "S3 bucket"


def _fields_route53(item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    return (
        str(item.get("Id") or item.get("Name") or ""),
        str(item.get("Name") or ""),
        f"{item.get('ResourceRecordSetCount', 0)} records",
    )


_SIMPLE_ENQUEUE: list[tuple[str, str, tuple[str, ...], str, _SimpleFields]] = [
    ("dynamodb", "dynamodb", ("TableNames",), "ungrouped", _fields_string_name),
    ("ecr", "ecr", ("repositories",), "ungrouped", _fields_ecr),
    ("apigateway", "apigateway", ("items",), "ungrouped", _fields_apigateway),
    ("amplify", "amplify", ("apps",), "ungrouped", _fields_amplify),
    ("cloudwatch", "cloudwatch", ("MetricAlarms",), "ungrouped", _fields_cloudwatch),
    ("s3", "s3", ("Buckets",), "global", _fields_s3),
    ("route53", "route53", ("HostedZones",), "global", _fields_route53),
]


class ResourceScanner:
    def __init__(self, mcp: McpClientManager) -> None:
        self.mcp = mcp

    async def scan(self, credentials: StoredAwsCredentials) -> ScanResult:
        region = credentials.region
        account_id = credentials.account_id

        commands = {
            "vpc": f"aws ec2 describe-vpcs --region {region}",
            "subnet": f"aws ec2 describe-subnets --region {region}",
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
    """Assemble nested region/VPC/subnet groups and resource nodes from scan payloads."""
    region_id = f"region-{region}"
    ungrouped_id = f"ungrouped-{region}"
    global_id = "global"

    boxes = _build_groups(region_id, global_id, region, parsed)
    pending = _enqueue_resources(parsed, boxes, region_id, ungrouped_id, global_id)
    _prune_empty_groups(boxes, pending)
    return _layout_and_emit(boxes, pending, region_id, global_id, account_id, region)


def _build_groups(
    region_id: str,
    global_id: str,
    region: str,
    parsed: dict[str, Any],
) -> dict[str, _GroupBox]:
    boxes: dict[str, _GroupBox] = {
        region_id: _GroupBox(
            id=region_id,
            label=region,
            kind="region",
            color="#00A4A6",
        ),
        global_id: _GroupBox(
            id=global_id,
            label="Global",
            kind="global",
            color="#E9EBED",
        ),
    }

    vpcs = _extract_list(parsed.get("vpc"), "Vpcs")
    for index, vpc in enumerate(vpcs):
        if not isinstance(vpc, dict):
            continue
        vpc_id = str(vpc.get("VpcId") or f"vpc-{index}")
        name = _tag_name(vpc)
        boxes[vpc_id] = _GroupBox(
            id=vpc_id,
            label=name or vpc_id,
            kind="vpc",
            color="#8C4FFF",
            parent_id=region_id,
        )
        boxes[region_id].child_group_ids.append(vpc_id)

    subnets = _extract_list(parsed.get("subnet"), "Subnets")
    for index, subnet in enumerate(subnets):
        if not isinstance(subnet, dict):
            continue
        subnet_id = str(subnet.get("SubnetId") or f"subnet-{index}")
        vpc_id = str(subnet.get("VpcId") or "")
        if vpc_id not in boxes:
            continue
        name = _tag_name(subnet)
        az = subnet.get("AvailabilityZone") or ""
        label = name or (f"{subnet_id} ({az})" if az else subnet_id)
        boxes[subnet_id] = _GroupBox(
            id=subnet_id,
            label=str(label)[:48],
            kind="subnet",
            color="#7AA116",
            parent_id=vpc_id,
        )
        boxes[vpc_id].child_group_ids.append(subnet_id)

    return boxes


def _enqueue_resources(
    parsed: dict[str, Any],
    boxes: dict[str, _GroupBox],
    region_id: str,
    ungrouped_id: str,
    global_id: str,
) -> list[_PendingNode]:
    pending: list[_PendingNode] = []

    def enqueue(
        resource_type: str,
        node_id: str,
        label: str,
        sublabel: str,
        parent_id: str,
    ) -> None:
        if not node_id:
            return
        pending.append(
            _PendingNode(
                id=str(node_id),
                label=str(label)[:40],
                sublabel=str(sublabel)[:40],
                type=resource_type,
                parent_id=parent_id,
            )
        )

    def ensure_ungrouped() -> None:
        if ungrouped_id in boxes:
            return
        boxes[ungrouped_id] = _GroupBox(
            id=ungrouped_id,
            label="Regional services",
            kind="vpc",
            color="#5A5A5A",
            parent_id=region_id,
        )
        boxes[region_id].child_group_ids.append(ungrouped_id)

    def resolve_vpc_parent(vpc_id: str | None) -> str:
        if vpc_id and vpc_id in boxes and boxes[vpc_id].kind == "vpc":
            return vpc_id
        ensure_ungrouped()
        return ungrouped_id

    def resolve_subnet_parent(subnet_id: str | None, vpc_id: str | None) -> str:
        if subnet_id and subnet_id in boxes and boxes[subnet_id].kind == "subnet":
            return subnet_id
        return resolve_vpc_parent(vpc_id)

    # --- EC2 ---
    instances: list[dict[str, Any]] = []
    for reservation in _extract_list(parsed.get("ec2"), "Reservations"):
        if isinstance(reservation, dict):
            instances.extend(
                i for i in _extract_list(reservation, "Instances") if isinstance(i, dict)
            )

    for inst in instances:
        instance_id = str(inst.get("InstanceId") or "")
        name = _tag_name(inst) or instance_id
        enqueue(
            "ec2",
            instance_id,
            name,
            str(inst.get("InstanceType") or "EC2"),
            resolve_subnet_parent(inst.get("SubnetId"), inst.get("VpcId")),
        )

    # --- EBS ---
    for volume in _extract_list(parsed.get("ebs"), "Volumes"):
        if not isinstance(volume, dict):
            continue
        volume_id = str(volume.get("VolumeId") or "")
        attachments = _extract_list(volume, "Attachments")
        parent = ungrouped_id
        if attachments and isinstance(attachments[0], dict):
            attached_instance = attachments[0].get("InstanceId")
            matching = next((i for i in instances if i.get("InstanceId") == attached_instance), None)
            if matching:
                parent = resolve_subnet_parent(matching.get("SubnetId"), matching.get("VpcId"))
            else:
                ensure_ungrouped()
                parent = ungrouped_id
        else:
            ensure_ungrouped()
            parent = ungrouped_id
        enqueue(
            "ebs",
            volume_id,
            volume_id,
            str(volume.get("State") or "EBS"),
            parent,
        )

    # --- RDS ---
    for db in _extract_list(parsed.get("rds"), "DBInstances"):
        if not isinstance(db, dict):
            continue
        vpc_id = None
        subnet_id = None
        subnet_group = db.get("DBSubnetGroup")
        if isinstance(subnet_group, dict):
            vpc_id = subnet_group.get("VpcId")
            subnets_in_group = _extract_list(subnet_group, "Subnets")
            if subnets_in_group and isinstance(subnets_in_group[0], dict):
                subnet_id = subnets_in_group[0].get("SubnetIdentifier")
        enqueue(
            "rds",
            str(db.get("DBInstanceIdentifier") or ""),
            str(db.get("DBInstanceIdentifier") or ""),
            str(db.get("Engine") or "RDS"),
            resolve_subnet_parent(subnet_id, vpc_id),
        )

    # --- Lambda ---
    for fn in _extract_list(parsed.get("lambda"), "Functions"):
        if not isinstance(fn, dict):
            continue
        vpc_config = fn.get("VpcConfig") if isinstance(fn.get("VpcConfig"), dict) else {}
        vpc_id = vpc_config.get("VpcId") if vpc_config else None
        subnet_ids = vpc_config.get("SubnetIds") if vpc_config else None
        subnet_id = subnet_ids[0] if isinstance(subnet_ids, list) and subnet_ids else None
        enqueue(
            "lambda",
            str(fn.get("FunctionArn") or fn.get("FunctionName") or ""),
            str(fn.get("FunctionName") or ""),
            str(fn.get("Runtime") or "Lambda"),
            resolve_subnet_parent(subnet_id, vpc_id) if vpc_id else resolve_vpc_parent(None),
        )

    # --- ELB ---
    for lb in _extract_list(parsed.get("elb"), "LoadBalancers"):
        if not isinstance(lb, dict):
            continue
        azs = _extract_list(lb, "AvailabilityZones")
        subnet_id = None
        if azs and isinstance(azs[0], dict):
            subnet_id = azs[0].get("SubnetId")
        enqueue(
            "elb",
            str(lb.get("LoadBalancerArn") or lb.get("LoadBalancerName") or ""),
            str(lb.get("LoadBalancerName") or ""),
            str(lb.get("Type") or "ELB"),
            resolve_subnet_parent(subnet_id, lb.get("VpcId")),
        )

    parent_ids = {"ungrouped": ungrouped_id, "global": global_id}
    for resource_type, payload_key, list_keys, parent_mode, fields_fn in _SIMPLE_ENQUEUE:
        parent_id = parent_ids[parent_mode]
        for item in _extract_list(parsed.get(payload_key), *list_keys):
            fields = fields_fn(item)
            if fields is None:
                continue
            node_id, label, sublabel = fields
            if parent_mode == "ungrouped":
                ensure_ungrouped()
            enqueue(resource_type, node_id, label, sublabel, parent_id)

    return pending


def _prune_empty_groups(boxes: dict[str, _GroupBox], pending: list[_PendingNode]) -> None:
    """Drop VPC/subnet/ungrouped groups with no nodes and no non-empty children."""
    parents_used = {p.parent_id for p in pending}

    def group_has_content(group_id: str) -> bool:
        if group_id in parents_used:
            return True
        box = boxes.get(group_id)
        if not box:
            return False
        return any(group_has_content(cid) for cid in box.child_group_ids)

    for gid in list(boxes.keys()):
        if boxes[gid].kind in {"region", "global"}:
            continue
        if not group_has_content(gid):
            parent = boxes[gid].parent_id
            if parent and parent in boxes and gid in boxes[parent].child_group_ids:
                boxes[parent].child_group_ids.remove(gid)
            del boxes[gid]


def _size_from_cursor(box: _GroupBox) -> None:
    box.width, box.height = box.cursor.content_size()


def layout_children_of(parent: _GroupBox, boxes: dict[str, _GroupBox]) -> None:
    """Nest child groups under parent using the same grid/stack math as before."""
    child_ids = [cid for cid in parent.child_group_ids if cid in boxes]
    if not child_ids:
        _size_from_cursor(parent)
        return

    for cid in child_ids:
        child = boxes[cid]
        layout_children_of(child, boxes)

    y = GROUP_PAD + HEADER_H
    max_w = MIN_GROUP_W
    for cid in child_ids:
        child = boxes[cid]
        child.x = GROUP_PAD
        child.y = y
        y += child.height + GAP_Y
        max_w = max(max_w, child.width)

    node_w, node_h = parent.cursor.content_size()
    if parent.cursor.index > 0:
        band_h = node_h if parent.cursor.index else GROUP_PAD + HEADER_H
        y = band_h + GAP_Y
        for cid in child_ids:
            child = boxes[cid]
            child.x = GROUP_PAD
            child.y = y
            y += child.height + GAP_Y
            max_w = max(max_w, child.width)
        parent.width = max(max_w + GROUP_PAD * 2, node_w)
        parent.height = y + GROUP_PAD
    else:
        parent.width = max_w + GROUP_PAD * 2
        parent.height = y + GROUP_PAD


def _layout_and_emit(
    boxes: dict[str, _GroupBox],
    pending: list[_PendingNode],
    region_id: str,
    global_id: str,
    account_id: str,
    region: str,
) -> ScanResult:
    scan_nodes: list[ScanNode] = []
    for item in pending:
        if item.parent_id not in boxes:
            continue
        box = boxes[item.parent_id]
        x, y = box.cursor.next_cell()
        scan_nodes.append(
            ScanNode(
                id=item.id,
                label=item.label,
                sublabel=item.sublabel,
                type=item.type,  # type: ignore[arg-type]
                x=x,
                y=y,
                parentId=item.parent_id,
            )
        )

    for box in boxes.values():
        if box.kind == "subnet":
            _size_from_cursor(box)

    for box in boxes.values():
        if box.kind == "vpc":
            layout_children_of(box, boxes)

    region_box = boxes[region_id]
    layout_children_of(region_box, boxes)

    global_box = boxes[global_id]
    _size_from_cursor(global_box)

    region_box.x = 40
    region_box.y = 40
    global_box.x = region_box.x + region_box.width + 48
    global_box.y = 40

    scan_groups: list[ScanGroup] = []
    for box in boxes.values():
        scan_groups.append(
            ScanGroup(
                id=box.id,
                label=box.label,
                x=box.x,
                y=box.y,
                width=box.width,
                height=box.height,
                color=box.color,
                kind=box.kind,  # type: ignore[arg-type]
                parentId=box.parent_id,
            )
        )

    return ScanResult(
        accountId=account_id,
        region=region,
        nodes=scan_nodes,
        edges=[],
        groups=scan_groups,
    )
