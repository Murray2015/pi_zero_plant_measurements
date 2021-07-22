from typing import Tuple
import boto3
from os import remove, listdir, getcwd
from datetime import datetime
from time import sleep
from datetime import datetime
from picamera import PiCamera
import ctypes

from LPS22HB import LPS22HB
from TCS34725_py3 import TCS34725
from registers import *



class SHTC3:
    def __init__(self):
        self.dll = ctypes.CDLL("/home/pi/projects/SHTC3.so")
        init = self.dll.init
        init.restype = ctypes.c_int
        init.argtypes = [ctypes.c_void_p]
        init(None)

    def SHTC3_Read_Humidity(self):
        humidity = self.dll.SHTC3_Read_RH
        humidity.restype = ctypes.c_float
        humidity.argtypes = [ctypes.c_void_p]
        return humidity(None)


class Photo_Client:
    def __init__(self) -> None:
        self._photo_name = '/home/pi/projects/' + str(datetime.now().timestamp()) + '_plant.jpg'
        self.camera = PiCamera()

    @property
    def photo_name(self):
        return self._photo_name

    def take_photo(self) -> None:
        self.camera.start_preview()
        sleep(1)
        self.camera.capture(self._photo_name)
        self.camera.stop_preview()

    def delete_recent_photo(self) -> None:
        remove(self._photo_name)

    def delete_all_photos(self) -> None:
        for file in listdir(getcwd()):
            if file.endswith('.jpg'):
                remove(file)


class Sensor_Client:
    def __init__(self) -> None:
        self.pressure_data = 0.0
        self.temperature_data = 0.0
        self.lux = 0.0
        self.u8Buf=[0,0,0]
        self.lps22hb=LPS22HB()
        self.lux_client = TCS34725()
        self.lux_client.TCS34725_init()
        self.humidity_client = SHTC3()

    def get_pressure(self) -> float:
        sleep(0.1)
        self.lps22hb.LPS22HB_START_ONESHOT()
        if (self.lps22hb._read_byte(LPS_STATUS)&0x01)==0x01:  # a new pressure data is generated
            self.u8Buf[0]=self.lps22hb._read_byte(LPS_PRESS_OUT_XL)
            self.u8Buf[1]=self.lps22hb._read_byte(LPS_PRESS_OUT_L)
            self.u8Buf[2]=self.lps22hb._read_byte(LPS_PRESS_OUT_H)
            self.pressure_data=((self.u8Buf[2]<<16)+(self.u8Buf[1]<<8)+self.u8Buf[0])/4096.0
        return self.pressure_data

    def get_temperature(self) -> float:
        sleep(0.1)
        self.lps22hb.LPS22HB_START_ONESHOT()
        if (self.lps22hb._read_byte(LPS_STATUS)&0x02)==0x02:   # a new pressure data is generated
            self.u8Buf[0]=self.lps22hb._read_byte(LPS_TEMP_OUT_L)
            self.u8Buf[1]=self.lps22hb._read_byte(LPS_TEMP_OUT_H)
            self.temperature_data=((self.u8Buf[1]<<8)+self.u8Buf[0])/100.0
        return self.temperature_data

    def get_lux(self) -> float:
        self.lux_client.Get_RGBData()
        self.lux = self.lux_client.Get_Lux()
        return self.lux

    def get_humidity(self) -> float:
        return self.humidity_client.SHTC3_Read_Humidity()


class AWS_Client:
    def __init__(self) -> None:
        self.s3 = boto3.client('s3')
        self.dynamodb = boto3.client('dynamodb', region_name='us-east-2')

    def upload_photo(self, photo_name, destination_photo_name, bucket =
                     'pi-zero-plant-photos', extra_args=None):
        response = self.s3.upload_file(photo_name, bucket,
                                       destination_photo_name,
                                       ExtraArgs=extra_args)
        print(response)
        return response

    def upload_sensor_data(self, lux, pressure_data, temperature_data,
                           humidity_data) -> None:
        response = self.dynamodb.put_item(TableName='pi_zero_plant_sensor_measurements',
                                    Item={'timestamp': {'S':str(datetime.now().timestamp())},
                                    'lux':{'N':str(lux)},
                                    'pressure': {'N': str(pressure_data)},
                                    'temperature': {'N':str(temperature_data)},
                                    'humidity': {'N': str(humidity_data)}}
                                    )
        print(response)
        return response

if __name__ == "__main__":
    sensor = Sensor_Client()
    # Get sensor data
    lux = sensor.get_lux()
    pressure = sensor.get_pressure()
    temperature = sensor.get_temperature()
    humidity = sensor.get_humidity()
    print(f"Pressure: {pressure}, temperature: {temperature}, humidity: {humidity}, lux: {lux}")
    # Upload to AWS 
    aws = AWS_Client()
    aws.upload_sensor_data(lux, pressure, temperature, humidity)
    # Only take a photo and upload it during day time
    if lux > 15:
        # Take photo
        photo = Photo_Client()
        photo_name = photo.photo_name
        photo.take_photo()
        aws.upload_photo(photo_name, photo_name.split('/')[-1])
        aws.upload_photo(photo_name, "plant.jpg", "static-plant-site",{'ACL':'public-read'})
        # Clean up
        photo.delete_recent_photo()