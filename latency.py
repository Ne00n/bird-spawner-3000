#!/usr/bin/python3
import subprocess, json, time, re

class Latency:
    def cmd(self,cmd):
        p = subprocess.run(cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        return [p.stdout.decode('utf-8'),p.stderr.decode('utf-8')]

    def parse(self,configRaw):
        parsed = re.findall('interface "(pipe.*?)".*?([0-9.]+).*?cost ([0-9]+)',configRaw, re.DOTALL)
        data = []
        for nic,target,weight in parsed:
            data.append({'nic':nic,'target':target,'weight':weight})
        return data

    def getAvrg(self,row):
        n,result = 12,0
        for index,entry in enumerate(row):
            if index <= n:
                result += float(entry[0])
        return int(float(result / 13) * 100)

    def getLatency(self,config):
        fping = ["fping", "-c", "15"]
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
            row.sort()
        for node in list(config):
            for entry,row in latency.items():
                if entry == node['target']:
                    node['latency'] = self.getAvrg(row)
                elif node['target'] not in latency and nic in config:
                    print("Warning: cannot reach",node['target'],"skipping")
                    del config[node['nic']]
        if (len(config) != len(latency)):
            print("Warning: Targets do not match expected responses.")
        return config

L = Latency()
#Check if bird is running
running = L.cmd("pgrep bird")
if running[0] == "": raise ValueError('Bird is ded, very sad.')
#Getting config
configRaw = L.cmd("cat /etc/bird/bird.conf")[0].rstrip()
#Parsing
config = L.parse(configRaw)
#fping
result = L.getLatency(config)
#filter anything with less or equal than 100 = 1ms change
count = 0
while count < len(result):
    entry = result[count]
    if abs(int(entry['weight']) - int(entry['latency'])) <= 100:
        print("Dropping",entry['nic'])
        del result[count]
    else:
        count = count +1
#update
configs = L.cmd('ip addr show')
local = re.findall("inet (10\.0[0-9.]+\.1)\/(32|30) scope global lo",configs[0], re.MULTILINE | re.DOTALL)
configRaw = re.sub(local[0][0]+"; #updated [0-9]+", local[0][0]+"; #updated "+str(int(time.time())), configRaw, 0, re.MULTILINE)
for entry in result:
    configRaw = re.sub("cost "+str(entry['weight'])+"; #"+entry['target'], "cost "+str(entry['latency'])+"; #"+entry['target'], configRaw, 0, re.MULTILINE)
    print("Updating",entry['nic'])
if not result:
    print("Nothing to do")
else:
    #push
    print("Writing config")
    L.cmd("echo '"+configRaw+"' > /etc/bird/bird.conf")
    #reload
    print("Reloading bird")
    L.cmd('service bird reload')
