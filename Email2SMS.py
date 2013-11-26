#!/usr/bin/python
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

""" Load pySerial extension """
import serial

""" More complicated file logging requires: """
import logging

logger = logging.getLogger(__name__)

log_file = 'Email2SMS.log'

FORMAT = '%(asctime)s [%(levelname)s] %(process)d: %(message)s'
formatter = logging.Formatter(FORMAT)

file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False


def comm(message, tout=1):
    """ Handles modem comms """
    logger.debug("function comm() - Entering")
    logger.info("Sending: %s" % message)

    try:
        """ Open serial connection """
        s = serial.Serial(modem_port, 19200)
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
            s = serial.Serial(i)
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
            s = serial.Serial(p_num, 19200, timeout=1)
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
        return False
    else:
        comm("%s%c" % (message, 26), tout=15)
    logger.debug("Releasing lock")
    #time.sleep(4) # Bit of a hack - the prob is with the above comm()
    # not getting a response
    text_running.release()


""" Start program proper """
logger.warning("Starting Email2SMS")

""" Set default modem port """
""" This should be set by an optional cmd line argument """
modem_port = -1

""" If no port is set, we must find one """
if modem_port == -1:
    """ Return all serial ports """
    serial_ports = serial_scan()
    if serial_ports == []:
        logger.critical('You have no serial ports')
        exit(1)

    """ Return only serial ports that have a modem attached """
    modem_ports = serial_has_modem(serial_ports)
    if modem_ports == []:
        logger.critical('No modems found')
        exit(1)

    """ Try to initialise all modems, but stop trying if one succeeds """
    for (p_num, p_name) in modem_ports:
        logger.debug("Trying modem on [%d - %s]" % (p_num, p_name))
        modem_port = p_num
        if modem_init(p_num):
            logger.info("Initialised modem on [%d - %s]" % (p_num, p_name))
            break
        logger.info("Failed to initialise modem on [%d - %s]" % (p_num,
                                                                 p_name))
else:
    if modem_init(modem_port):
        logger.info("Failed to initialise modem on [%d]" % modem_port)

""" Let's try sending a text """
#text("0861234567", "01..2..3..4..5..6..7..8..9..10..1..2..3..4..5..6..7..8..
#9..20..1..2..3..4..5..6..7..8..9..30..1..2..3..4..5..6..7..8..9..40..1..2..
#3..4..5..6..7..8..9..50..1..2..3..4..5..6..7..8..9..60..1..2..3..4..5..
#6..7..8..9..70")

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

# Change the hostname from localhost to receive emails from remote hosts
server = CustomSMTPServer(('localhost', 2005), None)

asyncore.loop()
