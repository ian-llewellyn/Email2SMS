#!/usr/bin/python
# chkconfig: 2345 90 10
# description: Listens for emails of a particular format and sends them via GSM
#              modem to the specified number.
""" Email to SMS Bridge
Project Started : 2009-03-09 16:00
Version : 0.1-alpha

Verbosity guide:
0 - No output
1 - Fatal Errors
2 - Errors
3 - Info + Warnings
4 - Operations
5 - Debug
"""


import logging
import os
import sys

""" Load pySerial extension """
import serial

logger = logging.getLogger(__name__)

LOG_FILE = '/var/log/Email2SMS.log'
PID_FILE = '/var/run/Email2SMS.pid'

FORMAT = '[%(asctime)s] %(process)d %(levelname)s: %(message)s'
formatter = logging.Formatter(FORMAT)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)


logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False

MODEM_PORT = None


def comm(message, tout=1):
    """ Handles modem comms """
    logger.debug("function comm() - Entering")
    logger.info("Sending: %s" % message)

    try:
        """ Open serial connection """
        s = serial.Serial(MODEM_PORT, 19200)
        s.timeout = tout
        """ When sending, \r or \r\n is ok """
        s.write("%s\r" % message)

        """ We should get back our message less a Ctrl-Z char if it was sent.
        In the case of a multiline message, we should read back the
        entire message including the response from the modem. """
        end_read = 0
        line = []
        line.append("")
        i = 0
        while end_read != 1:
            byte = s.read()
            if len(byte) < 1:
                logger.info("No bytes in serial buffer")
                break
            if byte == "\n":
                line[i] = line[i].rstrip("\r")
                if line[i] == "OK":
                    end_read = 1
                    break
                elif line[i] == "ERROR":
                    end_read = 1
                    break
                elif line[i] == "> ":
                    end_read = 1
                    break
                line.append("")
                i += 1
            else:
                line[i] = line[i] + byte

        """ Close serial connection """
        s.close()

        """ Format and return the response from the modem """
        reply = "\n".join(line)
        reply = reply.replace(message.rstrip("%c" % 26)+"\n", "", 1)
        logger.debug("Received: %s" % reply)
        return reply

    except serial.SerialException:
        logger.error("Unable to open serial port in comm function")
        return False


def serial_scan():
    """ Scan for available serial ports """
    logger.info("function serial_scan() - Entering")
    available = []
    for i in range(256):
        try:
            s = serial.Serial('/dev/ttyS%d' % i)
            logger.debug("Found serial port [%d - %s]" % (i, s.portstr))
            available.append((i, s.portstr))
            s.close()  # explicit close 'cause of delayed GC in java
        except serial.SerialException:
            pass
    """ Return a list of tuples (int num, string name) """
    return available


def serial_has_modem(ports):
    """ For each port, check to see if there's a modem attached;
        Send AT and see if we recieve OK back """
    logger.info("function serial_has_modem() - Entering")
    modems = []
    for (p_num, p_name) in ports:
        try:
            """ Open serial connection """
            s = serial.Serial(p_name, 19200, timeout=1)
            """ \r or \r\n """
            s.write("AT\r")
            """ The first read will read back what we wrote """
            if s.readline().rstrip("\r\n") == 'AT':
                if s.readline().rstrip("\r\n") == 'OK':
                    logger.debug("Modem present on [%d - %s]" % (p_num,
                                                                 p_name))
                    modems.append((p_num, p_name))
            s.close()
        except serial.SerialException:
            logger.info(
                "There was a problem attempting to connect to [%d - %s]"
                % (p_num, p_name)
            )
    return modems


def modem_init(p_num):
    """ Next, check to see if there is a SIM iserted
        Now, find out if it's looking for a PIN
        If yes, provide PIN. If not, move on """
    logger.info("function modem_init() - Entering")

    """ SIM Check """
    if comm("AT^SCKS?", tout=5) != "^SCKS: 0,1\n\nOK":
        logger.critical("SIM Not Present")
        exit()
    else:
        logger.info("SIM OK")

    """ PIN Check """
    if comm("AT+CPIN?") != "+CPIN: READY\n\nOK":
        """ Enter SIM PIN """
        logger.critical("Need to enter PIN")
        exit()
    else:
        logger.info("PIN OK")

    """ Switch to text mode """
    if comm("AT+CMGF=1") != "OK":
        logger.critical("Cannot switch GSM modem to Text mode")
        """ FAIL """
    else:
        logger.debug("Switched GSM modem to Text mode")

    return True

from threading import Lock
text_running = Lock()


def text(mob_num, message):
    logger.info("function text() - Entering")

    """ Is there a text function running """
    global text_running
    logger.debug("About to acquire lock")
    text_running.acquire()

    """ This next line constrains texts to Irish recipients """
    """ Recipients must be "08Xxxxxxxx" or "8Xxxxxxxx" """
    mob_num = "+353"+mob_num.lstrip("0")
    if comm("AT+CMGS=\"%s\"" % mob_num) != "> ":
        logger.critical("Cannot initialise SMS")
        text_running.release()
        return False
    else:
        comm("%s%c" % (message, 26), tout=15)
    logger.debug("Releasing lock")
    #time.sleep(4) # Bit of a hack - the prob is with the above comm()
    # not getting a response
    text_running.release()

