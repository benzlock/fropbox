#!/usr/bin/env sh

python3 -u /fropbox/server.py &
sleep 1
python3 -u /fropbox/client.py /source
