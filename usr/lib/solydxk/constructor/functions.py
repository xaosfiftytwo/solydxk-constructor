#! /usr/bin/env python3

# Make sure the right Gtk version is loaded
import gi
gi.require_version('Gtk', '3.0')

try:
    import os
    import pwd
    import shutil
    import re
    import operator
    import apt
    import apt_pkg
    import stat
    #import pycurl
    #import io
    import fnmatch
    import urllib.request, urllib.error, urllib.parse
    from os.path import join, exists, abspath, splitext
    from datetime import datetime
    import calendar
    import collections
    from execcmd import ExecCmd
    from gi.repository import Gtk
    import subprocess
except Exception as detail:
    print(detail)
    exit(1)


packageStatus = ['installed', 'notinstalled', 'uninstallable']

# Init
ec = ExecCmd()
cache = apt.Cache()

# General ================================================

def locate(pattern, root=os.curdir, locateDirsOnly=False):
    ret = []
    for path, dirs, files in os.walk(abspath(root)):
        if locateDirsOnly:
            obj = dirs
        else:
            obj = files
        for objname in fnmatch.filter(obj, pattern):
            ret.append(join(path, objname))
    return ret


# Get the login name of the current user
def getUserLoginName():
    p = os.popen('logname', 'r')
    userName = p.readline().strip()
    p.close()
    if userName == "":
        userName = pwd.getpwuid(os.getuid()).pw_name
    return userName


def repaintGui():
    # Force repaint: ugly, but gui gets repainted so fast that gtk objects don't show it
    while Gtk.events_pending():
        Gtk.main_iteration()


# Return the type string of a object
def getTypeString(object):
    tpString = ''
    tp = str(type(object))
    matchObj = re.search("'(.*)'", tp)
    if matchObj:
        tpString = matchObj.group(1)
    return tpString


# Convert string to number
def strToNumber(stringnr, toInt=False):
    nr = 0
    try:
        if toInt:
            nr = int(stringnr)
        else:
            nr = float(stringnr)
    except ValueError:
        nr = 0
    return nr


def getMonthsList():
    months = []
    for x in range(1, 13):
        months.append(datetime(1970, x, 1).strftime('%B'))
    return months


def getDaysInMonth(month=None, year=None):
    if month is None:
        month = datetime.now().month
    if year is None:
        year = datetime.now().year
    return calendar.monthrange(year, month)[1]


# Check if parameter is a list
def isList(lst):
    return isinstance(lst, list)


def areListsEqual(lst1, lst2):
    return collections.Counter(lst1) == collections.Counter(lst2)


# Check if parameter is a list containing lists
def isListOfLists(lst):
    return len(lst) == len([x for x in lst if isList(x)])


# Sort list on given column
def sortListOnColumn(lst, columsList):
    for col in reversed(columsList):
        lst = sorted(lst, key=operator.itemgetter(col))
    return lst


# Return a list with images from a given path
def getImgsFromDir(directoryPath):
    extensions = ['.png', '.jpg', '.jpeg', '.gif']
    imgs = getFilesFromDir(directoryPath, False, extensions)
    return imgs


# Return a list with files from a given path
def getFilesFromDir(directoryPath, recursive=False, extensionList=None):
    if recursive:
        filesUnsorted = getFilesAndFoldersRecursively(directoryPath, True, False)
    else:
        filesUnsorted = os.listdir(directoryPath)
    files = []
    for fle in filesUnsorted:
        if extensionList:
            for ext in extensionList:
                if splitext(fle)[1] == ext:
                    path = join(directoryPath, fle)
                    files.append(path)
                    break
        else:
            path = join(directoryPath, fle)
            files.append(path)
    return files


# Get files and folders recursively
def getFilesAndFoldersRecursively(directoryPath, files=True, dirs=True):
    paths = []
    if exists(directoryPath):
        for dirName, dirNames, fileNames in os.walk(directoryPath):
            if dirs:
                for subDirName in dirNames:
                    paths.append(join(dirName, subDirName + '/'))
            if files:
                for fileName in fileNames:
                    paths.append(join(dirName, fileName))
    return paths


