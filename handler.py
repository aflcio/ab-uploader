import boto3
import json
import os
from selenium import webdriver
from urllib.parse import unquote_plus
from upload import ABUploader

s3_client = boto3.client('s3')


def chrome_options():
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
    return chrome_options

def s3_handler(event, context):
    sfn_client = boto3.client('stepfunctions')
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    file_key = unquote_plus(record['s3']['object']['key'])
    campaign_key = file_key.split('_')[0]
    # Read config file
    s3_client.download_file(bucket, 'config.yml', '/tmp/config.yml')
    config = ABUploader.parse_config('/tmp/config.yml', campaign_key)
    sfn_client.start_execution(
        stateMachineArn=os.getenv('stateMachineArn'),
        input=json.dumps({
            "config": {
                **config,
            },
            "bucket": bucket,
            "campaign_key": campaign_key,
            "file_key": file_key
        })
    )
    return {
        "message": "File received: %s" % file_key,
        "event": event
    }

def start_upload(event, context):
    # Retrieve file to upload
    file_path = '/tmp/%s' % event['file_key']
    s3_client.download_file(
        event['bucket'],
        event['file_key'],
        file_path
    )
    # Do people upload unless specified
    if 'upload_type' not in event:
        event['upload_type'] = 'people'
    uploader = ABUploader(config=event['config'],
                          upload_file=file_path,
                          chrome_options=chrome_options())
    uploader.start_upload(event['upload_type'])
    uploader.confirm_upload()
    event['wait_time'] = 30
    return event


def check_upload_status(event, context):
    # Get status of upload
    uploader = ABUploader(
        config=event['config'], chrome_options=chrome_options())
    status = uploader.get_upload_status()
    event['upload_status'] = status
    # Exponential backoff
    if 'retries_left' not in event:
        event['retries_left'] = 6
        event['wait_time'] = 30
    else:
        event['retries_left'] -= 1
        event['wait_time'] *= 2
    if status == 'Complete':
        del event['wait_time'], event['retries_left']
        print("---Upload Complete---")
    return event
