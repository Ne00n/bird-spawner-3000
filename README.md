# bird-spawner-3000

Invasion of the Birds Expansion for pipe-builder-3000: https://github.com/Ne00n/pipe-builder-3000/ </br>
Configures bird2 with OSPF on all nodes, for the lowest latency between the servers.

**Dependencies**<br />
pip3 install netaddr<br />
apt-get install bird2 & fping

Getting bird2: https://packages.sury.org/bird/README.txt

**Prepare**<br />
Rename hosts.example.json to hosts.json and fill it up

**Examples**<br />

/etc/hosts<br />
```
bla.bla.bla.bla    Server1
bla.bla.bla.bla    Server2
bla.bla.bla.bla    Server3
```

**Usage**<br />
Configures/Updates bird2
```
python3 bird.py build
```
Shutdown of all bird instances
```
python3 bird.py shutdown
```
