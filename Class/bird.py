import subprocess, netaddr, json, re
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
            print("Stopping bird on",server)
            self.cmd(server,'service bird stop',False)

    def ping(self,server,ip):
        result = self.cmd(server,"ping -c 5 "+ip,True)
        latency = re.findall("mdev =.([0-9]+)",result)
        return latency[0]

    def resolve(self,ip,range,netmask):
        rangeDecimal = int(netaddr.IPAddress(range))
        ipDecimal = int(netaddr.IPAddress(ip))
        wildcardDecimal = pow( 2, ( 32 - int(netmask) ) ) - 1
        netmaskDecimal = ~ wildcardDecimal
        return ( ( ipDecimal & netmaskDecimal ) == ( rangeDecimal & netmaskDecimal ) );

    def getLatency(self,server,links):
        result = {}
        result["data"] = {}
        for link in links:
            origin = link[1]+link[2]
            #Client or Server roll the dice or rather not, so we ping the correct ip
            target = self.resolve(link[1]+str(int(link[2])+1),origin,31)
            if target == True:
                ip = link[1]+str(int(link[2])+1)
            else:
                ip = link[1]+str(int(link[2])-1)
            print("Getting Latency from",server+" ("+origin+")","to",link[0]+" ("+ip+")")
            latency = self.ping(server,ip)
            result["ip"] = link[1]+link[2]
            result["data"][link[0]] = {}
            result["data"][link[0]]['ms'] = latency
            result["data"][link[0]]['ip'] = ip
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
