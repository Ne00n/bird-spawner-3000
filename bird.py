from Class.bird import Bird
import sys
param = sys.argv[1]
print("Bird Spawner 3000")
bird = Bird()
if param == "build":
    bird.run()
elif param == "shutdown":
    bird.shutdown()
else:
    print("build, shutdown")
