import boto3
import json
import os
import time
from json.decoder import JSONDecodeError
from datetime import datetime
from parsons.etl import Table
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

    # Split csv if needed
    chunks = split_csv(file_key, bucket=bucket)
    if chunks:
        print('Splitting file in %d chunks' % chunks)
        uploads = ['%s_%d' % (u, c)  for c in range(chunks) for u in uploads]
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
            "uploads_todo": uploads,
            "upload_status": dict.fromkeys(uploads, ''),
            "chunks": chunks
        })
    )


def split_csv(file, chunk_size=5000, bucket=None):
    csv = read_csv(file, bucket)
    if csv.num_rows < chunk_size:
        return False
    for index, chunk in enumerate(csv.chunk(chunk_size)):
        filename = '%s.%s' % (file, index)
        write_csv(chunk, filename, bucket)
    return index + 1 # (number of chunks)


def read_csv(file, bucket=None):
    if bucket:
        return Table.from_s3_csv(bucket, file)
    else:
        return Table.from_csv(file)

def write_csv(list, filename, bucket=None):
    if bucket:
        list.to_s3_csv(bucket, filename)
    else:
        list.to_csv(filename)


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
    event['current_upload'] = event['uploads_todo'].pop(0)
    # If upload type ends with _N, we're dealing with a chunk
    upload_type = event['current_upload']
    chunk = upload_type.rsplit('_')[1] if '_' in upload_type else False
    file_key = event['file_key'] if not chunk else '%s.%s' % (event['file_key'], chunk)
    upload_type = upload_type if not chunk else upload_type.rsplit('_')[0]
    # Retrieve file to upload
    file_path = '/tmp/%s' % file_key
    s3_client.download_file(
        event['bucket'],
        file_key,
        file_path
    )

    uploader = ABUploader(config=event['config'],
                          upload_file=file_path,
                          chrome_options=chrome_options())
    print('---Starting Upload: %s - %s---' %
          (event['campaign_key'], event['current_upload']))
    uploader.start_upload(upload_type)

    try:
        # Try waiting for snackbar pop-up
        uploader.confirm_upload()
        event['wait_type'] = 'upload'
        print('---Confirmed with snackbar: %s - %s---' %
              (event['campaign_key'], event['current_upload']))
    except TimeoutException:
        # Fall back to checking status on upload list
        event['wait_type'] = 'processing'
    event['wait_time'] = 30
    return event


def check_upload_status(event, context):
    # Get status of upload
    uploader = ABUploader(
        config=event['config'], chrome_options=chrome_options())
    status = uploader.get_upload_status()
    current = event['current_upload']
    event['upload_status'][current] = status
    event['current_status'] = status
    event['next_move'] = 'keep_waiting'
    # Exponential backoff (max 62 minutes)
    if 'retries_left' not in event:
        event['retries_left'] = 14
        event['wait_time'] = 60
    else:
        event['retries_left'] -= 1
        event['wait_time'] = min(event['wait_time'] * 2, 300)
    # Upload ready to be confirmed (Needs Confirmation/Review)
    if 'Needs' in status:
        uploader.confirm_upload(from_list=True)
        print('---Confirmed Upload: %s - %s---' % (event['campaign_key'], current))
        event['retries_left'] = 6
        event['wait_time'] = 30
        event['wait_type'] = 'upload'
    # Upload is done
    if 'Complete' in status:
        print('---Upload Complete: %s - %s---' % (event['campaign_key'], current))
        # Cleanup our state variables before next upload
        del event['wait_time'], event['retries_left'], event['wait_type'],
        del event['current_status'], event['current_upload']
        event['next_move'] = 'next_upload'
        if not len(event['uploads_todo']):
            del event['uploads_todo']
            event['next_move'] = 'all_done'
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
        job_info = get_job_info(event['detail']['executionArn'])
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
        "errorDetails": None,
        "uploadStatus": "\n".join("%s:\t%s" % (u, s) for u, s in job_info['upload_status'].items()),
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


def get_job_info(exec_arn):
    sfn_client = boto3.client('stepfunctions')
    result = sfn_client.get_execution_history(
        executionArn=exec_arn,
        maxResults=5,
        reverseOrder=True
    )
    details = [v for e in result['events'] for v in e.values() if isinstance(v, dict)]
    info = next(v for d in details for k,v in d.items() if k == 'output' or k == 'input')
    return json.loads(info)


def get_errors(msg_params, exec_arn):
    sfn_client = boto3.client('stepfunctions')
    result = sfn_client.get_execution_history(
        executionArn=exec_arn,
        maxResults=1,
        reverseOrder=True
    )
    try:
        cause = json.loads(result['events'][0]['executionFailedEventDetails']['cause'])
        msg_params['error'] = cause['errorType']
        trace = [s.strip() for s in cause['stackTrace']]
        if msg_params['error'] in ['DataError', 'CampaignError']:
            msg_params['errorDetails'] = cause['errorMessage']
        else:
            msg_params['errorDetails'] = '\n'.join(trace)
    except JSONDecodeError:
        msg_params['error'] = result['events'][0]['executionFailedEventDetails']['cause']


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
{uploadStatus}
--------------------------------------------------------------------------------
""".format_map(msg_params)

    if msg_params['error']:
        msg += """Error: {error}
--------------------------------------------------------------------------------
{errorDetails}
--------------------------------------------------------------------------------
""".format_map(msg_params)
    msg += datetime.now().isoformat()
    print(msg)
    sns_client.publish(
        TopicArn=os.getenv('notifyTopic'),
        Message=msg,
        Subject=subject
    )
