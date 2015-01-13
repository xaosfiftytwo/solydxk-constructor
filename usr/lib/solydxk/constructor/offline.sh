#!/bin/bash

# Set the architecture for download
ARCH=$1
if [ "$ARCH" != "amd64" ] && [ "$ARCH" != "i386" ]; then
  M=$(uname -m)
  if [ "$M" == "x86_64" ]; then
    ARCH="amd64"
  else
    ARCH="i386"
  fi
fi

#echo ">>> Start dowloading packages ($ARCH)"
if [ -d offline ]; then
  rm -r offline
fi
mkdir offline
cd offline
#apt-get update
#echo ">>> Run command: apt-get --print-uris --yes install grub-efi:$ARCH | grep ^\' | cut -d\' -f2"
wget `apt-get --print-uris --yes install grub-efi:$ARCH | grep ^\' | cut -d\' -f2`
cd ../
