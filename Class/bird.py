import subprocess, json, re
from Class.templator import Templator

targets = []

class Bird:
    def __init__(self):
        global targets
        print("Loading config")
        with open('hosts.json') as handle:
            targets = json.loads(handle.read())

    def cmd(self,server,command,interactive):
        cmd = ['ssh','root@'+server,command]
        if interactive == True:
            return subprocess.check_output(cmd).decode("utf-8")
        else:
            subprocess.run(cmd)

    def prepare(self):
        print("Preparing")
        for server in targets:
            self.cmd(server,'service bird stop',False)

    def ping(self,server,ip):
        result = self.cmd(server,"ping -c 5 "+ip,True)
        latency = re.findall("mdev =.([0-9]+)",result)
        return latency[0]

    def getLatency(self,server,links):
        result = {}
        result["data"] = {}
        for link in links:
            print("Getting Latency from",server,"to",link[0])
            if link[3] == "31":
                ip = link[1]+str(int(link[2])+1)
            else:
                ip = link[1]+str(int(link[2])-1)
            latency = self.ping(server,ip)
            result["ip"] = link[1]+link[2]
            result["data"][link[0]] = latency
        return result

    def run(self):
        global targets
        self.prepare()
        T = Templator()
        print("Launching")
        for server in targets:
            configs = self.cmd(server,'ip addr show',True)
            links = re.findall("([A-Z0-9]+): <POINTOPOINT,NOARP.*?inet (10[0-9.]+\.)([0-9]+)/([0-9]+)",configs, re.MULTILINE | re.DOTALL)
            latency = self.getLatency(server,links)
            bird = T.genBird(latency)
            self.cmd(server,"echo '"+bird+"' > /etc/bird/bird.conf",False)
            self.cmd(server,'service bird start',False)
            print(server,"done")
