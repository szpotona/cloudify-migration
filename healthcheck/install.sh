#!/bin/bash

set -eax

virtualenv env
. env/bin/activate
pip install -r requirements.txt

