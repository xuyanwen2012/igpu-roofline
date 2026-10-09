#!/bin/bash
# reuse_queue.sh: device side. Three focused runs, one after the other (one measuring process at a time).
cd ~/roofline-study-20261010
F="--plan fast --stage matrix_feed --no-sustain"
./reuse_device.sh shared $F --variant matrix_int8_16x16x32_c2_lds --variant matrix_fp16_16x16x16_c4_lds --variant matrix_fp16_fp32_16x16x16_c2_lds
./reuse_device.sh cache-c4 $F --variant matrix_fp16_fp32_16x16x16_c4_gmem
./reuse_device.sh cache-c2 $F --variant matrix_fp16_fp32_16x16x16_c2_gmem
echo "QUEUE_DONE $(date -u +%FT%TZ)" > reuse-confirm/queue.status
