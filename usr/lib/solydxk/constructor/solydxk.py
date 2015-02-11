#! /usr/bin/env python3
#-*- coding: utf-8 -*-

import re
import threading
from os import remove, rmdir, makedirs, system, listdir
from shutil import copy, move
from datetime import datetime
from execcmd import ExecCmd
from os.path import join, exists, basename, abspath, dirname, lexists, isdir


class IsoUnpack(threading.Thread):

    def __init__(self, mountDir, unpackIso, unpackDir, queue):
        threading.Thread.__init__(self)
        self.ec = ExecCmd()
        self.mountDir = mountDir
        self.unpackIso = unpackIso
        self.unpackDir = unpackDir
        self.queue = queue
        self.returnMessage = None

    def run(self):
        try:
            if not exists(self.mountDir):
                print(("Create mount directory: %s" % self.mountDir))
                makedirs(self.mountDir)

            rootDir = join(self.unpackDir, "root")
            if not exists(rootDir):
                print(("Create root directory: %s" % rootDir))
                makedirs(rootDir)

            isolinuxDir = join(self.unpackDir, "boot/isolinux")
            if not exists(isolinuxDir):
                print(("Create isolinux directory: %s" % isolinuxDir))
                makedirs(isolinuxDir)

            liveDir = join(self.unpackDir, "boot/live")
            if not exists(liveDir):
                print(("Create liveDir directory: %s" % liveDir))
                makedirs(liveDir)

            # Mount the ISO
            system("mount -o loop '%s' '%s'" % (self.unpackIso, self.mountDir))

            # Check isolinux directory
            mountIsolinux = join(self.mountDir, "isolinux")
            if not exists(mountIsolinux):
                self.ec.run("umount --force '%s'" % self.mountDir)
                self.returnMessage = "ERROR: Cannot find isolinux directory in ISO"

            fixCfgCmd = None
            dirs = []
            mountSquashfs = None
            if self.returnMessage is None:
                subdirs = self.getDirectSubDirectories(self.mountDir)
                for subdir in subdirs:
                    if self.hasSquashFs(join(self.mountDir, subdir)):
                        mountSquashfs = join(self.mountDir, subdir)
                        if subdir != "live":
                            fixCfgCmd = "sed -i 's/\/%s/\/live/g' %s/isolinux.cfg" % (subdir, isolinuxDir)
                    elif subdir != "isolinux":
                        dirs.append(join(self.mountDir, subdir))

                if mountSquashfs is None:
                    self.ec.run("umount --force '%s'" % self.mountDir)
                    self.returnMessage = "ERROR: Cannot find squashfs directory in ISO"

            if self.returnMessage is None:
                # Copy files from ISO to unpack directory
                for d in dirs:
                    self.ec.run("rsync -at --del '%s' '%s'" % (d, join(self.unpackDir, "boot/")))
                self.ec.run("rsync -at --del '%s/' '%s'" % (mountIsolinux, isolinuxDir))
                self.ec.run("rsync -at --del '%s/' '%s'" % (mountSquashfs, liveDir))
                self.ec.run("umount --force '%s'" % self.mountDir)

                if fixCfgCmd is not None:
                    self.ec.run(fixCfgCmd)

                # copy squashfs root
                squashfs = join(liveDir, "filesystem.squashfs")
                if exists(squashfs):
                    self.ec.run("mount -t squashfs -o loop '%s' '%s'" % (squashfs, self.mountDir))
                    self.ec.run("rsync -at --del '%s/' '%s/'" % (self.mountDir, rootDir))
                    self.ec.run("umount --force '%s'" % self.mountDir)

                # Cleanup
                rmdir(self.mountDir)
                # set proper permissions
                self.ec.run("chmod 6755 '%s'" % join(rootDir, "usr/bin/sudo"))
                self.ec.run("chmod 0440 '%s'" % join(rootDir, "etc/sudoers"))

                # save iso_name
                cfgFile = join(isolinuxDir, "isolinux.cfg")
                isoNameFile = join(self.unpackDir, "iso_name")
                isoName = "SolydXK"
                cfgCont = None
                with open(cfgFile, 'r') as f:
                    cfgCont = f.read()
                reObj = re.search("Solyd.*\-bit", cfgCont)
                if reObj:
                    isoName = reObj.group(0).strip()
                with open(isoNameFile, 'w') as f:
                    f.write(isoName)

                self.returnMessage = "DONE - ISO unpacked to: %s" % self.unpackDir

            self.queue.put(self.returnMessage)

        except Exception as detail:
            self.ec.run("umount --force '%s'" % self.mountDir)
            rmdir(self.mountDir)
            self.returnMessage = "ERROR: IsoUnpack: %(detail)s" % {"detail": detail}
            self.queue.put(self.returnMessage)

    def getDirectSubDirectories(self, directory):
        subdirs = []
        names = listdir(directory)
        for name in names:
            if isdir(join(directory, name)):
                subdirs.append(name)
        return subdirs

    def hasSquashFs(self, directory):
        names = listdir(directory)
        for name in names:
            if name == "filesystem.squashfs":
                return True
        return False


