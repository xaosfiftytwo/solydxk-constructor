#!/bin/bash

# Remove old kernel and headers
VERSION=$(ls -al / | grep -e "\svmlinuz\s" | cut -d'/' -f2 | cut -d'-' -f2,3)
echo "=================================="
echo "Current kernel version: $VERSION"
echo "=================================="
if [ "$VERSION" != "" ]; then
  apt-get purge $(apt search linux-image-[0-9] linux-headers-[0-9] | grep ^i | grep -v "$VERSION" | egrep -v "[a-z]-486|[a-z]-686|[a-z]-586" | awk '{print $2}')
  KBCNT=$(apt search linux-kbuild | grep ^i | wc -l)
  if [ $KBCNT -gt 1 ]; then
    apt-get purge $(apt search linux-kbuild | grep ^i | egrep -v ${VERSION%-*} | awk '{print $2}'| head -n 1)
  fi
fi
echo "=================================="
echo "Try to fix if anything is broken"
echo "=================================="
apt-get -f install
echo "=================================="
echo "Check installed image and headers (wait 10s before closing)"
echo "list: linux-image, linux-headers, linux-kbuild"
echo "=================================="
apt search linux-image linux-headers linux-kbuild | grep ^i
sleep 10
