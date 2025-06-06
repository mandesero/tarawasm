#!/bin/bash

if [ "$1" == "pip" ]; then
    shift
    exec pip "$@"
else
    exec /app/target/tarawasm "$@"
fi
