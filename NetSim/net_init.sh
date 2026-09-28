#!/bin/sh
#Download ns-3.27

if [ ! -d "ns-allinone-3.27" ]; then
    wget -nc https://www.nsnam.org/releases/ns-allinone-3.27.tar.bz2
    tar xvf ns-allinone-3.27.tar.bz2
fi

HOME_DIR=$(pwd)
echo $HOME_DIR
NS3_HOME=$HOME_DIR/ns-allinone-3.27/ns-3.27
PATCH_PATH=$HOME_DIR/patches

#cd $NS3_HOME
ls -lrt
#patch the wscript file
if [ ! -f "$NS3_HOME/wscript_original" ]; then
    cp $NS3_HOME/wscript $NS3_HOME/wscript_original
    #cp $PATCH_PATH/wscript.patch .
    patch $NS3_HOME/wscript -i $PATCH_PATH/wscript.patch -o $NS3_HOME/wscript_out
    mv $NS3_HOME/wscript_out $NS3_HOME/wscript

    #patch other files
    cp $NS3_HOME/src/applications/model/packet-sink.h $NS3_HOME/src/applications/model/packet-sink.h_original
    patch $NS3_HOME/src/applications/model/packet-sink.h -i $PATCH_PATH/packet-sink.h.patch  -o $NS3_HOME/src/applications/model/packet-sink.h_out
    mv $NS3_HOME/src/applications/model/packet-sink.h_out $NS3_HOME/src/applications/model/packet-sink.h
fi
#cp $NS3_HOME/src/mobility/model/constant-position-mobility-model.h $NS3_HOME/src/mobility/model/constant-position-mobility-model.h_original
#patch $NS3_HOME/src/mobility/model/constant-position-mobility-model.h -i $PATCH_PATH/constant-position-mobility-model.h.patch -o $NS3_HOME/src/mobility/model/constant-position-mobility-model.h_out
#mv $NS3_HOME/src/mobility/model/constant-position-mobility-model.h_out $NS3_HOME/src/mobility/model/constant-position-mobility-model.h


#Configure and build ns-3
cd $NS3_HOME
./waf configure --disable-werror
./waf -j $(nproc)

#Copy the uav-sim code to ns-3 scratch folder
cp -r $HOME_DIR/uav-net-sim $NS3_HOME/scratch/
cp $HOME_DIR/config.xml $NS3_HOME/
chmod 644 $NS3_HOME/config.xml
