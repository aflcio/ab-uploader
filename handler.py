import boto3
import json
import os
import time
from datetime import datetime
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
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
    # print(event['Records'])
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    file_key = unquote_plus(record['s3']['object']['key'])
    file_type = file_key[-3:]
    print('Received file: %s' % file_key)
    if file_type == 'txt':
        handle_txt(bucket, file_key)
    if file_type == 'csv':
        handle_csv(bucket, file_key)
    return {
        "message": "File received: %s" % file_key,
        "event": event
    }


def handle_txt(bucket, file_key):
    txt_path = '/tmp/%s' % file_key
    s3_client.download_file(bucket, file_key, txt_path)
    try:
        csv_path = ABUploader.txt_to_csv(txt_path)
        s3_client.upload_file(csv_path, bucket, file_key.replace('.txt', '.csv'))
    except:
        print('Failed to convert file: %s' % file_key)
        raise


def handle_csv(bucket, file_key):
    sfn_client = boto3.client('stepfunctions')
    campaign_key = file_key.split('_')[0]
    # Read config file
    s3_client.download_file(bucket, 'config.yml', '/tmp/config.yml')
    config = ABUploader.parse_config('/tmp/config.yml', campaign_key)
    uploads = list(config['field_map'])
    uploads.remove('id')
    execution_name = '%s_%s' % (campaign_key, int(time.time()))
    # Start state machine
    sfn_client.start_execution(
        stateMachineArn=os.getenv('stateMachineArn'),
        name=execution_name,
        input=json.dumps({
            "execution_name": execution_name,
            "config": {
                **config,
            },
            "bucket": bucket,
            "campaign_key": campaign_key,
            "file_key": file_key,
            "uploads_todo": uploads
        })
    )


def one_ata_time(event, context):
    sfn_client = boto3.client('stepfunctions')
    executions = sfn_client.list_executions(
        stateMachineArn=os.getenv('stateMachineArn'),
        statusFilter='RUNNING'
    )['executions']
    oldest = executions[-1]['name']
    if event['execution_name'] == oldest:
        print('%s GO!' % event['campaign_key'])
        event['proceed'] = True
    else:
        print('%s waiting' % event['campaign_key'])
        event['proceed'] = False
    return event


def start_upload(event, context):
    # Retrieve file to upload
    file_path = '/tmp/%s' % event['file_key']
    s3_client.download_file(
        event['bucket'],
        event['file_key'],
        file_path
    )

    event['upload_type'] = event['uploads_todo'].pop(0)
    uploader = ABUploader(config=event['config'],
                          upload_file=file_path,
                          chrome_options=chrome_options())
    print('---Starting Upload: %s - %s---' %
          (event['campaign_key'], event['upload_type']))
    uploader.start_upload(event['upload_type'])

    try:
        # Try waiting for snackbar pop-up
        uploader.confirm_upload()
        event['wait_type'] = 'upload'
        print('---Confirmed with snackbar: %s - %s---' %
              (event['campaign_key'], event['upload_type']))
    except TimeoutException:
        # Fall back to checking status on upload list
        event['wait_type'] = 'processing'
    # event['wait_type'] = 'processing'
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
    # Upload ready to be confirmed (Needs Confirmation/Review)
    if 'Needs' in status:
        uploader.confirm_upload(from_list=True)
        print('---Confirmed Upload: %s - %s---' % (event['campaign_key'], event['upload_type']))
        event['retries_left'] = 6
        event['wait_time'] = 30
        event['wait_type'] = 'upload'
    # Upload is done
    if 'Complete' in status:
        del event['wait_time'], event['retries_left'], event['wait_type']
        if not len(event['uploads_todo']):
            del event['uploads_todo']
        print('---Upload Complete: %s - %s---' % (event['campaign_key'], event['upload_type']))
    # Upload failed
    if 'Failure' in status:
        raise Exception('Upload failed')
    return event


def confirm_upload(event, context):
    uploader = ABUploader(
        config=event['config'], chrome_options=chrome_options())
    uploader.confirm_upload(from_list=True)
    del event['wait_time'], event['retries_left']
    return event


def notify(event, context):
    if 'detail' in event:
        job_info = json.loads(event['detail']['input'])
        status = event['detail']['status']
    else:
        job_info = event
        status = 'STARTED'

    subject = "[ABUploader] JOB %s" % status
    msg_params = {
        "campaign": job_info['config']['campaign_name'],
        "file": job_info['file_key'],
        "instance": job_info['config']['instance'],
        "execution": job_info['execution_name'],
        "error": None,
        "errorDetails": None
    }

    if status == 'STARTED':
        msg_params['text'] = "File received. Starting uploads now!"
    if status == 'FAILED':
        msg_params['text'] = "The upload job could not be completed succesfully."
        get_errors(msg_params, exec_arn=event['detail']['executionArn'])
    if status == 'SUCCEEDED':
        msg_params['text'] = "The upload job finished successfully."

    send_notification(subject, msg_params)
    return event

def get_errors(msg_params, exec_arn):
    sfn_client = boto3.client('stepfunctions')
    result = sfn_client.get_execution_history(
        executionArn=exec_arn,
        maxResults=1,
        reverseOrder=True
    )
    cause = json.loads(result['events'][0]['executionFailedEventDetails']['cause'])
    msg_params['error'] = cause['errorType']
    trace = [s.strip() for s in cause['stackTrace']]
    if msg_params['error'] in ['DataError', 'CampaignError']:
        msg_params['errorDetails'] = cause['errorMessage']
    else:
        msg_params['errorDetails'] = '\n'.join(trace)


def send_notification(subject, msg_params):
    sns_client = boto3.client('sns')
    msg = """{text}
--------------------------------------------------------------------------------
Job Details
--------------------------------------------------------------------------------
Campaign    :   {campaign}
File Name    :   {file}
Instance       :   {instance}
Exec. ID       :   {execution}
--------------------------------------------------------------------------------
""".format_map(msg_params)

    if msg_params['error']:
        msg += """Error: {error}
--------------------------------------------------------------------------------
{errorDetails}
--------------------------------------------------------------------------------
""".format_map(msg_params)
    msg += datetime.now().isoformat()
    sns_client.publish(
        TopicArn=os.getenv('notifyTopic'),
        Message=msg,
        Subject=subject
    )
