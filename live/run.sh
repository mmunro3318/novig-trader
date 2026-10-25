#!/bin/bash
# restart wrapper: session reconciles from exchange on start; lockfile prevents duplicates
cd /workspace/novig-app/live
end=$(( $(date +%s) + 4*3600 ))
while [ $(date +%s) -lt $end ]; do python3 session.py >> session.out 2>&1; rc=$?; [ $rc -eq 0 ] && break; sleep 5; done
