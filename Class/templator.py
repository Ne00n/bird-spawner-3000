class Templator:

    def getFirst(self,latency):
        for entry in latency:
            return entry

    def genBird(self,latency):
        firstNode = self.getFirst(latency)
        template = '''log syslog all;
router id '''+latency[firstNode]["origin"]+''';

protocol device {
    scan time 10;
}

protocol direct {
    ipv4;
    interface "lo", "pipe*";
}

protocol kernel {
	ipv4 {
	      export filter {
		krt_prefsrc = '''+latency[firstNode]["origin"]+''';
		accept;
		};
	};
}

protocol kernel {
	ipv6 { export all; };
}

protocol ospf {
ipv4 {
		import all;
                export where source ~ [ RTS_DEVICE, RTS_STATIC ];
        };
	area 0 { '''
        for target,data in latency.items():
            template += '''
                interface "'''+target+'''" {
                        type ptmp;
                        neighbors {
                        '''+data['target']+''';
                        };
                        cost '''+str(data['latency'])+''';
                };
            '''
        template += """
        };
}"""
        return template
