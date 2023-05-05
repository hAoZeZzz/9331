import time  # to calculate the time delta of packet transmission
import sys
import random
import socket  # Core lib, to send packet via UDP socket
import threading
import struct


receiver_port = int(sys.argv[1])
sender_port = int(sys.argv[2])
receiver_address = ("127.0.0.1", receiver_port)
filename = sys.argv[3]
flp = float(sys.argv[4])
rlp = float(sys.argv[5])

BUFFERSIZE = 1024
mss = 0

# make packet easier to be understood
def get_in_bytes(type = 0, seqno = 0, length = mss, data = b''):
    fmt = "!2i%ds" % length
    new = struct.pack(fmt, type, seqno, data)
    return new

def unpack_data(packet):
    length = mss
    fmt = "!2i%ds" % length
    message = struct.unpack(fmt, packet)
    result = Segment(type=int(message[0]), seqno=int(message[1]), data=message[2])
    return result

# define format of segment
class Segment:
    def __init__(self, type=0, seqno=0, data=b''):
        self.type = type
        self.seqno = seqno
        self.data = data
        self.packet = get_in_bytes(type=type, seqno=seqno, length=mss, data=data)

# define segment loss function
def segment_loss(lp):
    rand_drop = random.random()
    if rand_drop > lp:
        return True
    else:
        return False

# initialize socket
try:
    receiver_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    receiver_socket.bind(receiver_address)
except:
    sys.exit()

# define timer to close socket
def close_socket():
    receiver_socket.shutdown(socket.SHUT_RDWR)
    receiver_socket.close()

# create a receiver_log file
receiver_log = open("Receiver_log.txt", "w")

# define figure to be printed in the end
amount_data_rcv = 0
no_data_segment_rcv = 0
no_dup_segment_rcv = 0
no_data_segment_drop = 0
no_ack_segment_drop = 0


f = open(filename, "wb")

# receive data and write file
expect_seq = 0
already_seq = []  # confirm whether send dup ack
last_seq = []  # the seqno that has been rcved
waiting_list = []  # to buffer the out order segments

# message, sender_address = receiver_socket.recvfrom(BUFFERSIZE)
start_time = time.time()
# mss = len(message) - 8
# message_unpack = unpack_data(message)

