#!/usr/bin/env python


#-------------------------------------------------------------------------------
import sys
import time
import commands
import ConfigParser
import logging
import re
import traceback
from urlparse import urljoin
from BeautifulSoup import BeautifulSoup, Comment
from simplejson import dumps, loads
logging.basicConfig(format = "%(asctime)-15s %(levelname)s %(name)s %(message)s", level = logging.DEBUG) 


#-------------------------------------------------------------------------------
import wss
import names


#-------------------------------------------------------------------------------
config = ConfigParser.ConfigParser()
config.read("config.cfg")

sharding = 16
subreddits = {}
topSubreddits = []
numClients = 0
clientNames = {}

symbolOrds = range(33, 48)
symbolOrds.extend(range(58,65))
symbolOrds.extend(range(91, 97))
symbolOrds.extend(range(123, 255))
safeOrds = range(32, 128)


################################################################################
def sanitize(html):
    html = ''.join(["&#%d;" % ord(i) if ord(i) in symbolOrds else i for i in html])
    return html
    

################################################################################
def strip(html):
    html = html.strip()    
    html = ''.join([i if ord(i) in safeOrds else '' for i in html])
    return html    


################################################################################
def ib(foo):
    lstrik = foo.find("&#42;&#42;", 0)
    while lstrik > -1:
        rstrik = foo.find("&#42;&#42;", lstrik + 10)
        if rstrik == -1:
            break
        foo = foo[:lstrik] + "<b>" + foo[lstrik+10:rstrik] + "</b>" + foo[rstrik+10:]
        lstrik = foo.find("&#42;&#42;", rstrik + 10)
    lstrik = foo.find("&#42;", 0)
    while lstrik > -1:
        rstrik = foo.find("&#42;", lstrik + 5)
        if rstrik == -1:
            break
        foo = foo[:lstrik] + "<i>" + foo[lstrik+5:rstrik] + "</i>" + foo[rstrik+5:]
        lstrik = foo.find("&#42;", rstrik + 5)
    return foo


################################################################################
def logerr():
    logging.warning(traceback.format_exc())


################################################################################
def updateSharding():
    global sharding
    f = open("sharding", 'r')
    sharding = int(f.readline().strip())
    f.close()


################################################################################
def echoShardSize(subreddit, shard):
    try:
        numClients = len(shard)
        for client in shard:
            client.put(jdicto(y = 'n', n = numClients, s = subreddit))
    except:
        logerr()


################################################################################
def createSubreddit(subredditName):
    if subredditName in subreddits:
        return
    else:
        subreddits[subredditName] = {"shards": [], "lastTen": [], 'population': 1}
        

################################################################################
def removeClientFromSubreddit(clientHandler, subreddit):
    try:
        if subreddit not in clientHandler.subreddits:
            return
        shard = clientHandler.subreddits[subreddit]
        del clientHandler.subreddits[subreddit]
        if not clientHandler in shard:
            return
        shard.remove(clientHandler)
        if len(shard) == 0:
            subreddits[subreddit]["shards"].remove(shard)
            if len(subreddits[subreddit]["shards"]) == 0:
                del subreddits[subreddit]
                if subreddit in topSubreddits:
                    topSubreddits.remove(subreddit)
                logging.debug("Deleted subreddit %s" % subreddit)
        else:
            # Tell the subreddit the number of clients.
            echoShardSize(subreddit, shard)
    except:
        logerr()


