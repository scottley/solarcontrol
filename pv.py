import json
import code
import readline
import asyncio

import pyemvue
import hoymiles_wifi

from pyemvue.enums import Scale, Unit
from hoymiles_wifi.dtu import DTU

VUE = pyemvue.PyEmVue()


def print_recursive(usage_dict, info, depth=0):

    for gid, device in usage_dict.items():
        for channelnum, channel in device.channels.items():
            name = channel.name
            if name == 'Main':
                name = info[gid].device_name
            print('-'*depth, f'{gid} {channelnum} {name} {channel.usage} kwh')
            if channel.nested_devices:
                print_recursive(channel.nested_devices, info, depth+1)

def vue_login():
    with open('emporia_keys.json') as f:
        data = json.load(f)

    VUE.login(id_token=data['id_token'],
        access_token=data['access_token'],
        refresh_token=data['refresh_token'],
        token_storage_file='emporia_keys.json')


vue_login()

devices = VUE.get_devices()
device_gids = []
device_info = {}
for device in devices:
    if not device.device_gid in device_gids:
        device_gids.append(device.device_gid)
        device_info[device.device_gid] = device
    else:
        device_info[device.device_gid].channels += device.channels

device_usage_dict = VUE.get_device_list_usage(deviceGids=device_gids, instant=None, scale=Scale.MINUTE.value, unit=Unit.KWH.value)
print('device_gid channel_num name usage unit')
print_recursive(device_usage_dict, device_info)


dtu = DTU("192.168.1.5")

loop = asyncio.get_event_loop()

#dtu_response = loop.run_until_complete(dtu.async_get_energy_storage_data(430124460077,240424510022))
dtu_response = loop.run_until_complete(dtu.async_get_gateway_info())

dtu_serial_number = dtu_response.serial_number
dtu_inverter_serial_number = dtu_response.mdevinfo[0].serial_number

if dtu_response:
	print(f"DTU Response: {dtu_serial_number} {dtu_inverter_serial_number}")
else:
	print("No response from DTU")

loop.close()

variables = globals().copy()
variables.update(locals())

#shell = code.InteractiveConsole(variables)
#shell.interact()




