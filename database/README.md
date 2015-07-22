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

    1. The script will ask you for your AWS credentials and the region. For an
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

1. Execute crontab - `crontab ~/aquamark/database/cron_backup`

## Downloading Backups

The backups stored in RDS are not accessible for download. To get a copy of a
backup, you need to:

1. Restore a backup to a new RDS instance.
1. Use [`pg_dump`] to pull all the data out of the new, temporary instance. You
   will need to make it publicly accessible (but password-protected). [Use SSL]
   to encrypt your connection.

    ```
    pg_dump -i -h AWS_HOST -p 5432 -U postgres -F c -b -v \
        -f "10.70.0.61.backup" postgres
    ```

    You can get the AWS_HOST ("Endpoint") and password from the AWS console.

1. Delete the temporary RDS instance (because it's publicly accessible).

[pricing policy]: http://aws.amazon.com/rds/pricing/
[deployment key]: https://github.com/blog/2024-read-only-deploy-keys
[AWS help]: https://console.aws.amazon.com/iam/home?nc2=h_m_sc#security_credential
[`pg_dump`]: http://www.postgresql.org/docs/9.4/static/app-pgdump.html
[Use SSL]: http://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html
