from app.models.schemas import AwsConfig, StoredAwsCredentials
import boto3
from botocore.exceptions import BotoCoreError, ClientError


def verify_aws_credentials(config: AwsConfig) -> StoredAwsCredentials:
    """Validate credentials via STS GetCallerIdentity."""
    session = boto3.Session(
        aws_access_key_id=config.accessKeyId,
        aws_secret_access_key=config.secretAccessKey,
        region_name=config.region,
    )
    sts = session.client("sts")
    try:
        identity = sts.get_caller_identity()
    except (BotoCoreError, ClientError) as exc:
        raise ValueError(f"Invalid AWS credentials: {exc}") from exc

    account_id = identity.get("Account")
    if not account_id:
        raise ValueError("Could not determine AWS account ID.")

    return StoredAwsCredentials(
        access_key_id=config.accessKeyId,
        secret_access_key=config.secretAccessKey,
        region=config.region,
        account_id=account_id,
    )
