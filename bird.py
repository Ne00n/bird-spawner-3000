from Class.bird import Bird
import sys
print("Bird Spawner 3000")
config = "hosts.json"
if len(sys.argv) > 2:
    config = sys.argv[2]
bird = Bird(config)
if len(sys.argv) == 1:
    print("build, shutdown")
elif sys.argv[1] == "build":
    bird.run(config)
elif sys.argv[1] == "shutdown":
    bird.shutdown()
