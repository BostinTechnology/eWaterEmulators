#!/usr/bin/env python3

# CUrrently doing:
#   Need to store the packet sent to resend if asked
#   The packet sent is currently just the data segment, it needs the rest wrapping around it
#   Creating PacketBuilder

# TODO:
#   upgrade pyserial to v3 and change commands marked #v3
#   Upgrade for v0.3 of the spec, I think this includes
#       Need to double check all covered
#   Send incorrect data (menu items exist, no content within the called routines
#   - Too small / big
#   - Out of Sync
#   - Wrong ID / No ID
#   - CRC Error
#   Implement Respond to IoT
#   Allow packet to send to be chosen
#   Add in the Bootloader functionality
#   Call DataPacketLoader and PacketGenerator from within this main menu
#   Consider adding the packets into a class so I can manipulate them easier maybe...
#   improve code by havingn writedata respond with a message if failed
#   - stops it repeating the same 5 lines of code
#
# Testing To Do
#   Test CTS control
#   Test data packet sending
# BUGS
#   conn in the try except routine at the end is not defined!
#


import RPi.GPIO as GPIO
import serial
import logging
import sys
import datetime
import traceback
import binascii

import PacketGenerator
import Settings


BAUDRATE = 9600         # The speed of the comms
PORT = "/dev/serial0"   # The port being used for the comms
TIMEOUT = 1             # The maximum time allowed to receive a message
GPIO_CTS = 11           # The CTS line, also known as GPIO17

# EWC_Records holds all the records generated or send to the IoT
# EWC_Pointer holds the value of the last record sent to the IoT
gbl_EWC_Records = [''] * Settings.QUANTITY_OF_RECORDS
gbl_EWC_Pointer = -1           # Set to -1 to indicate not yet initialised


def SerialSetup():
    """
    Setup the serial connection for the EWC, using serial
    Setup the GPIO port for the CTS line
    """
    # set the GPIO pin for the CTS line output
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(GPIO_CTS, GPIO.OUT)

    # open the serial port and set the speed accordingly
    fd = serial.Serial(PORT, BAUDRATE, timeout = TIMEOUT)

    # clear the serial buffer of any left over data
    #fd.reset_output_buffer()       #v3
    fd.flushOutput()

    if fd.isOpen():
        # if serial is setup and the opened channel is greater than zero (zero = fail)
        print ("PI setup complete on channel %s" % fd)
        logging.info("PI setup complete on channel %s" % fd)
    else:
        print ("Unable to Setup communications")
        logging.error ("Unable to Setup communications")
        sys.exit()

    return fd

def CTSControl(state="SWITCH"):
    """
    Set the state of the CTS line
    possible values for the state are
       HIGH     set it high
       LOW      set it low
       SWITCH   (default)
    """
    if state.upper() == "HIGH":
        GPIO.output(GPIO_CTS, GPIO.HIGH)
    elif state.upper() == "LOW":
        GPIO.output(GPIO_CTS, GPIO.LOW)
    elif state.upper() == "SWITCH":
        GPIO.output(GPIO_CTS, not(GPIO.input(GPIO_CTS)))
    else:
        print("CTS Control State requested outside of range")
        logging.error("CTS Control State requested outside of range")
    return

def WriteDataBinary(fd,send,cts=True):
    """
    This routine will take the given data and write it to the serial port
    returns the data length or 0 indicating fail
    if cts is False, doesn't control the cts line
    """

    try:
        if cts:
            CTSControl("LOW")
        ans = fd.write(b''.join(send))
        logging.info("Message >%s< written to LoRa module with response :%s" % (send, ans))
        if cts:
            CTSControl("HIGH")
    except Exception as e:
        logging.warning("Message >%s< FAILED with response :%s" % (send, ans))
        ans = 0
    return ans

