import subprocess, netaddr, time, json, re
from Class.templator import Templator

targets = []

class Bird:
    def __init__(self):
        global targets
        print("Loading config")
        with open('hosts.json') as handle:
            targets = json.loads(handle.read())

    def cmd(self,server,command,interactive=False,list=False):
        if list == True:
            cmd = command
        else:
            cmd = ['ssh','root@'+server,command]
        if interactive == True:
            return subprocess.check_output(cmd).decode("utf-8")
        else:
            subprocess.run(cmd)

    def resolve(self,ip,range,netmask):
        rangeDecimal = int(netaddr.IPAddress(range))
        ipDecimal = int(netaddr.IPAddress(ip))
        wildcardDecimal = pow( 2, ( 32 - int(netmask) ) ) - 1
        netmaskDecimal = ~ wildcardDecimal
        return ( ( ipDecimal & netmaskDecimal ) == ( rangeDecimal & netmaskDecimal ) );

    def genTargets(self,links):
        result = {}
        for link in links:
            nic,ip,lastByte = link[0],link[1],link[2]
            origin = ip+lastByte
            #Client or Server roll the dice or rather not, so we ping the correct ip
            target = self.resolve(ip+str(int(lastByte)+1),origin,31)
            if target == True:
                targetIP = ip+str(int(lastByte)+1)
            else:
                targetIP = ip+str(int(lastByte)-1)
            result[nic] = {}
            result[nic]["target"] = targetIP
            result[nic]["origin"] = origin
        return result

    def getLatency(self,server,targets):
        print(server,"Getting latency from all targets")
        fping = ['ssh','root@'+server,"fping", "-c", "15"]
        for nic,data in targets.items():
            fping.append(data['target'])
        result = subprocess.run(fping, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        installed = re.findall("bash: fping:",result.stderr.decode('utf-8'), re.DOTALL)
        if installed:
            print("fping not found, installing")
            self.cmd(server,"apt-get update && apt-get install fping -y")
            print("fping installed")
            print(server,"Getting latency from all targets")
            result = subprocess.run(fping, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        parsed = re.findall("([0-9.]+).*?([0-9]+.[0-9]).*?([0-9])% loss",result.stdout.decode('utf-8'), re.MULTILINE)
        latency =  {}
        for ip,ms,loss in parsed:
            if ip not in latency:
                latency[ip] = []
            latency[ip].append([ms,loss])
        for entry,row in latency.items():
            row.sort()
        for nic,data in list(targets.items()):
            for entry,row in latency.items():
                if entry == data['target']:
                    data['latency'] = int(((float(row[0][0]) + float(row[1][0]) + float(row[2][0]) + float(row[3][0]) + float(row[4][0])) / 5) * 100)
                elif data['target'] not in latency and nic in targets:
                    print("Warning: cannot reach",data['target'],"skipping")
                    del targets[nic]
        if (len(targets) != len(latency)):
            print("Warning: Targets do not match expected responses.")
        return targets

    def shutdown(self):
        global targets
        for server in targets:
            print("---",server,"---")
            print("Stopping bird")
            self.cmd(server,'service bird stop')

    def run(self):
        global targets
        T = Templator()
        print("Launching")
        for server in targets:
            print("---",server,"---")
            configs = self.cmd(server,'ip addr show',True)
            links = re.findall("(pipe[A-Za-z0-9]+): <POINTOPOINT,NOARP.*?inet (10[0-9.]+\.)([0-9]+)",configs, re.MULTILINE | re.DOTALL)
            local = re.findall("inet (10\.0[0-9.]+\.1)\/32 scope global lo",configs, re.MULTILINE | re.DOTALL)
            nodes = self.genTargets(links)
            latency = self.getLatency(server,nodes)
            print(server,"Generating config")
            bird = T.genBird(latency,local)
            print(server,"Writing config")
            self.cmd(server,"echo '"+bird+"' > /etc/bird/bird.conf",False)
            self.cmd(server,"touch /etc/bird/bgp.conf && touch /etc/bird/bgp_ospf.conf",False)
            try:
                self.cmd(server,"pgrep bird",True)
                print(server,"Reloading bird")
                self.cmd(server,'service bird reload')
                time.sleep(10)
            except:
                print(server,"Starting bird")
                self.cmd(server,'service bird start')
                time.sleep(15)
            print(server,"done")