################################################################################
def addClientToSubreddit(clientHandler, subreddit):

    # If the client is already in that subreddit, skip.
    if subreddit in subreddits:
        if subreddit in clientHandler.subreddits:
            return

    # If the subreddit does not exist, create it.
    if subreddit not in subreddits:
        createSubreddit(subreddit)
        logging.debug("Created subreddit %s" % subreddit)
    
    # Add the clientHandler to a shard in that subreddit.
    minShard = None
    minPopulation = 1e300
    emptyShards = []
    
    # Find the shard with the smallest population.
    for shard in subreddits[subreddit]["shards"]:
        if len(shard) < minPopulation:
            if len(shard) > 0 and len(shard) < sharding:
                minShard = shard
                minPopulation = len(shard)
            else:
                emptyShards.append(shard)
    
    # If there is such a shard, add the clientHandler to it.
    if minShard is not None:
        shard = minShard
        shard.append(clientHandler)
    
    # Otherwise, create a new shard and add the poor lonely clientHandler to it.
    else:
        shard = [clientHandler]
        clientHandler.shard = shard
        subreddits[subreddit]["shards"].append(shard)
        subreddits[subreddit]["lastTen"] = []
        
    # Add the subreddit/shard to the clientHandler
    clientHandler.subreddits[subreddit] = shard
    
    # Tell the subreddit the number of clients.
    echoShardSize(subreddit, shard)
    
    # Inform the new client of the last ten messages.
    for chat in reversed(subreddits[subreddit]["lastTen"]):
        clientHandler.put(chat)
    
    # Delete any empty shards we might have found.
    for shard in emptyShards:
        subreddits[subreddit]["shards"].remove(shard)
        if len(subreddits[subreddit]["shards"]) == 0:
            del subreddits[subreddit]
            logging.debug("Deleted subreddit %s" % subreddit)




################################################################################
def jdicto(**kwargs):
    return dumps(kwargs)
    

################################################################################
def onClientOpen(clientHandler):
    global numClients, names

    # Increment the client count.
    numClients += 1

    # Give the client a random name.
    rname = names.randomName()
    while rname in clientNames:
        rname = names.randomName()
    clientHandler.name = rname
    clientNames[rname] = clientHandler
    
    # Give the client an empty subreddit list.
    clientHandler.subreddits = {}
    

################################################################################
def onClientClose(clientHandler):
    global numClients, subreddits
    try:
        if hasattr(clientHandler, "subreddits"):
            for subreddit in clientHandler.subreddits.keys():
                removeClientFromSubreddit(clientHandler, subreddit)
    except:
        logerr()
    try:
        if hasattr(clientHandler, "name"):
            if clientHandler.name in clientNames:
                del clientNames[clientHandler.name]
            numClients = max(numClients - 1, 0)
    except:
        logerr()
    