# Replace a string (or regular expression) in a file
def replaceStringInFile(findStringOrRegExp, replString, filePath):
    replString = str(replString)
    if exists(filePath):
        try:
            tmpFile = '%s.tmp' % filePath
            # Get the data
            f = open(filePath)
            data = f.read()
            f.close()
            # Write the temporary file with new data
            tmp = open(tmpFile, "w")
            tmp.write(re.sub(findStringOrRegExp, replString, data))
            tmp.close()
            # Overwrite the original with the temporary file
            shutil.copy(tmpFile, filePath)
            os.remove(tmpFile)
        except:
            print("Cannot replace string: %(findStringOrRegExp)s with %(replString)s in %(filePath)s" % { "findStringOrRegExp": findStringOrRegExp, "replString": replString, "filePath": filePath })


# Create a backup file with date/time
def backupFile(filePath, removeOriginal=False):
    if exists(filePath):
        bak = filePath + '.{0:%Y%m%d_%H%M}.bak'.format(datetime.now())
        shutil.copy(filePath, bak)
        if removeOriginal:
            os.remove(filePath)


# Check if a file is locked
def isFileLocked(path):
    locked = False
    cmd = 'lsof %s' % path
    lsofList = ec.run(cmd, False)
    for line in lsofList:
        if path in line:
            locked = True
            break
    return locked


# Check for string in file
def doesFileContainString(filePath, searchString):
    doesExist = False
    f = open(filePath, 'r')
    cont = f.read()
    f.close()
    if searchString in cont:
        doesExist = True
    return doesExist


# Statusbar =====================================================

def pushMessage(statusbar, message, contextString='message'):
    context = statusbar.get_context_id(contextString)
    statusbar.push(context, message)


def popMessage(statusbar, contextString='message'):
    context = statusbar.get_context_id(contextString)
    statusbar.pop(context)


# System ========================================================

# Get linux-headers and linux-image package names
# If getLatest is set to True, the latest version of the packages is returned rather than the packages for the currently booted kernel.
# includeLatestRegExp is a regular expression that must be part of the package name (in conjuction with getLatest=True).
# excludeLatestRegExp is a regular expression that must NOT be part of the package name (in conjuction with getLatest=True).
def getLinuxHeadersAndImage(getLatest=False, includeLatestRegExp='', excludeLatestRegExp=''):
    returnList = []
    lhList = []
    if getLatest:
        lst = ec.run('aptitude search -w 150 linux-headers', False)
        for item in lst:
            lhMatch = re.search('linux-headers-\d+\.[a-zA-Z0-9-\.]*', item)
            if lhMatch:
                lh = lhMatch.group(0)
                addLh = True
                if includeLatestRegExp != '':
                    inclMatch = re.search(includeLatestRegExp, lh)
                    if not inclMatch:
                        addLh = False
                if excludeLatestRegExp != '':
                    exclMatch = re.search(excludeLatestRegExp, lh)
                    if exclMatch:
                        addLh = False

                # Append to list
                if addLh:
                    lhList.append(lh)
    else:
        # Get the current linux header package
        linHeader = ec.run('echo linux-headers-$(uname -r)', False)
        lhList.append(linHeader[0])

    # Sort the list and add the linux-image package name
    if lhList:
        lhList.sort(reverse=True)
        returnList.append(lhList[0])
        returnList.append('linux-image-' + lhList[0][14:])
    return returnList


# Get the host's installed EFI architecture (x86_64 or i386)
def getHostEfiArchitecture():
    return ec.run("ls /usr/lib/grub/ 2> /dev/null | grep efi | cut -d'-' -f1", False, False).strip()


# Get the possible EFI architecture of the target environment (x86_64 or i386)
def getGuestEfiArchitecture(rootPath):
    ret = ''
    if exists(rootPath):
        ret = 'i386'
        output = subprocess.check_output("file {}/bin/ls".format(rootPath), shell=True).decode('utf-8').strip()
        if 'x86-64' in output:
            ret = 'x86_64'
    return ret


# Get the system's video cards
def getVideoCards(pciId=None):
    videoCard = []
    cmdVideo = 'lspci -nn | grep VGA'
    hwVideo = ec.run(cmdVideo, False)
    for line in hwVideo:
        videoMatch = re.search(':\s(.*)\[(\w*):(\w*)\]', line)
        if videoMatch and (pciId is None or pciId.lower() + ':' in line.lower()):
            videoCard.append([videoMatch.group(1), videoMatch.group(2), videoMatch.group(3)])
    return videoCard


