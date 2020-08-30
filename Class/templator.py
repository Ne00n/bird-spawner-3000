class Templator:
    def genBird(self,latency):
        template = '''
log syslog all;
router id '''+latency["ip"]+''';
protocol device {
}

protocol direct {
	ipv4;
	interface "lo";
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
        for target,latency in latency["data"].items():
            template += '''
                interface "'''+target+'''" {
                        type ptp;
                        cost '''+latency+''';
                };
            '''
        template += """
        };
}"""
        return template
