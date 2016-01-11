This is the Asset Management Customer Value (AMCV) application - a web-based
survey tool for comparing organisations that manage large numbers of assets,
such as water utilities.

![AMCV Logo](doc/amcv_logo.png)

For historical reasons, the source code and build instructions may refer to
AMCV's former name, "Aquamark". Generally "AMCV" is only used in the user
interface.

## Deployment

Build with:

```bash
make
```

For custom builds, refer to the Docker command in the [Makefile](Makefile).

Run with:

```bash
sudo docker run -d --name postgres_aq postgres:9
crontab src/util/watchdog
sudo docker run -d --name aquamark \
    --link postgres_aq:postgres \
    -e ANALYTICS_ID=foo \
    vpac/aquamark
```

Where `ANALYTICS_ID` is a [Google Analytics][ga] ID. Omit that option to disable
analytics.

The first time the server is started, a default user is created:

 * Email: admin
 * Password: admin

The first thing you should do is log in as that user and change the password.
You might also want to change other details about the default user and
organisation.

[ga]: http://www.google.com.au/analytics/


## Deployment on AWS

Create an instance (e.g. t1.micro). Choose *ubuntu-trusty-14.04* as the base
image (AMI). Then log in to the new machine, clone the repository and build the
Docker image.

1. Install dependencies:

    ```bash
    sudo apt-get install git make
    wget -qO- https://get.docker.com/ | sudo sh
    ```

1. [Create a deployment key][ck] for the git repository:

    ```bash
    ssh-keygen -t rsa -b 4096 -C "aws+your@email.com"
    ```

    Then [add the key][ak] to the GitHub project.

1. Build the Docker image:

    ```bash
    cd /home/ubuntu

    git clone https://github.com/vpac-innovations/aquamark.git
    cd aquamark
    make
    ```

[ck]: https://help.github.com/articles/generating-ssh-keys/
[ak]: https://developer.github.com/guides/managing-deploy-keys/#deploy-keys

Edit the watchdog config file and add your email credentials. Then test that the
email function works.

```bash
nano /home/ubuntu/aquamark/src/util/watchdog.config
/home/ubuntu/aquamark/src/util/watchdog.py --test
```

Create a file `/home/ubuntu/aq.conf` to contain environment variables so they
can be easily reused for future deployments. The file should contain the
following data:

```bash
ANALYTICS_ID=<your analytics ID> \
DATABASE_URL=<as specified by AWS RDS> \
AWS_ACCESS_KEY_ID=<KEY ID> \
AWS_SECRET_ACCESS_KEY=<ACCESS KEY> \
```

Now start the container with restart option, and install the watchdog task.

```bash
sudo docker run -d --name aquamark \
    --restart=always \
    --env-file=/home/ubuntu/aq.conf \
    -p 80:8000 \
    vpac/aquamark
crontab /home/ubuntu/aquamark/src/util/watchdog
```

The database URL will be something like
`postgresql://postgres:PASSWORD@postgres.foo.ap-southeast-2.rds.amazonaws.com:5432/postgres`.

Check that it's running:

```bash
curl -w "\n" http://localhost/ping
# Should print "Web services are UP"
```

Now create an AMI of the instance from the AWS console. This AMI will be used by
the scaling group to start new instances. You can now delete the instance that
was used to make the AMI.

### AWS Auto scaling group

AWS Auto-scaling group supports dynamically scalibility upgrading for the
service. Not only used for Scaling services but used for fault tollerance
purpose. So AWS EC2 instances will be automatically created instance with the
image we created. Most of these instructions should be performed in the AWS
console.

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

Here are the steps of the creating auto-scaling group.

1. Create an instance and install Aquamark on it, as described in the previous
   section.

