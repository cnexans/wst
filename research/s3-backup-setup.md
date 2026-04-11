# Setup: S3 Backup for wst

## Overview

wst can backup your library to any S3-compatible storage. Each user creates their own bucket with a dedicated service account that only has access to that specific bucket. Credentials are stored locally in `~/wst/config.json`, separate from any existing AWS configuration.

## Supported Providers

| Provider | Endpoint URL | Free tier |
|---|---|---|
| AWS S3 | (default, leave empty) | 5 GB / 12 months |
| Cloudflare R2 | `https://<account_id>.r2.cloudflarestorage.com` | 10 GB forever |
| Backblaze B2 | `https://s3.<region>.backblazeb2.com` | 10 GB forever |
| MinIO | Your server URL | Self-hosted |

---

## Option A: AWS S3 (automated script)

### Prerequisites

```bash
# Install AWS CLI if not present
brew install awscli          # macOS
# or: sudo apt install awscli   # Linux

# Login with your personal/admin AWS account (one-time)
aws configure
```

### Run the setup script

```bash
# From the wst repo root
bash scripts/setup-s3-bucket.sh
```

The script will:
1. Create an S3 bucket named `wst-library-<random>`
2. Create an IAM user `wst-backup-<random>` with access ONLY to that bucket
3. Generate access keys for the service account
4. Print the credentials to configure wst

Then configure wst:

```bash
wst backup s3 --configure
# Paste the bucket name, access key, and secret key from the script output
```

### Manual AWS setup

If you prefer to do it manually or need to customize:

#### 1. Create the bucket

```bash
BUCKET_NAME="wst-library-$(whoami)"
AWS_REGION="us-east-1"

aws s3 mb "s3://$BUCKET_NAME" --region "$AWS_REGION"
```

#### 2. Create an IAM user for wst

```bash
USER_NAME="wst-backup"
aws iam create-user --user-name "$USER_NAME"
```

#### 3. Attach a policy scoped to the bucket only

```bash
cat > /tmp/wst-s3-policy.json << 'POLICY'
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
        "arn:aws:s3:::BUCKET_NAME",
        "arn:aws:s3:::BUCKET_NAME/*"
      ]
    }
  ]
}
POLICY

# Replace placeholder with actual bucket name
sed -i.bak "s/BUCKET_NAME/$BUCKET_NAME/g" /tmp/wst-s3-policy.json

aws iam put-user-policy \
  --user-name "$USER_NAME" \
  --policy-name "wst-backup-access" \
  --policy-document file:///tmp/wst-s3-policy.json

rm /tmp/wst-s3-policy.json /tmp/wst-s3-policy.json.bak
```

#### 4. Generate access keys

```bash
aws iam create-access-key --user-name "$USER_NAME"
```

Save the `AccessKeyId` and `SecretAccessKey` from the output.

#### 5. Configure wst

```bash
wst backup s3 --configure
```

---

## Option B: Cloudflare R2

R2 has no egress fees and 10 GB free forever. Good for personal use.

### Setup

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) > R2
2. Create a bucket (e.g., `wst-library`)
3. Go to R2 > Manage R2 API Tokens > Create API Token
4. Set permissions to "Object Read & Write" for the specific bucket
5. Copy the Access Key ID and Secret Access Key
6. Note your Account ID from the dashboard URL

### Configure wst

```bash
wst backup s3 --configure
```

Enter:
- **Bucket name:** `wst-library`
- **Region:** `auto`
- **Endpoint URL:** `https://<account_id>.r2.cloudflarestorage.com`
- **Access Key ID:** (from step 5)
- **Secret Access Key:** (from step 5)

---

## Option C: Backblaze B2

B2 has 10 GB free forever with low costs after that.

### Setup

1. Go to [Backblaze B2](https://www.backblaze.com/b2/cloud-storage.html) and create an account
2. Create a bucket (e.g., `wst-library`), set to **Private**
3. Go to App Keys > Add a New Application Key
4. Restrict to the bucket you created
5. Copy the `keyID` (Access Key) and `applicationKey` (Secret Key)
6. Note the bucket's region (e.g., `us-west-004`)

### Configure wst

```bash
wst backup s3 --configure
```

Enter:
- **Bucket name:** `wst-library`
- **Region:** `us-west-004` (your region)
- **Endpoint URL:** `https://s3.us-west-004.backblazeb2.com`
- **Access Key ID:** (keyID from step 5)
- **Secret Access Key:** (applicationKey from step 5)

---

## Security Notes

- Credentials are stored in `~/wst/config.json` (NOT in `~/.aws/`)
- The IAM user/service account should ONLY have access to the wst bucket
- Never reuse your personal AWS credentials — always create a dedicated service account
- The setup script creates a minimal IAM policy with only the permissions wst needs
- Consider enabling bucket versioning for extra safety: `aws s3api put-bucket-versioning --bucket $BUCKET_NAME --versioning-configuration Status=Enabled`
