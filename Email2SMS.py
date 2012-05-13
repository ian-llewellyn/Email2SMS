""" Email to SMS Bridge
Project Started : 2009-03-09 16:00
Version : 0.1-alpha

Verbosity guide:
0 - No output
1 - Fatal Errors
2 - Errors
3 - Warnings
4 - Operations
5 - Debug
"""

""" Load pySerial extension """
import serial

verbosity = 0
log_level = 5
log_file = 'Email2SMS.log'

def log_msg(level, message):
    """ Log handling function """
    if level <= verbosity:
        print '%d\t%s' % (level, message)
    if level <= log_level:
        fd = open(log_file, 'a')
        fd.write('%d\t%s\n' % (level, message))
        fd.close()

def comm(message, tout=1):
    """ Handles modem comms """
    log_msg(5, "function comm() - Entering")
    log_msg(4, "Sending: %s" % message)
    replies = []

    try:
        """ Open serial connection """
        s = serial.Serial(modem_port, 19200)
        s.timeout=tout
        """ When sending, \r or \r\n is ok """
        s.write("%s\r" % message)

        """ We should get back our message less a Ctrl-Z char if it was sent.
        In the case of a multiline message, we should read back the entire message
        including the response from the modem. """
        end_read = 0
        line = []
        line.append("")
        i = 0
        while end_read != 1:
            byte = s.read()
            if len(byte) < 1:
                log_msg(4, "No bytes in serial buffer")
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
        log_msg(5, "Received: %s" % reply)
        return reply

    except serial.SerialException:
        log_msg(2, "Unable to open serial port in comm function")
        return False

def serial_scan():
    """ Scan for available serial ports """
    log_msg(4, "function serial_scan() - Entering")
    available = []
    for i in range(256):
        try:
            s = serial.Serial(i)
            log_msg(5, "Found serial port [%d - %s]" % (i, s.portstr))
            available.append( (i, s.portstr))
            s.close()   #explicit close 'cause of delayed GC in java
        except serial.SerialException:
            pass
    """ Return a list of tuples (int num, string name) """
    return available

def serial_has_modem(ports):
    """ For each port, check to see if there's a modem attached;
        Send AT and see if we recieve OK back """
    log_msg(4, "function serial_has_modem() - Entering")
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
                    log_msg(5, "Modem present on [%d - %s]" % (p_num, p_name))
                    modems.append( (p_num, p_name) )
            s.close()
        except serial.SerialException:
            log_msg(2, "There was a problem attempting to connect to [%d - %s]" % (p_num, p_name))
    return modems

def modem_init(p_num):
    """ Next, check to see if there is a SIM iserted
        Now, find out if it's looking for a PIN
        If yes, provide PIN. If not, move on """
    log_msg(4, "function modem_init() - Entering")

    """ SIM Check """
    if comm("AT^SCKS?", tout=5) != "^SCKS: 0,1\n\nOK":
        log_msg(1, "SIM Not Present")
        exit()
    else: log_msg(4, "SIM OK")

    """ PIN Check """
    if comm("AT+CPIN?") != "+CPIN: READY\n\nOK":
        """ Enter SIM PIN """
        log_msg(1, "Need to enter PIN")
        exit()
    else: log_msg(4, "PIN OK")

    """ Switch to text mode """
    if comm("AT+CMGF=1") != "OK":
        log_msg(1, "Cannot switch GSM modem to Text mode")
        """ FAIL """
    else: log_msg(5, "Switched GSM modem to Text mode")

    return True

import time
text_running = 0
def text(mob_num, message):
    log_msg(4, "function text() - Entering")

    """ Is there a text function running """
    global text_running
    while text_running == 1:
        log_msg(5, "Waiting for another text function to complete")
        time.sleep(1)
    text_running = 1
    log_msg(5, "text_running set to 1")

    """ This next line constrains texts to Irish recipients """
    """ Recipients must be "08Xxxxxxxx" or "8Xxxxxxxx" """
    mob_num = "+353"+mob_num.lstrip("0")
    if comm("AT+CMGS=\"%s\"" % mob_num) != "> ":
        log_msg(1, "Cannot initialise SMS")
        return False
    else:
        comm("%s%c" % (message, 26), tout=15)
    log_msg(5, "Setting text_running to 0")
    #time.sleep(4) # Bit of a hack - the prob is with the above comm() not getting a response
    text_running = 0


""" Start program proper """
log_msg(4, "Starting Script")

""" Set default modem port """
""" This should be set by an optional cmd line argument """
modem_port = -1

""" If no port is set, we must find one """
if modem_port == -1:
    """ Return all serial ports """
    serial_ports = serial_scan()
    if serial_ports == []:
        log_msg(1, 'You have no serial ports')
        exit(1)

    """ Return only serial ports that have a modem attached """
    modem_ports = serial_has_modem(serial_ports)
    if modem_ports == []:
        log_msg(1, 'No modems found')
        exit(1)

    """ Try to initialise all modems, but stop trying if one succeeds """
    for (p_num, p_name) in modem_ports:
        log_msg(5, "Trying modem on [%d - %s]" % (p_num, p_name))
        modem_port = p_num
        if modem_init(p_num):
            log_msg(4, "Initialised modem on [%d - %s]" % (p_num, p_name))
            break
        log_msg(4, "Failed to initialise modem on [%d - %s]" % (p_num, p_name))
else:
    if modem_init(modem_port):
        log_msg(4, "Failed to initialise modem on [%d]" % modem_port)

""" Let's try sending a text """
#text("0861234567", "01..2..3..4..5..6..7..8..9..10..1..2..3..4..5..6..7..8..9..20..1..2..3..4..5..6..7..8..9..30..1..2..3..4..5..6..7..8..9..40..1..2..3..4..5..6..7..8..9..50..1..2..3..4..5..6..7..8..9..60..1..2..3..4..5..6..7..8..9..70")

""" Start the smtpd service """
import smtpd
import asyncore
import mimetypes
import email

class CustomSMTPServer(smtpd.SMTPServer):
    
    def process_message(self, peer, mailfrom, rcpttos, data):
        log_msg(4, "Receiving message from: %s, %d" % peer)
        log_msg(4, "Message addressed from: %s" % mailfrom)
        log_msg(4, "Message addressed to  : %s" % rcpttos)
        log_msg(4, "Message length        : %d" % len(data))
        #log_msg(4, "%s" % data)

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
                log_msg(3, "It's NOT all digits!")
                break
            log_msg(5, "It's all digits!")
            if len(txt_rcpt) != 10:
                log_msg(3, "It has NOT got 10 numbers!")
                break
            log_msg(5, "It has 10 numbers!")
            log_msg(5, "Recipient: %s" % txt_rcpt)
            #print "%s %s %s" % (msg_from, subject, message)
            text(txt_rcpt, "%s %s:\n%s" % (msg_from, subject, message))
        return

# Change the hostname from localhost to receive emails from remote hosts
server = CustomSMTPServer(('localhost', 25), None)

asyncore.loop()
