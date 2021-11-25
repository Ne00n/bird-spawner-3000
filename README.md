# bird-spawner-3000

Invasion of the Birds Expansion for pipe-builder-3000: https://github.com/Ne00n/pipe-builder-3000/ </br>
Configures bird2 with OSPF on all nodes, for the lowest latency between the servers.

![data mining](https://i.pinimg.com/originals/48/9d/34/489d348abbc913f65f3637ab1f00ec73.gif)

**Dependencies**<br />
```
pip3 install netaddr
apt-get install bird2 python3 fping -y
```

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
