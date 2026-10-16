#!/bin/bash
while kill -0 $1 2>/dev/null; do
    sleep 5
done
cd /home/devesh/Downloads
# Overwrite dataset.yaml to be sure
echo -e "path: /kaggle/input/yolo-rgbt-4ch\ntrain: images/train\nval: images/val\nnc: 4\nchannels: 4\nnames:\n  0: person\n  1: crowd\n  2: rider\n  3: uncertain" > YOLO_RGBT_4CH/dataset.yaml
zip -r -q YOLO_RGBT_4CH_Final.zip YOLO_RGBT_4CH
