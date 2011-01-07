

########################################################################################################################
import sys
import socket
import logging
import time
import random
import traceback
import re
import struct
from md5 import md5
import select


########################################################################################################################
N_SECONDS = 1.0
DISCARD_THRESHOLD = 4
KICK_THRESHOLD = 32

########################################################################################################################
logger = logging.getLogger("WebSocketServer")

########################################################################################################################
def logerr():
    logger.warning(traceback.format_exc())

########################################################################################################################
class Bucket:
    pass

########################################################################################################################
########################################################################################################################
class WebSocketServer:

    #-------------------------------------------------------------------------------------------------------------------
    def __init__(self, serverHost, serverPort, wsOrigin, wsLocation):
        """ Initializes the server and starts listening on the given port."""
        self.wsOrigin = wsOrigin
        self.wsLocation = wsLocation
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)        
        logger.info(" host %s listening on port %d." % (serverHost, serverPort))
        self.sock.setblocking(0)
        self.sock.bind((serverHost, serverPort))
        self.sock.listen(5)
        self.epoll = select.epoll()
        self.epoll.register(self.sock.fileno(), select.EPOLLIN)
        self.clientHandlers = {}
        self.onClientOpen = self.blankCallback
        self.onClientClose = self.blankCallback
        self.onMessage = self.blankCallback
        self.removalRegistry = []     
        self.addrs = {}   
        self.addrHashes = {}
        self.hashAddrs = {}
        self.filenoSocks = {}
        self.blacklist = []

    #-------------------------------------------------------------------------------------------------------------------
    def serve(self):
        """ Performs one iteration of client handling."""
        accepted = False
        # Handle sockets.
        clientSockets = self.clientHandlers.keys()
        events = self.epoll.poll(1)
        for fileno, event in events:
            if fileno == self.sock.fileno():
                accepted = True
                sock, addr = self.sock.accept()
                self.clientHandlers[sock] = ClientHandler(sock, addr, self)
                self.epoll.register(sock.fileno(), select.EPOLLIN | select.EPOLLOUT)
                self.filenoSocks[sock.fileno()] = sock
                if self.getAddr(addr).clientHandler != None:
                    self.getAddr(addr).clientHandler.close()    
                self.getAddr(addr).clientHandler = self.clientHandlers[sock]
            elif event & select.EPOLLIN:
                sock = self.filenoSocks[fileno]
                if self.clientHandlers[sock] not in self.removalRegistry:
                    self.clientHandlers[sock].receive()
            elif event & select.EPOLLOUT:
                sock = self.filenoSocks[fileno]
                if self.clientHandlers[sock] not in self.removalRegistry:
                    self.clientHandlers[sock].write()
            elif sock in selectError:
                sock = self.filenoSocks[fileno]
                if self.clientHandlers[sock] not in self.removalRegistry:
                    self.clientHandlers[sock].close()
                
        # Close removalRegistry clientHandlers and their sockets.
        for clientHandler in self.removalRegistry:
            # Decrement the connection count.
            self.getAddr(clientHandler.addr).numConnections -= 1
            try:
                if clientHandler.sock in self.clientHandlers:
                    del self.clientHandlers[clientHandler.sock]
            except:
                logerr()
            # Try to close the connection.
            try:
                clientHandler.sock.close()
            except socket.error:
                logerr()
            # Tell the application that we lost a clientHandler.
            self.onClientClose(clientHandler)
        
        # Empty the removal registry.
        self.removalRegistry = []
        
        return accepted



    #-------------------------------------------------------------------------------------------------------------------
    def getAddr(self, addr):
        iph = self.addrHash(addr)
        if iph not in self.addrs:
            b = Bucket()
            b.numConnections = 0
            b.requests = []
            b.clientHandler = None
            self.addrs[iph] = b
        return self.addrs[iph]

    #-------------------------------------------------------------------------------------------------------------------
    def addrHash(self, addr):
        if addr[0] not in self.addrHashes:
            hsh = hex(abs(hash(addr[0] + "wsssalt")))[2:]
            self.addrHashes[addr[0]] = hsh
            self.hashAddrs[hsh] = addr
        return self.addrHashes[addr[0]]

    #-------------------------------------------------------------------------------------------------------------------
    def removeClient(self, clientHandler):
        self.removalRegistry.append(clientHandler)

    #-------------------------------------------------------------------------------------------------------------------
    def getClients(self):
        return self.clientHandlers.values()

    #-------------------------------------------------------------------------------------------------------------------
    def close(self):
        """ Close the server."""
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()       

    #-------------------------------------------------------------------------------------------------------------------
    @staticmethod    
    def blankCallback(*args, **kwargs):
        pass
    

