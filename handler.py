import boto3
import os
from selenium import webdriver
from urllib.parse import unquote_plus
from upload import ABUploader

s3_client = boto3.client('s3')

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1280x1696')
chrome_options.add_argument('--user-data-dir=/tmp/user-data')
chrome_options.add_argument('--hide-scrollbars')
chrome_options.add_argument('--enable-logging')
chrome_options.add_argument('--log-level=0')
chrome_options.add_argument('--v=99')
chrome_options.add_argument('--single-process')
chrome_options.add_argument('--data-path=/tmp/data-path')
chrome_options.add_argument('--ignore-certificate-errors')
chrome_options.add_argument('--homedir=/tmp')
chrome_options.add_argument('--disk-cache-dir=/tmp/cache-dir')
chrome_options.add_argument(
    'user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36')
chrome_options.binary_location = "/opt/bin/headless-chromium"
driver = webdriver.Chrome(chrome_options=chrome_options)

def test(event, context):
    uploader = ABUploader(driver=driver,
                          config_file=None,
                          upload_file=None,
                          campaign=None)
    title = uploader.test()
    return {
        "message": "Success! Title is: %s" % title,
        "event": event
    }

def upload_handler(event, context):
    for record in event['Records']:
        print('----RECORD-----')
        print(record)
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        path = '/tmp/%s' % key.replace('/', '')
        s3_client.download_file(bucket, key, path)
        config_path = '/tmp/config.yml'
        s3_client.download_file(bucket, 'config.yml', config_path)
        campaign_key = key.split('_')[0]
        ab_upload(upload_file=path, config_file=config_path, campaign_key=campaign_key)
    return {
        "message": "Success! Finished uploads",
        "event": event
    }

def ab_upload(upload_file, config_file, campaign_key):
    uploader = ABUploader(driver=driver,
                          config_file=config_file,
                          upload_file=upload_file,
                          campaign_key=campaign_key')
    uploader.login()
    uploader.start_upload('people')
    uploader.confirm_upload()
    uploader.finish_upload()
    uploader.start_upload('info')
    uploader.confirm_upload()
    uploader.finish_upload()
    uploader.quit()
