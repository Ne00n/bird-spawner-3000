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
                    self.files[file] = {"created":int(datetime.now().timestamp())}
            else:
                self.files[file] = {"created":int(datetime.now().timestamp())}

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

    def getLatency(self,config,pings=4,isClient=False):
        fping = ["fping", "-c", str(pings)]
        clients = ["PI","CLIENT"]
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
                isClientLink = True  if any(cl in node['nic'] for cl in clients) else False
                if entry == node['target']:
                    node['latency'] = self.getAvrg(row)
                    if entry not in tempFile['network.json']: tempFile['network.json'][entry] = {"packetloss":[],"jitter":[]}

                    threshold,eventCount = 1,0
                    for event in list(tempFile['network.json'][entry]['packetloss']):
                        if event > int(datetime.now().timestamp()): 
                            eventCount += 1
                        else:
                            tempFile['network.json'][entry]['packetloss'].remove(event)
                    
                    expire = 900 if pings == 6 else 3600
                    hadLoss = True if eventCount >= threshold else False
                    hasLoss = len(row) < pings -1

                    if hadLoss or hasLoss:
                        node['latency'] = node['latency'] + 5000 #+ 50ms / weight
                        loss = loss +1

                    if hasLoss:
                        #limit the amount of entries to 15
                        if len(tempFile['network.json'][entry]['packetloss']) < 15:
                            tempFile['network.json'][entry]['packetloss'].append(int(datetime.now().timestamp()) + expire)
                        print(entry,"Packetloss detected","got",len(row),f"of {pings -1}")
                    elif hadLoss:
                        print(entry,"Ongoing Packetloss")

                    if pings > 6: row = row[:5]
                    threshold,eventCount = 10,0
                    for event in list(tempFile['network.json'][entry]['jitter']):
                        if event > int(datetime.now().timestamp()): 
                            eventCount += 1
                        else:
                            tempFile['network.json'][entry]['jitter'].remove(event)
                    hadJitter = True if eventCount > threshold else False
                    hasJitter = self.hasJitter(row,self.getAvrg(row,True))
                    
                    if isClient == False and isClientLink == False:
                        if hadJitter:
                            node['latency'] = node['latency'] + 1000 #+ 10ms /weight
                            jittar = jittar +1

                        if hasJitter:
                            tempFile['network.json'][entry]['jitter'].append(int(datetime.now().timestamp()) + 900)
                            print(entry,"High Jitter dectected")
                        elif hadJitter:
                            print(entry,"Ongoing Jitter")
                        total = total +1

        print (f"Total {total}, Jitter {jittar}, Packetloss {loss}")
        return config

L = Latency()
#Check if bird is running
print("Checking bird/fping status")
bird = L.cmd("pgrep bird")
if bird[0] == "": raise Exception('bird2 not running, exiting.')
#delay the measurement a bit
now = datetime.now()
time.sleep(int(str(now.minute)[1]))
#Check if fping is running
for run in range(3):
    fping = L.cmd("pgrep fping")
    if fping[0] == "": break
    if run == 2: raise Exception('fping is running, exiting.')
    print("Waiting for fping")
    time.sleep(randint(5, 10))
#longrun
cron = [5,15,25,35,45,55]
if datetime.now().minute in cron:
    runs,pings = 1,30
else:
    runs,pings = 3,6
for run in range(runs):
    #Getting config
    print("Reading bird config")
    configRaw = L.cmd("cat /etc/bird/bird.conf")[0].rstrip()
    #Parsing
    config = L.parse(configRaw)
    configs = L.cmd('ip addr show')
    isClient = "10.0.250" in configs[0]
    #fping
    print("Running fping")
    result = L.getLatency(config,pings,isClient)
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
    if pings == 6: time.sleep(15)