## Long-term Backup Script

Amazon Web Serivces (AWS) has its own managed database instance types known as RDS.
RDS has a default backup system. By default, 7 days of full backup everyday is kept. During those 7 days, it's easy to restore to any point in time using its Point-in-time recovery tool. The setting can be changed up to 35 days. But keep in mind if there is more space needed than the default storage it will be **charged** based on their [pricing policy].

This document describes how to set up a backup solution that lasts for longer
than RDS' maximum 35 days. This directory contains a script that should be run
as a cron job; the script creates regular manual backups that do not expire.

During the backup(manual or automatic), the instance of RDS can have a trouble of service. So RDS support [Multi-AZ Deployments](http://aws.amazon.com/rds/details/multi-az/).

Do not deploy this script on the main web instance. Because the web instance
has more open ports and runs our own custom code, it is more vulnerable to
security holes. This script has privilleged access to the RDS backup system, so
it should be run on a more secure machine - preferrably its own instance with
not much else running.

## System diagram

![System Diagrm](Backup.png)

## Backup Cron Job

These are the steps of create job on web instance.

1. Create EC2 instance on AWS. A tiny instance should be big enough.
1. Get a private SSH key from AWS, call it `aquamark.pem`.
1. SSH to backup instance using the private key.

    ```
    ssh -i aquamark.pem ubuntu@<INSTANCE IP OR DNS>`
    ```

1. Clone the git repository. You can get a [deployment key] for GitHub to avoid entering your password.

    ```
    git clone git@github.com:vpac-innovations/aquamark.git`
    ```

1. Install dependencies and cron job

    ```
    ./aquamark/database/setup-backup.sh
    ```

    The script will ask you for your AWS credentials and the region. For an
    Australian Aquamark deployment, use the `ap-southeast-2` region. For
    example:

    ```
    AWS Access Key ID []: <your key id>
    AWS Secret Access Key []: <your key secret>
    Default region name [None]: ap-southeast-2
    Default output format [None]:
    ```

    Details for creating an AWS API key are available in [AWS help]. If you
    need to edit them, the files are `~/.aws/config` and
    `~/.aws/credentials`.

    The script will install the [cron job].

## AWS Permissions and key

AWS S3 stores files attached on responses. And also S3 has [versioning functionality] on bucket.
Enable versioning is not reverasable so once it enabled only suspension versionning is possible. 
But if we give all the permission to the user, user(access key) can do everything so to restrict 
users permission.

For backup database we need to have permission to access DBSnapshot. Second part describes how to add this permission 

Here is the steps to do.

1. Login to AWS Console.
1. On top right corner of the screen, on the account has a dropdown menu. Select `Security Credentials`
1. Click `User` on the left side menu.
1. Click the user you want to use if there is no user create user.
1. On the permission tab, you can see `Inline Policies`, expand the tab.
    
    1. To create inline policy, click the link `click here`.
    1. Select `Custom Policy`.
    1. Type in name like `Aquamark_S3`.
    1. Type in policy.

        ```
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "1",
                    "Effect": "Allow",
                    "Action": [
                        "s3:AbortMultipartUpload",
                        "s3:GetBucketAcl",
                        "s3:GetBucketCORS",
                        "s3:GetBucketLocation",
                        "s3:GetBucketLogging",
                        "s3:GetBucketNotification",
                        "s3:GetBucketPolicy",
                        "s3:GetBucketRequestPayment",
                        "s3:GetBucketTagging",
                        "s3:GetBucketVersioning",
                        "s3:GetBucketWebsite",
                        "s3:GetLifecycleConfiguration",
                        "s3:GetObject",
                        "s3:GetObjectAcl",
                        "s3:GetObjectTorrent",
                        "s3:GetObjectVersion",
                        "s3:GetObjectVersionAcl",
                        "s3:GetObjectVersionTorrent",
                        "s3:ListAllMyBuckets",
                        "s3:ListBucket",
                        "s3:ListBucketMultipartUploads",
                        "s3:ListBucketVersions",
                        "s3:ListMultipartUploadParts",
                        "s3:PutBucketAcl",
                        "s3:PutBucketCORS",
                        "s3:PutBucketLogging",
                        "s3:PutBucketNotification",
                        "s3:PutBucketPolicy",
                        "s3:PutBucketRequestPayment",
                        "s3:PutBucketTagging",
                        "s3:PutBucketWebsite",
                        "s3:PutLifecycleConfiguration",
                        "s3:PutObject",
                        "s3:PutObjectAcl",
                        "s3:PutObjectVersionAcl",
                        "s3:RestoreObject"
                    ],
                    "Resource": [
                        "*"
                    ]
                }
            ]
        }
        ```

1. Add another policy for RDS snapshot
    1. Same as above steps create Custom Policy.
    1. Type in name like `Aquamark_RDS_backup`.
    1. Type in policy.

        ```
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "1",
                    "Effect": "Allow",
                    "Action": [
                        "rds:CreateDBSnapshot",
                        "rds:DescribeDBSnapshots"
                    ],
                    "Resource": [
                        "*"
                    ]
                }
            ]
        }
        ```

1. Using this policy, you can create key.
1. Finally you can login use `aws configure`


## Downloading Backups

The backups stored in RDS are not accessible for download. To get a copy of a
backup, you need to:

1. Restore a backup to a new RDS instance using the AWS console. You
   will need to make it publicly accessible (but password-protected).
1. Use [`pg_dump`] to pull all the data out of the new, temporary instance.
   [Use SSL] to encrypt your connection.

    ```bash
    # Get AWS root CA public key
    wget https://s3.amazonaws.com/rds-downloads/rds-combined-ca-bundle.pem

    # Construct connection string
    PG_USER=postgres
    PG_PASSWORD=postgres
    PG_DATABASE=postgres
    ENDPOINT=postgres.aiojafojipawefoij.ap-southeast-2.rds.amazonaws.com:5432
    QUERY="sslmode=verify-full&sslrootcert=rds-combined-ca-bundle.pem"
    CONN=postgres://$PG_USER:$PG_PASSWORD@$ENDPOINT/$PG_DATABASE?$QUERY

    pg_dump --format custom --blobs --verbose ${CONN} --file aq_dump
    ```

    You can get the ENDPOINT and password from the AWS console.

1. Delete the temporary RDS instance (because it's publicly accessible).

[pricing policy]: http://aws.amazon.com/rds/pricing/
[deployment key]: https://github.com/blog/2024-read-only-deploy-keys
[AWS help]: https://console.aws.amazon.com/iam/home?nc2=h_m_sc#security_credential
[`pg_dump`]: http://www.postgresql.org/docs/9.4/static/app-pgdump.html
[Use SSL]: http://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html
[cron job]: cron_backup
[versioning functionality]: http://docs.aws.amazon.com/AmazonS3/latest/dev/Versioning.html

