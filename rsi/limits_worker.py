"""Trusted launcher, called with -I. Applies limits before exec; no user code."""
import os
import resource
import sys

memory, cpu = int(sys.argv[1]), int(sys.argv[2])
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_FSIZE,(131072,131072))
resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu+1))
if memory:
    resource.setrlimit(resource.RLIMIT_AS,(memory*1024*1024, memory*1024*1024))
os.execv(sys.argv[3], sys.argv[3:])
