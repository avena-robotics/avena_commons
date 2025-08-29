import time

from avena_commons.util.catchtime import Catchtime

print("Przed Catchtime")
with Catchtime() as t:
    print("W Catchtime")
    time.sleep(0.1)
    print("Po sleep")
print("Po Catchtime")

print(f"t.t = {t.t}")
print(f"str(t) = {t}")
print(f"t.t w sekundach = {t.t:.6f}")
print(f"t.t w milisekundach = {t.t * 1000:.6f}")
