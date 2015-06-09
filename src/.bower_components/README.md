This is the directory where the Bower-managed web resources will be placed. This
happens automatically on startup.

# Location

This directoy is not kept inside the `app` directory, because it makes working
with Docker nicer:

 - The Docker build downloads the dependencies and stores them here.
 - A developer can use `-v` to override the `app` directory without overriding
   the Bower files.
 - Bower files are linked to the application using a symlink.