################################################################################
def onClientMessage(clientHandler):

    # Get all incoming messages.
    messages = clientHandler.get()
    
    # Handle messages.
    for msg in messages:
    
        # Decode the message.
        try:
            jmsg = loads(msg)    
        except:
            logerr()
            continue
        
        # Check that the message type exists.
        if not 'y' in jmsg:
            logging.debug("malformed message: %s" % str(jmsg))
            continue

        # Handle a subreddit entrance message.
        ########################################################################
        if jmsg['y'] == 'u':
            addClientToSubreddit(clientHandler, jmsg['u'])            

            continue
                    

        # Handle a subreddit exit message:
        ########################################################################
        if jmsg['y'] == 'x':
            
            # Make sure it has the subreddit we're exiting.
            if not 'x' in jmsg:
                continue
            
            # Remove the clientHandler from the shard.
            removeClientFromSubreddit(clientHandler, jmsg['x'])
            
            continue


        # Handle a chat-type message.
        ########################################################################
        if jmsg['y'] == 'c':
        
            # Set the timestamp.
            jmsg['t'] = int(time.time() * 1000)
            
            # Make sure the client is in a shard and get it.
            try:
                subreddit = jmsg['s']
                if not subreddit in clientHandler.subreddits:
                    addClientToSubreddit(clientHandler, subreddit)
                shard = clientHandler.subreddits[subreddit]
            except:
                logerr()
                continue
            
            # Broadcast.
            if jmsg['c'].startswith("/broadcast"):
                if clientHandler.name != "adminUsername":
                    clientHandler.put(jdicto(y = 'w', w = "What?"))
                    continue
                line = jmsg['c'].replace("/broadcast", '').strip()
                for ch in clientHandler.server.clientHandlers.values():
                    try:
                        ch.put(jdicto(y = 'f', f = line))
                    except:
                        logerr()
                continue

            # If it starts with a '/', reject.
            if jmsg['c'].startswith("/"):
                clientHandler.put(jdicto(y = 'w', w = "What?"))
                continue
            
            # Make sure it's of the right length.
            if len(jmsg['c']) > 512:
                clientHandler.put(jdicto(y = 'w', w = "Too long of a message."))
                continue
            if len(jmsg['c'].strip()) < 1:
                clientHandler.put(jdicto(y = 'w', w = "That's not really a message at all."))
                continue
            
            # Apply the user name.
            try:
                jmsg['n'] = clientHandler.name
            except:
                logerr()
                continue
                
            # Attach the addrHash to the message.
            try:
                jmsg['h'] = clientHandler.getAddrHash()
            except:
                logerr()
                continue
            
            # Handle a link type message.
            try:
                jmsg['c'] = sanitize(strip(jmsg['c']))
                r = re.compile(r"(http&#58;&#47;&#47;[^ ]+)")
                jmsg['c'] = r.sub(r'<a href="\1" target="_blank">\1</a>', jmsg['c'])            
                r = re.compile(r"(https&#58;&#47;&#47;[^ ]+)")
                jmsg['c'] = r.sub(r'<a href="\1" target="_blank">\1</a>', jmsg['c'])            
            except:
                logerr()
                continue
                
            # Handle bold and italics.
            try:
                jmsg['c'] = ib(jmsg['c'])
            except:
                logerr()
                continue
            
                
            # Recompile the message.
            try:
                msg = dumps(jmsg)
            except:
                logerr()
                continue
            
            # Send the message to the clients in this shard, or the target recipient if there is one.
            try:
                if 'a' in jmsg:
                    if jmsg['a'] in clientHandler.server.addrs:
                        b = clientHandler.server.addrs[jmsg['a']]
                        b.clientHandler.put(msg)
                        clientHandler.put(msg)
                else:
                    for client in shard:
                        client.put(msg)
                    # Push this one onto the lastTen list.
                    lastTen = subreddits[subreddit]["lastTen"]
                    lastTen.insert(0, msg)
                    subreddits[subreddit]["lastTen"] = lastTen[:32]
            except:
                logerr()
                continue
        
            
            continue
            
                
        # Handle a name-type message.
        ########################################################################
        if jmsg['y'] == 'n':
            
            # Make sure it has the name component.
            if 'n' not in jmsg:
                logging.debug("malformed message: %s" % str(jmsg))
                continue

            # Get the name in a handy variable.
            desire = jmsg['n'].strip()
            desire = desire.replace(" ", '')
            
            # Use my name.
            if desire == "adminPassword":
                clientNames["adminUsername"] = clientHandler
                del clientNames[clientHandler.name]
                clientHandler.name = "adminUsername"
                clientHandler.put(jdicto(y = 'f', f = "Hello, Dave."))
                continue

            # Handle random name request.
            if desire == "/random":
                rname = names.randomName()
                while rname in clientNames:
                    rname = names.randomName()
                del clientNames[clientHandler.name]
                clientHandler.name = rname
                clientNames[rname] = clientHandler
                clientHandler.put(jdicto(y = 'f', f = "You are now %s." % rname))
                continue

            # Make sure it's not too long.
            if len(desire) > 21:
                clientHandler.put(jdicto(y = 'w', w = "Name too long (21 character maximum)."))
                continue

            desire = strip(desire)
            
            # Make sure it's not too short.
            if len(desire) < 3 and len(desire) > 0:
                clientHandler.put(jdicto(y = 'w', w = "Name too short (3 character minimum)."))
                continue
                
            desire = sanitize(desire)

            # Make sure it's not too short.
            if len(desire) < 3 and len(desire) > 0:
                clientHandler.put(jdicto(y = 'w', w = "Name too short (3 character minimum)."))
                continue
                
            # Make sure this name does not already exist.
            if desire in clientNames:
                if clientNames[desire] == clientHandler:
                    clientHandler.put(jdicto(y = 'f', f = "You are already %s." % desire))
                else:
                    clientHandler.put(jdicto(y = 'w', w = "Name already in use."))
                continue
                
            # Can't use my name.
            if desire.lower() == "adminUsername":
                clientHandler.put(jdicto(y = 'w', w = "Don't be silly."))
                continue

            # Tell me my name!
            if desire == "":
                clientHandler.put(jdicto(y = 'f', f = "You are %s." % clientHandler.name))
                continue
            
            # This name appears to be okay. Delete the old name and use this one.
            del clientNames[clientHandler.name]
            clientHandler.name = desire
            clientNames[desire] = clientHandler
            clientHandler.put(jdicto(y = 'f', f = "You are now %s." % desire))
        
            continue
        
                
        # Handle a top ten request.
        ########################################################################
        if jmsg['y'] == 't':
        
            trs = {}
            for tr in topSubreddits:
                trs[tr] = subreddits[tr]['population']
            clientHandler.put(jdicto(y='t', t=trs))
                            
                
        # Handle an emote message:
        ########################################################################
        if jmsg['y'] == 'e':
        
            # Check form.
            if 'e' not in jmsg:
                logging.debug(" malformed message: %s" % str(jmsg))
                continue
        
            # Sanitize it.
            try:
                emote = sanitize(strip(jmsg['e'][:512]))
            except:
                logerr()
                continue

            # Create the emote.
            try:
                msg = jdicto(y = 'e', e = emote, n = clientHandler.name, h = clientHandler.getAddrHash(), s = jmsg['s'])
            except:
                logerr()
                continue

            # Send the message to the clients in this shard.
            for client in clientHandler.subreddits[jmsg['s']]:
                client.put(msg)
                
            # Push this one onto the lastTen list.
            try:
                lastTen = subreddits[jmsg['s']]["lastTen"]
                lastTen.insert(0, msg)
                subreddits[jmsg['s']]["lastTen"] = lastTen[:32]
            except:
                logerr()
                continue
                
                
                    