1. Create AMI images for current running instance.
    1. Select the image in the AWS console under EC2 > Instances.
    1. Click Actions > Image > Create Image button. Give the AMI a name like
       `aq-web-v1.0.1`. Allow the process to reboot the instance so a good copy
       of the hard drive is taken.
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
       ssh ubuntu@<internal IP> -i <key file.pem> \
           -o ProxyCommand="ssh  -q -W %h:%p ubuntu@<public IP> -i <key file.pem>"
       ```

       The key file does *not* need to be copied to the hop computer.


### Recalculation daemon

Some changes happen asynchronously, in an [eventually consistent][ec] manner.
Recalculation of scores takes a long time, so when the survey structure changes
the [recalculation is done by a daemon][rd], instead of when the author saves
their changes.
It happens every so often in a background service with Docker container on the
[backup machine][db]. It uses same Docker image as the currently working web
app, so it should be upgraded at the same time as the web app.


```bash
docker run -d --name recalc \
    -e DATABASE_URL=<DATABASE_URL> \
    --restart=always \
    vpac/aquamark python3 ./app/server/recalculate.py
```

[ec]: https://en.wikipedia.org/wiki/Eventual_consistency
[db]: database/README.md
[rd]: src/app/server/recalculate.py


### Notification daemon

The notification daemon provides regular activity notification to users. Each
user will receive emails about recent activity in AMCV. The process runs
often (every hour or so), but only sends emails according to each user's
nominated notification frequency. It uses the same Docker image as the web
app - and it connects to the same database - so it should be upgraded at the
same time as the web app.

First, copy [the config file][noti] and edit it to contain your preferred mail
settings:

```bash
cp src/app/server/notification.yaml.SAMPLE src/app/server/notification.yaml
nano src/app/server/notification.yaml
```

```bash
docker run -d --name noti \
    -e DATABASE_URL=<DATABASE_URL> \
    --restart=always \
    vpac/aquamark python3 ./app/server/notification.py
```

[db]: database/README.md
[noti]: src/app/server/notification.yaml.SAMPLE


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

Finally, if there have been any database schema changes, make sure the daemons
are updated too. See [Recalculation daemon](#recalculation-daemon).

**Important:** The old scaling group must be deleted, or some users will see the
old site.


[SSH tunnel]: http://blog.trackets.com/2014/05/17/ssh-tunnel-local-and-remote-port-forwarding-explained-with-examples.html


## Development

The easiest way to run during development is to start a Docker container as
shown above, but mount your code as a volume. Changes you make to the code will
automatically apply to the running container. This way you don't need to worry
about creating a database. Also, expose the web server's port - then you can
just connect to http://localhost:8000 for testing.

```bash
sudo docker run -d --name postgres_aq postgres:9
sudo docker run --rm --name aq \
    --link postgres_aq:postgres \
    -v "$PWD/src/app:/usr/share/aquamark/app" \
    -p 8000:8000 \
    -e DEV_MODE=True \
    vpac/aquamark
```


## Admin Tool

Some tasks can be performed from the command line using `admin.py`. For example,
to create a new organisation:

```bash
sudo docker run -it --rm --link postgres_aq:postgres vpac/aquamark \
    app/server/admin.py org 'ACME Water' \
        --region=Melbourne \
        --url='http://acme-water.com.au' \
        --customers=2000
```

To create a new user:

```bash
sudo docker run -it --rm --link postgres_aq:postgres vpac/aquamark \
    app/server/admin.py user sue@acme-water.com.au \
        --name='Sue Green' \
        --role=clerk \
        --org='ACME Water'
```

Run `admin.py -h` for more options.


## Dependencies

Client-side scripts are managed with Bower, which will automatically download
them when the application stats (see `start.sh`). When running in release
mode, the application will automatically use CDNs for some scripts and CSS
files, and will minify the others. If you add a dependency or change its
version number, you **must** make sure the versions specified in `bower.json`
and in `server/handlers.py` are the same.


## Debugging

You can debug the web server with the intereactive debugger, pudb. To do so,
edit the file you want to debug and import the `pudb` module. Then add a call to
`set_trace` to add a breakpoint. For example:

```diff
class ResponseHistoryHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, assessment_id, measure_id):
+       import pudb
+       pudb.set_trace()
        with model.session_scope() as session:
            # Current version
```

Then start the container with an interactive TTY:

```
sudo docker-compose run --service-ports web
```

Or if you're not using docker-compose, add the `-it` to your Docker run command.

Next time you make an appropriate web request, the breakpoint will be triggered
and you will have an interactive debugger in your console.