def DataLogPacketBuilder(data, inc_id=True, ewc_id=""):
    """
    See notes in book
    Takes the given data packet and
    - Increases the gbl_EWC_Pointer
        Checks for it wrapping around
    - Generates a full packet
        Adds it into the data structure
    returns the record
    if inc_id is False, the ID is not included
    """
    msg = []
    global gbl_EWC_Pointer              # Added as I am modifying the global variable
    global gbl_EWC_Records              # Added as I am modifying the global variable

    gbl_EWC_Pointer = gbl_EWC_Pointer + 1
    logging.debug("Datalog Packet being created / modified:%s" % gbl_EWC_Pointer)
    if gbl_EWC_Pointer >= Settings.QUANTITY_OF_RECORDS:
        # Pointer has jumped past the last record, reset to the start
        gbl_EWC_Pointer = 0
        logging.debug("Buffer reached limit and reset to zero")
    msg.append(Settings.CMD_DATALOG_PACKET)
    if inc_id:
        if ewc_id == "":
            msg = msg + Settings.EWC_ID
        else:
            msg = msg + ewc_id
            logging.debug("Wrong EWC ID Used:%s" % ewc_id)
    else:
        logging.debug("EWC ID NOT included")
    msg = msg + data
    # build pointer, lower part is simply AND'd with 0xFF, while the upper part is AND'd with 0xff00 and then shited 8 bits
    ptr_l = hex(gbl_EWC_Pointer & 0x000000ff).encode('utf-8')
    ptr_h = hex((gbl_EWC_Pointer & 0x0000ff00)>>8).encode('utf-8')
    msg.append(ptr_h)
    msg.append(ptr_l)
    msg.append(Settings.ETX)

    # Create and add the XOR checksum
    xor = 0
    for byte in (msg):
        logging.debug("byte being XOR'd:%s" % byte)
        xor = xor ^ int(binascii.b2a_hex(byte),16)

    msg.append(binascii.a2b_hex('{:02x}'.format(xor).encode('utf-8')))
    logging.info("Datalog Packet:%s" % msg)
    gbl_EWC_Records[gbl_EWC_Pointer] = msg
    return msg

def GenerateGoodPacket():
    """
    Generates and returns a single packet
    Uses the Packet Generator program to get a packet
    """
    # generated by the PacketGenerator script
    datalog = PacketGenerator.GeneratePacket()
    logging.debug("Data Packet Generated:%s" % datalog)
    packet = DataLogPacketBuilder(datalog)
    return packet

def GenerateErrorPacket(error):
    """
    Generates a packet with an error code first
    """
    # generated by the PacketGenerator script
    datalog = PacketGenerator.GeneratePacket(False,error)
    logging.debug("Data Packet Generated:%s" % datalog)
    packet = DataLogPacketBuilder(datalog)
    return packet

def Menu_ControlCTS(fd):
    """
    Allow the user to manually, or automatically toggle the CTS line
    """
    print("\nControl the CTS Line\n")
    choice = input("Choose (H)igh, (L)ow, (T)oggle or (R)epeatably Toggle:")
    if choice.upper() =="H":
        CTSControl("HIGH")
        print("CTS Now High")
    elif choice.upper() =="L":
        CTSControl("LOW")
        print("CTS Now Low")
    elif choice.upper() =="T":
        CTSControl("SWITCH")
        print("CTS Switched")
    elif choice.upper() =="R":
        speed =0
        while speed ==0:
            speed = input("Set time period (in seconds)")
            if speed.isdigit == False:
                print("Enter a number please")
                speed = 0
            elif speed < 0:
                print("Only positive numbers please")
                speed = 0
        print("CTRL-C to exit")
        try:
            while True:
                # in the loop waiting for the CTRL-C key press to exit
                starttime = datetime.datetime.now()
                endtime = starttime + datetime.timedelta(seconds=speed)
                while endtime > datetime.datetime.now():
                    print ("\r.", end="")
                CTSControl("SWITCH")
                print("Switched")
        except KeyboardInterrupt:
            print("Completed")
    else:
        print("Unknown Option")
    return

