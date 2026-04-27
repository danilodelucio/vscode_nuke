# -----------------------------------------------------------------------------
# VSCode connection to Nuke plugin
# Copyright (c) 2025 Jorge Hernandez Ibanez
#
# This file is part of the Nuke connect for vscode project.
# Repository: https://github.com/JorgeHI/vscode_nuke
#
# This file is licensed under the MIT License.
# See the LICENSE file in the root of this repository for details.
# -----------------------------------------------------------------------------
import sys
import nuke

# PySide compatibility
if nuke.NUKE_VERSION_MAJOR < 11:
    from PySide import QtCore, QtNetwork
elif nuke.NUKE_VERSION_MAJOR < 16:
    from PySide2 import QtCore, QtNetwork
else:
    from PySide6 import QtCore, QtNetwork

import NukeConnect.nkLogger as nkLogger
logger = nkLogger.getLogger(__name__)

SERVER_GLOBALS = {"nuke": nuke}


class NukeTcpServer(QtCore.QObject):
    serverStateChanged = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super(NukeTcpServer, self).__init__(parent)
        self.server = QtNetwork.QTcpServer(self)
        self.port = 8080
        self.connection = None
        self.running = False

        self.server.newConnection.connect(self.handle_connection)

    def init(self):
        prefs = nuke.toNode('preferences')
        if prefs is None:
            logger.warning("Preferences node not found. Nuke Connect server will not start.")
            return

        port_knob = prefs.knob("nuke_connect_port")
        startup_on = prefs.knob("nuke_connect_auto_startup")

        if port_knob is not None:
            self.port = int(port_knob.value())

        if startup_on is not None and startup_on.value():
            self.start()

    def start(self):
        if not self.server.listen(QtNetwork.QHostAddress.LocalHost, self.port):
            logger.error("Could not start server on port {}".format(self.port))
            self.running = False
            return False

        logger.info("Nuke Connect TCP server listening on port {}".format(self.port))
        self.running = True
        return True

    def stop(self):
        self.server.close()
        self.running = False
        logger.info("Nuke Connect TCP server stopped.")
        return False

    def is_running(self):
        return self.running

    def handle_connection(self):
        self.connection = self.server.nextPendingConnection()
        self.connection.readyRead.connect(self.read_data)

    def read_data(self):
        if not self.connection:
            return

        raw = self.connection.readAll().data()

        if len(raw) < 8:
            logger.error("Invalid message received: {}".format(raw))
            return

        try:
            header = raw[:8]
            expected_len = int(header)
        except:
            logger.error("Invalid header received: {}".format(raw))
            return

        body = raw[8:8 + expected_len]

        try:
            message = body.decode('utf-8', 'ignore')
        except:
            message = body

        out = self.execute_command(message)

        if out:
            self.send_output_msg(out)

    def execute_command(self, command, scope="global"):
        import StringIO

        old_stdout = sys.stdout
        old_stderr = sys.stderr

        sys.stdout = StringIO.StringIO()
        sys.stderr = StringIO.StringIO()

        try:
            exec(command, SERVER_GLOBALS)
            output = sys.stdout.getvalue() + sys.stderr.getvalue()
        except Exception as e:
            output = sys.stdout.getvalue() + sys.stderr.getvalue()
            output += "\n[Nuke Connect] Exception: {}".format(e)
            logger.error("Error executing command: {}".format(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return output

    def send_output_msg(self, output):
        if not self.connection:
            return

        try:
            if isinstance(output, unicode):
                msg_data = output.encode("utf-8", "ignore")
            else:
                msg_data = output

            header = str(len(msg_data)).zfill(8)
            self.connection.write(header + msg_data)

        except Exception as e:
            logger.error("Error sending output: {}".format(e))
