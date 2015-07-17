AWS RDS postgresql has a default backup system by itself. As a default 7 days of full backup everyday. So every time 7days backup / restore can be possible. And also it has Point-on-time recovery on the period of the retention period. The setting can be changed up to 35 days. **But should keep in mind if there is more space is need than default storage it will be charged based on their pricing policy(http://aws.amazon.com/rds/pricing/).**

During the backup(manual or automatic), the instance of RDS can have a trouble of service. So RDS support [Multi-AZ Deployments](http://aws.amazon.com/rds/details/multi-az/).

Our design said need to have a special instance of backup, this instance mostly standby and work in every week. So we decided this backup python script can be placed on the web instance as well.

So here are the steps of create job on web instance.
## Cron job backup.
1. SSH to web instance - `ssh -i aquamark.pem ubuntu@<INSTANCE IP OR DNS>`
1. git clone repository - `git clone git@github.com:vpac-innovations/aquamark.git`
  1. [Deploy key](https://github.com/blog/2024-read-only-deploy-keys) is needed.
1. install pip3 - `sudo apt-get update && apt-get install python3-pip`
1. install [boto3](https://boto3.readthedocs.org) - `sudo pip3 install boto3`
1. Login to AWS. You can create the key [AWS>Your ID>Security Credentials>Access Keys (Access Key ID and Secret Access Key)](https://console.aws.amazon.com/iam/home?nc2=h_m_sc#security_credential). Here are two options. Results are same.
  1. install AWS client and login manually - `sudo apt-get install awscli`
    1. login AWS - `aws configure`
  1. The other way is creating files(local hidden directory)

### ~/.aws/config 
```sh
[default]
region=ap-southeast-2
```
### ~/.aws/credentials
```sh
[default]
aws_access_key_id = <AWS_ACCESS_KEY>
aws_secret_access_key = <AWS_ACCESS_SECRET_KEY>
```

1. Execute crontab - `crontab ~/aquamark/database/cron_backup`