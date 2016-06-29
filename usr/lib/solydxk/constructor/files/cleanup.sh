#!/bin/bash

# Packages that deborphan must NOT treat as orphans - comma separated list
NotOrphan='baloo'

# Prefered plymouth theme
# This can be a partial string or regular expression
PREFEREDPLYMOUTHTHEME="solyd.*flat"

# --force-yes is deprecated in stretch
FORCE='--force-yes'
source /etc/lsb-release
if [[ -z "$DISTRIB_RELEASE" ]] || [ "$DISTRIB_RELEASE" -gt 8 ]; then
  FORCE='--allow-downgrades --allow-remove-essential --allow-change-held-packages'
fi


function sed_append_sting {
  PATTERN=$1
  LINE=$2
  FLE=$3
  
  if [ -e $FLE ]; then
    if grep -q $PATTERN "$FLE"; then
      # Escape forward slashes
      LINE=$(echo $LINE | sed 's/\//\\\//g')
      sed -i -e "s/$PATTERN/$LINE/" $FLE
    else
      echo $LINE >> $FLE
    fi
  fi
}


if [ -e /usr/share/mime/packages/kde.xml ]; then
  echo "> Remove fake mime types in KDE"
  sed -i -e /\<.*fake.*\>/,/^$/d /usr/share/mime/packages/kde.xml
fi


if which gconftool-2 >/dev/null; then
  echo "> Set gconf default settings"
  gconftool-2 --direct --config-source xml:readwrite:/etc/gconf/gconf.xml.defaults --type bool --set /apps/gksu/sudo-mode true
  gconftool-2 --direct --config-source xml:readwrite:/etc/gconf/gconf.xml.defaults --type bool --set /apps/gksu/display-no-pass-info false
  gconftool-2 --direct --config-source xml:readwrite:/etc/gconf/gconf.xml.defaults --type string --set /apps/blueman/transfer/browse_command "thunar --browser obex://[%d]"
fi

if [ -e '/usr/lib/solydxk/updatemanager/files' ]; then
  echo "> Write the current up version"
  timeout -s KILL 15 wget http://repository.solydxk.com/umfiles/repo.info
  if [ -e 'repo.info' ]; then
    VER=$(cat 'repo.info' | grep 'upd=')
    echo $VER > /usr/lib/solydxk/updatemanager/files/updatemanager.hist
    rm 'repo.info'
  fi
fi

AUTOFILE='/usr/lib/solydxk/updatemanager/files/updatemanagertray.desktop'
AUTODEST='/etc/xdg/autostart'
if [ -f "$AUTOFILE" ] && [ -d "$AUTODEST" ]; then
  echo "> Make the updatemanager autostart"
  cp -f "$AUTOFILE" "$AUTODEST/"
fi

echo "> Make sure all firmware drivers are installed but don't install from backports"
FIRMWARE=$(aptitude search ^firmware | grep ^p | awk '{print $2}')
for F in $FIRMWARE; do
  STABLE=$(apt-cache policy $F | grep 500 2>/dev/null)
  if [ "$STABLE" != "" ]; then
    sudo apt-get -y $FORCE install $F
  fi
done

echo "> Cleanup"
apt-get -y $FORCE clean
apt-get -y $FORCE autoremove
aptitude -y purge ~c
aptitude -y unmarkauto ~M
find . -type f -name "*.dpkg*" -exec rm {} \;

echo "> Remove unavailable packages only when not manually held back"
for PCK in $(env LANG=C apt-show-versions | grep 'available' | cut -d':' -f1); do
  REMOVE=true
  for HELDPCK in $(env LANG=C dpkg --get-selections | grep hold$ | awk '{print $1}'); do
    if [ $PCK == $HELDPCK ]; then
      REMOVE=false
    fi
  done
  if $REMOVE; then
    if [[ "$NotOrphan" =~ "$PCK" ]]; then
      echo "Not available but keep installed: $PCK"
    else
      apt-get purge -y $FORCE $PCK
    fi
  fi
done

