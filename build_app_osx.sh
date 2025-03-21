#!/bin/bash

source env/bin/activate

rm -rf build dist

python3.11 setup.py py2app && echo "✅ all done"

deactivate 
