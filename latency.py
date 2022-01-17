#!/usr/bin/python3
import subprocess, datetime, json, time, sys, re
from ipaddress import ip_network
from datetime import datetime
from random import randint
from pathlib import Path

class Latency:
    def __init__(self):
        self.configFiles,cron = ['events.json','peering.json','longtime.json'],[5,15,25,35,45,55]
        self.long,self.file,self.files = False,"peering.json",{}
        if len(sys.argv) == 2 and sys.argv[1] == "longtime" or datetime.now().minute in cron:
            self.file = "longtime.json"
            self.long = True
        for file in self.configFiles:
            if Path(file).exists():
                print("Loading",file)
                with open(file) as handle:
                    self.files[file] = json.loads(handle.read())
            else:
                self.files[file] = {}

    def isLongtime(self):
        return self.long

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
        parsed = re.findall('interface "([a-zA-Z0-9]{3,}?)".*?([0-9.]+).*?cost ([0-9]+)',configRaw, re.DOTALL)
        data = []
        for nic,target,weight in parsed:
            data.append({'nic':nic,'target':target,'weight':weight})
        return data

    def getAvrg(self,row,weight=False):
        result = 0
        for entry in row:
            result += float(entry[0])
        if weight: return int(float(result / len(row)))
        else: return int(float(result / len(row)) * 100)

    def hasJitter(self,row,avrg):
        grace = 20
        for entry in row:
            if float(entry[0]) > avrg + grace: return True
        return False

    def getLatency(self,config,pings=6):
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
        tempFile = self.files
        total,loss,jittar = 0,0,0
        for node in list(config):
            for entry,row in latency.items():
                if entry == node['target']:
                    node['latency'] = self.getAvrg(row)
                    if entry not in tempFile['longtime.json']: tempFile['longtime.json'][entry] = {"packetloss":0,"jitter":0}
                    if entry not in tempFile['peering.json']: tempFile['peering.json'][entry] = {"packetloss":0,"jitter":0}

                    if node['nic'] not in tempFile['events.json']: tempFile['events.json'][node['nic']] = {"events":{"jitter":[]}} 

                    hadLossLong = tempFile['longtime.json'][entry]['packetloss'] > current
                    hadLoss = tempFile['peering.json'][entry]['packetloss'] > current
                    hasLoss = len(row) < pings -1

                    if hasLoss or hadLoss or hadLossLong:
                        node['latency'] = node['latency'] + 5000 #+ 50ms / weight
                        loss = loss +1

                    if hasLoss:
                        tempFile[self.file][entry]['packetloss'] = current + 1800 #update event
                        print(entry,"Packetloss detected","got",len(row),f"of {pings -1}, adding penalty")
                    elif hadLoss or hadLossLong:
                        print(entry,"Ongoing Packetloss")

                    hadJitterLong = tempFile['longtime.json'][entry]['jitter'] > current
                    hasJitter = self.hasJitter(row,self.getAvrg(row,True))
                    hadJitter = tempFile['peering.json'][entry]['jitter'] > current

                    if hasJitter or hadJitter or hadJitterLong:
                        node['latency'] = node['latency'] + 1000 #+ 10ms /weight
                        jittar = jittar +1

                    if hasJitter:
                        extend = 3600 if self.isLongtime() else 900
                        tempFile[self.file][entry]['jitter'] = current + extend #update event
                        tempFile['events.json'][node['nic']]['events']['jitter'].append(current)
                        print(entry,"High Jitter dectected, adding penalty")
                    elif hadJitter or hadJitterLong:
                        print(entry,"Ongoing Jitter")
                    total = total +1

        print (f"Total {total}, Jitter {jittar}, Packetloss {loss}")
        return config

L = Latency()
#Check if bird is running
print("Checking bird/fping status")
bird = L.cmd("pgrep bird")
if bird[0] == "": raise Exception('bird2 not running, exiting.')
#Check if fping is running
for run in range(3):
    fping = L.cmd("pgrep fping")
    if fping[0] == "": break
    if run == 2: raise Exception('fping is running, exiting.')
    time.sleep(randint(5, 10))
#Getting config
print("Reading bird config")
configRaw = L.cmd("cat /etc/bird/bird.conf")[0].rstrip()
#Parsing
config = L.parse(configRaw)
#fping
print("Running fping")
if L.isLongtime():
    result = L.getLatency(config,60)
else:
    result = L.getLatency(config)
#update
configs = L.cmd('ip addr show')
local = re.findall("inet (10\.0[0-9.]+\.1)\/(32|30) scope global lo",configs[0], re.MULTILINE | re.DOTALL)
configRaw = re.sub(local[0][0]+"; #updated [0-9]+", local[0][0]+"; #updated "+str(int(time.time())), configRaw, 0, re.MULTILINE)
for entry in result:
    if "latency" not in entry: entry['latency'] = 65000
    configRaw = re.sub("cost "+str(entry['weight'])+"; #"+entry['target'], "cost "+str(entry['latency'])+"; #"+entry['target'], configRaw, 0, re.MULTILINE)
if not result:
    print("Nothing to do")
else:
    #push
    print("Waiting for deplayed update")
    time.sleep(randint(2,20))
    print("Writing config")
    L.cmd("echo '"+configRaw+"' > /etc/bird/bird.conf")
    #reload
    print("Reloading bird")
    L.cmd('/usr/sbin/service bird reload')
L.save()
