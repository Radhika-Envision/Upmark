## Deployment on AWS

These intructions are for creating a scalable installation on [AWS].

First, create an RDS instance. Choose Postgres as the engine and an appropriate
instance type. You might like to start with a *db.t2.medium* instance type with
100GB of SSD. Set the DB Instance Identifier to something meaningful, like
"aquamark", and don't allow public access.
Make sure automated backups are enabled and stored for 7 days (the maximum).

After creation, you will probably need to configure the RDS instance's security
group to allow connections from hosts in the subnet you're using for the web
servers.

Then create an instance that will be used to build the application, using a
*t2.small* instance type. Choose *ubuntu-trusty-14.04* as the base
image (AMI). Then log in to the new machine, clone the repository and build the
Docker image.

1. Install dependencies:

    ```bash
    sudo locale-gen en_AU en_AU.UTF-8
    sudo apt-get install git make curl python3-pip
    curl -fsSL https://get.docker.com/ | sh
    ```

    `python3-pip` is only needed for the watchdog script.

1. [Create a deployment key][ck] for the git repository:

    ```bash
    ssh-keygen -t rsa -b 4096 -C "aws+your@email.com"
    ```

   It doesn't need a password, because:

      1. It's only going to be used to get the source of the application.
      1. It won't have write access to the repository.
      1. The source code will be cloned to the instance anyway.

   Then [add the key][ak] to the GitHub project as a read-only deployment key.

1. Build the Docker image:

    ```bash
    cd /home/ubuntu

    git clone git@github.com:vpac-innovations/aquamark.git
    cd aquamark
    make
    ```

1. Copy the config files to a new directory, and edit them to suit your needs:

    ```
    cp -a src/app/config ~/aq_conf
    nano ~/aq_conf/aq.conf
    ```

    - `ANALYTICS_ID` is your Google Analytics ID (if you have one).
    - `DATABASE_URL` should be updated to use the RDS endpoint. It should be
      something like `postgresql://postgres:PASSWORD@postgres.foo.ap-southeast-2.rds.amazonaws.com:5432/postgres`
    - `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are the credentials of
      the AWS IAM user who has access to the aquamark bucket.

1. Initialise the database:

    ```
    sudo docker run --rm vpac/aquamark alembic upgrade head
    ```

[ck]: https://help.github.com/articles/generating-ssh-keys/
[ak]: https://developer.github.com/guides/managing-deploy-keys/#deploy-keys

Now start the web server. Tell it to restart if it goes down, so when we spin up
a new instance from the AMI it will start automatically.

```bash
sudo docker run -d --name aquamark \
    --restart=always \
    --env-file=/home/ubuntu/aq_conf/aq.conf \
    -p 80:8000 \
    vpac/aquamark
```

Check that it's running:

```bash
curl -w "\n" http://localhost/ping
# Should print "Web services are UP"
```

Edit the watchdog config file and add your email credentials. Then test that the
email function works.

```bash
nano src/util/watchdog.yaml
sudo ./src/util/watchdog-install-deps.sh
./src/util/watchdog.py --test
```

If the test passes (you should receive an email), install the cron job:

```bash
./src/util/watchdog-install.sh
```

Now create an AMI of the instance from the AWS console. This AMI will be used by
the scaling group to start new instances. You can now delete the instance that
was used to make the AMI.

[AWS]: https://aws.amazon.com/

### AWS Auto scaling group

First create a load balancer. This will be reused for all deployments.

1. Create Load Balacer
    1. LOAD BALANCING > Load Balancers > Create Load Balancer
    1. Ensure HTTP and HTTPS are enabled. Both should forward to port 80 on the
       instances. Don't worry, HTTP will be redirected to HTTPS by the web app.
       For HTTPS, install your SSL certificate.
    1. Under *Configure Health Check*, make sure the following settings are
       used:

        - Ping Protocol: `HTTP`
        - Ping Port: `80`
        - Ping Path: `/ping`

       The default ping path of `/index.html` can't be used because that page
       requires authentication. `/ping` is serviced by a special handler.

1. DNS
    1. Assign the domain name to the load balancer IP (use your domain registrar
       to do this).

Now create the auto-scaling group.

1. Create an instance and install Aquamark on it, as described in the previous
   section.

1. Create an AMI image for current running instance.
    1. Select the image in the AWS console under EC2 > Instances.
    1. Click Actions > Image > Create Image button. Give the AMI a name like
       `aq-web-v1.0.1-1`. Allow the process to reboot the instance so a good
       copy of the hard drive is taken.
    1. Create the image. This process takes a while. You can check the process
       in the IMAGES > AMIs screen.

1. Create Autoscaling Group

    1. AUTO SCALING > Launch Configurations > Create launch configuration
        1. Choose the AMI you created in the previous step.
        1. Under *Configure Details*, give this new configuration a similar
           name to the AMI.
            1. No IAM role is required because the AWS API key is set in the AMI.
            1. Under *Advanced Details > IP Address Type*, select *Assign a
               public IP address to every instance*. This is requred because we
               don't have NAT set up for the VPC.
        1. Under *Add Storage*, change the hard drive type to *General SSD*. The
           default size of 20GB should be fine.
        1. Under *Configure Security Group*, choose a group that allows web and
           SSH traffic (ports 80 and 22) *for the local subnet* for the
           machine's availability zone (AZ) e.g. `172.31.0.0/20`. Check your VPC
           configuration if you're not sure. Do not allow connections from
           0.0.0.0/32.

           HTTPS is not required because that is handled by the load balancer.

    1. AUTO SCALING > Launch Configurations > Create Auto Scaling Group
        1. Configure Auto Scaling group details
            1. Put in how many instances you need to prepare for scaling, Select
               a subnet that is not visible from the outside world, but which
               can be accessed from the load balancer.
            1. On advanced tab - check `Receive traffic from Elastic Load
               Balancer(s)` option and select load balancer which was previously
               created
        1. Configure scaling policies - You can specify condition of scale up or
           scale down of the instances

       This scaling group will create instances that are not accessible from the
       public Internet. To connect to the machine, either go via the load
       balancer (HTTP, HTTPS) or hop via another EC2 machine for SSH. For
       example:

       ```
       ssh -o ProxyCommand="ssh  -q -W %h:%p ubuntu@<public IP> -i <key file.pem>" \
           ubuntu@<internal IP> -i <key file.pem>
       ```

       The key file does *not* need to be copied to the hop computer.


### Recalculation daemon

Some changes happen asynchronously, in an [eventually consistent][ec] manner.
Recalculation of scores takes a long time, so when the survey structure changes
the [recalculation is done by a daemon][rd], instead of when the author saves
their changes.
It happens every so often in a background service with Docker container on the
[backup machine][db]. It uses the same Docker image as the currently working web
app, so it should be upgraded at the same time as the web app.

First, copy [the config file][recalc] and edit it to contain your preferred mail
settings:

```bash
mkdir -p ~/aq_conf
cp src/app/config/recalculate.yaml ~/aq_conf/
nano ~/aq_conf/recalculate.yaml
echo DATABASE_URL="<DATABASE_URL>" > ~/aq_conf/aq.conf
```

Important: If you are using Amazon SES, don't use port 25 for SMTP, because it's
throttled. [Use 587 instead][587].

Make sure the image has been built, and launch the script in a container:

```bash
make
sudo docker run -d --name recalc \
    --env-file=$HOME/aq_conf/aq.conf \
    -v $HOME/aq_conf:/usr/share/aquamark/app/config \
    --restart=always \
    vpac/aquamark:latest python3 ./server/recalculate.py