def SendSinglePacket(fd):
    """
    Send a single packet to the EWC
    Controls the CTS line automatically
    """
    print("Sending a packet")
    # Get a packet
    to_send = GenerateGoodPacket()

    # Send a packet
    ans = WriteDataBinary(fd,to_send)
    if ans > 0:
        print("Packet Sent: %s" % to_send)
    else:
        print("Failed to send packet")
    return

def SendRepeatingPacket(fd):
    """
    Allows the user to determine the speed of messaging and then sends a packet repeatably
    Controls the CTS line
    """

    speed =0
    while speed ==0:
        speed = input("Set time period (in seconds)")
        if speed.isdigit == False:
            print("Enter a number please")
            speed = 0
        else:
            if int(speed) < 0:
                print("Only positive numbers please")
                speed = 0
            else:
                speed = int(speed)
    print("CTRL-C to exit")
    try:
        while True:
            # in the loop waiting for the CTRL-C key press to exit
            starttime = datetime.datetime.now()
            endtime = starttime + datetime.timedelta(seconds=speed)
            while endtime > datetime.datetime.now():
                print ("\rWaiting", end="")
            print("\nSending a packet")
            # Get a packet
            to_send = GenerateGoodPacket()

            # Send a packet
            ans = WriteDataBinary(fd,to_send)
            if ans > 0:
                print("Packet Sent: %s" % to_send)
            else:
                print("Failed to Send Packet")
    except KeyboardInterrupt:
        print("Completed")
    return

def SendErrorPacket(fd):
    """
    Allow the user to select an error code and then send a single packet with the error code
    Controls the CTS line
    """
    err =0
    #Print the error codes

    while err ==0:
        err = input("Select Error Code (1 - %s)" % len(Settings.ERROR_CODES))
        if err.isdigit == False:
            print("Enter a number please")
            err = 0
        else:
            # Need to validate the error reqeusted is in the list of error codes
            # Convert to a binary number
            err_bin = binascii.unhexlify('{:02d}'.format(int(err)))
            if err_bin not in Settings.ERROR_CODES:
                print("Only numbers listed below are allowed\n%s" % Settings.ERROR_CODES)
                err = 0
    print("Sending a packet")
    # Get a packet
    to_send = GenerateErrorPacket(err)


    # Send a packet
    ans = WriteDataBinary(fd,to_send)
    if ans > 0:
        print("Packet Sent: %s" % to_send)
    else:
        print("Failed to Send Packet")
    return

def GenerateTooShort():
    """
    Send a data packet that is too short
    """
    # generated by the PacketGenerator script
    datalog = PacketGenerator.GeneratePacket()
    logging.debug("Datalog Packet Generated:%s" % datalog)
    packet = DataLogPacketBuilder(datalog[0:len(datalog)-1])
    return packet

def GenerateTooBig():
    """
    Send a data packet that is too big, added 0xff at the end
    """
    # generated by the PacketGenerator script
    datalog = PacketGenerator.GeneratePacket()
    datalog.append(b'\xff')
    logging.debug("Datalog Packet Generated:%s" % datalog)
    packet = DataLogPacketBuilder(datalog)
    return packet

def GenerateOutofSyncForward():
    """
    Send a data packet that is the wrong sequence number
    """
    for i in range(0,6):
        data = GenerateGoodPacket()
    return data

def GenerateOutofSyncBackward():
    """
    Send a data packet that is the wrong sequence number
    """
    cur_posn = gbl_EWC_Pointer
    if cur_posn > 5:
        new_posn = cur_posn - 5
    else:
        new_posn = 0
    logging.debug("Calculated position for sync backwards %s" % new_posn)
    data = gbl_EWC_Records[new_posn]
    return data

def GenerateWrongID():
    """
    Send a data packet with No ID at the front of it
    """
    wrong_ewc = [b'\x02',b'\xF0', b'\x00', b'\x0F']
    # generated by the PacketGenerator script
    datalog = PacketGenerator.GeneratePacket()
    logging.debug("Data Packet Generated:%s" % datalog)
    packet = DataLogPacketBuilder(datalog, ewc_id=wrong_ewc)
    return packet

