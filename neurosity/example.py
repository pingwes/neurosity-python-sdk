from neurosity import neurosity_sdk
from dotenv import load_dotenv
import os
import time

load_dotenv()

neurosity = neurosity_sdk({
    "device_id": os.getenv("NEUROSITY_DEVICE_ID")
})

neurosity.login({
    "email": os.getenv("NEUROSITY_EMAIL"),
    "password": os.getenv("NEUROSITY_PASSWORD")
})

info = neurosity.get_info()
print(info)


def callback(data):

    print(data)


neurosity.get_timesync()


unsubscribe = neurosity.focus(callback)
neurosity.add_marker(
    label="test"
)

time.sleep(10)
unsubscribe()
