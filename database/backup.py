import boto3
import datetime

def create_weekly_backup():
    client.create_db_snapshot(
        DBSnapshotIdentifier='WeeklyBackup-{0:04d}-{1:02d}-{2:02d}'.format(
            now.year, now.month, now.day),
        DBInstanceIdentifier='postgres',
    )

client = boto3.client('rds')

response = client.describe_db_snapshots(
    DBInstanceIdentifier='postgres',
)

now = datetime.datetime.now().replace(tzinfo=None)

response = [r for r in response["DBSnapshots"] if r[
    "DBSnapshotIdentifier"].lower().startswith("weekly")]

if response:
    last_snapshot = sorted(
        response, key=lambda snapshot: snapshot['InstanceCreateTime'], reverse=False)[0]

    if last_snapshot:
        week_ago = now + datetime.timedelta(days=-7)
        print(week_ago)
        print(last_snapshot['InstanceCreateTime'])
        if last_snapshot['InstanceCreateTime'].replace(tzinfo=None) < week_ago:
            create_weekly_backup()
else:
    create_weekly_backup()