def GenerateNoID():
    """
    Send a data packet that has NO ID in it
    """
    # generated by the PacketGenerator script
    datalog = PacketGenerator.GeneratePacket()
    logging.debug("Data Packet Generated:%s" % datalog)
    packet = DataLogPacketBuilder(datalog, inc_id=False)
    return packet

def Menu_BadPacket(fd):
    """
    Provide the menu to allow the different bad packets to be sent / received
    - Too small / big
    - Out of Sync
    - Wrong ID / No ID
    - CRC Error
    """
    print("\nSend a bad Packet from the EWC\n")
    print("Menu Options")
    print("------------\n\n")
    print("1 - Too short (1 byte)")
    print("2 - Too big (1 byte)")
    print("3 - Out of Sync Forward")
    print("4 - Out of Sync Backward")
    print("5 - Wrong ID")
    print("6 - No ID")
    print("any other key to return to previous menu")

    choice = input("Choose:")
    if choice =="1":
        to_send = GenerateTooShort()
    elif choice =="2":
        to_send = GenerateTooBig()
    elif choice =="3":
        to_send = GenerateOutofSyncForward()
    elif choice =="4":
        to_send = GenerateOutofSyncBackward()
    elif choice =="5":
        to_send = GenerateWrongID()
    elif choice =="6":
        to_send = GenerateNoID()

    ans = WriteDataBinary(fd,to_send)
    if ans > 0:
        print("Packet Sent: %s" % to_send)
    else:
        print("Failed to Send Packet")
    return

def Menu_IoTReply(fd):
    """
    Respond to the IoT commands automatically
    """
    print("Not Yet Implemented")
    return


def HelpText():
    """
    Display the list of commands possible for the program
    """
    print("Menu Options")
    print("------------\n\n")
    print("1 - Control CTS")
    print("2 - Send Datalog Packet")
    print("3 - Send Datalog Packet every x seconds")
    print("4 - Send Datalog Packet with error code ee")
    print("5 - Send bad Datalog Packet")
    print("0 - Respond to IoT")
    print("h - Show this help")
    print("e - exit")
    return

def SplashScreen():
    print("***********************************************")
    print("*        Bostin Technology Emulator           *")
    print("*                                             *")
    print("*       in association with eWater Pay        *")
    print("*                                             *")
    print("*                EWC Emulator                 *")
    print("***********************************************\n")
    return

def main():

    SplashScreen()

    logging.info("Application Started")
    conn = SerialSetup()

    HelpText()
    choice = ""
    while choice.upper() != "E":
        choice = input("Select Menu Option:")
        if choice == "1":
            Menu_ControlCTS(conn)
        elif choice == "2":
            SendSinglePacket(conn)
        elif choice == "3":
            SendRepeatingPacket(conn)
        elif choice == "4":
            SendErrorPacket(conn)
        elif choice == "5":
            Menu_BadPacket(conn)
        elif choice =="0":
            Menu_IoTReply(conn)
        elif choice.upper() =="E":
            print("Leaving")
            #exit()
        elif choice.upper() =="H":
            HelpText()
        else:
            print("Unknown Option")
    return

if __name__ == '__main__':

    conn = ""
    logging.basicConfig(filename="eWaterEmulator.txt", filemode="w", level=Settings.LG_LVL,
                        format='%(asctime)s:%(levelname)s:%(message)s')

    try:
        main()

    except Exception as err:
        # Write the Exception data
        logging.warning("Exception:%s" % traceback.format_exc())
        print("\nError Occurred, program halted - refer to log file\n")

    logging.info("gbl_EWC_Pointer:%s" % gbl_EWC_Pointer)
    logging.info("Capturing glb_EWC_Records data")
    for rcd in range(0, gbl_EWC_Pointer):
        logging.info("%s -> %s" %(rcd, gbl_EWC_Records[rcd]))
    if conn:
        conn.close()
    GPIO.cleanup()
    sys.exit()