########################################################################################################################
handshake75  = "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
handshake75 += "Upgrade: WebSocket\r\n"
handshake75 += "Connection: Upgrade\r\n"
handshake75 += "WebSocket-Origin: %s\r\n"
handshake75 += "WebSocket-Location: %s\r\n\r\n"
    
handshake76  = "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
handshake76 += "Upgrade: WebSocket\r\n"
handshake76 += "Connection: Upgrade\r\n"
handshake76 += "Sec-WebSocket-Origin: %s\r\n"
handshake76 += "Sec-WebSocket-Location: %s\r\n\r\n%s"

    
########################################################################################################################
########################################################################################################################
class ClientHandler():

    #-------------------------------------------------------------------------------------------------------------------
    def __init__(self, sock, address, server):
        self.sock = sock
        self.addr = address
        self.server = server
        self.sock.setblocking(0)
        self.handshaken = False
        self.outData = ""
        self.data = ""
        self.messages = []
                
    #-------------------------------------------------------------------------------------------------------------------
    def close(self):
        logger.debug(" deleting socket %s" % self.addr[0])
        self.server.removeClient(self)
        
    #-------------------------------------------------------------------------------------------------------------------
    def receive(self):
        try:
            recvd = self.sock.recv(4096)
        except socket.error, e:
            self.close()
            return
        if not recvd:
            self.close()
            return            
        self.data += recvd
        if not self.handshaken:
            try:
                lines = self.data.split('\r\n')
                if len(lines) >= 7:
                    wsOrigin = lines[4].replace("Origin:", '').strip()
                    if lines[6] == '':
                        # This is the old school protocol, respond without key.
                        eof = self.data.find('\r\n\r\n')
                        self.data = self.data[eof + 4:]
                        self.handshaken = True
                        self.sock.send(handshake75 % (wsOrigin, self.server.wsLocation))
                        self.server.onClientOpen(self)
                    elif len(lines) >= 9:
                        key1 = lines[5].replace("Sec-WebSocket-Key1: ", '')
                        key2 = lines[6].replace("Sec-WebSocket-Key2: ", '')
                        key1 = int(re.sub("\\D", "", key1))/re.subn(" ", "", key1)[1]
                        key2 = int(re.sub("\\D", "", key2))/re.subn(" ", "", key2)[1]
                        challenge = ""
                        challenge += struct.pack("!I", key1)
                        challenge += struct.pack("!I", key2)
                        challenge += lines[8].replace("\r\n", '')
                        response = md5(challenge).digest()
                        self.data = self.data[self.data.find(lines[8].replace("\r\n", '')) + 8:]
                        self.handshaken = True
                        self.sock.send(handshake76 % (wsOrigin, self.server.wsLocation, response))
                        self.server.onClientOpen(self)
            except:
                logerr()
                self.close()
        else:
            addr = self.server.getAddr(self.addr)
            currentTime = time.time()
            addr.requests.append(currentTime)
            for t in addr.requests[:]:
                if currentTime - t > N_SECONDS:
                    addr.requests.remove(t)
            if len(addr.requests) > KICK_THRESHOLD:
                for ch in addr.clientHandlers:
                    try:
                        ch.close()
                    except:
                        logerr()
                return
            if len(addr.requests) > DISCARD_THRESHOLD:
                self.data = ""
                return
            xff = self.data.find("\xff")
            while xff != -1:
                message = self.data[:xff].replace("\x00", "")
                self.messages.append(message)
                self.server.onClientMessage(self)
                self.data = self.data[xff + 1:]
                xff = self.data.find("\xff")
                if len(self.messages) > 0:
                    return True
        return False
        
    #-------------------------------------------------------------------------------------------------------------------
    def write(self):
        if len(self.outData) == 0:
            return
        if len(self.outData) > 0:
            try:
                sent = self.sock.send(self.outData)
                self.outData = self.outData[sent:]
            except:
                self.close()
                return                

    #-------------------------------------------------------------------------------------------------------------------
    def get(self):
        messages = self.messages
        self.messages = []
        return messages
    
    #-------------------------------------------------------------------------------------------------------------------
    def put(self, message):
        self.outData += "\x00" + message + "\xff"
        
    #-------------------------------------------------------------------------------------------------------------------
    def getAddrHash(self):
        return self.server.addrHash(self.addr)    
        
    

########################################################################################################################
########################################################################################################################
if __name__ == "__main__":

    wss = WebSocketServer("192.168.0.198", 9999, "http://192.168.0.198", "ws://192.168.0.198:9999/")
    while True:
        wss.serve()
        for ch in wss.getClients():
            for message in ch.get():
                ch.put('You say, "%s"' % message)
        
        


    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

