#! /usr/bin/env python3

# Password settings
# http://docs.python.org/2/library/spwd.html#module-spwd
# User settings
# http://docs.python.org/2/library/pwd.html

# Make sure the right Gtk version is loaded
import gi
gi.require_version('Gtk', '3.0')

# sudo apt-get install python3-gi
# from gi.repository import Gtk, GdkPixbuf, GObject, Pango, Gdk
from gi.repository import Gtk, GObject
from os import makedirs, remove, system, listdir
from shutil import copy, move, rmtree
import functions
import threading
import operator
from queue import Queue
# abspath, dirname, join, expanduser, exists, basename
from os.path import join, abspath, dirname, exists, isdir
from execcmd import ExecCmd
from solydxk import IsoUnpack, EditDistro, BuildIso, DistroGeneral
from treeview import TreeViewHandler
from dialogs import MessageDialogSafe, SelectFileDialog, SelectDirectoryDialog, QuestionDialog

# i18n: http://docs.python.org/3/library/gettext.html
import gettext
from gettext import gettext as _
gettext.textdomain('solydxk-constructor')


#class for the main window
class Constructor(object):

    def __init__(self):
        self.scriptDir = abspath(dirname(__file__))
        self.shareDir = join(self.scriptDir, '../../../share/solydxk/constructor')
        self.userAppDir = join(functions.get_user_home_dir(), ".constructor")
        self.distroFile = join(self.userAppDir, "distros.list")

        # Create the user's application directory if it doesn't exist
        if not isdir(self.userAppDir):
            user_name = functions.getUserLoginName()
            makedirs(self.userAppDir)
            old_distro_file = join(self.scriptDir, "distros.list")
            if exists(old_distro_file):
                move(old_distro_file, self.distroFile)
            system("chown -R %s:%s %s" % (user_name, user_name, self.userAppDir))

        # Load window and widgets
        self.builder = Gtk.Builder()
        self.builder.add_from_file(join(self.shareDir, 'constructor.glade'))

        # Main window objects
        go = self.builder.get_object
        self.window = go('constructorWindow')
        self.tvDistros = go('tvDistros')
        self.lblOutput = go('lblOutput')
        self.statusbar = go('statusbar')
        self.btnAdd = go('btnAdd')
        self.chkSelectAll = go('chkSelectAll')
        self.btnRemove = go('btnRemove')
        self.btnEdit = go('btnEdit')
        self.btnUpgrade = go('btnUpgrade')
        self.btnLocalize = go('btnLocalize')
        self.btnBuildIso = go('btnBuildIso')

        # Add iso window objects
        self.windowAddDistro = go('addDistroWindow')
        self.txtIso = go('txtIso')
        self.txtDir = go('txtDir')
        self.btnDir = go('btnDir')
        self.btnSave = go('btnSave')
        self.btnHelp = go('btnHelp')
        self.lblIso = go('lblIso')
        self.boxIso = go('boxIso')
        self.lblDir = go('lblDir')
        self.chkFromIso = go('chkFromIso')

        # Main window translations
        self.window.set_title(_("SolydXK Constructor"))
        self.chkSelectAll.set_label(_("Select all"))
        self.btnAdd.set_label("_{}".format(_("Add")))
        self.btnRemove.set_label("_{}".format(_("Remove")))
        self.btnEdit.set_label("_{}".format(_("Edit")))
        self.btnUpgrade.set_label("_{}".format(_("Upgrade")))
        self.btnLocalize.set_label("_{}".format(_("Localize")))
        self.btnBuildIso.set_label("_{}".format(_("Build")))
        self.btnHelp.set_label("_{}".format(_("Help")))

        # Add iso window translations
        self.lblIso.set_text(_("ISO"))
        go('btnCancel').set_label("_{}".format(_("Cancel")))

        # Init
        self.ec = ExecCmd()
        self.ec.run("modprobe loop", False)
        self.queue = Queue()
        self.mountDir = "/mnt/constructor"
        self.distroAdded = False
        self.iso = None
        self.dir = None
        self.isoName = None
        self.doneWav = join(self.shareDir, 'done.wav')
        self.help = join(self.shareDir, 'help.html')
        self.chkFromIso.set_active(True)
        self.toggleGuiElements(False)
        self.hostEfiArchitecture = functions.getHostEfiArchitecture()

        # Treeviews
        self.tvHandlerDistros = TreeViewHandler(self.tvDistros)
        self.fillTreeViewDistros()

        # Version information
        ver = _("Version")
        self.version = "%s: %s" % (ver, functions.getPackageVersion('solydxk-constructor'))
        self.showOutput(self.version)

        # Connect the signals and show the window
        self.builder.connect_signals(self)
        self.window.show()

    # ===============================================
    # Main Window Functions
    # ===============================================

    def on_btnAdd_clicked(self, widget):
        self.windowAddDistro.show()

    def on_btnRemove_clicked(self, widget):
        selected = self.tvHandlerDistros.getToggledValues(toggleColNr=0, valueColNr=2)
        for path in selected:
            qd = QuestionDialog(self.btnRemove.get_label(), _("Are you sure you want to remove the selected distribution from the list?\n" \
                                                              "(This will not remove the directory and its data)"), self.window)
            answer = qd.show()
            if answer:
                self.saveDistroFile(distroPath=path, addDistro=False)
        self.fillTreeViewDistros()

    def on_btnEdit_clicked(self, widget):
        selected = self.tvHandlerDistros.getToggledValues(toggleColNr=0, valueColNr=2)
        for path in selected:
            de = EditDistro(path)
            services = []
            if exists(join(path, 'root/etc/apache2/apache2.conf')):
                services.append("apache2")
            if exists(join(path, 'root/etc/mysql/debian.cnf')):
                services.append("mysql")
            if services:
                msg = "If you need to update packages that depend on these services,\n" \
                      "you will need to manually start them:\n"
                for service in services:
                    msg += "\nservice %s start" % service
                msg += "\n\nWhen done:\n"
                for service in services:
                    msg += "\nservice %s stop" % service
                self.showInfo(_("Services detected"), msg, self.window)
                functions.repaintGui()
            de.openTerminal()

    def on_btnUpgrade_clicked(self, widget):
        selected = self.tvHandlerDistros.getToggledValues(toggleColNr=0, valueColNr=2)
        upgraded = False
        for path in selected:
            upgraded = True
            rootPath = "%s/root" % path
            de = EditDistro(path)
            de.openTerminal("apt-get update")
            if exists(join(rootPath, 'etc/apache2/apache2.conf')):
                de.openTerminal("service apache2 start")
            if exists(join(rootPath, 'etc/mysql/debian.cnf')):
                de.openTerminal("service mysql start")
            de.openTerminal("apt-get -y --force-yes -o Dpkg::Options::=\"--force-confnew\" dist-upgrade")
            if exists(join(rootPath, 'etc/apache2/apache2.conf')):
                de.openTerminal("service apache2 stop")
            if exists(join(rootPath, 'etc/mysql/debian.cnf')):
                de.openTerminal("service mysql stop")

            # Cleanup old kernel and headers
            script = "rmoldkernel.sh"
            scriptSource = join(self.scriptDir, "files/{}".format(script))
            scriptTarget = join(rootPath, script)
            if exists(scriptSource):
                copy(scriptSource, scriptTarget)
                self.ec.run("chmod a+x %s" % scriptTarget)
                de.openTerminal("/bin/bash %s" % script)
                remove(scriptTarget)

            # Build EFI files
            if self.hostEfiArchitecture != "":
                print(">> Start building EFI files")
                self.build_efi_files()

            # Download offline packages
            print(">> Start downloading offline packages")
            self.download_offline_packages()

        if upgraded and exists("/usr/bin/aplay") and exists(self.doneWav):
            self.ec.run("/usr/bin/aplay '%s'" % self.doneWav, False)

    def on_btnLocalize_clicked(self, widget):
        # Set locale
        selected = self.tvHandlerDistros.getToggledValues(toggleColNr=0, valueColNr=2)
        for path in selected:
            rootPath = "%s/root" % path
            de = EditDistro(path)
            script = "setlocale.sh"
            scriptSource = join(self.scriptDir, "files/{}".format(script))
            scriptTarget = join(rootPath, script)
            if exists(scriptSource):
                copy(scriptSource, scriptTarget)
                self.ec.run("chmod a+x %s" % scriptTarget)
                de.openTerminal("/bin/bash %s" % script)
                remove(scriptTarget)

    def build_efi_files(self):

        # TODO - also 32-bit installs (haven't tested this)

        modules = "part_gpt part_msdos ntfs ntfscomp hfsplus fat ext2 normal chain boot configfile linux " \
                "multiboot iso9660 gfxmenu gfxterm loadenv efi_gop efi_uga loadbios fixvideo png " \
                "ext2 ntfscomp loopback search minicmd cat cpuid appleldr elf usb videotest " \
                "halt help ls reboot echo test normal sleep memdisk tar font video_fb video " \
                "gettext true  video_bochs video_cirrus multiboot2 acpi gfxterm_background gfxterm_menu"

        selected = self.tvHandlerDistros.getToggledValues(toggleColNr=0, valueColNr=2)
        for path in selected:
            rootPath = "%s/root" % path
            bootPath = "{}/boot".format(path)
            arch = functions.getGuestEfiArchitecture(rootPath)

            grubEfiName = "bootx64"
            efiName = "x64"
            if arch != "x86_64":
                arch = "i386"
                grubEfiName = "bootia32"
                efiName = "ia32"

            try:
                if not exists("{}/efi/boot".format(bootPath)):
                    makedirs("{}/efi/boot".format(bootPath))

                self.ec.run("efi-image {}/~tmp {}-efi {}".format(bootPath, arch, efiName))
                if exists("{}/~tmp/efi.img".format(bootPath) and
                   exists("{}/~tmp/boot/grub/{}-efi".format(bootPath, arch))):
                    self.ec.run("rm -r {}/boot/grub/{}-efi".format(bootPath, arch))
                    self.ec.run("mv -vf {}/~tmp/boot/grub/{}-efi {}/boot/grub/".format(bootPath, arch, bootPath))
                    self.ec.run("mv -vf {}/~tmp/efi.img {}/boot/grub/".format(bootPath, bootPath))
                    self.ec.run("rm -r {}/~tmp".format(bootPath))

                self.ec.run("grub-mkimage -O {}-efi -d /usr/lib/grub/{}-efi "
                            "-o {}/efi/boot/{}.efi "
                            "-p \"/boot/grub\" {}".format(arch, arch, bootPath, grubEfiName, modules))

                print((">> Finished building EFI files"))

            except Exception as detail:
                self.showError("Error: build EFI files", detail, self.window)

    def download_offline_packages(self):
        selected = self.tvHandlerDistros.getToggledValues(toggleColNr=0, valueColNr=2)
        for path in selected:
            rootPath = "%s/root" % path
            arch = functions.getGuestEfiArchitecture(rootPath)
            de = EditDistro(path)
            script = "offline.sh"
            scriptSource = join(self.scriptDir, "files/{}".format(script))
            scriptTarget = join(rootPath, script)
            offlineSource = join(rootPath, "offline")
            offlineTarget = join(rootPath, "../boot/offline")
            if exists(scriptSource):
                try:
                    copy(scriptSource, scriptTarget)
                    self.ec.run("chmod a+x %s" % scriptTarget)
                    # Run the script
                    de.openTerminal("/bin/bash {} {}".format(script, arch))
                    # Remove script
                    remove(scriptTarget)
                    # Move offline directory to boot directory
                    if exists(offlineSource):
                        print(("%s exists" % offlineSource))
                        if exists(offlineTarget):
                            print((">> Remove %s" % offlineTarget))
                            rmtree(offlineTarget)
                        print((">> Move %s to %s" % (offlineSource, offlineTarget)))
                        move(offlineSource, offlineTarget)
                    else:
                        print((">> Cannot find: %s" % offlineSource))
                except Exception as detail:
                    self.showError("Error: getting offline packages", detail, self.window)
            else:
                print((">> Cannot find: %s" % scriptSource))


    def on_btnBuildIso_clicked(self, widget):
        selected = self.tvHandlerDistros.getToggledValues(toggleColNr=0, valueColNr=2)
        msg = ""
        for path in selected:
            self.toggleGuiElements(True)
            self.showOutput("Start building ISO in: %s" % path)
            functions.repaintGui()

            # Start building the ISO in a thread
            t = BuildIso(path, self.queue)
            t.start()
            self.queue.join()

            # Thread is done
            # Get the data from the queue
            ret = self.queue.get()
            self.queue.task_done()

            if ret is not None:
                self.showOutput(ret)
                if "error" in ret.lower():
                    self.showError("Error", ret, self.window)
                else:
                    msg += "%s\n" % ret

        if msg != "":
            if exists("/usr/bin/aplay") and exists(self.doneWav):
                self.ec.run("/usr/bin/aplay '%s'" % self.doneWav, False)
            self.showInfo("", msg, self.window)
        self.toggleGuiElements(False)

    def on_chkSelectAll_toggled(self, widget):
        self.tvHandlerDistros.treeviewToggleAll(toggleColNrList=[0], toggleValue=widget.get_active())

    def on_tvDistros_row_activated(self, widget, path, column):
        self.tvHandlerDistros.treeviewToggleRows(toggleColNrList=[0])

    def on_btnHelp_clicked(self, widget):
        if functions.isPackageInstalled("firefox"):
            system("firefox file://%s &" % self.help)
        else:
            system("xdg-open file://%s &" % self.help)

    def on_btnOpenDir_clicked(self, widget):
        selected = self.tvHandlerDistros.getToggledValues(toggleColNr=0, valueColNr=2)
        for path in selected:
            system("xdg-open %s &" % path)

    def fillTreeViewDistros(self, selectDistros=[]):
        contentList = [[_("Select"), _("Distribution"), _("Working directory")]]
        distros = self.getDistros()
        for distro in distros:
            select = False
            for selectDistro in selectDistros:
                if distro[0] == selectDistro:
                    select = True
            contentList.append([select, distro[0], distro[1]])
        self.tvHandlerDistros.fillTreeview(contentList=contentList, columnTypesList=['bool', 'str', 'str'], firstItemIsColName=True)

    def getDistros(self):
        distros = []
        if exists(self.distroFile):
            with open(self.distroFile, 'r') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip().rstrip('/')
                print(line)
                if exists(line):
                    dg = DistroGeneral(line)
                    isoName = dg.description
                    distros.append([isoName, line])
            # Sort on iso name
            if distros:
                distros = sorted(distros, key=operator.itemgetter(0))
        return distros

    # ===============================================
    # Add ISO Window Functions
    # ===============================================

    def on_btnIso_clicked(self, widget):
        fleFilter = Gtk.FileFilter()
        fleFilter.set_name("ISO")
        fleFilter.add_mime_type("application/x-cd-image")
        fleFilter.add_pattern("*.iso")

        startDir = None
        if exists(dirname(self.txtIso.get_text())):
            startDir = dirname(self.txtIso.get_text())

        filePath = SelectFileDialog(title=_('Select SolydXK ISO'), start_directory=startDir, parent=self.window, gtkFileFilter=fleFilter).show()
        if filePath is not None:
            self.txtIso.set_text(filePath)

    def on_btnDir_clicked(self, widget):
        startDir = None
        if exists(self.txtDir.get_text()):
            startDir = self.txtDir.get_text()
        dirText = SelectDirectoryDialog(title=_('Select directory'), start_directory=startDir, parent=self.window).show()
        if dirText is not None:
            self.txtDir.set_text(dirText)

    def on_btnSave_clicked(self, widget):
        self.iso = ""
        if self.chkFromIso.get_active():
            self.iso = self.txtIso.get_text()
        self.dir = self.txtDir.get_text()

        title = _("Save existing working directory")
        if self.iso != "":
            title = _("Unpack ISO and save")

        if not exists(self.dir):
            makedirs(self.dir)

        if not exists(self.dir):
            self.showError(title, _("Could not create directory %(dir)s: exiting" % {"dir": self.dir}), self.window)
        else:
            self.windowAddDistro.hide()
            if self.iso != "":
                if not exists(self.iso):
                    self.showInfo(self.btnSave.get_label(), _("The path to the ISO file does not exist:\n{}".format(self.iso)), self.window)
                    return
                if listdir(self.dir):
                    qd = QuestionDialog(self.btnSave.get_label(),
                        _("The destination directory is not empty.\n"
                        "Are you sure you want to overwrite all data in {}?".format(self.dir)),
                        self.window)
                    answer = qd.show()
                    if not answer:
                        return

                self.showOutput("Start unpacking the ISO...")
                self.toggleGuiElements(True)
                t = IsoUnpack(self.mountDir, self.iso, self.dir, self.queue)
                t.start()
                self.queue.join()
                GObject.timeout_add(1000, self.checkThread, True)
            else:
                self.saveDistroFile(self.dir, True)
                self.fillTreeViewDistros()
                self.showOutput(_("Existing working directory added"))
                #self.toggleGuiElements(False)

    def on_btnCancel_clicked(self, widget):
        self.windowAddDistro.hide()

    def on_addDistroWindow_delete_event(self, widget, data=None):
        self.windowAddDistro.hide()
        return True

    def on_txtIso_changed(self, widget):
        path = self.txtIso.get_text()
        if exists(path):
            self.txtDir.set_sensitive(True)
            self.btnDir.set_sensitive(True)
            if exists(self.txtDir.get_text()):
                self.btnSave.set_sensitive(True)
        else:
            self.txtDir.set_sensitive(False)
            self.btnDir.set_sensitive(False)
            self.btnSave.set_sensitive(False)

    def on_txtDir_changed(self, widget):
        blnFromIso = self.chkFromIso.get_active()
        isoPath = self.txtIso.get_text()
        dirText = self.txtDir.get_text()
        self.btnSave.set_sensitive(False)
        if exists(dirText):
            if blnFromIso:
                if exists(isoPath):
                    self.btnSave.set_sensitive(True)
            else:
                self.btnSave.set_sensitive(True)

    def on_chkFromIso_toggled(self, widget):
        if widget.get_active():
            self.lblIso.set_visible(True)
            self.boxIso.set_visible(True)
            self.txtDir.set_sensitive(False)
            self.btnDir.set_sensitive(False)
            self.btnSave.set_sensitive(False)
            self.lblDir.set_text(_("Unpack ISO to directory"))
            self.btnSave.set_label(_("Unpack & Save"))
        else:
            self.txtIso.set_text("")
            self.lblIso.set_visible(False)
            self.boxIso.set_visible(False)
            self.txtDir.set_sensitive(True)
            self.btnDir.set_sensitive(True)
            self.btnSave.set_sensitive(True)
            self.lblDir.set_text(_("Work directory"))
            self.btnSave.set_label(_("Save"))

    # ===============================================
    # General functions
    # ===============================================

    def showInfo(self, title, message, parent=None):
        MessageDialogSafe(title, message, Gtk.MessageType.INFO, parent).show()

    def showError(self, title, message, parent=None):
        MessageDialogSafe(title, message, Gtk.MessageType.ERROR, parent).show()

    def showOutput(self, message):
        print(message)
        functions.pushMessage(self.statusbar, message)

    def checkThread(self, addDistro=None):
        #print 'Thread count = ' + str(threading.active_count())
        # As long there's a thread active, keep spinning
        if threading.active_count() > 1:
            return True

        # Thread is done
        # Get the data from the queuez
        ret = self.queue.get()
        self.queue.task_done()

        # Thread is done
        if addDistro is not None:
            self.saveDistroFile(self.dir, addDistro)
            self.fillTreeViewDistros(self.isoName)
        self.toggleGuiElements(False)
        if exists("/usr/bin/aplay") and exists(self.doneWav):
            self.ec.run("/usr/bin/aplay '%s'" % self.doneWav, False)
        if ret is not None:
            self.showOutput(ret)
            if "error" in ret.lower():
                self.showError("Error", ret, self.window)
            else:
                self.showInfo("", ret, self.window)
        return False

    def toggleGuiElements(self, startThread):
        if startThread:
            self.chkSelectAll.set_sensitive(False)
            self.tvDistros.set_sensitive(False)
            self.btnAdd.set_sensitive(False)
            self.btnBuildIso.set_sensitive(False)
            self.btnEdit.set_sensitive(False)
            self.btnRemove.set_sensitive(False)
            self.btnUpgrade.set_sensitive(False)
            self.btnLocalize.set_sensitive(False)
            self.btnDir.set_sensitive(False)
            self.btnHelp.set_sensitive(False)
        else:
            self.chkSelectAll.set_sensitive(True)
            self.tvDistros.set_sensitive(True)
            self.btnAdd.set_sensitive(True)
            self.btnBuildIso.set_sensitive(True)
            self.btnEdit.set_sensitive(True)
            self.btnRemove.set_sensitive(True)
            self.btnUpgrade.set_sensitive(True)
            self.btnLocalize.set_sensitive(True)
            self.btnDir.set_sensitive(True)
            self.btnHelp.set_sensitive(True)

    def saveDistroFile(self, distroPath, addDistro=True):
        newCont = []
        dg = DistroGeneral(distroPath)
        self.isoName = dg.description

        cfg = []
        if exists(self.distroFile):
            with open(self.distroFile, 'r') as f:
                cfg = f.readlines()
            for line in cfg:
                line = line.strip()
                if distroPath not in line and exists(line):
                    newCont.append(line)

        if addDistro:
            newCont.append(distroPath)

        with open(self.distroFile, 'w') as f:
            f.write('\n'.join(newCont))

        self.iso = ""
        self.dir = ""

    # Close the gui
    def on_constructorWindow_destroy(self, widget):
        # Close the app
        Gtk.main_quit()

if __name__ == '__main__':
    # Create an instance of our GTK application
    try:
        gui = Constructor()
        Gtk.main()
    except KeyboardInterrupt:
        pass
