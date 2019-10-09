#!/bin/bash

projdir=$(dirname $0)
python3 -m unittest discover ${projdir} "$@"
