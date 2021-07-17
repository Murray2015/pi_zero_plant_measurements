import boto3
from os import remove, listdir, getcwd
from datetime import datetime
from time import sleep
from datetime import datetime
from picamera import PiCamera

from LPS22HB import LPS22HB
from TCS34725_py3 import TCS34725
from registers import *
import secrets

class Photo_Client: 
    def __init__(self) -> None:
        self._photo_name = f"{secrets.PI_ZERO_WORKING_DIR}{str(datetime.now().timestamp())}_plant.jpg"
        self.camera = PiCamera()
    
    @property
    def photo_name(self):
        return self._photo_name
    
    def take_photo(self):
        self.camera.start_preview()
        sleep(1)
        self.camera.capture(self._photo_name)
        self.camera.stop_preview()
    
    def delete_recent_photo(self):
        remove(self._photo_name)

    def delete_all_photos(self):
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
        
    def get_pressure_data(self) -> float:
        sleep(0.1)
        self.lps22hb.LPS22HB_START_ONESHOT()
        if (self.lps22hb._read_byte(LPS_STATUS)&0x01)==0x01:  
            self.u8Buf[0]=self.lps22hb._read_byte(LPS_PRESS_OUT_XL)
            self.u8Buf[1]=self.lps22hb._read_byte(LPS_PRESS_OUT_L)
            self.u8Buf[2]=self.lps22hb._read_byte(LPS_PRESS_OUT_H)
            self.pressure_data=((self.u8Buf[2]<<16)+(self.u8Buf[1]<<8)+self.u8Buf[0])/4096.0
        return self.pressure_data
    
    def get_temperature_data(self) -> float: 
        sleep(0.1)
        self.lps22hb.LPS22HB_START_ONESHOT()
        if (self.lps22hb._read_byte(LPS_STATUS)&0x02)==0x02:   
            self.u8Buf[0]=self.lps22hb._read_byte(LPS_TEMP_OUT_L)
            self.u8Buf[1]=self.lps22hb._read_byte(LPS_TEMP_OUT_H)
            self.temperature_data=((self.u8Buf[1]<<8)+self.u8Buf[0])/100.0
        return self.temperature_data

    def get_lux(self) -> float: 
        self.lux_client.Get_RGBData()
        self.lux = self.lux_client.Get_Lux()
        return self.lux


class AWS_Client: 
    def __init__(self) -> None:
        self.s3 = boto3.client('s3')
        self.dynamodb = boto3.client('dynamodb', region_name='us-east-2')
    
    def upload_photo(self, photo_name, destination_photo_name, bucket = secrets.PLANT_PHOTOS_BUCKET):
        response = self.s3.upload_file(photo_name, bucket, destination_photo_name)
        return response

    def upload_sensor_data(self, lux, pressure_data, temperature_data):
        response = self.dynamodb.put_item(TableName=secrets.PLANT_DATA_TABLE, 
                                    Item={'timestamp': {'S':str(datetime.now().timestamp())}, 
                                    'lux':{'N':str(lux)},
                                    'pressure': {'N': str(pressure_data)}, 
                                    'temperature': {'N':str(temperature_data)}}
                                    )
        return response                                    

if __name__ == "__main__": 
    sensor = Sensor_Client() 
    lux = sensor.get_lux() 
    if lux > 15: 
        # Take photo
        photo = Photo_Client()
        photo_name = photo.photo_name
        photo.take_photo()
        # Get sensor data
        pressure = sensor.get_pressure_data()
        temperature = sensor.get_temperature_data() 
        # Upload to AWS 
        aws = AWS_Client() 
        aws.upload_photo(photo_name, photo_name)
        aws.upload_photo(photo_name, "plant.jpg", secrets.STATIC_SITE_BUCKET)
        aws.upload_sensor_data(lux, pressure, temperature)
        # Clean up
        photo.delete_recent_photo()