class BuildIso(threading.Thread):

    def __init__(self, distroPath, queue):
        threading.Thread.__init__(self)
        self.ec = ExecCmd()
        self.dg = DistroGeneral(distroPath)
        self.ed = EditDistro(distroPath)
        self.queue = queue

        self.returnMessage = None

        # Paths
        distroPath = distroPath.rstrip('/')
        if basename(distroPath) == "root":
            distroPath = dirname(distroPath)
        self.distroPath = distroPath
        self.rootPath = join(distroPath, "root")
        self.bootPath = join(distroPath, "boot")
        self.livePath = join(self.bootPath, "live")
        self.scriptDir = abspath(dirname(__file__))

        # Check for old dir
        oldDir = join(self.bootPath, "solydxk")
        if exists(oldDir):
            self.ec.run("rm -r %s" % oldDir)

        # Make sure live directory exists
        if not exists(self.livePath):
            self.ec.run("mkdir -p %s" % self.livePath)

        # ISO Name
        self.isoName = self.dg.getIsoName()
        d = datetime.now()
        self.dateString = d.strftime("%Y%m")
        self.fullIsoName = "%(isoName)s %(dateString)s" % {"isoName": self.isoName, "dateString": self.dateString}

        # ISO distribution
        self.distribution = self.dg.getDistribution()
        if self.distribution is None:
            self.distribution = basename(distroPath)
        self.isoBaseName = "%(distribution)s_%(dateString)s.iso" % {"distribution": self.distribution, "dateString": self.dateString}
        self.isoFileName = join(self.distroPath, self.isoBaseName)

        # Trackers, and webseeds
        self.trackers = ""
        self.webseeds = ""
        trackersPath = join(self.scriptDir, "trackers")
        webseedsPath = join(self.scriptDir, "webseeds")
        if exists(trackersPath):
            with open(trackersPath, "r") as f:
                lines = f.readlines()
                trList = []
                for line in lines:
                    trList.append(line.strip())
                self.trackers = ",".join(trList)
        if exists(webseedsPath):
            with open(webseedsPath, "r") as f:
                lines = f.readlines()
                wsList = []
                #webseedIsoName = "%s_latest.iso" % self.distribution
                for line in lines:
                    #wsList.append("%s/%s" % (line.strip(), webseedIsoName))
                    wsList.append("%s/%s" % (line.strip(), self.isoBaseName))
                self.webseeds = ",".join(wsList)

    def run(self):
        try:
            if not exists(self.rootPath):
                self.returnMessage = "ERROR: Cannot find root directory: %s" % self.rootPath

            if not exists(self.bootPath):
                self.returnMessage = "ERROR: Cannot find boot directory: %s" % self.bootPath

            if self.returnMessage is None:
                print("======================================================")
                print("INFO: Cleanup and prepare ISO build...")
                print("======================================================")

                # Clean-up
                cleanup = "cleanup.sh"
                if exists(join(self.scriptDir, cleanup)):
                    copy(join(self.scriptDir, cleanup), join(self.rootPath, cleanup))
                    self.ec.run("chmod a+x %s" % join(self.rootPath, cleanup))
                    plymouthTheme = self.dg.getPlymouthTheme()
                    #self.ec.run("chroot '%(rootPath)s' /bin/bash %(cleanup)s %(plymouthTheme)s" % {"rootPath": self.rootPath, "cleanup": cleanup, "plymouthTheme": plymouthTheme})
                    cmd = "/bin/bash %(cleanup)s %(plymouthTheme)s" % {"cleanup": cleanup, "plymouthTheme": plymouthTheme}
                    self.ed.openTerminal(cmd)
                    remove(join(self.rootPath, cleanup))

                rootHome = join(self.rootPath, "root")
                nanoHist = join(rootHome, ".nano_history")
                if exists(nanoHist):
                    remove(nanoHist)
                bashHist = join(rootHome, ".bash_history")
                if exists(bashHist):
                    remove(bashHist)

                # write iso name to boot/isolinux/isolinux.cfg
                cfgFile = join(self.bootPath, "isolinux/isolinux.cfg")
                sedstring = "sed -ie 's/\(menu title Welcome to \).*/\\1%(isoName)s/' %(cfg)s" % {"isoName": self.fullIsoName, "cfg": cfgFile}
                self.ec.run(sedstring)

                # Make sure that the paths are correct (correcting old stuff)
                self.ec.run("sed -ie 's/.lz/.img/g' %s" % cfgFile)
                self.ec.run("sed -ie 's/\/solydxk/\/live/g' %s" % cfgFile)

                # Write info for grub (EFI)
                grubFile = join(self.bootPath, "boot/grub/grub.cfg")
                if exists(grubFile):
                    content = ""
                    with open(grubFile, 'r') as f:
                        content = f.read()
                    if content != "":
                        content = re.sub("Start.*\d", "Start %s" % self.fullIsoName, content)
                        with open(grubFile, 'w') as f:
                            f.write(content)

                loopbackFile = join(self.bootPath, "boot/grub/loopback.cfg")
                if exists(loopbackFile):
                    content = ""
                    with open(loopbackFile, 'r') as f:
                        content = f.read()
                    if content != "":
                        content = re.sub("Start.*\d", "Start %s" % self.fullIsoName, content)
                        with open(loopbackFile, 'w') as f:
                            f.write(content)

                # Clean boot/live directory
                #popen("rm -rf %s/live/*" % self.bootPath)

                # Vmlinuz
                vmlinuzSymLink = join(self.distroPath, "root/vmlinuz")
                if lexists(vmlinuzSymLink):
                    vmlinuzFile = self.ec.run("ls -al %s | cut -d'>' -f2" % vmlinuzSymLink)[0].strip()
                else:
                    self.returnMessage = "ERROR: %s not found" % vmlinuzSymLink

            if self.returnMessage is None:
                vmlinuzPath = join(self.distroPath, "root/%s" % vmlinuzFile)
                if exists(vmlinuzPath):
                    print("Copy vmlinuz")
                    copy(vmlinuzPath, join(self.livePath, "vmlinuz"))
                else:
                    self.returnMessage = "ERROR: %s not found" % vmlinuzPath

            if self.returnMessage is None:
                # Initrd
                initrdSymLink = join(self.distroPath, "root/initrd.img")
                if lexists(initrdSymLink):
                    initrdFile = self.ec.run("ls -al %s | cut -d'>' -f2" % initrdSymLink)[0].strip()
                else:
                    self.returnMessage = "ERROR: %s not found" % initrdSymLink

            if self.returnMessage is None:
                initrdPath = join(self.distroPath, "root/%s" % initrdFile)
                if exists(initrdPath):
                    print("Copy initrd")
                    copy(initrdPath, join(self.livePath, "initrd.img"))
                else:
                    self.returnMessage = "ERROR: %s not found" % initrdPath

            if self.returnMessage is None:
                # Generate UUID
                #diskDir = join(self.bootPath, ".disk")
                #if not exists(diskDir):
                    #makedirs(diskDir)
                #self.ec.run("rm -rf %s/*uuid*" % diskDir)
                #self.ec.run("uuidgen -r > %s/live-uuid-generic" % diskDir)
                #copy(join(diskDir, "live-uuid-generic"), join(diskDir, "live-uuid-generic"))

                #Update filesystem.size
                #self.ec.run("du -b %(directory)s/root/ 2> /dev/null | tail -1 | awk {'print $1;'} > %(directory)s/live/filesystem.size" % {"directory": self.bootPath})

                print("======================================================")
                print("INFO: Start building ISO...")
                print("======================================================")

                # build squash root
                print("Creating SquashFS root...")
                print("Updating File lists...")
                dpkgQuery = ' dpkg -l | awk \'/^ii/ {print $2, $3}\' | sed -e \'s/ /\t/g\' '
                self.ec.run('chroot \"' + self.rootPath + '\"' + dpkgQuery + ' > \"' + join(self.livePath, "filesystem.packages") + '\"' )
                #dpkgQuery = ' dpkg-query -W --showformat=\'${Package} ${Version}\n\' '
                #self.ec.run('chroot \"' + self.rootPath + '\"' + dpkgQuery + ' > \"' + join(self.bootPath, "live/filesystem.manifest") + '\"' )
                #copy(join(self.bootPath, "live/filesystem.manifest"), join(self.bootPath, "live/filesystem.manifest-desktop"))
                # check for existing squashfs root
                if exists(join(self.livePath, "filesystem.squashfs")):
                    print("Removing existing SquashFS root...")
                    remove(join(self.livePath, "filesystem.squashfs"))
                print("Building SquashFS root...")
                # check for alternate mksquashfs
                # check for custom mksquashfs (for multi-threading, new features, etc.)
                mksquashfs = self.ec.run(cmd="echo $MKSQUASHFS", returnAsList=False).strip()
                rootPath = join(self.distroPath, "root/")
                squashfsPath = join(self.livePath, "filesystem.squashfs")
                if mksquashfs == '' or mksquashfs == 'mksquashfs':
                    try:
                        nrprocessors = int(int(self.ec.run("nproc", False, False))/2)
                        if nrprocessors < 1:
                            nrprocessors = 1
                    except:
                        nrprocessors = 1
                    cmd = "mksquashfs \"{}\" \"{}\" -comp xz -processors {}".format(rootPath, squashfsPath, nrprocessors)
                else:
                    cmd = "{} \"{}\" \"{}\"".format(mksquashfs, rootPath, squashfsPath)
                #print(cmd)
                self.ec.run(cmd)

                # build iso
                print("Creating ISO...")
                # update manifest files
                #self.ec.run("/usr/lib/solydxk/constructor/updateManifest.sh %s" % self.distroPath)
                # update md5
                print("Updating md5 sums...")
                if exists(join(self.bootPath, "md5sum.txt")):
                    remove(join(self.bootPath, "md5sum.txt"))
                if exists(join(self.bootPath, "MD5SUMS")):
                    remove(join(self.bootPath, "MD5SUMS"))
                self.ec.run('cd \"' + self.bootPath + '\"; ' + 'find . -type f -print0 | xargs -0 md5sum > md5sum.txt')
                #Remove md5sum.txt, MD5SUMS, boot.cat and isolinux.bin from md5sum.txt
                self.ec.run("sed -i '/md5sum.txt/d' %s/md5sum.txt" % self.bootPath)
                self.ec.run("sed -i '/MD5SUMS/d' %s/md5sum.txt" % self.bootPath)
                self.ec.run("sed -i '/boot.cat/d' %s/md5sum.txt" % self.bootPath)
                self.ec.run("sed -i '/isolinux.bin/d'  %s/md5sum.txt" % self.bootPath)
                #Copy md5sum.txt to MD5SUMS (for Debian compatibility)
                copy(join(self.bootPath, "md5sum.txt"), join(self.bootPath, "MD5SUMS"))

                # Update isolinux files
                isolinuxPath = "%s/isolinux" % self.bootPath
                self.ec.run("chmod -R +w %s" % isolinuxPath)
                try:
                    cat = "%s/boot.cat" % isolinuxPath
                    if exists(cat):
                        remove(cat)
                    copy("/usr/lib/syslinux/modules/bios/chain.c32", isolinuxPath)
                    copy("/usr/lib/ISOLINUX/isolinux.bin", isolinuxPath)
                    copy("/usr/lib/syslinux/modules/bios/reboot.c32", isolinuxPath)
                    copy("/usr/lib/syslinux/modules/bios/vesamenu.c32", isolinuxPath)
                    copy("/usr/lib/syslinux/modules/bios/poweroff.c32", isolinuxPath)
                    copy("/usr/lib/syslinux/modules/bios/ldlinux.c32", isolinuxPath)
                    copy("/usr/lib/syslinux/modules/bios/libcom32.c32", isolinuxPath)
                    copy("/usr/lib/syslinux/modules/bios/libutil.c32", isolinuxPath)
                    copy("/boot/memtest86+.bin", join(isolinuxPath, "memtest86"))
                    copy("/boot/memtest86+.bin", join(self.bootPath, "boot"))
                except Exception as detail:
                    self.returnMessage = "WARNING: BuildIso: %(detail)s" % {"detail": detail}

                # remove existing iso
                if exists(self.isoFileName):
                    print("Removing existing ISO...")
                    remove(self.isoFileName)

                # Save ISO name in iso_name file
                if not exists(join(self.distroPath, "iso_name")):
                    self.ec.run("echo \"%s\" > %s/iso_name" % (self.isoName, self.distroPath))

                # build iso according to architecture
                print("Building ISO...")
                self.ec.run('genisoimage -o \"' + self.isoFileName + '\" -b \"isolinux/isolinux.bin\" -c \"isolinux/boot.cat\" -no-emul-boot -boot-load-size 4 -boot-info-table -V \"' + self.fullIsoName + '\" -cache-inodes -r -J -l \"' + self.bootPath + '\"')

                print("Making Hybrid ISO...")
                self.ec.run("isohybrid %s" % self.isoFileName)

                self.ec.run("rm -rf %s" % join(self.bootPath, "isolinux/*.cfge"))
                self.ec.run("rm -rf %s" % join(self.bootPath, "boot/grub/*.cfge"))

                print("Create ISO md5sum file...")
                self.ec.run("echo \"%s:\" $(md5sum \"%s\" | cut -d' ' -f 1) > \"%s.md5sum\"" % (self.isoName, self.isoFileName, self.isoFileName))

                print("Create Torrent file...")
                torrentFile = "%s.torrent" % self.isoFileName
                if exists(torrentFile):
                    remove(torrentFile)
                self.ec.run("mktorrent -a \"%s\" -c \"%s %s\" -w \"%s\" -o \"%s\" \"%s\"" % (self.trackers, self.isoName, self.dateString, self.webseeds, torrentFile, self.isoFileName))

                print("======================================================")
                self.returnMessage = "DONE - ISO Located at: %s" % self.isoFileName
                print((self.returnMessage))
                print("======================================================")

            self.queue.put(self.returnMessage)

        except Exception as detail:
            self.returnMessage = "ERROR: BuildIso: %(detail)s" % {"detail": detail}
            self.queue.put(self.returnMessage)


