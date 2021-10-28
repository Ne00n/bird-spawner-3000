#!/usr/bin/python3
import subprocess, datetime, json, time, sys, re
from datetime import datetime
from random import randint
from pathlib import Path

class Latency:
    def __init__(self):
        self.files = {"peering.json":{},'longtime.json':{}}
        self.long,self.file = False,"peering.json"
        if len(sys.argv) == 2 and sys.argv[1] == "longtime" or datetime.now().minute == 0:
            self.file = "longtime.json"
            self.long = True
        files = ["peering.json","longtime.json"]
        for file in files:
            if Path(file).exists():
                print("Loading",file)
                with open(file) as handle:
                    self.files[file] = json.loads(handle.read())
            else:
                self.files[file] = {}

    def isLongtime(self):
        return self.long

    def save(self):
        print(f"Saving {self.file}")
        with open(self.file, 'w') as f:
            json.dump(self.files[self.file], f, indent=4)

    def cmd(self,cmd):
        p = subprocess.run(cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        return [p.stdout.decode('utf-8'),p.stderr.decode('utf-8')]

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
        grace = 10
        if avrg < 10: grace = 5
        for entry in row:
            if float(entry[0]) > avrg + grace: return True
        return False

    def getLatency(self,config,pings=5):
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
        for node in list(config):
            for entry,row in latency.items():
                if entry == node['target']:
                    node['latency'] = self.getAvrg(row)
                    if entry not in self.files[self.file]: self.files[self.file][entry] = {"packetloss":0,"jitter":0}

                    hadLoss = self.files[self.file][entry]['packetloss'] > int(datetime.now().timestamp())
                    hasLoss = len(row) < pings -1

                    if hadLoss or hasLoss:
                        if hasLoss:
                            self.files[self.file][entry]['packetloss'] = int(datetime.now().timestamp()) + 1800
                            print(entry,"Packetloss detected","got",len(row),f"of {pings -1}, adding penalty")
                        if hadLoss: print(entry,"Ongoing Packetloss")
                        node['latency'] = node['latency'] + 6000

                    hasJitter = self.hasJitter(row,self.getAvrg(row,True))
                    hadJitter = self.files[self.file][entry]['jitter'] > int(datetime.now().timestamp())
                    hadJitterLong = False
                    if self.files['longtime.json']:
                        hadJitterLong = self.files['longtime.json'][entry]['jitter'] > int(datetime.now().timestamp())

                    if hadJitter or hasJitter or hadJitterLong:
                        if hasJitter:
                            if self.isLongtime():
                                self.files[self.file][entry]['jitter'] = int(datetime.now().timestamp()) + 3600
                            else:
                                self.files[self.file][entry]['jitter'] = int(datetime.now().timestamp()) + 1800
                            print(entry,"High Jitter dectected, adding penalty")
                        if hadJitter: print(entry,"Ongoing Jitter")
                        node['latency'] = node['latency'] + 1000

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
    time.sleep(randint(10, 20))
#Getting config
print("Reading bird config")
configRaw = L.cmd("cat /etc/bird/bird.conf")[0].rstrip()
#Parsing
config = L.parse(configRaw)
print("Waiting for deplayed fping")
time.sleep(randint(2,30))
#fping
print("Running fping")
if L.isLongtime():
    result = L.getLatency(config,300)
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
    time.sleep(randint(5,40))
    print("Writing config")
    L.cmd("echo '"+configRaw+"' > /etc/bird/bird.conf")
    #reload
    print("Reloading bird")
    L.cmd('/usr/sbin/service bird reload')
L.save()