################################################################################
################################################################################
def main():

    print "Starting chattit."

    serverHost = commands.getoutput("ifconfig").split("\n")[1].split()[1][5:]
    serverPort = 9998
    if serverHost.startswith("192"):
        wsOrigin   = "chrome-extension://babbojgbjcianhbiocmekglcgibbbjen"
    else:
        wsOrigin   = "chrome-extension://igompnenmemgiffpkhmblimkmaagdgoe"
    wsLocation = "ws://%s:%d/" % (serverHost, serverPort)

    server = wss.WebSocketServer(serverHost, serverPort, wsOrigin, wsLocation)
    server.onClientMessage = onClientMessage
    server.onClientClose = onClientClose
    server.onClientOpen = onClientOpen

    updateSharding()

    updateTime = 0

    # Load balancing.
    lastTime = 0
    sleepy = 0.1
    ZzzTotal = sleepy
    ZzzCount = 0

    # Loop forever.
    while True:

        # Run the server.
        while server.serve():
            pass
        
        # Check to see if it's time to run periodic jobs.
        currentTime = time.time()
        if currentTime - updateTime > 1.0:
            updateTime = currentTime
            
            # Update sharding value.
            updateSharding()
            
            # Update subreddit populations.
            for subreddit in subreddits.keys():
                subreddits[subreddit]['population'] = 0
                for shard in subreddits[subreddit]['shards']:
                    subreddits[subreddit]['population'] += len(shard)
                if subreddit not in topSubreddits:
                    if len(topSubreddits) < 10:
                        topSubreddits.append(subreddit)
                    else:
                        for sr in topSubreddits:
                            if subreddits[subreddit]['population'] > subreddits[sr]['population']:
                                topSubreddits.remove(sr)
                                topSubreddits.append(subreddit)
                                break
            
            # Log load information.
            logging.info("chattit 2.0: %d subreddits open, %d clients, %5.2f%% idle" %(len(subreddits), 
                         len(server.clientHandlers.keys()), 100*ZzzTotal/max(ZzzCount, 1)))
#            if 100*ZzzTotal/max(ZzzCount, 1) < 1.0:
#                sys.exit()
            ZzzTotal = 0
            ZzzCount = 0

                                        
        Zzz = max(0.0, sleepy - (time.time() - lastTime))
        ZzzTotal += Zzz / sleepy
        ZzzCount += 1
        time.sleep(Zzz)
        lastTime = time.time()
                

if __name__ == "__main__":
    main() 
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
