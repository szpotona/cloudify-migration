#!/bin/bash

DATA_FILE="cloudify_migration_data_metrics_gf35.tar.gz"

sudo rm -Rf /opt/influxdb/shared/data/*
sudo tar -xf $DATA_FILE -C /

rm -f $DATA_FILE

