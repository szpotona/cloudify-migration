#!/bin/bash

OLD_MAGIC_PATH="/tmp/cloudify_migration_data_metrics_53hot.tar.gz"

sudo tar -czf $OLD_MAGIC_PATH  /opt/influxdb/shared/data