# Class to create a chrooted terminal for a given directory
class EditDistro(object):

    def __init__(self, distroPath):
        self.ec = ExecCmd()
        self.dg = DistroGeneral(distroPath)
        distroPath = distroPath.rstrip('/')
        if basename(distroPath) == "root":
            distroPath = dirname(distroPath)
        self.rootPath = join(distroPath, "root")
        # ISO distribution
        self.distribution = self.dg.getDistribution()
        if self.distribution is None:
            self.distribution = basename(distroPath)

    def openTerminal(self, command=""):
        try:
            # setup environment
            # copy dns info
            resolveCnfHost = "/etc/resolv.conf"
            resolveCnf = join(self.rootPath, "etc/resolv.conf")
            resolveCnfBak = "%s.bak" % resolveCnf
            wgetrc = join(self.rootPath, "etc/wgetrc")
            wgetrcBak = "%s.bak" % wgetrc
            terminal = "/tmp/constructor-terminal.sh"
            proc = join(self.rootPath, "proc/")
            dev = join(self.rootPath, "dev/")
            pts = join(self.rootPath, "dev/pts/")

            if exists(resolveCnf):
                move(resolveCnf, resolveCnfBak)
            if exists(resolveCnfHost):
                copy(resolveCnfHost, resolveCnf)

            # umount /proc /dev /dev/pts
            self.unmount([pts, dev, proc])

            # mount /proc /dev /dev/pts
            self.ec.run("mount --bind /proc '%s'" % proc)
            self.ec.run("mount --bind /dev '%s'" % dev)
            self.ec.run("mount --bind /dev/pts '%s'" % pts)

            # copy apt.conf
            #copy("/etc/apt/apt.conf", join(self.rootPath, "etc/apt/apt.conf"))

            # copy wgetrc
            move(wgetrc, wgetrcBak)
            copy("/etc/wgetrc", wgetrc)

            # HACK: create temporary script for chrooting
            if exists(terminal):
                remove(terminal)
            scr = "#!/bin/sh\nchroot '%s' %s\n" % (self.rootPath, command)
            with open(terminal, 'w') as f:
                f.write(scr)
            self.ec.run("chmod a+x %s" % terminal)
            if self.ec.run('which x-terminal-emulator'):
                # use x-terminal-emulator if xterm isn't available
                if exists("/usr/bin/xterm"):
                    self.ec.run('export HOME=/root ; xterm -bg black -fg white -rightbar -title \"%s\" -e %s' % (self.distribution, terminal))
                else:
                    self.ec.run('export HOME=/root ; x-terminal-emulator -e %s' % terminal)
            else:
                print('Error: no valid terminal found')

            # restore wgetrc
            move(wgetrcBak, wgetrc)

            # remove apt.conf
            #remove(join(self.rootPath, "root/etc/apt/apt.conf"))

            # move dns info
            if exists(resolveCnfBak):
                move(resolveCnfBak, resolveCnf)
            else:
                remove(resolveCnf)

            # umount /proc /dev /dev/pts
            self.unmount([pts, dev, proc])

            # remove temp script
            if exists(terminal):
                remove(terminal)

        except Exception as detail:
            # restore wgetrc
            move(wgetrcBak, wgetrc)

            # remove apt.conf
            #remove(join(self.rootPath, "etc/apt/apt.conf"))

            # move dns info
            if exists(resolveCnfBak):
                move(resolveCnfBak, resolveCnf)
            else:
                remove(resolveCnf)

            # umount /proc /dev /dev/pts
            self.unmount([pts, dev, proc])

            # remove temp script
            if exists("/tmp/constructor-terminal.sh"):
                remove("/tmp/constructor-terminal.sh")

            errText = 'Error launching terminal: '
            print((errText, detail))

    def unmount(self, mounts=[]):
        for mount in mounts:
            self.ec.run("umount --force '%s'" % mount)
            self.ec.run("umount -l '%s'" % mount)

