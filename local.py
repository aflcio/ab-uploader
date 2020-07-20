from dotenv import load_dotenv
from selenium import webdriver
from upload import ABUploader
import os

load_dotenv()
upload_file = '/Users/jmann/Desktop/AB Data/Sample:Demo/Auto Upload Test Data.csv'

uploader = ABUploader(driver=webdriver.Chrome(),
                      config_file='fields.example.yml',
                      upload_file=upload_file,
                      instance=os.getenv('AB_INSTANCE'),
                      campaign='Upload Test')
# uploader.login()
# uploader.start_upload('people')
# uploader.confirm_upload()
# uploader.finish_upload()
# uploader.start_upload('info')
# uploader.confirm_upload()
# uploader.finish_upload()

print(uploader.test())
uploader.quit()
