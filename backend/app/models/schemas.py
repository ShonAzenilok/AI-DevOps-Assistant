from typing import Any, Literal

from pydantic import BaseModel, Field


class AwsConfig(BaseModel):
    accessKeyId: str
    secretAccessKey: str
    region: str


class AwsVerifyResponse(BaseModel):
    accountId: str


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatHistoryItem] = Field(default_factory=list)


class ToolCall(BaseModel):
    label: str
    detail: str
    durationMs: int | None = None
    output: str | None = None


class PendingAction(BaseModel):
    id: str
    label: str
    detail: str
    resource: dict[str, str]
    status: Literal["pending", "executed", "cancelled", "failed"] = "pending"
    resultSummary: str | None = None
    resultOutput: str | None = None


class ActionResultResponse(BaseModel):
    status: Literal["pending", "executed", "cancelled", "failed"]
    summary: str | None = None
    output: str | None = None


AwsResourceType = Literal[
    "vpc",
    "ec2",
    "s3",
    "rds",
    "lambda",
    "cloudwatch",
    "elb",
    "ebs",
    "dynamodb",
    "ecr",
    "apigateway",
    "amplify",
    "route53",
]

GroupKind = Literal["region", "vpc", "subnet", "global"]


class ScanNode(BaseModel):
    id: str
    label: str
    sublabel: str
    type: AwsResourceType
    x: float
    y: float


class ScanEdge(BaseModel):
    id: str | None = None
    source: str
    target: str


class ScanGroup(BaseModel):
    id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    color: str | None = None
    kind: GroupKind | None = None


class ScanResult(BaseModel):
    accountId: str | None = None
    region: str | None = None
    nodes: list[ScanNode]
    edges: list[ScanEdge] = Field(default_factory=list)
    groups: list[ScanGroup] | None = None


class StoredAwsCredentials(BaseModel):
    access_key_id: str
    secret_access_key: str
    region: str
    account_id: str


class StagedMcpCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    label: str
    detail: str
    resource: dict[str, str]