class DistroGeneral(object):

    def __init__(self, distroPath):
        self.ec = ExecCmd()
        distroPath = distroPath.rstrip('/')
        if basename(distroPath) == "root":
            distroPath = dirname(distroPath)
        self.distroPath = distroPath
        self.rootPath = join(distroPath, "root")

    def getPlymouthTheme(self):
        plymouthTheme = ""
        if exists(join(self.rootPath, "usr/share/plymouth/themes/solydk-logo")):
            plymouthTheme = "solydk-logo"
        elif exists(join(self.rootPath, "usr/share/plymouth/themes/solydkbe-logo")):
            plymouthTheme = "solydkbe-logo"
        elif exists(join(self.rootPath, "usr/share/plymouth/themes/solydxbe-logo")):
            plymouthTheme = "solydxbe-logo"
        elif exists(join(self.rootPath, "usr/share/plymouth/themes/solydkbo-logo")):
            plymouthTheme = "solydkbo-logo"
        elif exists(join(self.rootPath, "usr/share/plymouth/themes/solydx-logo")):
            plymouthTheme = "solydx-logo"
        return plymouthTheme

    def getDistribution(self):
        distribution = None
        info = join(self.rootPath, "etc/solydxk/info")
        if exists(info):
            distribution = self.ec.run("cat %s | grep EDITION | cut -d'=' -f2" % info, returnAsList=False).lower().strip('"')
            if not "solyd" in distribution:
                if "kde 32" in distribution:
                    distribution = "solydk32"
                elif "kde 64" in distribution:
                    distribution = "solydk64"
                if "xfce 32" in distribution:
                    distribution = "solydx32"
                elif "xfce 64" in distribution:
                    distribution = "solydx64"
        return distribution

    def getIsoName(self):
        isoName = "SolydXK"
        isoFile = join(self.distroPath, "iso_name")
        if exists(isoFile):
            with open(isoFile, 'r') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if line != "":
                    isoName = line
                    break
        return isoName
