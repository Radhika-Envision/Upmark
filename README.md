This is the Aquamark application - a web-based survey tool for assessing
water management utilities.

![Aquamark Logo](doc/aquamark_logo.png)

## Deployment

Build with:

```bash
sudo docker build -t vpac/aquamark src/app
```

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

Clone the repository and build the image.

```bash
cd /home/ubuntu

git clone https://github.com/vpac-innovations/aquamark.git
# Enter your username and password
sudo docker build -t vpac/aquamark /home/ubuntu/aquamark/src/app
```

Edit the watchdog config file and add your email credentials. Then test that the
email function works.

```bash
nano /home/ubuntu/aquamark/src/util/watchdog.config
/home/ubuntu/aquamark/src/util/watchdog.py --test
```

Start the container with restart option, and the watchdog task.

```bash
sudo docker run -d --name aquamark \
    --restart=always \
    -e ANALYTICS_ID=<your analytics ID> \
    -e DATABASE_URL=<as specified by AWS RDS> \
    vpac/aquamark
crontab /home/ubuntu/aquamark/src/util/watchdog
```

### AWS Auto scaling group

AWS Auto-scaling group supports dynamically scalibility upgrading for the service. Not
only used for Scaling services but used for fault tollerance purpose. So AWS EC2 instances
will be automatically created instance with the image we created.

Here are the steps of the creating auto-scaling group.
1. Create AMI images for current running instance.
    1. Right click on AWS console.
    1. Click Image > Create Image button. 
    1. Create image.
    1. This process takes a bit while. You can check the process on IMAGES > AMIs menu.
1. Create Load Balacer
    1. LOAD BALANCING > Load Balancers > Create
    1. Process with default option and proper names
1. Create Autoscaling
    1. AUTO SCALING > Launch Configurations
        1. Configure Auto Scaling group details
            1. Put in how many instance you need to prepare for scaling, Select proper network
            1. On advanced tab - check `Receive traffic from Elastic Load Balancer(s)` option and select load balancer which is previously created
        1. Configure scaling policies - You can specify condition of scale up or scale down of the instacnes
    1. AUTO SCALING > Auto Scaling Groups
        1. Create Launch Configuration > My AMIs 
        1. Select AMI which created before
        1. Choose same instance type (default)
        1. At `Configure details`, you need to expand `Advanced details` field and type in `docker restart aq` on User data
        1. Choose same storage space with images


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
    -e DEBUG_MODE=True \
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
