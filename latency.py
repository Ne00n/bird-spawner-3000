#!/usr/bin/python3
import subprocess, json, time, re
from datetime import datetime
from random import randint
from pathlib import Path

class Latency:
    def __init__(self):
        if Path("peering.json").exists():
            print("Loading","peering.json")
            with open("peering.json") as handle:
                self.peering = json.loads(handle.read())
        else:
            self.peering = {}

    def save(self):
        with open("peering.json", 'w') as f:
            json.dump(self.peering, f, indent=4)

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
        if avrg > 300: grace = 25
        elif avrg > 200: grace = 20
        elif avrg > 100: grace = 15
        else: grace = 10
        for entry in row:
            if float(entry[0]) > avrg + grace: return True
        return False

    def getLatency(self,config):
        fping = ["fping", "-c", "16"]
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
            del row[len(row) -1] #drop the highest ping result
        for node in list(config):
            for entry,row in latency.items():
                if entry == node['target']:
                    node['latency'] = self.getAvrg(row)
                    if entry not in self.peering: self.peering[entry] = {"packetloss":0,"jitter":0}

                    hadLoss = self.peering[entry]['packetloss'] > int(datetime.now().timestamp())
                    hasLoss = len(row) < 13

                    if hadLoss or hasLoss:
                        if hasLoss:
                            self.peering[entry]['packetloss'] = int(datetime.now().timestamp()) + 1800
                            print(entry,"Packetloss detected","got",len(row),"of 13, adding penalty")
                        if hadLoss: print(entry,"Ongoing Packetloss")
                        node['latency'] = node['latency'] + 6000

                    hasJitter = self.hasJitter(row,self.getAvrg(row,True))
                    hadJitter = self.peering[entry]['jitter'] > int(datetime.now().timestamp())

                    if hadJitter or hasJitter:
                        if hasJitter:
                            self.peering[entry]['jitter'] = int(datetime.now().timestamp()) + 1800
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
#fping
print("Running fping")
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
    time.sleep(randint(10,60))
    print("Writing config")
    L.cmd("echo '"+configRaw+"' > /etc/bird/bird.conf")
    #reload
    print("Reloading bird")
    L.cmd('service bird reload')
print("Saving","peering.json")
L.save()
