from dotenv import load_dotenv
from upload import ABUploader

load_dotenv()
# Change these variables.
upload_file = '/Users/jmann/Desktop/AB Data/Sample:Demo/auto-upload-test_20200722.csv'
config_file = 'config.example.yml'
campaign_key = 'upload-test'
config = ABUploader.parse_config(config_file, campaign_key)
uploader = ABUploader(config, upload_file)
uploader.start_upload('people')
uploader.confirm_upload()
uploader.finish_upload()
uploader.start_upload('info')
uploader.confirm_upload()
uploader.finish_upload()
uploader.quit()