while True:
    try:
        message, sender_address = receiver_socket.recvfrom(BUFFERSIZE)
        mss = len(message) - 8
        message_unpack = unpack_data(message)

        if message_unpack.type == 4:  # RESET segment received
            print("the connection is being reset.")
            receiver_socket.close()
            sys.exit()

        result = segment_loss(flp)
        if not result:
            if message_unpack.type == 0:  # drop DATA segment
                no_data_segment_drop += 1
                curr_time = time.time()
                logtime = (curr_time - start_time) * 1000
                receiver_log.writelines("drp {:.3f} DATA {:5d} {:4d}\n".format(logtime, message_unpack.seqno,
                                                                                    len(message_unpack.data)))


            elif message_unpack.type == 3:  # drop FIN segment
                curr_time = time.time()
                logtime = (curr_time - start_time) * 1000
                receiver_log.writelines("drp {:.3f} FIN {:5d} 0\n".format(logtime, message_unpack.seqno))
            
            elif message_unpack.type == 2: # drop SYN segment
                curr_time = time.time()
                logtime = (curr_time - start_time) * 1000
                receiver_log.writelines("drp {:.3f} SYN {:5d} 0\n".format(logtime, message_unpack.seqno))

        else:
            if message_unpack.type == 2:  # SYN segments received
                receiver_log.writelines("rcv 0 SYN {:5d} 0\n".format(message_unpack.seqno))

                # second hand
                rand_reverse = random.random()
                second_hand = Segment(type=1, seqno=message_unpack.seqno + 1)
                expect_seq = second_hand.seqno
                curr_time = time.time()
                logtime = (curr_time - start_time) * 1000
                receiver_log.writelines("snd {:.3f} ACK {:5d} 0\n".format(logtime, second_hand.seqno))

                if rand_reverse < rlp:
                    no_ack_segment_drop += 1
                else:
                    receiver_socket.sendto(second_hand.packet, sender_address)

            elif message_unpack.type == 0:  # DATA segments received
                no_data_segment_rcv += 1
                
                if message_unpack.seqno == expect_seq:  # DATA segments in order
                    amount_data_rcv += len(message_unpack.data)
                    f.write(message_unpack.data)
                    expect_seq += len(message_unpack.data)
                    if expect_seq > 2**16-1:
                        expect_seq = (expect_seq + 1) % (2**16)
                    last_seq.append(message_unpack.seqno)

                    curr_time = time.time()
                    logtime = (curr_time - start_time) * 1000
                    receiver_log.writelines("rcv {:.3f} DATA {:5d} {:3d}\n".format(logtime, message_unpack.seqno,
                                                                                        len(message_unpack.data)))

                    i = 0  # need check whether there are segments already been transferred
                    while i < len(waiting_list):
                        if waiting_list[i].seqno == expect_seq:
                            f.write(waiting_list[i].data)
                            expect_seq += len(waiting_list[i].data)
                            if expect_seq > 2**16-1:
                                expect_seq = (expect_seq + 1) % (2**16)
                            amount_data_rcv += len(waiting_list[i].data)
                            del waiting_list[i]
                            i -= 1
                        i += 1

                    # send back ack
                    time.sleep(0.01)
                    response = Segment(type=1, seqno=expect_seq)
                    result = segment_loss(rlp)
                    if result:
                        receiver_socket.sendto(response.packet, sender_address)
                        curr_time = time.time()
                        logtime = (curr_time - start_time) * 1000
                        receiver_log.writelines("snd {:.3f} ACK {:5d} 0\n".format(logtime, response.seqno))

                    else:  # fail to send back ack
                        no_ack_segment_drop += 1
                        curr_time = time.time()
                        logtime = (curr_time - start_time) * 1000
                        receiver_log.writelines("drp {:.3f} ACK {:5d} 0\n".format(logtime, response.seqno))

                else:  # receive segment which is out of order
                    
                    if message_unpack.seqno in last_seq:  # if have received it
                        no_dup_segment_rcv += 1
                        curr_time = time.time()
                        logtime = (curr_time - start_time) * 1000
                        receiver_log.writelines("rcv {:.3f} DATA {:5d} {:3d}\n".format(logtime, message_unpack.seqno, 
                                                                                    len(message_unpack.data)))

                    else:
                        last_seq.append(message_unpack.seqno)
                        curr_time = time.time()
                        logtime = (curr_time - start_time) * 1000
                        receiver_log.writelines("rcv {:.3f} DATA {:5d} {:3d}\n".format(logtime, message_unpack.seqno, 
                                                                                    len(message_unpack.data)))

                        
                        waiting_list.append(message_unpack) # put into buffer

                    # send back ack
                    time.sleep(0.01)
                    response = Segment(type=1,seqno=expect_seq)
                    result = segment_loss(rlp)
                    if result:
                        receiver_socket.sendto(response.packet, sender_address)
                        curr_time = time.time()
                        logtime = (curr_time - start_time) * 1000
                        receiver_log.writelines("snd {:.3f} ACK {:5d} 0\n".format(logtime, response.seqno))
                    
                    else: # fail to send back ack
                        no_ack_segment_drop += 1
                        curr_time = time.time()
                        logtime = (curr_time - start_time) * 1000
                        receiver_log.writelines("drp {:.3f} ACK {:5d} 0\n".format(logtime, response.seqno))
                    
                    
                    

            elif message_unpack.type == 3:  # received FIN segment
                receiver_socket.settimeout(2)

                first_end = message_unpack
                curr_time = time.time()
                logtime = (curr_time - start_time) * 1000
                receiver_log.writelines("rcv {:.3f} FIN {:5d} 0\n".format(logtime, first_end.seqno))

                # send back FIN-ACK
                second_end = Segment(type=1, seqno=first_end.seqno+1)
                result = segment_loss(rlp)
                if result:
                    receiver_socket.sendto(second_end.packet, sender_address)
                    curr_time = time.time()
                    logtime = (curr_time - start_time) * 1000
                    receiver_log.writelines("snd {:.3f} ACK {:5d} 0\n".format(logtime, second_end.seqno))
                    break

                else:  # fail to send back ack
                    no_ack_segment_drop += 1
                    curr_time = time.time()
                    logtime = (curr_time - start_time) * 1000
                    receiver_log.writelines("drp {:.3f} ACK {:5d} 0\n".format(logtime, second_end.seqno))
    
    except socket.timeout:
        break

receiver_socket.close()

receiver_log.writelines("Amount of DATA Received: %d\n" % amount_data_rcv)
receiver_log.writelines("Number of DATA Segments Received: %d\n" % no_data_segment_rcv)
receiver_log.writelines("Number of duplicate Data segments received: %d\n" % no_dup_segment_rcv)
receiver_log.writelines("Number of Data segments dropped: %d\n" % no_data_segment_drop)
receiver_log.writelines("Number of ACK segments dropped: %d\n" % no_ack_segment_drop)

f.close()
receiver_log.close()
