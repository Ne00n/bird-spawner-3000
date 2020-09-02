class Templator:
    def genBird(self,latency):
        template = '''log syslog all;
router id '''+latency["ip"]+''';

protocol device {
    scan time 10;
}

protocol direct {
    interface "lo";
    interface "pipe*";
}

protocol direct {
    ipv4;
    interface "lo", "pipe*";
}

protocol kernel {
	ipv4 {
	      export filter {
		krt_prefsrc = '''+latency["ip"]+''';
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
        for target,data in latency["data"].items():
            template += '''
                interface "pipe'''+target+'''" {
                        type ptmp;
                        neighbors {
                        '''+data['ip']+''';
                        };
                        cost '''+data['ms']+''';
                };
            '''
        template += """
        };
}"""
        return template