# Get system version information
def getSystemVersionInfo():
    info = ''
    try:
        infoList = ec.run('cat /proc/version', False)
        if infoList:
            info = infoList[0]
    except Exception as detail:
        print("ERROR (functions.getSystemVersionInfo: %(detail)s" % {"detail": detail})
    return info


# Get the system's distribution
def getDistribution(returnBaseDistribution=True):
    distribution = ''
    if returnBaseDistribution:
        sysInfo = getSystemVersionInfo().lower()
        if 'debian' in sysInfo:
            distribution = 'debian'
        elif 'ubuntu' in sysInfo:
            distribution = 'ubuntu'
        elif 'arm' in sysInfo:
            distribution = 'arm'
    else:
        if exists('/etc/solydxk/info'):
            lst = ec.run("cat /etc/solydxk/info | grep EDITION | cut -d'=' -f 2", False)
            if lst:
                distribution = lst[0]
    return distribution


# Get the system's distribution
def getDistributionDescription():
    distribution = ''
    try:
        cmdDist = 'cat /etc/*-release | grep DISTRIB_DESCRIPTION'
        dist = ec.run(cmdDist, False)[0]
        distribution = dist[dist.find('=') + 1:]
        distribution = distribution.replace('"', '')
    except Exception as detail:
        print("ERROR (functions.getDistributionDescription: %(detail)s" % {"detail": detail})
    return distribution


# Get the system's distribution
def getDistributionReleaseNumber():
    release = 0
    try:
        cmdRel = 'cat /etc/*-release | grep DISTRIB_RELEASE'
        relLst = ec.run(cmdRel, False)
        if relLst:
            rel = relLst[0]
            release = rel[rel.find('=') + 1:]
            release = release.replace('"', '')
            release = strToNumber(release)
    except Exception as detail:
        print("ERROR (functions.getDistributionReleaseNumber: %(detail)s" % {"detail": detail})
    return release


# Get the system's desktop
def getDesktopEnvironment():
    desktop_environment = 'generic'
    if os.environ.get('KDE_FULL_SESSION') == 'true':
        desktop_environment = 'kde'
    elif os.environ.get('GNOME_DESKTOP_SESSION_ID'):
        desktop_environment = 'gnome'
    elif os.environ.get('MATE_DESKTOP_SESSION_ID'):
        desktop_environment = 'mate'
    else:
        try:

            info = ec.run('xprop -root _DT_SAVE_MODE', False, False)
            if ' = "xfce4"' in info:
                desktop_environment = 'xfce'
        except (OSError, RuntimeError):
            pass
    return desktop_environment


# Get valid screen resolutions
def getResolutions(minRes='', maxRes='', reverseOrder=False, getVesaResolutions=False):
    cmd = None
    cmdList = ['640x480', '800x600', '1024x768', '1280x1024', '1600x1200']

    if getVesaResolutions:
        vbeModes = '/sys/bus/platform/drivers/uvesafb/uvesafb.0/vbe_modes'
        if exists(vbeModes):
            cmd = "cat %s | cut -d'-' -f1" % vbeModes
        elif isPackageInstalled('v86d') and isPackageInstalled('hwinfo'):
            cmd = "sudo hwinfo --framebuffer | grep '0x0' | cut -d' ' -f5"
    else:
        cmd = "xrandr | grep '^\s' | cut -d' ' -f4"

    if cmd is not None:
        cmdList = ec.run(cmd, False)
    # Remove any duplicates from the list
    resList = list(set(cmdList))

    avlRes = []
    avlResTmp = []
    minW = 0
    minH = 0
    maxW = 0
    maxH = 0

    # Split the minimum and maximum resolutions
    if 'x' in minRes:
        minResList = minRes.split('x')
        minW = strToNumber(minResList[0], True)
        minH = strToNumber(minResList[1], True)
    if 'x' in maxRes:
        maxResList = maxRes.split('x')
        maxW = strToNumber(maxResList[0], True)
        maxH = strToNumber(maxResList[1], True)

    # Fill the list with screen resolutions
    for line in resList:
        for item in line.split():
            itemChk = re.search('\d+x\d+', line)
            if itemChk:
                itemList = item.split('x')
                itemW = strToNumber(itemList[0], True)
                itemH = strToNumber(itemList[1], True)
                # Check if it can be added
                if itemW >= minW and itemH >= minH and (maxW == 0 or itemW <= maxW) and (maxH == 0 or itemH <= maxH):
                    avlResTmp.append([itemW, itemH])

    # Sort the list and return as readable resolution strings
    avlResTmp.sort(key=operator.itemgetter(0), reverse=reverseOrder)
    for res in avlResTmp:
        avlRes.append(str(res[0]) + 'x' + str(res[1]))
    return avlRes


