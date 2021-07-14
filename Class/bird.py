import subprocess, netaddr, time, json, re
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
        p = subprocess.run(cmd, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        return [p.stdout.decode('utf-8'),p.stderr.decode('utf-8')]

    def resolve(self,ip,range,netmask):
        rangeDecimal = int(netaddr.IPAddress(range))
        ipDecimal = int(netaddr.IPAddress(ip))
        wildcardDecimal = pow( 2, ( 32 - int(netmask) ) ) - 1
        netmaskDecimal = ~ wildcardDecimal
        return ( ( ipDecimal & netmaskDecimal ) == ( rangeDecimal & netmaskDecimal ) );

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
        fping = ['ssh','root@'+server,"fping", "-c", "15"]
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
                    print(server,"Warning: cannot reach",data['target'],"skipping")
                    print(server,"Restarting wireguard connection",data['target'])
                    route = self.cmd("ip route get "+data['target'],server)
                    interface = re.findall(".*?dev ([a-zA-Z0-9]+)",route[0], re.MULTILINE)
                    self.cmd("systemctl stop wg-quick@"+interface[0],server)
                    time.sleep(3)
                    self.cmd("systemctl start wg-quick@"+interface[0],server)
                    del targets[nic]
        if (len(targets) != len(latency)):
            print(server,"Warning: Targets do not match expected responses.")
        return targets

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
                self.cmd('echo \\"*/5 * * * *  /root/latency.py > /dev/null 2>&1\\" | crontab -u root -',server)
            else:
                if "/root/latency.py" in cron[0]:
                    print(server,"Cronjob already exists")
                else:
                    print(server,"Adding cronjob")
                    self.cmd('crontab -u root -l 2>/dev/null | { cat; echo \\"*/5 * * * *  /root/latency.py > /dev/null 2>&1\\"; } | crontab -u root -',server)
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
