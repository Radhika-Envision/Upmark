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
sudo docker run --name aquamark vpac/aquamark
```

For the development use this to run docker
1. for the postgresql
```bash
sudo docker run --name postgres -e POSTGRES_PASSWORD=mysecretpassword -d postgres
```
2. link postgre to aquamark
```bash
sudo docker run -d --name aquamark -p 8000:8000 -v "$YOUR_GIT_ROOT/src/app:/usr/share/aquamark" --link postgres:postgres vpac/aquamark
```

## Dependencies

Client-side scripts are managed with Bower, which will automatically download
them when the application stats (see `start.sh`). When running in release
mode, the application will automatically use CDNs for some scripts and CSS
files, and will minify the others. If you add a dependency or change its
version number, you **must** make sure the versions specified in `bower.json`
and in `server/handlers.py` are the same.
