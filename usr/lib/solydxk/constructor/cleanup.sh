#!/bin/bash

PLYMOUTHTHEME=$1

# Remove fake mime types in kde
if [ -e /usr/share/mime/packages/kde.xml ]; then
  sed -i -e /\<.*fake.*\>/,/^$/d /usr/share/mime/packages/kde.xml
fi

# Write the current up version
if [ -e '/usr/lib/solydxk/updatemanager/files' ]; then
  wget http://repository.solydxk.com/umfiles/repo.info
  if [ -e 'repo.info' ]; then
    VER=$(cat 'repo.info' | grep 'upd=')
    echo $VER > /usr/lib/solydxk/updatemanager/files/updatemanager.hist
    rm 'repo.info'
  fi
fi

# Cleanup
apt-get -y --force-yes clean
apt-get -y --force-yes autoremove
aptitude -y purge ~c
aptitude -y unmarkauto ~M

# Remove unavailable packages
apt-get purge -y --force-yes $(env LANG=C bash -c "apt-show-versions | grep 'available' | cut -d':' -f1")

# Remove orphaned packages
while [ $(deborphan | wc -l) -ne 0 ]; do
  apt-get purge -y --force-yes $(deborphan);
  apt-get purge -y --force-yes $(COLUMNS=132 dpkg -l | grep ^rc | awk '{ print $2 }');
done

for a in $(ls /var/cache/apt/archives | grep '\.deb$' | cut -d _ -f1 | sort | uniq); do
    ls -tr /var/cache/apt/archives/${a}_* | sed '$ d' | xargs -r -p rm -v -f
done

# Disable memtest in Grub
chmod -x /etc/grub.d/20_memtest86+

# Set plymouth theme
if [ "$PLYMOUTHTHEME" != "" ]; then
  plymouth-set-default-theme $PLYMOUTHTHEME
  plymouth-set-default-theme
  update-grub
  update-initramfs -t -u -k all
fi

# Live user in LightDM
if [ -e /etc/lightdm/lightdm.conf ]; then
  sed -i -r 's/^#?(autologin-user)\s*=.*/\1=solydxk/' /etc/lightdm/lightdm.conf
  sed -i -r 's/^#?(autologin-user-timeout)\s*=.*/\1=0/' /etc/lightdm/lightdm.conf
fi

# Set default SolydXK settings
/usr/lib/solydxk/system/adjust.py

# Refresh xapian database
update-apt-xapian-index

# Update database for mlocate
updatedb

# Recreate pixbuf cache
PB='/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders'
if [ -e $PB ]; then
  $PB --update-cache
else
  PB='/usr/lib/i386-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders'
  if [ -e $PB ]; then
    $PB --update-cache
  fi
fi

# Settings for the firewall
modprobe ip_tables
ufw default deny incoming
ufw default allow outgoing
if [ -e "/lib/live/config/1170-openssh-server" ]; then
  ufw allow in 22
fi
ufw enable

# Cleanup temporary files
rm -rf /tmp/*
rm -rf /tmp/.??*
rm -rf /var/tmp/*
rm -rf /var/tmp/.??*
if [ -d /offline ]; then
  rm -rf /offline
fi

# Delete all log files
find /var/log -type f -delete