# Check the status of a package
def getPackageStatus(packageName):
    status = ''
    try:
        pkg = cache[packageName]
        if pkg.is_installed and pkg._pkg.current_state == apt_pkg.CURSTATE_INSTALLED:
            # Package is installed
            status = packageStatus[0]
        elif not pkg.is_installed and pkg._pkg.current_state == apt_pkg.CURSTATE_NOT_INSTALLED:
            # Package is not installed
            status = packageStatus[1]
        else:
            # If something went wrong: assume that package is uninstallable
            status = packageStatus[2]
    except:
        # Package is not found: uninstallable
        status = packageStatus[2]

    return status


# Check if a package is installed
def isPackageInstalled(packageName, alsoCheckVersion=True):
    isInstalled = False
    try:
        pkg = cache[packageName]
        if (not pkg.is_installed or
            pkg._pkg.current_state != apt_pkg.CURSTATE_INSTALLED or
            cache._depcache.broken_count > 0):
            isInstalled = False
        elif alsoCheckVersion:
            if pkg.installed.version == pkg.candidate.version:
                isInstalled = True
        else:
            isInstalled = True
    except:
        pass
    return isInstalled


# Check if a package exists
def doesPackageExist(packageName):
    exists = False
    try:
        cache[packageName]
        exists = True
    except:
        pass
    return exists


# List all dependencies of a package
def getPackageDependencies(packageName, reverseDepends=False):
    retList = []
    try:
        if reverseDepends:
            cmd = 'apt-cache rdepends %s | grep "^ "' % packageName
            depList = ec.run(cmd, False)
            if depList:
                for line in depList:
                    if line[0:2] != 'E:':
                        matchObj = re.search('([a-z0-9\-]+)', line)
                        if matchObj:
                            if matchObj.group(1) != '':
                                retList.append(matchObj.group(1))
        else:
            pkg = cache[packageName]
            deps = pkg.candidate.get_dependencies("Depends")
            for basedeps in deps:
                for dep in basedeps:
                    retList.append(dep.name)
    except:
        pass
    return retList


# List all packages with a given installed file name
def getPackagesWithFile(fileName):
    packages = []
    if len(fileName) > 0:
        cmd = 'dpkg -S %s' % fileName
        packageList = ec.run(cmd, False)
        for package in packageList:
            if '*' not in package:
                packages.append(package[:package.find(':')])
    return packages


# Check if a process is running
def isProcessRunning(processName):
    isProc = False
    cmd = 'ps -C %s' % processName
    procList = ec.run(cmd, False)
    if procList:
        if len(procList) > 1:
            isProc = True
    return isProc


# Kill a process by name and return success
def killProcessByName(processName):
    killed = False
    lst = ec.run('killall -I -q %s' % processName)
    if len(lst) == 0:
        killed = True
    return killed


# Get the package version number
def getPackageVersion(packageName, candidate=False):
    version = ''
    try:
        cache = apt.Cache()
        pkg = cache[packageName]
        if candidate:
            version = pkg.candidate.version
        elif pkg.installed is not None:
            version = pkg.installed.version
    except:
        pass
    return version


# Get the package description
def getPackageDescription(packageName, firstLineOnly=True):
    descr = ''
    try:
        cache = apt.Cache()
        pkg = cache[packageName]
        descr = pkg.installed.description
        if firstLineOnly:
            lines = descr.split('\n')
            if lines:
                descr = lines[0]
    except:
        pass
    return descr


