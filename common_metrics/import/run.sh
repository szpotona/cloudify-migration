#!/bin/bash

DATA_FILE="cloudify_migration_data_metrics_gf35.tar.gz"

sudo rm -Rf /opt/influxdb/shared/data/*
sudo tar -xf $DATA_FILE -C /
sudo pkill -9 influxdb

rm -f $DATA_FILE

