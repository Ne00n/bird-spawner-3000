from Class.bird import Bird
import sys
print("Bird Spawner 3000")
config,latency = "hosts.json","no"
if len(sys.argv) > 2:
    config = sys.argv[2]
if len(sys.argv) > 3:
    latency = sys.argv[3]
bird = Bird(config)
if len(sys.argv) == 1:
    print("build, update, shutdown")
elif sys.argv[1] == "build":
    bird.run(latency)
elif sys.argv[1] == "update":
    bird.update()
elif sys.argv[1] == "shutdown":
    bird.shutdown()