echo "> Removing orphaned packages, except the ones listed in NotOrphan"
Exclude=${NotOrphan//,/\/d;/}
Orphaned=$(deborphan | sed '/'$Exclude'/d')
while [ "$Orphaned" ]; do
  apt-get -y $FORCE purge $Orphaned
  RC=$(dpkg-query -l | sed -n 's/^rc\s*\(\S*\).*/\1/p')
  [ "$RC" ] && apt-get -y $FORCE purge $RC
  Orphaned=$(deborphan | sed '/'$Exclude':/d')
done

echo "> Disable memtest in Grub"
chmod -x /etc/grub.d/20_memtest86+

PLYMOUTHTHEME=$(plymouth-set-default-theme)
if [[ ! "$PLYMOUTHTHEME" =~ $PREFEREDPLYMOUTHTHEME ]]; then
  echo "> Set plymouth theme"
  PLYMOUTHTHEMES=$(plymouth-set-default-theme -l)
  for PT in $PLYMOUTHTHEMES; do
    # Check for preferred theme
    if [[ "$PT" =~ $PREFEREDPLYMOUTHTHEME ]]; then
      PLYMOUTHTHEME=$PT
      break
    fi
  done
  if [ "$PLYMOUTHTHEME" != "" ]; then
    plymouth-set-default-theme -R $PLYMOUTHTHEME
    echo "Plymouth theme set: $(plymouth-set-default-theme)"
    update-grub
  fi
fi

echo "> Configure LightDM"
CONF='/etc/lightdm/lightdm-kde-greeter.conf'
if [ -e '/etc/lightdm/lightdm-gtk-greeter.conf' ]; then
  CONF='/etc/lightdm/lightdm-gtk-greeter.conf'
fi
   
if [ -e /usr/bin/startxfce* ]; then
  sed_append_sting '^background\s*=.*' 'background=/usr/share/images/desktop-base/solydx-lightdmbg-flat.png' $CONF
  sed_append_sting '^theme-name\s*=.*' 'theme-name=greybird-solydx' $CONF
elif [ -e /usr/bin/startkde* ]; then
  sed_append_sting '^background\s*=.*' 'background=/usr/share/images/desktop-base/solydk-lightdmbg-flat.png' $CONF
  sed_append_sting '^theme-name\s*=.*' 'theme-name=greybird-solydk-gtk3' $CONF
else
  sed_append_sting '^background\s*=.*' 'background=' $CONF
  sed_append_sting '^theme-name\s*=.*' 'theme-name=' $CONF
fi
sed_append_sting '^default-user-image\s*=.*' 'default-user-image=/usr/share/pixmaps/faces/user-generic.png' $CONF
    
CONF='/etc/lightdm/lightdm.conf'
if [ -e $CONF ]; then
  sed -i -e '/^greeter-hide-users\s*=/ c greeter-hide-users=false' $CONF
  sed -i -r 's/^#?(autologin-user)\s*=.*/\1=solydxk/' $CONF
  sed -i -r 's/^#?(autologin-user-timeout)\s*=.*/\1=0/' $CONF
fi

CONF='/etc/lightdm/users.conf'
if [ -e $CONF ]; then
  sed -i -e '/^minimum-uid\s*=/ c minimum-uid=1000' $CONF
fi

echo "> Set default SolydXK settings"
/usr/lib/solydxk/system/adjust.py

echo "> Refresh xapian database"
update-apt-xapian-index

echo "> Update database for mlocate"
updatedb

echo "> Update geoip database"
if [ -e /usr/sbin/update-geoip-database ]; then
  /usr/sbin/update-geoip-database
fi

# Update pixbuf cache
PB='/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders'
if [ ! -e $PB ]; then
  PB='/usr/lib/i386-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders'
fi
if [ -e $PB ]; then
  echo "> Update pixbuf cache"
  $PB --update-cache
fi

echo "> Setup the firewall"
ufw default deny incoming
ufw default allow outgoing
ufw allow CIFS
ufw enable

echo "> Cleanup temporary files"
rm -rf /media/*
rm -rf /var/backups/*
rm -rf /tmp/*
rm -rf /tmp/.??*
rm -rf /var/tmp/*
rm -rf /var/tmp/.??*
if [ -d /offline ]; then
  rm -rf /offline
fi

echo "> Cleanup all log files"
find /var/log -type f -delete

echo "> Delete grub.cfg: it will be generated during install"
rm -rf /boot/grub/grub.cfg

# Removing redundant kernel module structure(s) from /lib/modules (if any)
VersionPlusArch=$(ls -l /vmlinuz | sed 's/.*\/vmlinuz-\(.*\)/\1/')
L=${#VersionPlusArch}
for I in /lib/modules/*; do
   if [ ${I: -$L} != $VersionPlusArch ] && [ ! -d $I/kernel ]; then
      echo "> Removing redundant kernel module structure: $I"
      rm -fr $I
   fi
done