# Check if system has wireless (not necessarily a wireless connection)
def hasWireless():
    wi = getWirelessInterface()
    if wi is not None:
        return True
    else:
        return False


# Get the wireless interface (usually wlan0)
def getWirelessInterface():
    wi = None
    rtsFound = False
    cmd = 'iwconfig'
    wiList = ec.run(cmd, False)
    for line in reversed(wiList):
        if not rtsFound:
            reObj = re.search('\bRTS\b', line)
            if reObj:
                rtsFound = True
        else:
            reObj = re.search('^[a-z0-9]+', line)
            if reObj:
                wi = reObj.group(0)
                break
    return wi


# Check if we're running live
def isRunningLive():
    live = False
    liveDirs = ['/live', '/lib/live/mount', '/rofs']
    for ld in liveDirs:
        if exists(ld):
            live = True
            break
    return live


# Get diverted files
# mustContain is a string that must be found in the diverted list items
def getDivertedFiles(mustContain=None):
    divertedFiles = []
    cmd = 'dpkg-divert --list'
    if mustContain:
        cmd = 'dpkg-divert --list | grep %s | cut -d' ' -f3' % mustContain
    divertedFiles = ec.run(cmd, False)
    return divertedFiles


# Check for internet connection
def hasInternetConnection(testUrl='http://google.com'):
    try:
        urllib.request.urlopen(testUrl, timeout=1)
        return True
    except urllib.error.URLError:
        pass
    return False


# Get default terminal
def getDefaultTerminal():
    terminal = None
    cmd = "update-alternatives --display x-terminal-emulator"
    terminalList = ec.run(cmd, False)
    for line in terminalList:
        reObj = re.search("\'(\/.*)\'", line)
        if reObj:
            terminal = reObj.group(1)
    return terminal


# Get an estimated bandwidth speed
#def getBandwidthSpeed():
    #testFile = 'http://downloads.solydxk.com/.speedtest/10mb.bin'
    #speed = 0
    #c = pycurl.Curl()
    #buff = io.StringIO()
    #c.setopt(pycurl.URL, testFile)
    #c.setopt(pycurl.CONNECTTIMEOUT, 10)
    #c.setopt(pycurl.TIMEOUT, 100)
    #c.setopt(pycurl.FOLLOWLOCATION, 1)
    #c.setopt(pycurl.WRITEFUNCTION, buff.write)
    #try:
        #c.perform()
        #return_code = c.getinfo(pycurl.HTTP_CODE)
        #if (return_code == 200):
            #speed = c.getinfo(pycurl.SPEED_DOWNLOAD)
            #speed = int(round(speed / 1000))
            #log("Download speed = %dKbps" % speed)
        #else:
            #log("getBandwidthSpeed returns HTTP code %d" % return_code)
    #except pycurl.error as error:
        #errno, errstr = error
        #log("ERROR: getBandwidthSpeed() - %s" % errstr)

    #return speed


# Ownership to current user
def chownCurUsr(path):
    if exists(path):
        uid = os.getuid()
        gid = os.getgid()
        os.chown(path, uid, gid)


# Make file executable
def makeExecutable(path):
    if exists(path):
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC)


# Get current user home directory
def getUserDir():
    usr = pwd.getpwuid(os.getuid()).pw_name
    return pwd.getpwnam(usr).pw_dir


# Get active network interface
def getNetworkInterface():
    interface = None
    found = False
    cmd = '/sbin/ifconfig'
    ifList = ec.run(cmd)
    for line in reversed(ifList):
        if not found:
            reObj = re.search('inet.*bcast.*', line, re.I)
            if reObj:
                found = True
        else:
            reObj = re.search('^[a-z0-9]+', line, re.I)
            if reObj:
                interface = reObj.group(0)
                break
    return interface


# Find regular expression in string
def findRegExpInString(regExp, searchStr, groupNr=0, caseSensitive=False):
    ret = None
    if caseSensitive:
        reObj = re.search(regExp, searchStr)
    else:
        reObj = re.search(regExp, searchStr, re.I)
    if reObj:
        ret = reObj.group(groupNr)
    return ret


# Get the contents of a file
def getFileContents(path):
    cont = None
    if exists(path):
        f = open(path, 'r')
        cont = f.read()
        f.close()
    return cont
