#!/bin/bash
# WikiMovieRec cron wrapper.
# Runs the Wikipedia collector only if no model training is in progress
# (to avoid overloading the 1.9GB server).

set -e
cd /root/WikiMovieRec

# If a training process (src.main) is running, skip collection.
if pgrep -f "src.main --train" > /dev/null 2>&1; then
    echo "$(date): training in progress, skipping collection" >> logs/wiki_cron.log
    exit 0
fi

# Run collector (incremental/resumable; lock file prevents parallel runs).
.venv/bin/python collect_wiki_movies.py --max-movies 20000 --out wp_movies_extended.ndjson >> logs/wiki_cron.log 2>&1

echo "$(date): collection run finished" >> logs/wiki_cron.log