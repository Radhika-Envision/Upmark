## Provisioning

Launch an Ubuntu 16.04 machine. Usually the security group should be set
so that only local SSH and Web ports are open.


## Building

```
sudo apt-get update
sudo apt-get install docker.io docker-compose
git clone git@github.com:vpac-innovations/upmark.git
cd upmark
cp -a src/app/config ../u-conf
nano ../u-conf/upmark.conf
sudo docker-compose build web-standalone
```


## Running

```
sudo docker-compose up -d web-standalone
```


## Database management

```
sudo docker-compose run --rm dbadmin-standalone
```
