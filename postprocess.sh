#!/bin/bash

if [[ $1 == *.mkv ]]
then
    mkvpropedit "$1" --edit track:a1 --set language=eng --edit track:v1 --set language=eng
    echo "Ran MKV Prop Edit"
fi

python /home/wils/server_configs/plex/scripts/postprocess.py -i "$1" --transcode
