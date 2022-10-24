#!/usr/bin/python3
import subprocess, json, time, sys, re
from ipaddress import ip_network
from datetime import datetime
from random import randint
from pathlib import Path

class Latency:
    def __init__(self):
        self.configFiles = ['network.json']
        self.file,self.files = "network.json",{}
        for file in self.configFiles:
            if Path(file).exists():
                print("Loading",file)
                try:
                    with open(file) as handle:
                        self.files[file] = json.loads(handle.read())
                except:
                    self.files[file] = {"created":int(datetime.now().timestamp()),"updated":0}
            else:
                self.files[file] = {"created":int(datetime.now().timestamp()),"updated":0}

    def save(self):
        for file in self.configFiles:
            print(f"Saving {file}")
            with open(file, 'w') as f:
                json.dump(self.files[file], f, indent=4)

    def cmd(self,cmd):
        p = subprocess.run(cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        return [p.stdout.decode('utf-8'),p.stderr.decode('utf-8')]

    def sameNetwork(self,origin,target):
        o = ip_network(origin, strict = False).network_address
        t = ip_network(target, strict = False).network_address
        return o == t

    def parse(self,configRaw):
        parsed = re.findall('interface "([a-zA-Z0-9]{3,}?)".{50,200}?([0-9.]+).{50,200}?cost ([0-9.]+);',configRaw, re.DOTALL)
        data = []
        for nic,target,weight in parsed:
            data.append({'nic':nic,'target':target,'weight':weight})
        return data

    def getAvrg(self,row,weight=False):
        result = 0
        for entry in row:
            result += float(entry[0])
        if weight: return int(float(result / len(row)))
        else: return int(float(result / len(row)) * 10)

    def hasJitter(self,row,avrg):
        grace = 20
        for entry in row:
            if float(entry[0]) > avrg + grace: return True,float(entry[0]) - (avrg + grace)
        return False,0

    def getLatency(self,config,pings=4):
        fping = ["fping", "-c", str(pings)]
        for row in config:
            fping.append(row['target'])
        result = subprocess.run(fping, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        parsed = re.findall("([0-9.]+).*?([0-9]+.[0-9]).*?([0-9])% loss",result.stdout.decode('utf-8'), re.MULTILINE)
        latency =  {}
        for ip,ms,loss in parsed:
            if ip not in latency: latency[ip] = []
            latency[ip].append([ms,loss])
        for entry,row in latency.items():
            del row[0] #drop the first ping result
            row.sort()
            #del row[len(row) -1] #drop the highest ping result
        current = int(datetime.now().timestamp())
        total,loss,jittar = 0,0,0
        for node in list(config):
            for entry,row in latency.items():
                if entry == node['target']:
                    node['latency'] = self.getAvrg(row)
                    if entry not in self.files['network.json']: self.files['network.json'][entry] = {"packetloss":{},"jitter":{}}

                    threshold,eventCount,eventScore = 1,0,0
                    for event,lost in list(self.files['network.json'][entry]['packetloss'].items()):
                        if int(event) > int(datetime.now().timestamp()): 
                            eventCount += 1
                            eventScore += lost
                        #delete events after 30 minutes
                        elif (int(datetime.now().timestamp()) - 1800) > int(event):
                            del self.files['network.json'][entry]['packetloss'][event]
                    
                    if eventCount > 0:
                        eventScore = eventScore / eventCount
                    hadLoss = True if eventCount >= threshold else False
                    hasLoss,peakLoss = len(row) < pings -1,(pings -1) - len(row)

                    if hadLoss or hasLoss:
                        node['latency'] = node['latency'] + (500 * eventScore) #+ 50ms / weight
                        loss = loss +1

                    if hasLoss:
                        self.files['network.json'][entry]['packetloss'][int(datetime.now().timestamp()) + 300] = peakLoss
                        print(entry,"Packetloss detected","got",len(row),f"of {pings -1}")
                    elif hadLoss:
                        print(entry,"Ongoing Packetloss")

                    threshold,eventCount,eventScore = 5,0,0
                    for event,peak in list(self.files['network.json'][entry]['jitter'].items()):
                        if int(event) > int(datetime.now().timestamp()): 
                            eventCount += 1
                            eventScore += peak
                        #delete events after 30 minutes
                        elif (int(datetime.now().timestamp()) - 1800) > int(event):
                            del self.files['network.json'][entry]['jitter'][event]
                    
                    if eventCount > 0:
                        eventScore = eventScore / eventCount
                    hadJitter = True if eventCount > threshold else False
                    hasJitter,peakJitter = self.hasJitter(row,self.getAvrg(row,True))
                    
                    if hadJitter:
                        node['latency'] = node['latency'] + (100 * eventScore) #+ 10ms /weight
                        jittar += 1

                    if hasJitter:
                        self.files['network.json'][entry]['jitter'][int(datetime.now().timestamp()) + 300] = peakJitter
                        print(entry,"High Jitter dectected")
                    elif hadJitter:
                        print(entry,"Ongoing Jitter")
                    total += 1
                    #make sure its always int
                    node['latency'] = int(node['latency'])

        print (f"Total {total}, Jitter {jittar}, Packetloss {loss}")
        self.files['network.json']['updated'] = int(datetime.now().timestamp())
        return config

L = Latency()
#Check if bird is running
print("Checking bird/fping status")
bird = L.cmd("pgrep bird")
if bird[0] == "": raise Exception('bird2 not running, exiting.')
for run in range(3):
    #Getting config
    print("Reading bird config")
    configRaw = L.cmd("cat /etc/bird/bird.conf")[0].rstrip()
    #Parsing
    config = L.parse(configRaw)
    configs = L.cmd('ip addr show')
    #fping
    print("Running fping")
    result = L.getLatency(config,11)
    #update
    local = re.findall("inet (10\.0[0-9.]+\.1)\/(32|30) scope global lo",configs[0], re.MULTILINE | re.DOTALL)
    configRaw = re.sub(local[0][0]+"; #updated [0-9]+", local[0][0]+"; #updated "+str(int(time.time())), configRaw, 0, re.MULTILINE)
    for entry in result:
        if "latency" not in entry: entry['latency'] = 65000
        configRaw = re.sub("cost "+str(entry['weight'])+"; #"+entry['target'], "cost "+str(entry['latency'])+"; #"+entry['target'], configRaw, 0, re.MULTILINE)
    if not result:
        print("Nothing to do")
    else:
        #write
        print("Writing config")
        L.cmd("echo '"+configRaw+"' > /etc/bird/bird.conf")
        #reload
        print("Reloading bird")
        L.cmd('/usr/sbin/service bird reload')
    L.save()
    if run != 2: time.sleep(9)