import json
import code
import readline
import asyncio

import python_weather

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

def query_vue(vue_instance):
    devices = vue_instance.get_devices()
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

async def query_inverter():
    dtu = DTU("192.168.1.5")

    dtu_response = await dtu.async_get_gateway_info()
    dtu_sn = dtu_response.serial_number
    dtu_inverter_sn = dtu_response.mdevinfo[0].serial_number

    dtu_response = await dtu.async_get_energy_storage_data(dtu_sn, dtu_inverter_sn)

    if dtu_response:
        print(f"Battery SoC: {dtu_response.battery_management.state_of_charge}")
        print(f"Flow: {dtu_response.power_flow}")
    else:
        print("No response from DTU")
    

async def query_weather():
    # Declare the client. The measuring unit used defaults to the metric system (celcius, km/h, etc.)
    async with python_weather.Client(unit=python_weather.IMPERIAL) as client:

        # Fetch a weather forecast from a city.
        weather = await client.get('Jamestown, Missouri, United States')

        # Fetch the temperature for today.
        print(f"Current Temperature: {weather.temperature}\nCurrent Conditions: {weather.kind}")

        # Fetch weather forecast for upcoming days.
        for daily in weather:
            print(daily)



async def main() -> None:

    #vue_login()
    #query_vue(VUE)

    #await query_inverter()
    await query_weather()





asyncio.run(main())




