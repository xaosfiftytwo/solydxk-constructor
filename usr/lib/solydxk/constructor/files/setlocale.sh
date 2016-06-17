#!/bin/bash

# Extra locale specific packages
# When adding locales: change code at the bottom of this script
zh_TW='libthai0 fonts-thai-tlwg im-config fcitx fcitx-table-thai fcitx-sunpinyin fcitx-libpinyin fcitx-googlepinyin fcitx-frontend-gtk3 fcitx-ui-classic fcitx-config-gtk'
zh_SG='fonts-arphic-ukai fonts-arphic-uming im-config fcitx fcitx-sunpinyin fcitx-libpinyin fcitx-googlepinyin fcitx-frontend-gtk3 fcitx-ui-classic fcitx-config-gtk'
zh_HK='fonts-arphic-ukai fonts-arphic-uming im-config fcitx fcitx-table-cantonhk fcitx-sunpinyin fcitx-libpinyin fcitx-googlepinyin fcitx-frontend-gtk3 fcitx-ui-classic fcitx-config-gtk'
zh_CN='fonts-arphic-ukai fonts-arphic-uming im-config fcitx fcitx-sunpinyin fcitx-libpinyin fcitx-googlepinyin fcitx-frontend-gtk3 fcitx-ui-classic fcitx-config-gtk'
ko_KR='fonts-unfonts* im-config fcitx fcitx-hangul fcitx-frontend-gtk3 fcitx-ui-classic fcitx-config-gtk'
ja_JP='fonts-vlgothic fonts-takao im-config fcitx fcitx-mozc fcitx-frontend-gtk3 fcitx-ui-classic fcitx-config-gtk mozc-utils-gui'

# --force-yes is deprecated in stretch
FORCE='--force-yes'
VER=$(head -c 1 /etc/debian_version | sed 's/[a-zA-Z]/0/' 2>/dev/null || echo 0)
if [ "$VER" -eq 0 ] || [ "$VER" -gt 8 ]; then
  FORCE='--allow-downgrades --allow-remove-essential --allow-change-held-packages'
fi

# Check if package is installed
function isInstalled() {
    PKG=$(dpkg-query -l $1 | grep ^i)
    if [ "${PKG:0:1}" == "i" ]; then
        return 0
    else
        return 1
    fi
}

# Check if package exists in the repositories
function doesExist() {
    PKG=$(apt-cache pkgnames | grep ^"$1"$)
    if [ "$PKG" == "$1" ]; then
        return 0
    else
        return 1
    fi
}

# Change FF/TB prefs.js file
function localizePref() {
    PREF=$1
    PRM=$2
    VAL=$3
    if [ -f $PREF ]; then
        if grep -q $PRM "$PREF"; then
            sed -i -e "s/.*$PRM.*/user_pref(\"$PRM\", \"$VAL\");/" "$PREF"
        else
            echo "user_pref(\"$PRM\", \"$VAL\");" >> "$PREF"
        fi
    fi
}

# Change live configuration
function localizeLive() {
    LIVE='/etc/live/config.conf'
    if [ -f $LIVE ]; then
        PRM=$1
        VAL=$2
        if grep -q $PRM "$LIVE"; then
            sed -i -e "s/.*$PRM.*/export $PRM=\"$VAL\"" "$LIVE"
        else
            echo "export $PRM=\"$VAL\"" >> "$LIVE"
        fi
    fi
}

# Set locale
#echo "$LOC.UTF-8 UTF-8" >> /etc/locale.gen
#locale-gen
#update-locale LANG="$LOC.UTF-8"
dpkg-reconfigure locales
. /etc/default/locale
LOC=$(echo $LANG | cut -d'.' -f 1)
LOC1=$(echo $LOC | cut -d'_' -f 1)
LOC2U=$(echo $LOC | cut -d'_' -f 2)
LOC2L=${LOC2U,,}


# Set timezone
dpkg-reconfigure  tzdata
TIMEZONE=$(cat /etc/timezone)
cp -vf /usr/share/zoneinfo/$TIMEZONE /etc/localtime

# Live configuration
localizeLive 'LIVE_LOCALES' "$LANG"
localizeLive 'LIVE_TIMEZONE' "$TIMEZONE"
localizeLive 'LIVE_UTC' 'no'

# Update cache before installing packages
apt-get update

