#!/usr/bin/python3
import subprocess, json, time, re
from random import randint

class Latency:
    def cmd(self,cmd):
        p = subprocess.run(cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        return [p.stdout.decode('utf-8'),p.stderr.decode('utf-8')]

    def parse(self,configRaw):
        parsed = re.findall('interface "([a-zA-Z0-9]{3,}?)".*?([0-9.]+).*?cost ([0-9]+)',configRaw, re.DOTALL)
        data = []
        for nic,target,weight in parsed:
            data.append({'nic':nic,'target':target,'weight':weight})
        return data

    def getAvrg(self,row):
        result = 0
        for entry in row:
            result += float(entry[0])
        return int(float(result / len(row)) * 100)

    def getLatency(self,config):
        fping = ["fping", "-c", "16"]
        for row in config:
            fping.append(row['target'])
        result = subprocess.run(fping, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        parsed = re.findall("([0-9.]+).*?([0-9]+.[0-9]).*?([0-9])% loss",result.stdout.decode('utf-8'), re.MULTILINE)
        latency =  {}
        for ip,ms,loss in parsed:
            if ip not in latency:
                latency[ip] = []
            latency[ip].append([ms,loss])
        for entry,row in latency.items():
            del row[0] #drop the first ping result
            row.sort()
            del row[len(row) -1] #drop the highest ping result
        for node in list(config):
            for entry,row in latency.items():
                if entry == node['target']:
                    node['latency'] = self.getAvrg(row)
                    if len(row) < 13:
                        print(entry,"Packetloss detected","got",len(row),"of 13")
                        node['latency'] = node['latency'] + 1000
                        print(entry,"Added 10ms penalty")

        return config

L = Latency()
#Check if bird is running
print("Checking bird/fping status")
bird = L.cmd("pgrep bird")
if bird[0] == "": raise ValueError('bird2 not running, exiting.')
#Check if fping is running
fping = L.cmd("pgrep fping")
if fping[0] != "": raise ValueError('fping is running, exiting.')
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
