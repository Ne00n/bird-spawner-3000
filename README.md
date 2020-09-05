# bird-spawner-3000

Invasion of the Birds Expansion for pipe-builder-3000: https://github.com/Ne00n/pipe-builder-3000/ </br>
Configures bird2 with OSPF on all nodes, based on measured latency.

**Dependencies**<br />
pip3 install netaddr<br />
apt-get install bird2

Getting bird2: https://packages.sury.org/bird/README.txt

**Prepare**<br />
Rename hosts.example.json to hosts.json and fill it up

**Usage**<br />
python3 bird.py