# KDE
if isInstalled "kde-runtime"; then
    echo "Localizing KDE..."
    if doesExist "kde-l10n-$LOC1$LOC2L"; then
        apt-get install --yes $FORCE kde-l10n-$LOC1$LOC2L
    else
        apt-get install --yes $FORCE kde-l10n-$LOC1
    fi
fi

# LibreOffice
if isInstalled "libreoffice"; then
    echo "Localizing LibreOffice..."
    if doesExist "libreoffice-l10n-$LOC1-$LOC2L"; then
        apt-get install --yes $FORCE libreoffice-l10n-$LOC1-$LOC2L
        apt-get install --yes $FORCE libreoffice-help-$LOC1-$LOC2L
        apt-get install --yes $FORCE myspell-$LOC1-$LOC2L
    else
        apt-get install --yes $FORCE libreoffice-l10n-$LOC1
        apt-get install --yes $FORCE libreoffice-help-$LOC1
        apt-get install --yes $FORCE myspell-$LOC1
    fi
fi

# Firefox ESR
if isInstalled "firefox-esr"; then
    echo "Localizing Firefox ESR..."
    LAN="$LOC1-$LOC2U"
    if doesExist "firefox-esr-l10n-$LOC1-$LOC2L"; then
        apt-get install --yes $FORCE firefox-esr-l10n-$LOC1-$LOC2L
    else
        LAN=$LOC1
        apt-get install --yes $FORCE firefox-esr-l10n-$LOC1
    fi
    PREF='/etc/skel/.mozilla/firefox/mwad0hks.default/prefs.js'
    localizePref $PREF 'spellchecker.dictionary' $LOC
    localizePref $PREF 'extensions.qls.visiblemenuitems' "$LAN#en-US"
    localizePref $PREF 'extensions.qls.contentlocale' "$LAN"
    localizePref $PREF 'extensions.qls.locale' "$LAN"
    localizePref $PREF 'general.useragent.locale' "$LAN"
fi

# Firefox
if isInstalled "firefox"; then
    echo "Localizing Firefox..."
    LAN="$LOC1-$LOC2U"
    if doesExist "firefox-l10n-$LOC1-$LOC2L"; then
        apt-get install --yes $FORCE firefox-l10n-$LOC1-$LOC2L
    else
        LAN=$LOC1
        apt-get install --yes $FORCE firefox-l10n-$LOC1
    fi
    PREF='/etc/skel/.mozilla/firefox/mwad0hks.default/prefs.js'
    localizePref $PREF 'spellchecker.dictionary' $LOC
    localizePref $PREF 'extensions.qls.visiblemenuitems' "$LAN#en-US"
    localizePref $PREF 'extensions.qls.contentlocale' "$LAN"
    localizePref $PREF 'extensions.qls.locale' "$LAN"
    localizePref $PREF 'general.useragent.locale' "$LAN"
fi

# Thunderbird
if isInstalled "thunderbird"; then
    echo "Localizing Thunderbird..."
    LAN="$LOC1-$LOC2U"
    if doesExist "thunderbird-l10n-$LOC1-$LOC2L"; then
        apt-get install --yes $FORCE thunderbird-l10n-$LOC1-$LOC2L
    else
        LAN=$LOC1
        apt-get install --yes $FORCE thunderbird-l10n-$LOC1
    fi
    PREF='/etc/skel/.thunderbird/pjzwmea6.default/prefs.js'
    localizePref $PREF 'spellchecker.dictionary' $LOC1
    localizePref $PREF 'extensions.qls.visiblemenuitems' "$LAN#en-US"
    localizePref $PREF 'extensions.qls.contentlocale' "$LAN"
    localizePref $PREF 'extensions.qls.locale' "$LAN"
    localizePref $PREF 'general.useragent.locale' "$LAN"
fi

# Install locale specific packages
if [ "$LOC" == "zh_TW" ]; then apt-get install --yes $FORCE $zh_TW; fi
if [ "$LOC" == "zh_SG" ]; then apt-get install --yes $FORCE $zh_SG; fi
if [ "$LOC" == "zh_HK" ]; then apt-get install --yes $FORCE $zh_HK; fi
if [ "$LOC" == "zh_CN" ]; then apt-get install --yes $FORCE $zh_CN; fi
if [ "$LOC" == "ko_KR" ]; then apt-get install --yes $FORCE $ko_KR; fi
if [ "$LOC" == "ja_JP" ]; then apt-get install --yes $FORCE $ja_JP; fi
