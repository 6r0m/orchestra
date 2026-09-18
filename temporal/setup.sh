#!/bin/sh
# One-shot setup steps of the Temporal stack, each safe to run on every start.
#   schema    - create or upgrade the two PostgreSQL schemas the server needs
#   namespace - create the orchestration namespace and pin its retention
set -eu

NAMESPACE=orchestration
# Closed runs stay readable for this long; the CLI's own default is 3 days.
RETENTION=90d

sql() {
    temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" -u temporal -p 5432 --db "$@"
}

schema() {
    for db in temporal temporal_visibility; do
        dir=temporal
        [ "$db" = temporal_visibility ] && dir=visibility
        # A database that exists already has a schema; only a new one needs creating.
        if ! sql "$db" update-schema -d "/etc/temporal/schema/postgresql/v12/$dir/versioned"; then
            sql "$db" create
            sql "$db" setup-schema -v 0.0
            sql "$db" update-schema -d "/etc/temporal/schema/postgresql/v12/$dir/versioned"
        fi
    done
}

namespace() {
    if temporal operator namespace describe -n "$NAMESPACE" >/dev/null 2>&1; then
        temporal operator namespace update -n "$NAMESPACE" --retention "$RETENTION"
    else
        temporal operator namespace create -n "$NAMESPACE" --retention "$RETENTION"
    fi
    temporal operator namespace describe -n "$NAMESPACE"
}

"$1"
