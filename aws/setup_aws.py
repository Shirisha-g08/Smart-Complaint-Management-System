"""
aws/setup_aws.py
----------------
Run ONCE to provision all AWS resources needed by the Smart CMS:
  • DynamoDB  : scms_users  (PK: email)
  • DynamoDB  : scms_complaints  (PK: complaint_id, GSI: user_email-index)
  • SNS Topic : scms-notifications

Usage:
    python aws/setup_aws.py

After running, copy the printed SNS_TOPIC_ARN into your .env file.
"""

import os
import sys
import time

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

AWS_REGION       = os.environ.get("AWS_REGION", "us-east-1")
USERS_TABLE      = os.environ.get("DYNAMODB_USERS_TABLE", "scms_users")
COMPLAINTS_TABLE = os.environ.get("DYNAMODB_COMPLAINTS_TABLE", "scms_complaints")
SNS_TOPIC_NAME   = "scms-notifications"

dynamodb_client = boto3.client("dynamodb", region_name=AWS_REGION)
sns_client      = boto3.client("sns",      region_name=AWS_REGION)


# ── DynamoDB helpers ──────────────────────────────────────────────────────────

def table_exists(name: str) -> bool:
    try:
        dynamodb_client.describe_table(TableName=name)
        return True
    except dynamodb_client.exceptions.ResourceNotFoundException:
        return False


def wait_for_active(name: str, timeout: int = 60) -> None:
    print(f"   Waiting for table '{name}' to become ACTIVE …", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp   = dynamodb_client.describe_table(TableName=name)
        status = resp["Table"]["TableStatus"]
        if status == "ACTIVE":
            print(" ACTIVE")
            return
        print(".", end="", flush=True)
        time.sleep(3)
    print(" TIMEOUT — check AWS Console")


def create_users_table() -> None:
    if table_exists(USERS_TABLE):
        print(f"[SKIP] Table '{USERS_TABLE}' already exists.")
        return

    dynamodb_client.create_table(
        TableName=USERS_TABLE,
        KeySchema=[
            {"AttributeName": "email", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    wait_for_active(USERS_TABLE)
    print(f"[OK ] Table '{USERS_TABLE}' created.")


def create_complaints_table() -> None:
    if table_exists(COMPLAINTS_TABLE):
        print(f"[SKIP] Table '{COMPLAINTS_TABLE}' already exists.")
        return

    dynamodb_client.create_table(
        TableName=COMPLAINTS_TABLE,
        KeySchema=[
            {"AttributeName": "complaint_id", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "complaint_id", "AttributeType": "S"},
            {"AttributeName": "user_email",   "AttributeType": "S"},
            {"AttributeName": "timestamp",    "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "user_email-index",
                "KeySchema": [
                    {"AttributeName": "user_email", "KeyType": "HASH"},
                    {"AttributeName": "timestamp",  "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    wait_for_active(COMPLAINTS_TABLE)
    print(f"[OK ] Table '{COMPLAINTS_TABLE}' created (GSI: user_email-index).")


# ── SNS helper ────────────────────────────────────────────────────────────────

def create_sns_topic() -> str:
    response  = sns_client.create_topic(Name=SNS_TOPIC_NAME)
    topic_arn = response["TopicArn"]
    print(f"[OK ] SNS topic '{SNS_TOPIC_NAME}' ready.")
    return topic_arn


def subscribe_email(topic_arn: str, email: str) -> None:
    """
    Subscribe an email address to the SNS topic.
    The subscriber must confirm via the email link AWS sends.
    """
    sns_client.subscribe(
        TopicArn=topic_arn,
        Protocol="email",
        Endpoint=email,
    )
    print(f"[OK ] Subscription request sent to {email} — check inbox to confirm.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  Smart Complaint Management System — AWS Setup")
    print(f"  Region : {AWS_REGION}")
    print("=" * 60)

    try:
        create_users_table()
        create_complaints_table()
        topic_arn = create_sns_topic()

        # Optionally subscribe the admin email
        admin_email = os.environ.get("ADMIN_EMAIL", "")
        if admin_email:
            subscribe_email(topic_arn, admin_email)

        print()
        print("=" * 60)
        print("  All resources provisioned successfully!")
        print()
        print("  Add the following line to your .env file:")
        print(f"  SNS_TOPIC_ARN={topic_arn}")
        print("=" * 60)

    except ClientError as exc:
        print(f"\n[ERROR] AWS error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
