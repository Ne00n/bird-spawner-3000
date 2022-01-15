import subprocess, netaddr, random, time, json, re
from Class.templator import Templator
from threading import Thread

class Bird:
    def __init__(self,config="hosts.json"):
        print("Loading",config)
        with open(config) as handle:
            self.targets = json.loads(handle.read())
        self.templator = Templator()

    def cmd(self,cmd,server,ssh=True):
        cmd = 'ssh root@'+server+' "'+cmd+'"' if ssh else cmd
        for run in range(4):
            try:
                p = subprocess.run(cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True ,timeout=60)
                if p.returncode != 0:
                    print("Warning got returncode",p.returncode,"on",server)
                    print("Error:",p.stderr.decode('utf-8'))
                if p.returncode != 255: return [p.stdout.decode('utf-8'),p.stderr.decode('utf-8')]
            except Exception as e:
                print("Error:",e)
            print("Retrying",cmd,"on",server)
            time.sleep(random.randint(5, 15))

    def resolve(self,ip,range,netmask):
        rangeDecimal = int(netaddr.IPAddress(range))
        ipDecimal = int(netaddr.IPAddress(ip))
        wildcardDecimal = pow( 2, ( 32 - int(netmask) ) ) - 1
        netmaskDecimal = ~ wildcardDecimal
        return ( ( ipDecimal & netmaskDecimal ) == ( rangeDecimal & netmaskDecimal ) );

    def getAvrg(self,row):
        result = 0
        for entry in row:
            result += float(entry[0])
        return int(float(result / len(row)) * 100)

    def genTargets(self,links):
        result = {}
        for link in links:
            nic,ip,lastByte = link[0],link[2],link[3]
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
        fping = ['ssh','root@'+server,"fping", "-c", "30"]
        for nic,data in targets.items():
            fping.append(data['target'])
        result = subprocess.run(fping, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        installed = re.findall("bash: fping:",result.stderr.decode('utf-8'), re.DOTALL)
        if installed:
            print("fping not found, installing")
            self.cmd('apt-get update && apt-get install fping -y',server)
            print("fping installed")
            print(server,"Getting latency from all targets")
            result = subprocess.run(fping, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        parsed = re.findall("([0-9.]+).*?([0-9]+.[0-9]).*?([0-9])% loss",result.stdout.decode('utf-8'), re.MULTILINE)
        latency =  {}
        print(server,"Processing responses")
        for ip,ms,loss in parsed:
            if ip not in latency:
                latency[ip] = []
            latency[ip].append([ms,loss])
        for entry,row in latency.items():
            row = row[20:] #drop the first 20 pings
            row.sort()
        for nic,data in list(targets.items()):
            for entry,row in latency.items():
                if entry == data['target']:
                    if len(row) < 10: print(server,"Warning, expected 10 pings, got",len(row),"from",data['target'],"possible Packetloss")
                    data['latency'] = self.getAvrg(row)
                elif data['target'] not in latency and nic in targets:
                    print(server,"Warning: cannot reach",data['target'],"skipping")
                    del targets[nic]
        if (len(targets) != len(latency)):
            print(server,"Warning: Targets do not match expected responses. This can be ignored on the last machine.")
        return targets

    def update(self,):
        print("Launching")
        for server in self.targets['servers']:
            print(server,"Updating latency.py")
            self.cmd('scp latency.py root@'+server+':/root/','',False)
            self.cmd('chmod +x /root/latency.py',server)

    def restart(self):
        self.shutdown()
        self.startup()

    def startup(self):
        for server in self.targets['servers']:
            print("---",server,"---")
            print("Starting bird")
            self.cmd('service bird start',server)

    def shutdown(self):
        for server in self.targets['servers']:
            print("---",server,"---")
            print("Stopping bird")
            self.cmd('service bird stop',server)

    def work(self,server,latency):
        configs = self.cmd('ip addr show',server)
        links = re.findall("(("+self.targets['prefixes']+")[A-Za-z0-9]+): <POINTOPOINT.*?inet (10[0-9.]+\.)([0-9]+)",configs[0], re.MULTILINE | re.DOTALL)
        local = re.findall("inet (10\.0\.(?!252)[0-9.]+\.1)\/(32|30) scope global lo",configs[0], re.MULTILINE | re.DOTALL)
        nodes = self.genTargets(links)
        latencyData = self.getLatency(server,nodes)
        print(server,"Generating config")
        bird = self.templator.genBird(latencyData,local,int(time.time()))
        print(server,"Writing config")
        subprocess.check_output(['ssh','root@'+server,"echo '"+bird+"' > /etc/bird/bird.conf"])
        self.cmd("touch /etc/bird/bgp.conf && touch /etc/bird/bgp_ospf.conf",server)
        proc = self.cmd("pgrep bird",server)
        if proc[0] == "":
            print(server,"Starting bird")
            self.cmd("service bird start",server)
        else:
            print(server,"Reloading bird")
            self.cmd("service bird reload",server)
        if latency == "yes":
            print(server,"Updating latency.py")
            self.cmd('scp latency.py root@'+server+':/root/','',False)
            self.cmd('chmod +x /root/latency.py',server)
            print(server,"Checking cronjob")
            cron = self.cmd("crontab -u root -l",server)
            if cron[0] == '':
                print(server,"Creating cronjob")
                self.cmd('echo \\"*/1 * * * *  /root/latency.py > /dev/null 2>&1\\" | crontab -u root -',server)
            else:
                if "/root/latency.py" in cron[0]:
                    print(server,"Cronjob already exists")
                else:
                    print(server,"Adding cronjob")
                    self.cmd('crontab -u root -l 2>/dev/null | { cat; echo \\"*/1 * * * *  /root/latency.py > /dev/null 2>&1\\"; } | crontab -u root -',server)
        else:
            self.cmd("crontab -u root -l | grep -v '/root/latency.py'  | crontab -u root -",server)
        print(server,"done")

    def run(self,latency="no"):
        threads = []
        print("Launching")
        print("latency.py",latency)
        answer = input("Use Threading? (y/n): ")
        for server in self.targets['servers']:
            if answer != "y":
                self.work(server,latency)
            else:
                threads.append(Thread(target=self.work, args=([server,latency])))
        if answer == "y":
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