```

[ec]: https://en.wikipedia.org/wiki/Eventual_consistency
[db]: ../database/README.md
[rd]: ../src/app/server/recalculate.py
[recalc]: ../src/app/config/recalculate.yaml
[587]: http://docs.aws.amazon.com/ses/latest/DeveloperGuide/smtp-connect.html


### Notification daemon

The notification daemon provides regular activity notification to users. Each
user will receive emails about recent activity in Upmark. The process runs
often (every hour or so), but only sends emails according to each user's
nominated notification frequency. It uses the same Docker image as the web
app - and it connects to the same database - so it should be upgraded at the
same time as the web app.

First, copy [the config file][noti] and edit it to contain your preferred mail
settings:

```bash
mkdir -p ~/aq_conf
cp src/app/config/notification.yaml ~/aq_conf/
nano ~/aq_conf/notification.yaml
echo DATABASE_URL="<DATABASE_URL>" > ~/aq_conf/aq.conf
```

Important: If you are using Amazon SES, don't use port 25 for SMTP, because it's
throttled. [Use 587 instead][587].

Now make sure the image has been built, and launch the script in a container:

```bash
make
sudo docker run -d --name notify \
    --env-file=$HOME/aq_conf/aq.conf \
    -v $HOME/aq_conf:/usr/share/aquamark/app/config \
    --restart=always \
    vpac/aquamark:latest python3 ./server/notifications.py
```

[db]: ../database/README.md
[noti]: ../src/app/config/notification.yaml


### Upgrading

Create an instance from the former Aquamark AMI: in the AWS console, choose
*EC2 > IMAGES > AMIs*, then select the image and choose *Actions > Launch*. A
*t1.micro* machine should be sufficient.

Under *Configure Security Group*, choose a security group that allows SSH (but
probably not anything else). If you want to test the web services, open an [SSH
tunnel]. This is important because the machine may have access to confidential
data but the connection may not be encrypted.

Launch the instance. When you do so, you will be prompted to choose an SSH key.
Make sure you choose one that you have access to. You can create a new one if
you need to; when you download it, save it to `~/.ssh/` and give it permissions
of `400`. Then connect to the machine:

```
ssh ubuntu@<host> -i <key file.pem>
```

Check the current configuration (you may need to reuse some of it), then delete
the current Docker instance. Remember to delete the volumes with the `-v`
switch:

```
sudo docker inspect aquamark
sudo docker rm -fv aquamark
```

Update the source code, and check out the branch you're interested in. Discard
local changes. Replace `v1.0.1` with the branch, tag or ref you're
interested in.

```
cd aquamark
git fetch
git reset --hard HEAD
git checkout v1.0.1
```

Now build the Docker image and start a fresh `aquamark` instance as described
above. There is no need to reinstall the watchdog crontab if it was installed
previously, because it will automatically refer to the new file (provided the
path in the source code has not changed).

Follow the process for creating a new AWS launch configuration and
scaling group using the new instance to create the AMI. Add it to the existing
load balancer. After the new scaling group is active, delete the old one and
ensure the old instances have stopped.

Finally, if there have been any database schema changes, run alembic and then
make sure the daemons are updated too.
See [Recalculation daemon](#recalculation-daemon).

**Important:** The old scaling group must be deleted, or some users will see the
old site.


[SSH tunnel]: http://blog.trackets.com/2014/05/17/ssh-tunnel-local-and-remote-port-forwarding-explained-with-examples.html