""" Start the smtpd service """
import smtpd
import asyncore
import email


class CustomSMTPServer(smtpd.SMTPServer):

    def process_message(self, peer, mailfrom, rcpttos, data):
        logger.info("Receiving message from: %s, %d" % peer)
        logger.info("Message addressed from: %s" % mailfrom)
        logger.info("Message addressed to  : %s" % rcpttos)
        logger.info("Message length        : %d" % len(data))
        #logger.info("%s" % data)

        msg = email.message_from_string(data)

        msg_from = msg['From']
        subject = msg['Subject']

        counter = 1
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue

            if part.get_content_type() == "text/plain":
                message = part.get_payload(decode=True)
                break

            counter += 1

        #print msg.as_string()

        for rcptto in rcpttos:
            txt_rcpt = rcptto.split('@')[0]
            # Check to see if it is all numbers and that there are 10 of them!
            if not txt_rcpt.isdigit():
                logger.warning("It's NOT all digits!")
                break
            logger.debug("It's all digits!")
            if len(txt_rcpt) != 10:
                logger.warning("It has NOT got 10 numbers!")
                break
            logger.debug("It has 10 numbers!")
            logger.debug("Recipient: %s" % txt_rcpt)
            #print "%s %s %s" % (msg_from, subject, message)
            text(txt_rcpt, "%s %s:\n%s" % (msg_from, subject, message))
        return


def write_pid(pid):
    with open(PID_FILE, 'w') as pid_file:
        pid_file.write('%i' % pid)


def get_pid_from_file():
    content = None
    try:
        with open(PID_FILE, 'r') as pid_file:
            content = ''.join(pid_file.readlines()).strip()
    except IOError:
        pass
    return int(content) if content else content


def is_running(pid):
    if pid:
        return os.path.exists('/proc/%s' % pid)
    # TODO Improve the lookup with the proces name
    return False


def start():
    """ Start program proper """
    write_pid(os.getpid())
    global MODEM_PORT
    logger.warning("Starting Email2SMS")

    """ Set default modem port """
    """ This should be set by an optional cmd line argument """

    """ If no port is set, we must find one """
    if MODEM_PORT is None:
        """ Return all serial ports """
        serial_ports = serial_scan()
        if serial_ports == []:
            logger.critical('You have no serial ports')
            exit(1)

        """ Return only serial ports that have a modem attached """
        MODEM_PORTS = serial_has_modem(serial_ports)
        if MODEM_PORTS == []:
            logger.critical('No modems found')
            exit(1)

        """ Try to initialise all modems, but stop trying if one succeeds """
        for (p_num, p_name) in MODEM_PORTS:
            logger.debug("Trying modem on [%d - %s]" % (p_num, p_name))
            MODEM_PORT = p_name
            if modem_init(p_num):
                logger.info("Initialised modem on [%d - %s]" % (p_num, p_name))
                break
            logger.info("Failed to initialise modem on [%d - %s]" % (p_num,
                                                                     p_name))
    else:
        if modem_init(MODEM_PORT):
            logger.info("Failed to initialise modem on [%d]" % MODEM_PORT)

    """ Let's try sending a text """
    #text("0861234567", "01..2..3..4..5..6..7..8..9..10..
    #1..2..3..4..5..6..7..8..9..20..1..2..3..4..5..6..7..8..9..30..
    #1..2..3..4..5..6..7..8..9..40..1..2..3..4..5..6..7..8..9..50..
    #1..2..3..4..5..6..7..8..9..60..1..2..3..4..5..6..7..8..9..70")

    CustomSMTPServer(('localhost', 2005), None)

    asyncore.loop()


def cmd_start(pid):
    pid = os.fork()
    if pid == 0:
        start()
    else:
        exit()


def cmd_stop(pid):
    if is_running(pid):
        os.kill(pid, 9)
        return True
    return False


if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command in ('start', 'stop', 'restart', 'status', 'fg'):
            pid = get_pid_from_file()
            if command == 'start':
                if is_running(pid):
                    print 'Already running on PID %s' % pid
                    sys.exit(1)
                else:
                    cmd_start(pid)
            elif command == 'fg':
                stream_handler = logging.StreamHandler()
                stream_handler.setLevel(logging.DEBUG)
                stream_handler.setFormatter(formatter)
                logger.addHandler(stream_handler)
                start()
            elif command == 'stop':
                if not cmd_stop(pid):
                    print 'Email2SMS is not running'
            elif command == 'status':
                if is_running(pid):
                    print 'Running with PID: %s' % pid
                    sys.exit(0)
                else:
                    print 'Not running'
                    sys.exit(1)
            elif command == 'restart':
                cmd_stop(pid)
                cmd_start(pid)
