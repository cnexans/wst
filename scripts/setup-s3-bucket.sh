#!/usr/bin/env bash
#
# Creates an S3 bucket and a dedicated IAM user with access only to that bucket.
# Requires: aws cli configured with an account that can create IAM users and S3 buckets.
#
set -euo pipefail

SUFFIX=$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c 8)
BUCKET_NAME="wst-library-${SUFFIX}"
USER_NAME="wst-backup-${SUFFIX}"
REGION="${AWS_REGION:-us-east-1}"

echo "=== wst S3 Backup Setup ==="
echo ""
echo "Bucket:  $BUCKET_NAME"
echo "User:    $USER_NAME"
echo "Region:  $REGION"
echo ""

# 1. Create bucket
echo "Creating S3 bucket..."
if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket \
        --bucket "$BUCKET_NAME" \
        --region "$REGION" \
        > /dev/null
else
    aws s3api create-bucket \
        --bucket "$BUCKET_NAME" \
        --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION" \
        > /dev/null
fi
echo "  Created: s3://$BUCKET_NAME"

# 2. Create IAM user
echo "Creating IAM user..."
aws iam create-user --user-name "$USER_NAME" > /dev/null
echo "  Created: $USER_NAME"

# 3. Create and attach policy (scoped to this bucket only)
echo "Attaching bucket policy..."
POLICY_DOC=$(cat <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}",
        "arn:aws:s3:::${BUCKET_NAME}/*"
      ]
    }
  ]
}
POLICY
)

aws iam put-user-policy \
    --user-name "$USER_NAME" \
    --policy-name "wst-backup-access" \
    --policy-document "$POLICY_DOC"
echo "  Policy attached (bucket-only access)"

# 4. Generate access keys
echo "Generating access keys..."
KEYS=$(aws iam create-access-key --user-name "$USER_NAME")
ACCESS_KEY=$(echo "$KEYS" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKey']['AccessKeyId'])")
SECRET_KEY=$(echo "$KEYS" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKey']['SecretAccessKey'])")

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Configure wst with these values:"
echo ""
echo "  wst backup s3 --configure"
echo ""
echo "  Bucket name:        $BUCKET_NAME"
echo "  Region:             $REGION"
echo "  Endpoint URL:       (leave empty for AWS S3)"
echo "  Access Key ID:      $ACCESS_KEY"
echo "  Secret Access Key:  $SECRET_KEY"
echo ""
echo "IMPORTANT: Save the Secret Access Key now — it cannot be retrieved again."
echo ""
echo "To delete everything later:"
echo "  aws s3 rb s3://$BUCKET_NAME --force"
echo "  aws iam delete-user-policy --user-name $USER_NAME --policy-name wst-backup-access"
echo "  aws iam delete-access-key --user-name $USER_NAME --access-key-id $ACCESS_KEY"
echo "  aws iam delete-user --user-name $USER_NAME"
