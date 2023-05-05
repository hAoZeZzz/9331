import time  # to calculate the time delta of packet transmission
import sys
import random
import socket  # Core lib, to send packet via UDP socket
import threading
import struct
import os

sender_port = int(sys.argv[1])
receiver_port = int(sys.argv[2])
sender_address = ("127.0.0.1", sender_port)
receiver_address = ("127.0.0.1", receiver_port)
filename = sys.argv[3]
max_win = int(sys.argv[4])
rto = int(sys.argv[5])

BUFFERSIZE = 1024
mss = 1000

# make packet easier to be understood
def get_in_bytes(type = 0, seqno = 0, data = b''):
    length = len(data)
    fmt = "!2i%ds" % length
    new = struct.pack(fmt, type, seqno, data)
    return new

def unpack_data(packet):
    length = len(packet) - 8
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
        self.packet = get_in_bytes(type=type, seqno=seqno, data=data)


# initialize socket
try:
    sender_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    sender_socket.bind(sender_address)
    sender_socket.settimeout(float(rto / 1000))
except:
    sys.exit()

# create a sender_log file
sender_log = open("sender_log.txt", "w")

# Define figure to be printed in the end
no_trans_segment = 0
no_retrans_segment = 0
no_dup_ack = 0

# check whether happen
if_rcv_seg = False  # confirm whether receive ack
if_start_timer = False  # confirm whether start timer
if_seg_timeout = False  # confirm whether timeout
if_fin_trans = False  # confirm whether close receive thread

start_time = time.time()

# first hand
seq = random.randint(0, 2 ** 16 - 1)
first_hand = Segment(type=2, seqno=seq)
sender_socket.sendto(first_hand.packet, receiver_address)
sender_log.writelines("snd 0 SYN {:5d} 0\n".format(seq))

# second hand
no_retrans_time = 0
while no_retrans_time < 3:
    try:
        packet_rev, address = sender_socket.recvfrom(BUFFERSIZE)
        if packet_rev:
            second_hand = unpack_data(packet_rev)
            curr_time = time.time()
            logtime = (curr_time - start_time) * 1000
            sender_log.writelines("rcv {:.3f} ACK {:5d} 0\n".format(logtime, second_hand.seqno))
            break
    except socket.timeout:
        no_retrans_segment += 1
        no_retrans_time += 1
        sender_socket.sendto(first_hand.packet, receiver_address)

if no_retrans_time == 3:
    reset_segment = Segment(type=4)
    sender_socket.sendto(reset_segment.packet, receiver_address)
    print("the connection is being reset.")
    no_retrans_time = 0
    sender_socket.close()
    sys.exit()


# separate file
seq += 1
send_starter = seq
lastno = seq  # last seq received

f = open(filename, "rb")
file_packets = []
f_state = os.stat(filename)
f_seq = seq
f_seq_list = [seq]
order = 0
while order < f_state.st_size:
    msg = f.read(mss)
    data_send = Segment(type=0, seqno=f_seq, data=msg)
    file_packets.append(data_send)
    f_seq += mss
    if f_seq > 2**16 - 1: 
        f_seq = (f_seq + 1) % (2**16)
    f_seq_list.append(f_seq)
    order += mss


# send file
class SenderThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        global seq
        global send_starter
        global lastno
        global no_trans_segment
        global no_retrans_segment
        global no_dup_ack
        global start_time
        global sending_time
        global if_rcv_seg
        global if_start_timer
        global if_seg_timeout
        global if_fin_trans
        global no_sending

        i = 0
        no_sending = [send_starter]
        while 1:
            # while (seq - send_starter) <= max_win and i < len(file_packets):
            while len(no_sending)-1 <= max_win / 1000 and i < len(file_packets):    
                # if seq + len(file_packets[i].data) - send_starter > max_win:
                #    break
                if len(no_sending) > max_win/1000:
                    break

                sender_socket.sendto(file_packets[i].packet, receiver_address)
                if not if_start_timer:
                    sending_time = time.time()
                    if_start_timer = True

                curr_time = time.time()
                logtime = (curr_time - start_time) * 1000
                sender_log.writelines("snd {:.3f} DATA {:5d} {:3d}\n".format(logtime, file_packets[i].seqno,
                                                                              len(file_packets[i].data)))

                no_trans_segment += 1




                seq += len(file_packets[i].data)
               
                
                if seq > 2 ** 16 - 1:
                    seq = (seq + 1) % (2**16)
                no_sending.append(seq)
                i += 1


            if if_fin_trans:
                break



class ReceiverThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        global seq
        global send_starter
        global lastno
        global no_trans_segment
        global no_retrans_segment
        global no_dup_ack
        global start_time
        global sending_time
        global if_rcv_seg
        global if_start_timer
        global if_seg_timeout
        global if_fin_trans
        global no_sending


        i = 0
        while True:
            if if_start_timer:
                try:
                    response, rcvaddress = sender_socket.recvfrom(BUFFERSIZE)
                    response_unpack = unpack_data(response)
                    if response_unpack.type == 1:
                        lastno = response_unpack.seqno

                        # if response_unpack.seqno > send_starter:
                        if no_sending.index(response_unpack.seqno) > no_sending.index(send_starter):
                            curr_time = time.time()
                            logtime = (curr_time - start_time) * 1000
                            sender_log.writelines("rcv {:.3f} ACK {:5d} 0\n".format(logtime, response_unpack.seqno))


                            i = 1
                            no_sending.remove(send_starter)
                            send_starter = response_unpack.seqno
                            if_rcv_seg = True

                            if seq != send_starter:  # existing unACKed
                                sending_time = time.time()
                                if_start_timer = True

                        else:
                            # if response_unpack.seqno == send_starter:
                            if no_sending.index(response_unpack.seqno) == no_sending.index(send_starter):
                                i += 1
                                no_dup_ack += 1
                                curr_time = time.time()
                                logtime = (curr_time - start_time) * 1000
                                sender_log.writelines("rcv {:.3f} ACK {:5d} 0\n".format(logtime, response_unpack.seqno))

                                if i >= 3:  # fast retransmitting
                                    i = 0

                                    j = f_seq_list.index(response_unpack.seqno)

                                    sender_socket.sendto(file_packets[j].packet, receiver_address)
                                    curr_time = time.time()
                                    logtime = (curr_time - start_time) * 1000
                                    sender_log.writelines("snd {:.3f} DATA {:5d} {:3d}\n".format(logtime, file_packets[j].seqno,
                                                                                                  len(file_packets[j].data)))


                                    if not if_start_timer:
                                        sending_time = time.time()
                                        if_start_timer = True

                                    no_retrans_segment += 1

                            else:
                                i = 0


                        if response_unpack.seqno == file_packets[-1].seqno + len(file_packets[-1].data):
                            if_fin_trans = True
                            break

                except socket.timeout:
                    
                    j = f_seq_list.index(no_sending[0])


                    sender_socket.sendto(file_packets[j].packet, receiver_address)
                    if not if_start_timer:
                        sending_time = time.time()
                        if_start_timer = True

                    curr_time = time.time()
                    logtime = (curr_time - start_time) * 1000
                    sender_log.writelines("snd {:.3f} DATA {:5d} {:3d}\n".format(logtime, file_packets[j].seqno,
                                                                                len(file_packets[j].data)))

                    time.sleep(0.02)
                    no_retrans_segment += 1

thread_list = []
snd_thread = SenderThread()
rcv_thread = ReceiverThread()
snd_thread.start()
rcv_thread.start()
thread_list.append(snd_thread)
thread_list.append(rcv_thread)
for i in thread_list:
    i.join()


if if_fin_trans:
    fin = Segment(type=3, seqno=(first_hand.seqno+2+f_state.st_size)%(2**16))
    sender_socket.sendto(fin.packet, receiver_address)
    curr_time = time.time()
    logtime = (curr_time - start_time) * 1000
    sender_log.writelines("snd {:.3f} FIN {:5d} 0\n".format(logtime, fin.seqno))

    no_retrans_time = 0
    while no_retrans_time < 3:
        try:
            fin_ack, address = sender_socket.recvfrom(BUFFERSIZE)
            if fin_ack:
                fin_ack_unpack = unpack_data(fin_ack)
                curr_time = time.time()
                logtime = (curr_time - start_time) * 1000
                sender_log.writelines("rcv {:.3f} ACK {:5d} 0\n".format(logtime, fin_ack_unpack.seqno))
                sender_socket.close()
                break
        except socket.timeout:
            no_retrans_segment += 1
            no_retrans_time += 1
            sender_socket.sendto(fin.packet, receiver_address)

    if no_retrans_time == 3:
        reset_segment = Segment(type=4)
        sender_socket.sendto(reset_segment.packet,receiver_address)
        sender_socket.close()


    sender_log.writelines("Amount fo (original) Data Transfered(in bytes): %d\n" % f_state.st_size)
    sender_log.writelines("Number of Data Segments Sent(excluding retransmissions): %d\n" % no_trans_segment)
    sender_log.writelines("Number of Retransmitted Data Segments: %d\n" % no_retrans_segment)
    sender_log.writelines("Number of Duplicate Acknowledgements received: %d\n" % no_dup_ack)

    f.close()
    sender_log.close()
